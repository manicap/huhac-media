from __future__ import annotations

import json
from pathlib import Path

import pytest


IMAGE_SHA = "a" * 64
VIDEO_SHA = "b" * 64
KEYFRAME_FP = "c" * 64
WORKSPACE_ID = "workspace-test-id"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def canonical_result(**overrides):
    value = {
        "scene": "indoor gathering",
        "people": {"approx_count": 3, "crowd": False},
        "activities": ["standing"],
        "objects": ["table"],
        "environment": ["indoor"],
        "visual_attributes": ["warm lighting"],
        "tags": ["people", "interior"],
        "description": "Several people are standing near a table indoors.",
    }
    value.update(overrides)
    return value


def add_keyframe_result(
    workspace: Path,
    fingerprint: str = KEYFRAME_FP,
    *,
    valid: bool = True,
    keyframes: int = 1,
) -> Path:
    result_path = (
        workspace
        / "analysis"
        / "video-keyframes"
        / "video-keyframes-v1"
        / fingerprint
        / VIDEO_SHA[:2]
        / f"{VIDEO_SHA}.json"
    )
    items = []
    for index in range(keyframes):
        keyframe_id = f"keyframe-{index:04d}"
        image = result_path.with_suffix("") / "keyframes" / f"{keyframe_id}.jpg"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"jpeg-keyframe")
        items.append(
            {
                "keyframe_id": keyframe_id,
                "location": image.relative_to(workspace).as_posix(),
                "timestamp_s": float(index + 1),
                "source_video_asset_id": f"sha256:{VIDEO_SHA}",
                "source_video_sha256": VIDEO_SHA,
                "configuration_fingerprint": fingerprint,
            }
        )
    payload = {
        "result_schema_version": 1,
        "workspace_contract_version": 1,
        "workspace_id": WORKSPACE_ID,
        "asset_id": f"sha256:{VIDEO_SHA}",
        "sha256": VIDEO_SHA,
        "processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
        "configuration_fingerprint": fingerprint,
        "status": "success" if valid else "failed",
        "result": {"keyframes": items} if valid else None,
    }
    write_json(result_path, payload)
    return result_path


@pytest.fixture
def workspace_factory(tmp_path):
    def create(*, preview: bool = True, keyframes: bool = True, keyframe_count: int = 1):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        write_json(
            workspace / "workspace.json",
            {
                "workspace_contract_version": 1,
                "schema_version": 1,
                "workspace_id": WORKSPACE_ID,
                "asset_catalog": "metadata/catalog.json",
            },
        )
        preview_path = workspace / "previews" / "images" / "aa" / f"{IMAGE_SHA}.jpg"
        if preview:
            preview_path.parent.mkdir(parents=True)
            preview_path.write_bytes(b"jpeg-preview")
        assets = [
            {
                "asset_id": f"sha256:{IMAGE_SHA}",
                "sha256": IMAGE_SHA,
                "media_type": "image",
                "availability": "available",
                "preview_location": preview_path.relative_to(workspace).as_posix() if preview else None,
            },
            {
                "asset_id": f"sha256:{VIDEO_SHA}",
                "sha256": VIDEO_SHA,
                "media_type": "video",
                "availability": "available",
                "preview_location": None,
            },
        ]
        write_json(
            workspace / "metadata" / "catalog.json",
            {
                "workspace_contract_version": 1,
                "workspace_id": WORKSPACE_ID,
                "source_root": str(tmp_path / "originals"),
                "assets": assets,
            },
        )
        if keyframes:
            add_keyframe_result(workspace, keyframes=keyframe_count)
        return workspace

    return create
