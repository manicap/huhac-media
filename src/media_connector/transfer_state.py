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
            self.connection.execute("PRAGMA journal_mode=DELETE")
            self.connection.execute("PRAGMA synchronous=FULL")
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

    def create_run(self, run_id: str, workspace_id: str, started_at: str) -> None:
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO transfer_runs(run_id,workspace_id,status,started_at) VALUES(?,?,?,?)",
                    (run_id, workspace_id, "running", started_at),
                )
                self.event(run_id, None, "run_started", started_at)
        except sqlite3.IntegrityError as exc:
            raise ConnectorError("OPERATION_ID_EXISTS", "operation_id already exists", 4) from exc

    def create_item(
        self,
        *,
        run_id: str,
        item_id: str,
        source_id: str,
        object_id: str,
        version_token: str,
        logical_path: str,
        now: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO transfer_items(
                run_id,item_id,source_id,object_id,version_token,logical_path,status
                ) VALUES(?,?,?,?,?,?,?)""",
                (run_id, item_id, source_id, object_id, version_token, logical_path, "pending"),
            )
            self.event(run_id, item_id, "item_planned", now)

    def update_item(self, run_id: str, item_id: str, status: str, now: str, **values: Any) -> None:
        allowed = {
            "content_sha256", "size_bytes", "canonical_suffix", "profile_id",
            "staging_path", "final_relative_path", "error_code",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported state fields: {sorted(unknown)}")
        assignments = ["status=?", *(f"{key}=?" for key in values)]
        parameters = [status, *values.values(), run_id, item_id]
        with self.connection:
            self.connection.execute(
                f"UPDATE transfer_items SET {','.join(assignments)} WHERE run_id=? AND item_id=?",
                parameters,
            )
            self.event(run_id, item_id, status, now, values)

    def complete_item(
        self,
        *,
        run_id: str,
        item_id: str,
        source_id: str,
        object_id: str,
        version_token: str,
        logical_path: str,
        content_hash: str,
        size: int,
        suffix: str,
        profile_id: str,
        relative_path: str,
        status: str,
        now: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR IGNORE INTO content_objects(
                content_sha256,size_bytes,canonical_suffix,profile_id,relative_path,verified_at
                ) VALUES(?,?,?,?,?,?)""",
                (content_hash, size, suffix, profile_id, relative_path, now),
            )
            self.connection.execute(
                """INSERT OR IGNORE INTO source_content_links(
                source_id,object_id,version_token,logical_path,content_sha256,run_id,linked_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (source_id, object_id, version_token, logical_path, content_hash, run_id, now),
            )
            self.connection.execute(
                """UPDATE transfer_items SET status=?,content_sha256=?,size_bytes=?,
                canonical_suffix=?,profile_id=?,final_relative_path=?,error_code=NULL
                WHERE run_id=? AND item_id=?""",
                (status, content_hash, size, suffix, profile_id, relative_path, run_id, item_id),
            )
            self.event(run_id, item_id, status, now, {"content_sha256": content_hash})

    def finish_run(self, run_id: str, status: str, completed_at: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE transfer_runs SET status=?,completed_at=? WHERE run_id=?",
                (status, completed_at, run_id),
            )
            self.event(run_id, None, f"run_{status}", completed_at)

    def recoverable_items(self) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM transfer_items WHERE status IN ('transferring','verified_staged','publishing') ORDER BY run_id,item_id"
            )
        )

    def run_items(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM transfer_items WHERE run_id=? ORDER BY item_id", (run_id,)
            )
        )
