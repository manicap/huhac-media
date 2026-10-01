import json
import hashlib
from pathlib import Path

import pytest


@pytest.fixture
def keyframe_workspace_factory(tmp_path: Path):
    def create(assets: list[dict], *, contract_version: int = 1) -> tuple[Path, Path]:
        workspace = tmp_path / "workspace"
        source_root = tmp_path / "sources"
        (workspace / "metadata").mkdir(parents=True)
        (workspace / "state").mkdir()
        source_root.mkdir()
        (workspace / "state" / "catalog.sqlite3").write_bytes(b"must not be read")
        workspace_id = "test-workspace"
        (workspace / "workspace.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "workspace_contract_version": contract_version,
                    "workspace_id": workspace_id,
                    "asset_catalog": "metadata/catalog.json",
                }
            ),
            encoding="utf-8",
        )
        catalog_assets = []
        for index, spec in enumerate(assets):
            content = spec.get("content", f"synthetic video {index}".encode())
            sha256 = spec.get("sha256", hashlib.sha256(content).hexdigest())
            sources = spec.get(
                "sources",
                [
                    {
                        "source_version_id": f"source-{index}",
                        "relative_path": spec.get("relative_path", f"video-{index}.mp4"),
                        "status": "active",
                    }
                ],
            )
            if spec.get("create_source", True):
                for source in sources:
                    if source.get("status") == "active" and ".." not in source["relative_path"]:
                        path = source_root.joinpath(*Path(source["relative_path"]).parts)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content)
            catalog_assets.append(
                {
                    "asset_id": f"sha256:{sha256}",
                    "sha256": sha256,
                    "size_bytes": 15,
                    "media_type": spec.get("media_type", "video"),
                    "format": spec.get("format", "MP4"),
                    "mime_type": spec.get("mime_type", "video/mp4"),
                    "availability": spec.get("availability", "available"),
                    "metadata_location": None,
                    "preview_location": None,
                    "sources": sources,
                }
            )
        (workspace / "metadata" / "catalog.json").write_text(
            json.dumps(
                {
                    "workspace_contract_version": contract_version,
                    "workspace_id": workspace_id,
                    "generated_at": "2026-10-01T00:00:00+00:00",
                    "generated_by_run_id": "run-id",
                    "source_root": str(source_root.resolve()),
                    "assets": catalog_assets,
                }
            ),
            encoding="utf-8",
        )
        return workspace, source_root

    return create
