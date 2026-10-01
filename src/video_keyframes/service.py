from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, Any

from video_keyframes.contract import load_workspace
from video_keyframes.frames import sample_video
from video_keyframes.models import AssetPlan, KeyframeConfig, WorkspaceInput
from video_keyframes.output import (
    cleanup_keyframes,
    configuration_fingerprint,
    failure_payload,
    publish_keyframes,
    read_reusable_result,
    result_path,
    success_payload,
    write_json_atomic,
)
from video_keyframes.selection import select_keyframes
from video_keyframes.tools import FFmpeg, FFprobe


class Embedder(Protocol):
    def embed(self, paths: tuple[Path, ...]) -> Any: ...


class SourceIdentityError(RuntimeError):
    code = "SOURCE_IDENTITY_MISMATCH"


def _verify_source_identity(path: Path, expected_sha256: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise SourceIdentityError(
            "Active source bytes no longer match the catalogued video asset"
        )


@dataclass(frozen=True)
class PreparedRun:
    workspace: WorkspaceInput
    config: KeyframeConfig
    configuration_fingerprint: str
    plans: tuple[AssetPlan, ...]


@dataclass(frozen=True)
class RunResult:
    prepared: PreparedRun
    processed: int
    reused: int
    failed: int
    skipped: int
    dry_run: bool


def prepare_workspace(workspace_path: Path, config: KeyframeConfig) -> PreparedRun:
    config.validate()
    workspace = load_workspace(workspace_path)
    fingerprint = configuration_fingerprint(config)
    plans: list[AssetPlan] = []
    for asset in workspace.assets:
        target = result_path(workspace, fingerprint, asset)
        if read_reusable_result(workspace, target, config, fingerprint, asset) is not None:
            action = "reuse"
        elif asset.source is None:
            action = "source_unavailable"
        else:
            action = "process"
        plans.append(AssetPlan(asset, target, action))
    return PreparedRun(workspace, config, fingerprint, tuple(plans))


def execute_prepared(
    prepared: PreparedRun,
    *,
    dry_run: bool,
    ffprobe: FFprobe | None = None,
    ffmpeg: FFmpeg | None = None,
    embedder: Embedder | None = None,
) -> RunResult:
    if dry_run:
        return RunResult(
            prepared,
            processed=0,
            reused=sum(plan.action == "reuse" for plan in prepared.plans),
            failed=0,
            skipped=sum(plan.action == "source_unavailable" for plan in prepared.plans),
            dry_run=True,
        )
    if any(plan.action == "process" for plan in prepared.plans) and (
        ffprobe is None or ffmpeg is None or embedder is None
    ):
        raise RuntimeError("Processing dependencies were not provided")

    processed = reused = failed = skipped = 0
    for plan in prepared.plans:
        asset = plan.asset
        if plan.action == "reuse":
            reused += 1
            continue
        if plan.action == "source_unavailable":
            payload = failure_payload(
                prepared.workspace,
                prepared.config,
                prepared.configuration_fingerprint,
                asset,
                "SOURCE_UNAVAILABLE",
                "No accessible active source exists for the available video asset",
            )
            write_json_atomic(plan.output_path, payload)
            failed += 1
            continue
        assert asset.source is not None
        try:
            _verify_source_identity(asset.source.absolute_path, asset.sha256)
            with TemporaryDirectory(prefix="video-keyframes-") as temporary:
                duration, frames = sample_video(
                    asset.source.absolute_path,
                    Path(temporary),
                    prepared.config,
                    ffprobe,
                    ffmpeg,
                )
                embeddings = embedder.embed(tuple(frame.path for frame in frames))
                if len(embeddings) != len(frames):
                    raise ValueError("Embedding count does not match sampled frame count")
                selections = select_keyframes(
                    embeddings, prepared.config.coverage_similarity
                )
                keyframes = publish_keyframes(
                    prepared.workspace,
                    prepared.config,
                    prepared.configuration_fingerprint,
                    asset,
                    frames,
                    selections,
                )
                payload = success_payload(
                    prepared.workspace,
                    prepared.config,
                    prepared.configuration_fingerprint,
                    asset,
                    duration,
                    len(frames),
                    keyframes,
                )
                write_json_atomic(plan.output_path, payload)
            processed += 1
        except Exception as exc:
            cleanup_keyframes(
                prepared.workspace, prepared.configuration_fingerprint, asset
            )
            payload = failure_payload(
                prepared.workspace,
                prepared.config,
                prepared.configuration_fingerprint,
                asset,
                getattr(exc, "code", type(exc).__name__.upper()),
                str(exc),
                getattr(exc, "diagnostics", {}),
            )
            write_json_atomic(plan.output_path, payload)
            failed += 1
    return RunResult(prepared, processed, reused, failed, skipped, dry_run=False)
