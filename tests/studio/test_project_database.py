from __future__ import annotations

import sqlite3

import pytest

from huhac_studio.database import SCHEMA_VERSION, ProjectDatabase
from huhac_studio.errors import DatabaseIntegrityError


def test_initializes_hardened_versioned_schema(tmp_path):
    path = tmp_path / "profile" / "projects.sqlite3"
    ProjectDatabase(path)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"projects", "project_tags", "project_media_links"} <= tables
    finally:
        connection.close()


def test_refuses_unknown_newer_or_unversioned_database(tmp_path):
    newer = tmp_path / "newer.sqlite3"
    connection = sqlite3.connect(newer)
    connection.execute("PRAGMA user_version=99")
    connection.close()
    with pytest.raises(DatabaseIntegrityError):
        ProjectDatabase(newer)

    unversioned = tmp_path / "unversioned.sqlite3"
    connection = sqlite3.connect(unversioned)
    connection.execute("CREATE TABLE foreign_data(value TEXT)")
    connection.close()
    with pytest.raises(DatabaseIntegrityError):
        ProjectDatabase(unversioned)


def test_backup_uses_sqlite_backup_api_and_is_valid(tmp_path):
    database = ProjectDatabase(tmp_path / "projects.sqlite3")
    destination = tmp_path / "backups" / "projects.sqlite3"

    assert database.backup(destination) == destination
    connection = sqlite3.connect(destination)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        connection.close()
    with pytest.raises(FileExistsError):
        database.backup(destination)


def test_refuses_a_second_authoritative_writer(tmp_path):
    path = tmp_path / "projects.sqlite3"
    first = ProjectDatabase(path)
    try:
        with pytest.raises(DatabaseIntegrityError, match="active writer"):
            ProjectDatabase(path)
    finally:
        first.close()
    second = ProjectDatabase(path)
    second.close()
