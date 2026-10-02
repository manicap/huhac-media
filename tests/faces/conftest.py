from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from faces.image_io import write_image


IMAGE_SHA = "a" * 64
VIDEO_SHA = "b" * 64
KEYFRAME_FP = "c" * 64
WORKSPACE_ID = "faces-workspace-test"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_test_image(path: Path, value: int = 64) -> None:
    image = np.full((24, 32, 3), value, dtype=np.uint8)
    write_image(path, image)


def add_keyframe_result(workspace: Path, fingerprint: str = KEYFRAME_FP) -> None:
    result_path = (
        workspace
        / "analysis"
        / "video-keyframes"
        / "video-keyframes-v1"
        / fingerprint
        / VIDEO_SHA[:2]
        / f"{VIDEO_SHA}.json"
    )
    image = result_path.with_suffix("") / "keyframes" / "keyframe-0000.jpg"
    write_test_image(image, 96)
    write_json(
        result_path,
        {
            "result_schema_version": 1,
            "workspace_contract_version": 1,
            "workspace_id": WORKSPACE_ID,
            "asset_id": f"sha256:{VIDEO_SHA}",
            "sha256": VIDEO_SHA,
            "processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
            "configuration_fingerprint": fingerprint,
            "status": "success",
            "result": {
                "keyframes": [
                    {
                        "keyframe_id": "keyframe-0000",
                        "location": image.relative_to(workspace).as_posix(),
                        "timestamp_s": 1.25,
                        "source_video_asset_id": f"sha256:{VIDEO_SHA}",
                        "source_video_sha256": VIDEO_SHA,
                        "configuration_fingerprint": fingerprint,
                    }
                ]
            },
        },
    )


@pytest.fixture
def workspace_factory(tmp_path):
    def create(*, preview: bool = True, keyframes: bool = True):
        workspace = tmp_path / "pracovní prostor žluťoučký"
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
        preview_path = workspace / "previews" / "obrázky" / f"{IMAGE_SHA}.jpg"
        if preview:
            write_test_image(preview_path)
        write_json(
            workspace / "metadata" / "catalog.json",
            {
                "workspace_contract_version": 1,
                "workspace_id": WORKSPACE_ID,
                "assets": [
                    {
                        "asset_id": f"sha256:{IMAGE_SHA}",
                        "sha256": IMAGE_SHA,
                        "media_type": "image",
                        "availability": "available",
                        "preview_location": (
                            preview_path.relative_to(workspace).as_posix() if preview else None
                        ),
                    },
                    {
                        "asset_id": f"sha256:{VIDEO_SHA}",
                        "sha256": VIDEO_SHA,
                        "media_type": "video",
                        "availability": "available",
                        "preview_location": None,
                    },
                ],
            },
        )
        if keyframes:
            add_keyframe_result(workspace)
        return workspace

    return create
