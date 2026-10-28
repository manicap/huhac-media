from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from huhac_studio.errors import DatabaseIntegrityError


SCHEMA_VERSION = 1

_SCHEMA_V1 = (
    """
    CREATE TABLE projects (
        project_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        notes TEXT,
        status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
        revision INTEGER NOT NULL CHECK (revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT,
        CHECK ((status = 'active' AND archived_at IS NULL) OR
               (status = 'archived' AND archived_at IS NOT NULL))
    )
    """,
    """
    CREATE TABLE project_tags (
        project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        normalized_key TEXT NOT NULL,
        display_name TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (position >= 0),
        PRIMARY KEY (project_id, normalized_key),
        UNIQUE (project_id, position)
    )
    """,
    """
    CREATE TABLE project_media_links (
        project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
        asset_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('source', 'reference', 'deliverable')),
        note TEXT,
        position INTEGER CHECK (position IS NULL OR position >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (project_id, asset_id)
    )
    """,
    "CREATE INDEX projects_workspace_status_updated ON projects(workspace_id, status, updated_at DESC)",
    "CREATE INDEX project_media_links_asset ON project_media_links(asset_id)",
    "CREATE INDEX project_media_links_order ON project_media_links(project_id, position, created_at)",
)


class _WriterLock:
    """Non-blocking host-local lock held for the lifetime of the backend."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = path.open("a+b")
        if self._handle.seek(0, 2) == 0:
            self._handle.write(b"\0")
            self._handle.flush()
        self._handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self._handle.close()
            raise DatabaseIntegrityError(
                "Project database already has an active writer", lock_path=str(path)
            ) from exc

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()


class ProjectDatabase:
    """Owns schema/migrations and serializes writes for one backend process."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self._write_lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._writer_lock = _WriterLock(self.path.with_suffix(self.path.suffix + ".writer.lock"))
        try:
            self._initialize()
        except Exception:
            self._writer_lock.close()
            raise

    def close(self) -> None:
        self._writer_lock.close()

    def __del__(self) -> None:
        writer_lock = getattr(self, "_writer_lock", None)
        if writer_lock is not None:
            try:
                writer_lock.close()
            except Exception:
                pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise DatabaseIntegrityError(
                    "Project database schema is newer than this application",
                    schema_version=version,
                    supported_version=SCHEMA_VERSION,
                )
            if version == 0:
                existing = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if existing:
                    raise DatabaseIntegrityError(
                        "Unversioned non-empty project database will not be overwritten"
                    )
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in _SCHEMA_V1:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            self._verify(connection)
        finally:
            connection.close()

    @staticmethod
    def _verify(connection: sqlite3.Connection) -> None:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise DatabaseIntegrityError("SQLite quick_check failed", result=quick_check)
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise DatabaseIntegrityError(
                "SQLite foreign_key_check failed", violations=len(foreign_key_errors)
            )

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def backup(self, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(destination)
        with self._write_lock:
            source = self._connect()
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
                result = target.execute("PRAGMA quick_check").fetchone()[0]
                if result != "ok":
                    raise DatabaseIntegrityError("Backup quick_check failed", result=result)
            finally:
                target.close()
                source.close()
        return destination
