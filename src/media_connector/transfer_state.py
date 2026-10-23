from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from media_connector.errors import ConnectorError


SCHEMA_VERSION = 1


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transfer_runs (
  run_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, status TEXT NOT NULL,
  started_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS transfer_items (
  run_id TEXT NOT NULL REFERENCES transfer_runs(run_id), item_id TEXT NOT NULL,
  source_id TEXT NOT NULL, object_id TEXT NOT NULL, version_token TEXT NOT NULL,
  logical_path TEXT NOT NULL, status TEXT NOT NULL, content_sha256 TEXT,
  size_bytes INTEGER, canonical_suffix TEXT, profile_id TEXT,
  staging_path TEXT, final_relative_path TEXT, error_code TEXT,
  PRIMARY KEY (run_id, item_id)
);
CREATE TABLE IF NOT EXISTS content_objects (
  content_sha256 TEXT PRIMARY KEY, size_bytes INTEGER NOT NULL,
  canonical_suffix TEXT NOT NULL, profile_id TEXT NOT NULL,
  relative_path TEXT NOT NULL UNIQUE, verified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_content_links (
  source_id TEXT NOT NULL, object_id TEXT NOT NULL, version_token TEXT NOT NULL,
  logical_path TEXT NOT NULL, content_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL, linked_at TEXT NOT NULL,
  PRIMARY KEY (source_id, object_id, version_token, content_sha256)
);
CREATE TABLE IF NOT EXISTS transfer_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
  item_id TEXT, event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


class TransferRepository:
    def __init__(self, state_root: Path, workspace_id: str):
        self.path = state_root / "connector-state.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.executescript(SCHEMA)
            current = self.connection.execute(
                "SELECT value FROM metadata WHERE key='workspace_id'"
            ).fetchone()
            if current is not None and current[0] != workspace_id:
                raise ConnectorError("STATE_LIBRARY_MISMATCH", "state belongs to another workspace", 4)
            self.connection.execute(
                "INSERT OR IGNORE INTO metadata(key,value) VALUES('workspace_id',?)", (workspace_id,)
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            self.connection.commit()
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def event(self, run_id: str, item_id: str | None, event_type: str, now: str, payload: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO transfer_events(run_id,item_id,event_type,payload_json,created_at) VALUES(?,?,?,?,?)",
            (run_id, item_id, event_type, json.dumps(payload or {}, sort_keys=True), now),
        )

