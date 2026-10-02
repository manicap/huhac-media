from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator
import re

from faces import PROCESSOR_NAME, PROCESSOR_VERSION, RESULT_SCHEMA_VERSION
from faces.models import FacesConfig, VisualInput, WorkspaceInput


LANDMARK_NAMES = ("right_eye", "left_eye", "nose_tip", "right_mouth", "left_mouth")
_FACE_ID = re.compile(r"face-[0-9]{4}")


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def configuration_fingerprint(config: FacesConfig) -> str:
    return canonical_sha256(config.as_dict())


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
        raise ValueError("Faces output path escapes the workspace")
    return resolved


def model_provenance(config: FacesConfig) -> dict[str, Any]:
    return {
        "detector": {
            "framework": config.detector_framework,
            "name": config.detector_model,
            "device": config.detector_device,
        },
        "embedding": {
            "framework": config.embedding_framework,
            "name": config.embedding_model,
            "precision": config.embedding_model_precision,
            "device": config.embedding_device,
        },
    }


def _valid_face(
    value: object,
    dimensions: int,
    image_width: int,
    image_height: int,
    score_threshold: float,
    provenance: dict[str, Any],
) -> bool:
    if not isinstance(value, dict):
        return False
    bbox = value.get("bbox")
    landmarks = value.get("landmarks")
    embedding = value.get("embedding")
    return (
        isinstance(value.get("face_id"), str)
        and bool(_FACE_ID.fullmatch(value["face_id"]))
        and value.get("provenance") == provenance
        and isinstance(bbox, dict)
        and set(bbox) == {"x", "y", "width", "height"}
        and all(not isinstance(bbox[key], bool) and isinstance(bbox[key], int) for key in bbox)
        and bbox["x"] >= 0
        and bbox["y"] >= 0
        and bbox["width"] > 0
        and bbox["height"] > 0
        and bbox["x"] + bbox["width"] <= image_width
        and bbox["y"] + bbox["height"] <= image_height
        and isinstance(value.get("confidence"), (int, float))
        and not isinstance(value.get("confidence"), bool)
        and math.isfinite(value["confidence"])
        and score_threshold <= value["confidence"] <= 1
        and isinstance(landmarks, list)
        and len(landmarks) == 5
        and all(isinstance(item, dict) for item in landmarks)
        and [item.get("name") for item in landmarks if isinstance(item, dict)]
        == list(LANDMARK_NAMES)
        and all(
            not isinstance(item.get("x"), bool)
            and isinstance(item.get("x"), (int, float))
            and math.isfinite(item["x"])
            and not isinstance(item.get("y"), bool)
            and isinstance(item.get("y"), (int, float))
            and math.isfinite(item["y"])
            for item in landmarks
        )
        and isinstance(embedding, list)
        and len(embedding) == dimensions
        and all(
            not isinstance(number, bool)
            and isinstance(number, (int, float))
            and math.isfinite(number)
            for number in embedding
        )
        and abs(math.sqrt(sum(float(number) ** 2 for number in embedding)) - 1.0) <= 1e-5
    )


def read_reusable_result(
    workspace: WorkspaceInput,
    target: Path,
    config: FacesConfig,
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
    image = result.get("image") if isinstance(result, dict) else None
    faces = result.get("faces") if isinstance(result, dict) else None
    valid_image = (
        isinstance(image, dict)
        and set(image) == {"width", "height", "color_order"}
        and not isinstance(image.get("width"), bool)
        and isinstance(image.get("width"), int)
        and image["width"] > 0
        and not isinstance(image.get("height"), bool)
        and isinstance(image.get("height"), int)
        and image["height"] > 0
        and image.get("color_order") == "BGR"
    )
    valid = (
        isinstance(payload, dict)
        and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
        and payload.get("workspace_contract_version") == workspace.contract_version
        and payload.get("workspace_id") == workspace.workspace_id
        and payload.get("asset_id") == visual_input.asset_id
        and payload.get("sha256") == visual_input.sha256
        and payload.get("processor") == {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
        and payload.get("model") == model_provenance(config)
        and payload.get("configuration") == config.as_dict()
        and payload.get("configuration_fingerprint") == fingerprint
        and payload.get("input_kind") == visual_input.kind
        and payload.get("input") == visual_input.provenance
        and payload.get("status") == "success"
        and isinstance(result, dict)
        and valid_image
        and isinstance(faces, list)
        and all(
            _valid_face(
                face,
                config.embedding_dimensions,
                image["width"],
                image["height"],
                config.score_threshold,
                visual_input.provenance,
            )
            and face["face_id"] == f"face-{index:04d}"
            for index, face in enumerate(faces)
        )
    )
    return payload if valid else None


@contextmanager
def atomic_target(target: Path) -> Iterator[Path]:
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


def write_json_atomic(target: Path, payload: dict[str, Any]) -> None:
    with atomic_target(target) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())


def _envelope(
    workspace: WorkspaceInput,
    config: FacesConfig,
    fingerprint: str,
    visual_input: VisualInput,
    status: str,
    error: dict[str, str] | None,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "workspace_contract_version": workspace.contract_version,
        "workspace_id": workspace.workspace_id,
        "asset_id": visual_input.asset_id,
        "sha256": visual_input.sha256,
        "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
        "model": model_provenance(config),
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
    config: FacesConfig,
    fingerprint: str,
    visual_input: VisualInput,
    width: int,
    height: int,
    faces: list[dict[str, Any]],
) -> dict[str, Any]:
    return _envelope(
        workspace,
        config,
        fingerprint,
        visual_input,
        "success",
        None,
        {"image": {"width": width, "height": height, "color_order": "BGR"}, "faces": faces},
    )


def failure_payload(
    workspace: WorkspaceInput,
    config: FacesConfig,
    fingerprint: str,
    visual_input: VisualInput,
    code: str,
    message: str,
) -> dict[str, Any]:
    return _envelope(
        workspace,
        config,
        fingerprint,
        visual_input,
        "failed",
        {"code": code, "message": message},
        None,
    )
