from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, Protocol

from vision.contract import load_workspace
from vision.models import InputPlan, VisionConfig, WorkspaceInput
from vision.output import (
    configuration_fingerprint,
    failure_payload,
    read_reusable_result,
    result_path,
    success_payload,
    write_json_atomic,
)
from vision.prompt import initial_prompt, repair_prompt
from vision.schema import parse_and_normalize


class VisionModel(Protocol):
    def analyze(self, image_path: Path, prompt: str) -> str: ...


@dataclass(frozen=True)
class PreparedRun:
    workspace: WorkspaceInput
    config: VisionConfig
    configuration_fingerprint: str
    plans: tuple[InputPlan, ...]
    force: bool


@dataclass(frozen=True)
class RunResult:
    prepared: PreparedRun
    processed: int
    reused: int
    failed: int
    skipped: int
    dry_run: bool
    timings: tuple["InputTiming", ...]


@dataclass(frozen=True)
class InputTiming:
    total_seconds: float
    model_seconds: float
    attempts: int

    def as_dict(self) -> dict:
        return {
            "total_seconds": self.total_seconds,
            "model_seconds": self.model_seconds,
            "attempts": self.attempts,
        }


ProgressCallback = Callable[[int, int, InputPlan, str, InputTiming], None]


def prepare_workspace(
    workspace_path: Path,
    config: VisionConfig,
    *,
    keyframe_fingerprint: str | None = None,
    force: bool = False,
) -> PreparedRun:
    config.validate()
    workspace = load_workspace(workspace_path, keyframe_fingerprint)
    fingerprint = configuration_fingerprint(config)
    plans: list[InputPlan] = []
    for visual_input in workspace.inputs:
        target = result_path(workspace, fingerprint, visual_input)
        reusable = None if force else read_reusable_result(
            workspace, target, config, fingerprint, visual_input
        )
        plans.append(InputPlan(visual_input, target, "reuse" if reusable else "process"))
    return PreparedRun(workspace, config, fingerprint, tuple(plans), force)


def _attempt(
    model: VisionModel,
    image_path: Path,
    prompt: str,
    kind: str,
    index: int,
) -> tuple[dict | None, dict]:
    raw = model.analyze(image_path, prompt)
    canonical, errors = parse_and_normalize(raw)
    record = {
        "attempt": index,
        "kind": kind,
        "raw_model_response": raw,
        "validation_errors": errors,
    }
    return canonical, record


def execute_prepared(
    prepared: PreparedRun,
    *,
    dry_run: bool,
    model: VisionModel | None = None,
    progress: ProgressCallback | None = None,
) -> RunResult:
    skipped = len(prepared.workspace.issues)
    if dry_run:
        return RunResult(
            prepared,
            processed=0,
            reused=sum(plan.action == "reuse" for plan in prepared.plans),
            failed=0,
            skipped=skipped,
            dry_run=True,
            timings=(),
        )
    if any(plan.action == "process" for plan in prepared.plans) and model is None:
        raise RuntimeError("Vision model dependency was not provided")

    processed = reused = failed = 0
    timings: list[InputTiming] = []
    process_total = sum(plan.action == "process" for plan in prepared.plans)
    process_index = 0
    for plan in prepared.plans:
        if plan.action == "reuse":
            reused += 1
            continue
        visual_input = plan.visual_input
        attempts: list[dict] = []
        input_started = perf_counter()
        model_seconds = 0.0
        attempt_count = 0
        try:
            assert model is not None
            attempt_count += 1
            model_started = perf_counter()
            try:
                canonical, record = _attempt(
                    model, visual_input.path, initial_prompt(), "initial", 0
                )
            finally:
                model_seconds += perf_counter() - model_started
            attempts.append(record)
            repair_number = 0
            while canonical is None and repair_number < prepared.config.max_repair_attempts:
                repair_number += 1
                attempt_count += 1
                model_started = perf_counter()
                try:
                    canonical, record = _attempt(
                        model,
                        visual_input.path,
                        repair_prompt(
                            attempts[-1]["raw_model_response"],
                            attempts[-1]["validation_errors"],
                        ),
                        "repair",
                        repair_number,
                    )
                finally:
                    model_seconds += perf_counter() - model_started
                attempts.append(record)
            timing = InputTiming(
                round(perf_counter() - input_started, 6),
                round(model_seconds, 6),
                attempt_count,
            )
            if canonical is None:
                payload = failure_payload(
                    prepared.workspace,
                    prepared.config,
                    prepared.configuration_fingerprint,
                    visual_input,
                    "INVALID_MODEL_RESULT",
                    "Model output did not satisfy Vision v1 schema after repair attempts",
                    attempts,
                    timing.as_dict(),
                    {"validation_errors": attempts[-1]["validation_errors"]},
                )
                failed += 1
                outcome = "failed"
            else:
                payload = success_payload(
                    prepared.workspace,
                    prepared.config,
                    prepared.configuration_fingerprint,
                    visual_input,
                    attempts,
                    canonical,
                    timing.as_dict(),
                )
                processed += 1
                outcome = "processed"
            write_json_atomic(plan.output_path, payload)
        except Exception as exc:
            timing = InputTiming(
                round(perf_counter() - input_started, 6),
                round(model_seconds, 6),
                attempt_count,
            )
            payload = failure_payload(
                prepared.workspace,
                prepared.config,
                prepared.configuration_fingerprint,
                visual_input,
                getattr(exc, "code", type(exc).__name__.upper()),
                str(exc),
                attempts,
                timing.as_dict(),
                getattr(exc, "diagnostics", {}),
            )
            write_json_atomic(plan.output_path, payload)
            failed += 1
            outcome = "failed"
        timings.append(timing)
        process_index += 1
        if progress is not None:
            progress(process_index, process_total, plan, outcome, timing)
    return RunResult(
        prepared, processed, reused, failed, skipped, dry_run=False, timings=tuple(timings)
    )
