from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4

import pytest

from huhac_media.services.archive_init import SimulatedInterruption, initialize_archive


def local(_: Path) -> str:
    return "local"


@pytest.mark.integration
def test_empty_archive_is_ready_and_idempotent(tmp_path: Path) -> None:
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    operation_id = str(uuid4())
    result = initialize_archive(storage, workspace, operation_id, classifier=local)
    assert result.state == "ready"
    manifest = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    catalog = json.loads((workspace / "metadata" / "catalog.json").read_text(encoding="utf-8"))
    assert manifest["workspace_contract_version"] == 1
    assert manifest["workspace_id"] == result.workspace_id == catalog["workspace_id"]
    assert catalog["assets"] == []
    assert Path(catalog["source_root"]) == storage.resolve()
    assert list(storage.iterdir()) == []
    database = workspace / "state" / "catalog.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspace").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    before = {path.relative_to(workspace): (path.stat().st_size, path.stat().st_mtime_ns) for path in workspace.rglob("*") if path.is_file()}
    again = initialize_archive(storage, workspace, str(uuid4()), classifier=local)
    after = {path.relative_to(workspace): (path.stat().st_size, path.stat().st_mtime_ns) for path in workspace.rglob("*") if path.is_file()}
    assert again.state == "ready_existing"
    assert again.workspace_id == result.workspace_id
    assert after == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


@pytest.mark.integration
@pytest.mark.parametrize("phase", [
    "reserved", "storage_ready", "layout_ready", "sqlite_ready", "workspace_row_ready",
    "run_started", "report_ready", "catalog_ready", "run_finished", "manifest_ready",
])
def test_retry_after_every_interruption_point(tmp_path: Path, phase: str) -> None:
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    operation_id = str(uuid4())

    def interrupt(current: str) -> None:
        if current == phase:
            raise SimulatedInterruption(current)

    failed = initialize_archive(
        storage, workspace, operation_id, classifier=local, phase_hook=interrupt
    )
    assert failed.state == "failed_recoverable"
    assert failed.error and failed.error.code == "INTERRUPTED"
    resumed = initialize_archive(storage, workspace, operation_id, classifier=local)
    assert resumed.state in {"ready", "ready_existing"}
    assert resumed.operation_id == operation_id
    assert resumed.workspace_id
    catalog = json.loads((workspace / "metadata" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["assets"] == []


@pytest.mark.integration
def test_unknown_collision_is_preserved(tmp_path: Path) -> None:
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    operation_id = str(uuid4())
    initialize_archive(
        storage,
        workspace,
        operation_id,
        classifier=local,
        phase_hook=lambda phase: (_ for _ in ()).throw(SimulatedInterruption()) if phase == "reserved" else None,
    )
    foreign = workspace / "foreign.txt"
    foreign.write_text("do not touch", encoding="utf-8")
    result = initialize_archive(storage, workspace, operation_id, classifier=local)
    assert result.state == "failed_requires_manual_action"
    assert result.error and result.error.code == "WORKSPACE_CHANGED"
    assert foreign.read_text(encoding="utf-8") == "do not touch"


@pytest.mark.integration
def test_nonempty_storage_is_never_modified(tmp_path: Path) -> None:
    storage = tmp_path / "media"
    storage.mkdir()
    original = storage / "original.jpg"
    original.write_bytes(b"original")
    result = initialize_archive(storage, tmp_path / "workspace", str(uuid4()), classifier=local)
    assert result.state == "rejected"
    assert result.error and result.error.code == "STORAGE_NOT_EMPTY"
    assert original.read_bytes() == b"original"
    assert not (tmp_path / "workspace").exists()


@pytest.mark.integration
def test_concurrent_initialization_has_one_writer(tmp_path: Path) -> None:
    storage = tmp_path / "media"
    workspace = tmp_path / "workspace"
    operation_id = str(uuid4())
    entered = threading.Event()
    release = threading.Event()
    holder: list = []

    def pause(phase: str) -> None:
        if phase == "reserved":
            entered.set()
            assert release.wait(5)

    thread = threading.Thread(
        target=lambda: holder.append(initialize_archive(
            storage, workspace, operation_id, classifier=local, phase_hook=pause
        ))
    )
    thread.start()
    assert entered.wait(5)
    competing = initialize_archive(storage, workspace, operation_id, classifier=local)
    release.set()
    thread.join(10)
    assert competing.state == "failed_recoverable"
    assert competing.error and competing.error.code == "INITIALIZATION_BUSY"
    assert holder and holder[0].state == "ready"
