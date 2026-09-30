from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from huhac_media.storage.atomic import write_json_atomic
from huhac_media.storage.database import Database


WORKSPACE_CONTRACT_VERSION = 1
ASSET_CATALOG = PurePosixPath("metadata/catalog.json")


def export_asset_catalog(
    database: Database,
    work_path: Path,
    input_path: Path,
    workspace_id: str,
    run_id: str,
) -> Path:
    """Export the public, portable asset inventory from ingest's private state."""
    with database.transaction() as connection:
        assets = connection.execute(
            """
            SELECT asset_id, sha256, size_bytes, media_type, format, mime_type
            FROM assets ORDER BY sha256
            """
        ).fetchall()
        sources = connection.execute(
            """
            SELECT sv.asset_id, sv.id AS source_version_id, sp.relative_path,
                   sv.status
            FROM source_versions sv
            JOIN source_paths sp ON sp.id = sv.source_path_id
            ORDER BY sv.asset_id, sp.relative_path, sv.created_at, sv.id
            """
        ).fetchall()

    sources_by_asset: dict[str, list[dict[str, str]]] = {}
    for source in sources:
        sources_by_asset.setdefault(source["asset_id"], []).append(
            {
                "source_version_id": source["source_version_id"],
                "relative_path": source["relative_path"],
                "status": source["status"],
            }
        )

    exported_assets = []
    for asset in assets:
        sha256 = asset["sha256"]
        asset_sources = sources_by_asset.get(asset["asset_id"], [])
        metadata = PurePosixPath("metadata/assets") / sha256[:2] / f"{sha256}.json"
        preview = PurePosixPath("previews/images") / sha256[:2] / f"{sha256}.jpg"
        exported_assets.append(
            {
                "asset_id": asset["asset_id"],
                "sha256": sha256,
                "size_bytes": asset["size_bytes"],
                "media_type": asset["media_type"],
                "format": asset["format"],
                "mime_type": asset["mime_type"],
                "availability": (
                    "available"
                    if any(source["status"] == "active" for source in asset_sources)
                    else "unavailable"
                ),
                "metadata_location": (
                    metadata.as_posix() if (work_path / metadata).is_file() else None
                ),
                "preview_location": (
                    preview.as_posix() if (work_path / preview).is_file() else None
                ),
                "sources": asset_sources,
            }
        )

    payload = {
        "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
        "workspace_id": workspace_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by_run_id": run_id,
        "source_root": str(input_path.resolve()),
        "assets": exported_assets,
    }
    target = work_path / ASSET_CATALOG
    write_json_atomic(target, payload)
    return target
