from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from faces.contract import load_workspace
from faces.image_io import read_image
from faces.inference import crop_face, l2_normalize
from faces.models import FaceDetection, FacesConfig, InputPlan, WorkspaceInput
from faces.output import (
    LANDMARK_NAMES,
    configuration_fingerprint,
    failure_payload,
    read_reusable_result,
    result_path,
    success_payload,
    write_json_atomic,
)


class FaceDetector(Protocol):
    def detect(self, image) -> tuple[FaceDetection, ...]: ...


class FaceEmbedder(Protocol):
    def embed(self, crop): ...


@dataclass(frozen=True)
class PreparedRun:
    workspace: WorkspaceInput
    config: FacesConfig
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
    detected_faces: int
    dry_run: bool


ProgressCallback = Callable[[int, int, InputPlan, str, int], None]


def prepare_workspace(
    workspace_path: Path,
    config: FacesConfig,
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


def _serialized_faces(image, detections, embedder: FaceEmbedder, provenance: dict) -> list[dict]:
    serialized: list[dict] = []
    for index, detection in enumerate(detections):
        crop = crop_face(image, detection.bbox)
        embedding = l2_normalize(embedder.embed(crop))
        values = [round(float(value), 8) for value in embedding]
        if len(values) != 256:
            raise ValueError("Embedding must contain 256 values")
        landmarks = [
            {"name": name, "x": round(float(point[0]), 6), "y": round(float(point[1]), 6)}
            for name, point in zip(LANDMARK_NAMES, detection.landmarks, strict=True)
        ]
        serialized.append(
            {
                "face_id": f"face-{index:04d}",
                "provenance": provenance,
                "bbox": detection.bbox.as_dict(),
                "confidence": round(float(detection.confidence), 8),
                "landmarks": landmarks,
                "embedding": values,
            }
        )
    return serialized


def execute_prepared(
    prepared: PreparedRun,
    *,
    dry_run: bool,
    detector: FaceDetector | None = None,
    embedder: FaceEmbedder | None = None,
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
            detected_faces=0,
            dry_run=True,
        )
    if any(plan.action == "process" for plan in prepared.plans) and (
        detector is None or embedder is None
    ):
        raise RuntimeError("Faces model dependencies were not provided")

    processed = reused = failed = detected_faces = 0
    process_total = sum(plan.action == "process" for plan in prepared.plans)
    process_index = 0
    for plan in prepared.plans:
        if plan.action == "reuse":
            reused += 1
            continue
        visual_input = plan.visual_input
        face_count = 0
        try:
            assert detector is not None and embedder is not None
            image = read_image(visual_input.path)
            detections = detector.detect(image)
            faces = _serialized_faces(image, detections, embedder, visual_input.provenance)
            face_count = len(faces)
            height, width = image.shape[:2]
            payload = success_payload(
                prepared.workspace,
                prepared.config,
                prepared.configuration_fingerprint,
                visual_input,
                width,
                height,
                faces,
            )
            processed += 1
            detected_faces += face_count
            outcome = "processed"
        except Exception as exc:
            payload = failure_payload(
                prepared.workspace,
                prepared.config,
                prepared.configuration_fingerprint,
                visual_input,
                getattr(exc, "code", type(exc).__name__.upper()),
                str(exc),
            )
            failed += 1
            outcome = "failed"
        write_json_atomic(plan.output_path, payload)
        process_index += 1
        if progress is not None:
            progress(process_index, process_total, plan, outcome, face_count)
    return RunResult(
        prepared,
        processed,
        reused,
        failed,
        skipped,
        detected_faces,
        dry_run=False,
    )
