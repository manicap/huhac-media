from __future__ import annotations

import json
from pathlib import Path

from huhac_media.storage.atomic import write_json_atomic
from huhac_media.storage.database import Database


def raw_path(work: Path, sha256: str, tool: str) -> Path:
    return work / "metadata" / "raw" / sha256[:2] / f"{sha256}.{tool}.json"


def asset_path(work: Path, sha256: str) -> Path:
    return work / "metadata" / "assets" / sha256[:2] / f"{sha256}.json"


def write_raw_sidecars(work: Path, sha256: str, exif: dict | None, ffprobe: dict | None) -> dict:
    references: dict[str, str] = {}
    if exif is not None:
        path = raw_path(work, sha256, "exiftool")
        write_json_atomic(path, exif)
        references["exiftool"] = path.relative_to(work).as_posix()
    if ffprobe is not None:
        path = raw_path(work, sha256, "ffprobe")
        write_json_atomic(path, ffprobe)
        references["ffprobe"] = path.relative_to(work).as_posix()
    return references


def export_asset(database: Database, work: Path, asset_id: str) -> Path:
    with database.transaction() as connection:
        asset = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        stages = connection.execute(
            "SELECT stage, processor_version, config_fingerprint, status, finished_at, output_path, error_code FROM asset_stages WHERE asset_id = ?",
            (asset_id,),
        ).fetchall()
    metadata = json.loads(asset["metadata_json"]) if asset["metadata_json"] else {}
    payload = {
        "schema_version": 1,
        "asset": {
            "asset_id": asset["asset_id"],
            "sha256": asset["sha256"],
            "size_bytes": asset["size_bytes"],
            "media_type": asset["media_type"],
            "format": asset["format"],
            "mime_type": asset["mime_type"],
        },
        **metadata,
        "stages": {
            row["stage"]: {
                "processor_version": row["processor_version"],
                "config_fingerprint": row["config_fingerprint"],
                "status": row["status"],
                "finished_at": row["finished_at"],
                "output": Path(row["output_path"]).relative_to(work).as_posix()
                if row["output_path"] and Path(row["output_path"]).is_relative_to(work)
                else row["output_path"],
                "error_code": row["error_code"],
            }
            for row in stages
        },
    }
    target = asset_path(work, asset["sha256"])
    write_json_atomic(target, payload)
    return target


def export_sources(database: Database, work: Path, relative_paths: set[str]) -> None:
    with database.transaction() as connection:
        rows = connection.execute(
            """
            SELECT sv.id, sp.relative_path, sv.filename, sv.size_bytes,
                   sv.filesystem_mtime_ns, sv.asset_id, sv.status,
                   sv.created_at, sv.last_seen_run_id, a.sha256, a.media_type,
                   a.format, a.mime_type
            FROM source_paths sp
            JOIN source_versions sv ON sv.source_path_id = sp.id
            JOIN assets a ON a.asset_id = sv.asset_id
            """
        ).fetchall()
    for row in rows:
        if row["relative_path"] not in relative_paths:
            continue
        payload = {
            "schema_version": 1,
            "source": {
                "source_version_id": row["id"],
                "relative_path": row["relative_path"],
                "filename": row["filename"],
                "size_bytes": row["size_bytes"],
                "filesystem_mtime_ns": row["filesystem_mtime_ns"],
                "asset_id": row["asset_id"],
                "sha256": row["sha256"],
                "media_type": row["media_type"],
                "format": row["format"],
                "mime_type": row["mime_type"],
                "status": row["status"],
                "first_seen_at": row["created_at"],
                "last_seen_run_id": row["last_seen_run_id"],
            },
        }
        write_json_atomic(work / "metadata" / "sources" / f"{row['id']}.json", payload)
