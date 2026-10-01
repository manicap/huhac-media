from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterator

from video_keyframes import PROCESSOR_NAME, PROCESSOR_VERSION, RESULT_SCHEMA_VERSION
from video_keyframes.models import (
    CoverageSelection,
    KeyframeConfig,
    SampledFrame,
    VideoAsset,
    WorkspaceInput,
)


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def configuration_fingerprint(config: KeyframeConfig) -> str:
    return _canonical_sha256(config.as_dict())


def result_path(workspace: WorkspaceInput, fingerprint: str, asset: VideoAsset) -> Path:
    target = (
        workspace.workspace
        / "analysis"
        / PROCESSOR_NAME
        / PROCESSOR_VERSION
        / fingerprint
        / asset.sha256[:2]
        / f"{asset.sha256}.json"
    )
    resolved_workspace = workspace.workspace.resolve(strict=False)
    resolved_target = target.resolve(strict=False)
    if resolved_workspace not in resolved_target.parents:
        raise ValueError("Video keyframe output path escapes the workspace")
    return resolved_target


def keyframe_directory(
    workspace: WorkspaceInput, fingerprint: str, asset: VideoAsset
) -> Path:
    return result_path(workspace, fingerprint, asset).with_suffix("") / "keyframes"


def _resolve_result_location(workspace: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    target = workspace.joinpath(*pure.parts).resolve(strict=False)
    if target != workspace and workspace not in target.parents:
        return None
    return target


def read_reusable_result(
    workspace: WorkspaceInput,
    target: Path,
    config: KeyframeConfig,
    fingerprint: str,
    asset: VideoAsset,
) -> dict | None:
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    valid = (
        isinstance(payload, dict)
        and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
        and payload.get("workspace_contract_version") == workspace.contract_version
        and payload.get("asset_id") == asset.asset_id
        and payload.get("sha256") == asset.sha256
        and payload.get("processor")
        == {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
        and payload.get("model")
        == {
            "framework": "OpenCLIP",
            "name": config.clip_model,
            "version": config.clip_pretrained,
            "pretrained": config.clip_pretrained,
            "device": config.device,
        }
        and payload.get("configuration") == config.as_dict()
        and payload.get("configuration_fingerprint") == fingerprint
        and payload.get("status") == "success"
        and isinstance(payload.get("result"), dict)
        and isinstance(payload["result"].get("keyframes"), list)
        and bool(payload["result"]["keyframes"])
    )
    if not valid:
        return None
    for keyframe in payload["result"]["keyframes"]:
        if not isinstance(keyframe, dict):
            return None
        location = _resolve_result_location(workspace.workspace, keyframe.get("location"))
        expected_directory = keyframe_directory(workspace, fingerprint, asset).resolve(
            strict=False
        )
        if (
            location is None
            or expected_directory not in location.parents
            or not location.is_file()
        ):
            return None
    return payload


@contextmanager
def _atomic_target(target: Path) -> Iterator[Path]:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json_atomic(target: Path, payload: dict) -> None:
    with _atomic_target(target) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())


def publish_keyframes(
    workspace: WorkspaceInput,
    config: KeyframeConfig,
    fingerprint: str,
    asset: VideoAsset,
    frames: tuple[SampledFrame, ...],
    selections: tuple[CoverageSelection, ...],
) -> list[dict]:
    destination = keyframe_directory(workspace, fingerprint, asset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(dir=destination.parent, prefix=f".{asset.sha256}.", suffix=".tmp")
    )
    keyframes: list[dict] = []
    try:
        ordered = sorted(selections, key=lambda item: item.representative_index)
        for output_index, selection in enumerate(ordered):
            frame = frames[selection.representative_index]
            name = f"keyframe-{output_index:04d}.jpg"
            target = staging / name
            shutil.copyfile(frame.path, target)
            location = (destination / name).relative_to(workspace.workspace).as_posix()
            keyframes.append(
                {
                    "keyframe_id": f"keyframe-{output_index:04d}",
                    "location": location,
                    "timestamp_s": frame.timestamp_s,
                    "source_video_asset_id": asset.asset_id,
                    "source_video_sha256": asset.sha256,
                    "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
                    "model": {
                        "framework": "OpenCLIP",
                        "name": config.clip_model,
                        "version": config.clip_pretrained,
                        "pretrained": config.clip_pretrained,
                    },
                    "configuration_fingerprint": fingerprint,
                    "representation": {
                        "format": "JPEG",
                        "width": frame.width,
                        "height": frame.height,
                        "color_space": "sRGB",
                    },
                    "coverage": {
                        "candidate_sample_index": selection.coverage_candidate_index,
                        "member_sample_indices": list(selection.member_indices),
                        "member_count": len(selection.member_indices),
                    },
                }
            )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return keyframes


def cleanup_keyframes(
    workspace: WorkspaceInput, fingerprint: str, asset: VideoAsset
) -> None:
    destination = keyframe_directory(workspace, fingerprint, asset)
    if destination.is_dir():
        shutil.rmtree(destination)


def _envelope(
    workspace: WorkspaceInput,
    config: KeyframeConfig,
    fingerprint: str,
    asset: VideoAsset,
    status: str,
    error: dict | None,
    result: dict | None,
) -> dict:
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "workspace_contract_version": workspace.contract_version,
        "workspace_id": workspace.workspace_id,
        "asset_id": asset.asset_id,
        "sha256": asset.sha256,
        "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
        "model": {
            "framework": "OpenCLIP",
            "name": config.clip_model,
            "version": config.clip_pretrained,
            "pretrained": config.clip_pretrained,
            "device": config.device,
        },
        "configuration": config.as_dict(),
        "configuration_fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "error": error,
        "result": result,
    }


def success_payload(
    workspace: WorkspaceInput,
    config: KeyframeConfig,
    fingerprint: str,
    asset: VideoAsset,
    duration_s: float,
    sample_count: int,
    keyframes: list[dict],
) -> dict:
    assert asset.source is not None
    return _envelope(
        workspace,
        config,
        fingerprint,
        asset,
        "success",
        None,
        {
            "source": {
                "source_version_id": asset.source.source_version_id,
                "relative_path": asset.source.relative_path,
            },
            "sampling": {
                "duration_s": duration_s,
                "interval_s": config.sampling_interval_s,
                "sample_count": sample_count,
            },
            "coverage_similarity": config.coverage_similarity,
            "keyframes": keyframes,
        },
    )


def failure_payload(
    workspace: WorkspaceInput,
    config: KeyframeConfig,
    fingerprint: str,
    asset: VideoAsset,
    code: str,
    message: str,
    diagnostics: dict | None = None,
) -> dict:
    return _envelope(
        workspace,
        config,
        fingerprint,
        asset,
        "failed",
        {"code": code, "message": message, "diagnostics": diagnostics or {}},
        None,
    )
