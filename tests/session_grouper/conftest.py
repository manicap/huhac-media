import hashlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def workspace_factory(tmp_path: Path):
    def create(assets: list[dict], *, contract_version: int = 1) -> Path:
        workspace = tmp_path / f"workspace-{len(list(tmp_path.iterdir()))}"
        workspace.mkdir()
        catalog_assets = []
        for definition in assets:
            digest = hashlib.sha256(definition["name"].encode("utf-8")).hexdigest()
            asset_id = f"sha256:{digest}"
            metadata_location = None
            if definition.get("metadata", True):
                metadata_location = f"metadata/assets/{digest[:2]}/{digest}.json"
                metadata_path = workspace / Path(metadata_location)
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                capture = definition.get("capture")
                metadata_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "asset": {"asset_id": asset_id},
                            "capture": capture,
                        }
                    ),
                    encoding="utf-8",
                )
            catalog_assets.append(
                {
                    "asset_id": asset_id,
                    "sha256": digest,
                    "size_bytes": 1,
                    "media_type": definition.get("media_type", "image"),
                    "format": (
                        "JPEG"
                        if definition.get("media_type", "image") == "image"
                        else "MP4"
                    ),
                    "mime_type": "image/jpeg"
                    if definition.get("media_type", "image") == "image"
                    else "video/mp4",
                    "availability": definition.get("availability", "available"),
                    "metadata_location": metadata_location,
                    "preview_location": None,
                    "sources": [],
                }
            )
        manifest = {
            "schema_version": 1,
            "workspace_contract_version": contract_version,
            "workspace_id": "test-workspace",
            "asset_catalog": "metadata/catalog.json",
        }
        (workspace / "workspace.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        catalog_path = workspace / "metadata" / "catalog.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(
            json.dumps(
                {
                    "workspace_contract_version": contract_version,
                    "workspace_id": "test-workspace",
                    "generated_at": "2026-09-30T12:00:00+00:00",
                    "generated_by_run_id": "run-1",
                    "source_root": "unused",
                    "assets": catalog_assets,
                }
            ),
            encoding="utf-8",
        )
        (workspace / "state").mkdir()
        (workspace / "state" / "catalog.sqlite3").write_bytes(b"must not be read")
        return workspace

    return create
