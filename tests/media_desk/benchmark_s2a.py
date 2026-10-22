"""Reproducible S2a validation/startup benchmark; not collected by pytest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from media_desk.config import Settings
from media_desk import originals
from media_desk.web import create_app


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_workspace(root: Path, count: int) -> tuple[Path, Path]:
    workspace = root / "workspace"
    local_root = root / "local-originals"
    entries = []
    for index in range(count):
        content = f"s2a-asset-{index:08d}".encode()
        digest = hashlib.sha256(content).hexdigest()
        relative = f"set-{index % 64:02d}/asset-{index:08d}.jpg"
        target = local_root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        entries.append(
            {
                "asset_id": f"sha256:{digest}",
                "sha256": digest,
                "size_bytes": len(content),
                "media_type": "video" if index % 7 == 0 else "image",
                "format": "MP4" if index % 7 == 0 else "JPEG",
                "mime_type": "video/mp4" if index % 7 == 0 else "image/jpeg",
                "availability": "available",
                "metadata_location": None,
                "preview_location": None,
                "sources": [
                    {
                        "source_version_id": f"source-{index}",
                        "relative_path": relative,
                        "status": "active",
                    }
                ],
            }
        )
    _write_json(
        workspace / "workspace.json",
        {
            "schema_version": 1,
            "workspace_contract_version": 1,
            "workspace_id": "s2a-benchmark",
            "asset_catalog": "metadata/catalog.json",
        },
    )
    _write_json(
        workspace / "metadata/catalog.json",
        {
            "workspace_contract_version": 1,
            "workspace_id": "s2a-benchmark",
            "generated_at": "2026-10-22T00:00:00Z",
            "generated_by_run_id": "s2a-benchmark",
            "source_root": r"D:\Archive\Huhac",
            "assets": entries,
        },
    )
    return workspace, local_root


def run(count: int, keep: Path | None) -> dict:
    temporary = None
    if keep is None:
        temporary = tempfile.TemporaryDirectory(prefix="media-desk-s2a-")
        root = Path(temporary.name)
    else:
        root = keep
        root.mkdir(parents=True, exist_ok=True)
    workspace = root / "workspace"
    local_root = root / "local-originals"
    if not (workspace / "workspace.json").is_file():
        workspace, local_root = build_workspace(root, count)

    real_hash = originals._sha256_file
    hash_calls = 0

    def counted_hash(path: Path) -> str:
        nonlocal hash_calls
        hash_calls += 1
        return real_hash(path)

    originals._sha256_file = counted_hash
    try:
        tick = time.perf_counter()
        validation = originals.validate_mapping_candidate(workspace, local_root)
        validation_ms = (time.perf_counter() - tick) * 1000
        validation_hash_calls = hash_calls
        hash_calls = 0
        if not validation.valid or validation.mapping is None:
            raise RuntimeError(validation.message)
        tick = time.perf_counter()
        app = create_app(
            settings=Settings(
                workspace=workspace,
                workspace_source="profile",
                originals_mapping=validation.mapping,
            )
        )
        startup_ms = (time.perf_counter() - tick) * 1000
        startup_hash_calls = hash_calls
        snapshot = app.state.snapshot
        if snapshot is None:
            raise RuntimeError(app.state.startup_error)
    finally:
        originals._sha256_file = real_hash

    result = {
        "asset_count": count,
        "validation_ms": round(validation_ms, 3),
        "validation_hash_calls": validation_hash_calls,
        "sampled_assets": validation.sampled_assets,
        "startup_ms": round(startup_ms, 3),
        "startup_hash_calls": startup_hash_calls,
        "online_originals": sum(asset.original_online for asset in snapshot.assets),
        "original_references": sum(asset.original is not None for asset in snapshot.assets),
        "unchecked_originals": sum(
            asset.original_access_state == "unchecked" for asset in snapshot.assets
        ),
        "workspace": str(workspace) if keep else None,
    }
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=int, default=10_000)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.assets, args.keep), indent=2))
