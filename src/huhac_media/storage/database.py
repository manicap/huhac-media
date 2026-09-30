from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

from huhac_media.storage.migrations import apply_migrations


class Database:
    def __init__(self, path: Path, *, read_only: bool = False):
        self.path = path
        self.read_only = read_only

    def connect(self) -> sqlite3.Connection:
        if self.read_only:
            uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        if not self.read_only:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            apply_migrations(connection)
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

