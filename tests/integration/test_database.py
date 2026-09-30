from pathlib import Path

import pytest

from huhac_media.storage.database import Database


pytestmark = pytest.mark.integration


def test_database_creates_schema_and_enforces_foreign_keys(tmp_path: Path) -> None:
    database = Database(tmp_path / "state" / "catalog.sqlite3")
    with database.transaction() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "workspace",
            "assets",
            "source_paths",
            "source_versions",
            "asset_stages",
            "runs",
            "run_items",
            "errors",
            "schema_migrations",
        } <= tables
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_read_only_database_does_not_mutate(tmp_path: Path) -> None:
    path = tmp_path / "catalog.sqlite3"
    with Database(path).transaction():
        pass
    before = path.stat().st_mtime_ns
    with Database(path, read_only=True).transaction() as connection:
        assert connection.execute("SELECT version FROM schema_migrations").fetchone()[0] == 1
    assert path.stat().st_mtime_ns == before

