from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
import json
import os
from typing import Iterator
from uuid import uuid4

from huhac_media.domain.errors import FatalError
from huhac_media.storage.atomic import write_json_atomic
from huhac_media.storage.contract import ASSET_CATALOG, WORKSPACE_CONTRACT_VERSION


def select_work_path(input_path: Path, configured: Path | None, new_workspace: bool) -> Path:
    if configured is not None:
        return configured.resolve(strict=False)
    base = input_path / "_processing"
    if not new_workspace:
        return base.resolve(strict=False)
    index = 1
    while True:
        candidate = input_path / f"_processing_{index:03d}"
        if not candidate.exists():
            return candidate.resolve(strict=False)
        index += 1


def validate_paths(input_path: Path, work_path: Path) -> None:
    resolved_input = input_path.resolve(strict=True)
    if not resolved_input.is_dir():
        raise NotADirectoryError(resolved_input)
    resolved_work = work_path.resolve(strict=False)
    if resolved_work == resolved_input:
        raise ValueError("WORK must not be the same directory as INPUT")
    if resolved_work in resolved_input.parents:
        raise ValueError("WORK must not contain INPUT")


WORKSPACE_DIRECTORIES = (
    "state",
    "metadata/sources",
    "metadata/assets",
    "metadata/raw",
    "previews/images",
    "analysis",
    "runs",
    "logs",
    "tmp",
    "locks",
)


def initialize_workspace(work_path: Path) -> dict:
    manifest = work_path / "workspace.json"
    if work_path.exists() and not manifest.exists() and any(work_path.iterdir()):
        raise FatalError(f"Refusing to use non-empty unrecognized workspace: {work_path}")
    work_path.mkdir(parents=True, exist_ok=True)
    for relative in WORKSPACE_DIRECTORIES:
        (work_path / relative).mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FatalError(f"Invalid workspace manifest: {manifest}") from exc
        if payload.get("schema_version") != 1:
            raise FatalError("Unsupported workspace schema version")
        contract_version = payload.get("workspace_contract_version")
        if contract_version not in (None, WORKSPACE_CONTRACT_VERSION):
            raise FatalError("Unsupported workspace contract version")
        catalog = payload.get("asset_catalog")
        if catalog not in (None, ASSET_CATALOG.as_posix()):
            raise FatalError("Unsupported asset catalog location")
        if contract_version is None or catalog is None:
            payload["workspace_contract_version"] = WORKSPACE_CONTRACT_VERSION
            payload["asset_catalog"] = ASSET_CATALOG.as_posix()
            write_json_atomic(manifest, payload)
        return payload
    payload = {
        "schema_version": 1,
        "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
        "workspace_id": str(uuid4()),
        "asset_catalog": ASSET_CATALOG.as_posix(),
    }
    write_json_atomic(manifest, payload)
    return payload


@contextmanager
def workspace_lock(work_path: Path) -> Iterator[None]:
    lock_path = work_path / "locks" / "ingest.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+b")
    try:
        stream.seek(0)
        if stream.read(1) == b"":
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise FatalError(f"Workspace is already locked: {work_path}") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(f"pid={os.getpid()}\n".encode("ascii"))
        stream.flush()
        yield
    finally:
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        stream.close()
