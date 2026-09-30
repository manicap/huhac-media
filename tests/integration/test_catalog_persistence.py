from pathlib import Path

import pytest

from huhac_media.services.planner import CatalogSnapshot, Planner
from huhac_media.services.scanner import Scanner
from huhac_media.storage.catalog import CatalogStore, read_catalog
from huhac_media.storage.database import Database


pytestmark = pytest.mark.integration


def record(input_path: Path, database: Database, policy: str = "reprocess") -> str:
    snapshot = read_catalog(database)
    plan = Planner().plan(Scanner().scan(input_path), snapshot)
    store = CatalogStore(database)
    run_id = store.start_run(input_path, input_path / "_processing", {"policy": policy})
    store.record_discovery(run_id, plan, changed_source_policy=policy)
    store.finish_run(run_id, "success")
    return run_id


def test_duplicates_and_repeat_are_idempotent(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    payload = b"\xff\xd8\xffsame"
    (input_path / "a.jpg").write_bytes(payload)
    (input_path / "b.jpg").write_bytes(payload)
    database = Database(tmp_path / "catalog.sqlite3")

    record(input_path, database)
    record(input_path, database)

    with database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM source_paths").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2


def test_changed_source_preserves_history_and_absent_source(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    source = input_path / "photo.jpg"
    gone = input_path / "gone.jpg"
    source.write_bytes(b"\xff\xd8\xffone")
    gone.write_bytes(b"\xff\xd8\xffgone")
    database = Database(tmp_path / "catalog.sqlite3")
    record(input_path, database)

    source.write_bytes(b"\xff\xd8\xfftwo")
    gone.unlink()
    record(input_path, database)

    with database.transaction() as connection:
        versions = connection.execute(
            """
            SELECT sv.status FROM source_versions sv
            JOIN source_paths sp ON sp.id = sv.source_path_id
            WHERE sp.relative_path = 'photo.jpg' ORDER BY sv.created_at
            """
        ).fetchall()
        assert {row["status"] for row in versions} == {"active", "superseded"}
        absent = connection.execute(
            "SELECT absent_since FROM source_paths WHERE relative_path = 'gone.jpg'"
        ).fetchone()
        assert absent["absent_since"] is not None


def test_changed_error_records_new_identity_and_error(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    source = input_path / "photo.jpg"
    source.write_bytes(b"\xff\xd8\xffone")
    database = Database(tmp_path / "catalog.sqlite3")
    record(input_path, database)
    source.write_bytes(b"\xff\xd8\xfftwo")

    record(input_path, database, "error")

    with database.transaction() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM source_versions"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT code FROM errors"
        ).fetchone()["code"] == "CHANGED_SOURCE_REJECTED"

