from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class WorkspaceBuilder:
    def __init__(self, root: Path, originals: Path) -> None:
        self.root = root
        self.originals = originals
        self.workspace_id = "workspace-test"
        self.assets: list[dict[str, Any]] = []

    def add_asset(
        self,
        index: int,
        media_type: str = "image",
        *,
        preview: bool = True,
        original: bool = True,
        source_name: str | None = None,
    ) -> dict[str, Any]:
        sha256 = f"{index:064x}"
        source_name = source_name or f"set/media-{index}.{'jpg' if media_type == 'image' else 'mp4'}"
        metadata_location = f"metadata/assets/{sha256[:2]}/{sha256}.json"
        preview_location = f"previews/images/{sha256[:2]}/{sha256}.jpg" if media_type == "image" else None
        entry = {
            "asset_id": f"sha256:{sha256}",
            "sha256": sha256,
            "size_bytes": 100 + index,
            "media_type": media_type,
            "format": "JPEG" if media_type == "image" else "MP4",
            "mime_type": "image/jpeg" if media_type == "image" else "video/mp4",
            "availability": "available",
            "metadata_location": metadata_location,
            "preview_location": preview_location,
            "sources": [
                {
                    "source_version_id": f"source-{index}",
                    "relative_path": source_name,
                    "status": "active",
                }
            ],
        }
        write_json(
            self.root / metadata_location,
            {
                "schema_version": 1,
                "asset": {"asset_id": entry["asset_id"], "sha256": sha256},
                "capture": {
                    "datetime": f"2026-10-{index:02d}T20:00:00+02:00",
                    "source": "ExifIFD:DateTimeOriginal",
                    "timezone_offset": "+02:00",
                    "filesystem_fallback": False,
                },
                "technical": {"width": 1600, "height": 900},
            },
        )
        if preview and preview_location:
            target = self.root / preview_location
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic-jpeg")
        if original:
            target = self.originals.joinpath(*source_name.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"0123456789-original-media")
        self.assets.append(entry)
        return entry

    def add_keyframes(self, entry: dict[str, Any], *fingerprints: str) -> None:
        sha256 = entry["sha256"]
        for fingerprint in fingerprints:
            location = (
                f"analysis/video-keyframes/video-keyframes-v1/{fingerprint}/"
                f"{sha256[:2]}/{sha256}/keyframes/keyframe-0000.jpg"
            )
            image = self.root / location
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b"synthetic-keyframe")
            result_path = image.parents[1].with_suffix(".json")
            write_json(
                result_path,
                {
                    "result_schema_version": 1,
                    "workspace_contract_version": 1,
                    "workspace_id": self.workspace_id,
                    "asset_id": entry["asset_id"],
                    "sha256": sha256,
                    "processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
                    "configuration_fingerprint": fingerprint,
                    "status": "success",
                    "result": {
                        "keyframes": [
                            {
                                "keyframe_id": "keyframe-0000",
                                "timestamp_s": 0.0,
                                "location": location,
                                "source_video_asset_id": entry["asset_id"],
                                "source_video_sha256": sha256,
                                "configuration_fingerprint": fingerprint,
                            }
                        ]
                    },
                },
            )

    def add_analysis(self, entry: dict[str, Any], fingerprint: str) -> None:
        sha256 = entry["sha256"]
        for name, version, result, model in (
            (
                "vision",
                "vision-v1",
                {"vision": {"description": "A synthetic indoor scene."}, "attempts": []},
                {"framework": "Ollama", "name": "test-model"},
            ),
            (
                "faces",
                "faces-v1",
                {"image": {"width": 10, "height": 10, "color_order": "BGR"}, "faces": []},
                {"detector": {"name": "test"}, "embedding": {"name": "test"}},
            ),
        ):
            write_json(
                self.root / f"analysis/{name}/{version}/{fingerprint}/{sha256[:2]}/{sha256}/image-preview.json",
                {
                    "result_schema_version": 1,
                    "workspace_contract_version": 1,
                    "workspace_id": self.workspace_id,
                    "asset_id": entry["asset_id"],
                    "sha256": sha256,
                    "processor": {"name": name, "version": version},
                    "model": model,
                    "configuration_fingerprint": fingerprint,
                    "created_at": "2026-10-20T10:00:00Z",
                    "status": "success",
                    "result": result,
                },
            )
        session_path = self.root / f"analysis/session-grouper/session-grouper-v1/{fingerprint}/{'e' * 64}.json"
        write_json(
            session_path,
            {
                "result_schema_version": 1,
                "workspace_contract_version": 1,
                "workspace_id": self.workspace_id,
                "processor": {"name": "session-grouper", "version": "session-grouper-v1"},
                "configuration_fingerprint": fingerprint,
                "status": "success",
                "result": {
                    "sessions": [
                        {
                            "session_id": "session-synthetic",
                            "start": "2026-10-01T20:00:00",
                            "end": "2026-10-01T21:00:00",
                            "confidence": "medium",
                            "assets": [{"asset_id": entry["asset_id"]}],
                        }
                    ]
                },
            },
        )
        cluster_path = self.root / f"analysis/faces/faces-clustering-v1/{fingerprint}/{'f' * 64}.json"
        write_json(
            cluster_path,
            {
                "result_schema_version": 1,
                "workspace_contract_version": 1,
                "workspace_id": self.workspace_id,
                "processor": {"name": "faces-clustering", "version": "faces-clustering-v1"},
                "configuration_fingerprint": fingerprint,
                "status": "success",
                "result": {
                    "clusters": [
                        {
                            "cluster_id": "face-cluster-0000",
                            "status": "uncertain",
                            "member_count": 1,
                            "members": [{"asset_id": entry["asset_id"]}],
                        }
                    ]
                },
            },
        )

    def publish(self, *, version: int = 1) -> Path:
        write_json(
            self.root / "workspace.json",
            {
                "schema_version": 1,
                "workspace_contract_version": version,
                "workspace_id": self.workspace_id,
                "asset_catalog": "metadata/catalog.json",
            },
        )
        write_json(
            self.root / "metadata/catalog.json",
            {
                "workspace_contract_version": version,
                "workspace_id": self.workspace_id,
                "generated_at": "2026-10-20T10:00:00Z",
                "generated_by_run_id": "run-test",
                "source_root": str(self.originals.resolve()),
                "assets": self.assets,
            },
        )
        return self.root


@pytest.fixture
def workspace_builder(tmp_path: Path) -> WorkspaceBuilder:
    return WorkspaceBuilder(tmp_path / "workspace", tmp_path / "originals")
