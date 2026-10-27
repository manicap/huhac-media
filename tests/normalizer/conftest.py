from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def default_technical(media_type: str) -> dict:
    common = {
        "manufacturer": "Canon",
        "camera_model": "Camera 1",
        "software": None,
    }
    if media_type == "image":
        return common | {
            "width": 6000,
            "height": "4000",
            "orientation": 1,
            "color_space": "sRGB",
            "lens": "35mm",
            "focal_length_mm": "35.0",
            "exposure_seconds": 0.008,
            "aperture": "2.8",
            "iso": "400",
            "flash": None,
            "gps": {"latitude": 50.1, "longitude": "14.4"},
        }
    return common | {
        "container": "mov,mp4",
        "duration_seconds": "12.5",
        "width": 1920,
        "height": 1080,
        "fps": "25",
        "video_codec": "h264",
        "bitrate": "8000000",
        "rotation": "90",
        "audio_present": True,
        "audio_codec": "aac",
        "sample_rate": "48000",
        "channels": 2,
    }


@pytest.fixture
def workspace_factory(tmp_path: Path):
    counter = 0

    def create(
        definitions: list[dict] | None = None,
        *,
        workspace_id: object = "normalizer-workspace",
        contract_version: int = 1,
        source_root: str = "D:\\Media",
        reverse: bool = False,
    ) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"workspace-{counter}"
        root.mkdir()
        definitions = definitions or [
            {"name": "photo", "media_type": "image"},
            {"name": "video", "media_type": "video"},
        ]
        entries = []
        for definition in definitions:
            digest = hashlib.sha256(definition["name"].encode()).hexdigest()
            asset_id = f"sha256:{digest}"
            media_type = definition.get("media_type", "image")
            location = f"metadata/assets/{digest[:2]}/{digest}.json"
            has_metadata = definition.get("metadata", True) not in {None, False}
            metadata_location = location if has_metadata else None
            entry = {
                "asset_id": definition.get("asset_id", asset_id),
                "sha256": definition.get("sha256", digest),
                "size_bytes": definition.get("size_bytes", 123),
                "media_type": media_type,
                "format": "JPEG" if media_type == "image" else "MP4",
                "mime_type": "image/jpeg" if media_type == "image" else "video/mp4",
                "availability": definition.get("availability", "available"),
                "metadata_location": definition.get("metadata_location", metadata_location),
                "preview_location": None,
                "sources": definition.get(
                    "sources",
                    [{"source_version_id": f"source-{definition['name']}", "relative_path": f"event/{definition['name']}.bin", "status": "active"}],
                ),
            }
            entries.append(entry)
            if metadata_location is not None and not definition.get("skip_metadata_file", False):
                capture = definition.get(
                    "capture",
                    {
                        "datetime": "2026-10-26T12:30:00+01:00",
                        "source": "EXIF:DateTimeOriginal",
                        "timezone_offset": "+01:00",
                        "filesystem_fallback": False,
                    },
                )
                metadata = definition.get(
                    "metadata_payload",
                    {
                        "schema_version": 1,
                        "asset": {"asset_id": asset_id},
                        "detected": {
                            "format": entry["format"],
                            "mime_type": entry["mime_type"],
                        },
                        "capture": capture,
                        "technical": definition.get("technical", default_technical(media_type)),
                        "raw_metadata": {"exiftool": "metadata/raw/do-not-read.json"},
                        "stages": {
                            "metadata": {
                                "processor_version": "metadata-v2",
                                "config_fingerprint": "normalized-v1",
                                "status": "success",
                            }
                        },
                    },
                )
                path = root / Path(location)
                path.parent.mkdir(parents=True, exist_ok=True)
                if definition.get("corrupt_metadata"):
                    path.write_text("{not-json", encoding="utf-8")
                else:
                    write_json(path, metadata)
        if reverse:
            entries.reverse()
        write_json(
            root / "workspace.json",
            {
                "schema_version": 1,
                "workspace_contract_version": contract_version,
                "workspace_id": workspace_id,
                "asset_catalog": "metadata/catalog.json",
            },
        )
        write_json(
            root / "metadata" / "catalog.json",
            {
                "workspace_contract_version": contract_version,
                "workspace_id": workspace_id,
                "generated_at": "2026-10-26T12:00:00+00:00",
                "generated_by_run_id": "run-1",
                "source_root": source_root,
                "assets": entries,
            },
        )
        (root / "state").mkdir()
        (root / "state" / "catalog.sqlite3").write_bytes(b"must-not-be-read")
        return root

    return create
