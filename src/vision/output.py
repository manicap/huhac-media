from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

from vision import PROCESSOR_NAME, PROCESSOR_VERSION, RESULT_SCHEMA_VERSION
from vision.models import VisionConfig, VisualInput, WorkspaceInput
from vision.schema import validate_vision_result


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def configuration_fingerprint(config: VisionConfig) -> str:
    return _canonical_sha256(config.as_dict())


def result_path(
    workspace: WorkspaceInput, fingerprint: str, visual_input: VisualInput
) -> Path:
    base = (
        workspace.workspace
        / "analysis"
        / PROCESSOR_NAME
        / PROCESSOR_VERSION
        / fingerprint
        / visual_input.sha256[:2]
        / visual_input.sha256
    )
    if visual_input.kind == "image_preview":
        target = base / "image-preview.json"
    else:
        assert visual_input.keyframe_configuration_fingerprint is not None
        target = (
            base
            / "video-keyframes"
            / visual_input.keyframe_configuration_fingerprint
            / f"{visual_input.input_id}.json"
        )
    resolved = target.resolve(strict=False)
    if workspace.workspace.resolve(strict=False) not in resolved.parents:
        raise ValueError("Vision output path escapes the workspace")
    return resolved


def _model(config: VisionConfig) -> dict[str, Any]:
    return {"framework": "Ollama", "name": config.model}


def _valid_attempts(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for index, attempt in enumerate(value):
        if (
            not isinstance(attempt, dict)
            or attempt.get("attempt") != index
            or attempt.get("kind") not in {"initial", "repair"}
            or not isinstance(attempt.get("raw_model_response"), str)
            or not isinstance(attempt.get("validation_errors"), list)
            or not all(isinstance(error, str) for error in attempt["validation_errors"])
        ):
            return False
    return value[0]["kind"] == "initial"


def read_reusable_result(
    workspace: WorkspaceInput,
    target: Path,
    config: VisionConfig,
    fingerprint: str,
    visual_input: VisualInput,
) -> dict[str, Any] | None:
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    canonical = result.get("vision") if isinstance(result, dict) else None
    valid = (
        isinstance(payload, dict)
        and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
        and payload.get("workspace_contract_version") == workspace.contract_version
        and payload.get("workspace_id") == workspace.workspace_id
        and payload.get("asset_id") == visual_input.asset_id
        and payload.get("sha256") == visual_input.sha256
        and payload.get("processor") == {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
        and payload.get("model") == _model(config)
        and payload.get("configuration") == config.as_dict()
        and payload.get("configuration_fingerprint") == fingerprint
        and payload.get("input_kind") == visual_input.kind
        and payload.get("input") == visual_input.provenance
        and payload.get("status") == "success"
        and isinstance(result, dict)
        and _valid_attempts(result.get("attempts"))
        and not validate_vision_result(canonical)
    )
    return payload if valid else None


@contextmanager
def _atomic_target(target: Path) -> Iterator[Path]:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
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


def write_json_atomic(target: Path, payload: dict[str, Any]) -> None:
    with _atomic_target(target) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())


def _envelope(
    workspace: WorkspaceInput,
    config: VisionConfig,
    fingerprint: str,
    visual_input: VisualInput,
    status: str,
    error: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "workspace_contract_version": workspace.contract_version,
        "workspace_id": workspace.workspace_id,
        "asset_id": visual_input.asset_id,
        "sha256": visual_input.sha256,
        "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
        "model": _model(config),
        "configuration": config.as_dict(),
        "configuration_fingerprint": fingerprint,
        "input_kind": visual_input.kind,
        "input": visual_input.provenance,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "error": error,
        "result": result,
    }


def success_payload(
    workspace: WorkspaceInput,
    config: VisionConfig,
    fingerprint: str,
    visual_input: VisualInput,
    attempts: list[dict[str, Any]],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    return _envelope(
        workspace,
        config,
        fingerprint,
        visual_input,
        "success",
        None,
        {"attempts": attempts, "vision": canonical},
    )


def failure_payload(
    workspace: WorkspaceInput,
    config: VisionConfig,
    fingerprint: str,
    visual_input: VisualInput,
    code: str,
    message: str,
    attempts: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    partial = {"attempts": attempts, "vision": None}
    return _envelope(
        workspace,
        config,
        fingerprint,
        visual_input,
        "failed",
        {"code": code, "message": message, "diagnostics": diagnostics or {}},
        partial,
    )
