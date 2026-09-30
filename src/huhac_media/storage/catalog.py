from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from huhac_media import __version__
from huhac_media.domain.enums import PlanKind
from huhac_media.domain.models import ExistingSource
from huhac_media.domain.models import IngestPlan
from huhac_media.services.planner import CatalogSnapshot
from huhac_media.storage.database import Database


def read_catalog(database: Database) -> CatalogSnapshot:
    with database.transaction() as connection:
        sources = {
            row["relative_path"]: ExistingSource(
                source_path_id=row["source_path_id"],
                source_version_id=row["source_version_id"],
                relative_path=row["relative_path"],
                asset_id=row["asset_id"],
                stage_failures=row["stage_failures"],
                change_blocked=bool(row["change_blocked"]),
            )
            for row in connection.execute(
                """
                SELECT sp.id AS source_path_id, sv.id AS source_version_id,
                       sp.relative_path, sv.asset_id,
                       (SELECT COUNT(*) FROM asset_stages ast
                        WHERE ast.asset_id = sv.asset_id AND ast.status = 'failed') AS stage_failures,
                       COALESCE((
                         SELECT ri.result_status = 'error'
                         FROM run_items ri JOIN runs r ON r.id = ri.run_id
                         WHERE ri.relative_path = sp.relative_path
                         ORDER BY r.started_at DESC LIMIT 1
                       ), 0) AS change_blocked
                FROM source_paths sp
                JOIN source_versions sv ON sv.id = sp.current_source_version_id
                """
            )
        }
        counts = {
            row["asset_id"]: row["count"]
            for row in connection.execute(
                "SELECT asset_id, COUNT(*) AS count FROM source_versions "
                "WHERE status = 'active' GROUP BY asset_id"
            )
        }
        failures = frozenset(
            row["asset_id"]
            for row in connection.execute(
                "SELECT DISTINCT asset_id FROM asset_stages WHERE status = 'failed'"
            )
        )
    return CatalogSnapshot(sources, counts, failures)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CatalogStore:
    def __init__(self, database: Database):
        self.database = database

    def start_run(self, input_path: Path, work_path: Path, effective_config: dict) -> str:
        run_id = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs(id, status, started_at, input_path, work_path,
                                 app_version, effective_config_json)
                VALUES (?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _now(),
                    str(input_path),
                    str(work_path),
                    __version__,
                    json.dumps(effective_config, ensure_ascii=False, sort_keys=True),
                ),
            )
        return run_id

    def ensure_workspace(self, workspace_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO workspace(id, schema_version, created_at)
                VALUES (?, 1, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (workspace_id, _now()),
            )

    def record_discovery(
        self,
        run_id: str,
        plan: IngestPlan,
        *,
        changed_source_policy: str = "reprocess",
        scan_complete: bool = True,
    ) -> set[str]:
        if changed_source_policy not in {"reprocess", "error"}:
            raise ValueError("Unsupported changed source policy")
        timestamp = _now()
        observed_paths = {
            item.scanned.relative_path.as_posix() for item in plan.items
        } | {item.relative_path.as_posix() for item in plan.unsupported}
        with self.database.transaction() as connection:
            for item in plan.items:
                self._record_item(
                    connection,
                    run_id,
                    item,
                    changed_source_policy=changed_source_policy,
                    timestamp=timestamp,
                )
            absent_paths = (
                self._mark_absent(connection, observed_paths, timestamp)
                if scan_complete
                else set()
            )
        return absent_paths

    def finish_run(self, run_id: str, status: str, summary: dict | None = None) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE runs SET status = ?, finished_at = ?, summary_json = ? WHERE id = ?",
                (status, _now(), json.dumps(summary or {}, sort_keys=True), run_id),
            )

    def recover_interrupted(self) -> list[str]:
        timestamp = _now()
        with self.database.transaction() as connection:
            run_ids = [
                row["id"]
                for row in connection.execute("SELECT id FROM runs WHERE status = 'running'")
            ]
            connection.execute(
                "UPDATE runs SET status = 'interrupted', finished_at = ? WHERE status = 'running'",
                (timestamp,),
            )
            connection.execute(
                """
                UPDATE asset_stages SET status = 'pending', finished_at = ?,
                       error_code = 'INTERRUPTED', error_message = 'Recovered after interrupted run'
                WHERE status = 'processing'
                """,
                (timestamp,),
            )
        return run_ids

    def stage_needs_run(
        self, asset_id: str, stage: str, version: str, fingerprint: str, output: Path | None
    ) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT status, output_path FROM asset_stages
                WHERE asset_id = ? AND stage = ? AND processor_version = ?
                      AND config_fingerprint = ?
                """,
                (asset_id, stage, version, fingerprint),
            ).fetchone()
        if row is None or row["status"] != "success":
            return True
        recorded = Path(row["output_path"]) if row["output_path"] else output
        return recorded is None or not recorded.is_file()

    def start_stage(self, asset_id: str, stage: str, version: str, fingerprint: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO asset_stages(asset_id, stage, processor_version,
                    config_fingerprint, status, attempts, started_at)
                VALUES (?, ?, ?, ?, 'processing', 1, ?)
                ON CONFLICT(asset_id, stage, processor_version, config_fingerprint)
                DO UPDATE SET status = 'processing', attempts = attempts + 1,
                    started_at = excluded.started_at, finished_at = NULL,
                    error_code = NULL, error_message = NULL
                """,
                (asset_id, stage, version, fingerprint, _now()),
            )

    def complete_stage(
        self, asset_id: str, stage: str, version: str, fingerprint: str, output: Path
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE asset_stages SET status = 'success', finished_at = ?, output_path = ?,
                       error_code = NULL, error_message = NULL
                WHERE asset_id = ? AND stage = ? AND processor_version = ?
                      AND config_fingerprint = ?
                """,
                (_now(), str(output), asset_id, stage, version, fingerprint),
            )

    def fail_stage(
        self,
        run_id: str,
        relative_path: str,
        asset_id: str,
        stage: str,
        version: str,
        fingerprint: str,
        code: str,
        message: str,
        diagnostics: dict | None = None,
    ) -> None:
        timestamp = _now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE asset_stages SET status = 'failed', finished_at = ?, error_code = ?,
                       error_message = ?
                WHERE asset_id = ? AND stage = ? AND processor_version = ?
                      AND config_fingerprint = ?
                """,
                (timestamp, code, message, asset_id, stage, version, fingerprint),
            )
            connection.execute(
                """
                INSERT INTO errors(run_id, relative_path, asset_id, phase, code,
                                   message, diagnostics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    relative_path,
                    asset_id,
                    stage,
                    code,
                    message,
                    json.dumps(diagnostics or {}, ensure_ascii=False),
                    timestamp,
                ),
            )

    def update_asset_metadata(self, asset_id: str, metadata: dict) -> None:
        detected = metadata.get("detected", {})
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE assets SET metadata_json = ?,
                    format = COALESCE(?, format), mime_type = COALESCE(?, mime_type)
                WHERE asset_id = ?
                """,
                (
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    detected.get("format"),
                    detected.get("mime_type"),
                    asset_id,
                ),
            )

    def error_count(self, run_id: str) -> int:
        with self.database.transaction() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM errors WHERE run_id = ?", (run_id,)
            ).fetchone()[0]

    def record_error(
        self,
        run_id: str,
        phase: str,
        code: str,
        message: str,
        *,
        relative_path: str | None = None,
        asset_id: str | None = None,
        diagnostics: dict | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO errors(run_id, relative_path, asset_id, phase, code,
                                   message, diagnostics_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    relative_path,
                    asset_id,
                    phase,
                    code,
                    message,
                    json.dumps(diagnostics or {}, ensure_ascii=False),
                    _now(),
                ),
            )

    def errors(self, run_id: str) -> list[dict]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                """
                SELECT relative_path, asset_id, phase, code, message,
                       diagnostics_json, created_at
                FROM errors WHERE run_id = ? ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "relative_path": row["relative_path"],
                "asset_id": row["asset_id"],
                "phase": row["phase"],
                "code": row["code"],
                "message": row["message"],
                "diagnostics": json.loads(row["diagnostics_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _record_item(
        connection: sqlite3.Connection,
        run_id: str,
        item,
        *,
        changed_source_policy: str,
        timestamp: str,
    ) -> None:
        scanned = item.scanned
        assert scanned.asset_id is not None and scanned.sha256 is not None
        connection.execute(
            """
            INSERT INTO assets(asset_id, sha256, size_bytes, media_type, format,
                               mime_type, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (
                scanned.asset_id,
                scanned.sha256,
                scanned.size_bytes,
                scanned.media_type.value,
                scanned.format,
                scanned.mime_type,
                timestamp,
                timestamp,
            ),
        )
        relative_path = scanned.relative_path.as_posix()
        source_path_id = item.existing.source_path_id if item.existing else str(uuid4())
        if item.existing is None:
            connection.execute(
                """
                INSERT INTO source_paths(id, relative_path, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_path_id, relative_path, timestamp, timestamp),
            )
        else:
            connection.execute(
                "UPDATE source_paths SET last_seen_at = ?, absent_since = NULL WHERE id = ?",
                (timestamp, source_path_id),
            )

        if item.kind == PlanKind.KNOWN:
            source_version_id = item.existing.source_version_id
            connection.execute(
                """
                UPDATE source_versions
                SET last_seen_run_id = ?, status = 'active'
                WHERE id = ?
                """,
                (run_id, source_version_id),
            )
        else:
            if item.existing is not None:
                connection.execute(
                    """
                    UPDATE source_versions SET status = 'superseded', superseded_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, item.existing.source_version_id),
                )
            previous = connection.execute(
                "SELECT id FROM source_versions WHERE source_path_id = ? AND asset_id = ?",
                (source_path_id, scanned.asset_id),
            ).fetchone()
            source_version_id = previous["id"] if previous else str(uuid4())
            if previous:
                connection.execute(
                    """
                    UPDATE source_versions
                    SET filename = ?, size_bytes = ?, filesystem_mtime_ns = ?,
                        status = 'active', last_seen_run_id = ?, superseded_at = NULL
                    WHERE id = ?
                    """,
                    (
                        scanned.filename,
                        scanned.size_bytes,
                        scanned.filesystem_mtime_ns,
                        run_id,
                        source_version_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO source_versions(
                        id, source_path_id, asset_id, filename, size_bytes,
                        filesystem_mtime_ns, status, first_seen_run_id,
                        last_seen_run_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        source_version_id,
                        source_path_id,
                        scanned.asset_id,
                        scanned.filename,
                        scanned.size_bytes,
                        scanned.filesystem_mtime_ns,
                        run_id,
                        run_id,
                        timestamp,
                    ),
                )
            connection.execute(
                "UPDATE source_paths SET current_source_version_id = ? WHERE id = ?",
                (source_version_id, source_path_id),
            )
        result = "error" if item.kind == PlanKind.CHANGED and changed_source_policy == "error" else "recorded"
        connection.execute(
            """
            INSERT INTO run_items(run_id, relative_path, source_version_id, asset_id,
                                  plan_kind, result_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, relative_path, source_version_id, scanned.asset_id, item.kind.value, result),
        )
        if result == "error":
            connection.execute(
                """
                INSERT INTO errors(run_id, relative_path, asset_id, phase, code,
                                   message, created_at)
                VALUES (?, ?, ?, 'discovery', 'CHANGED_SOURCE_REJECTED', ?, ?)
                """,
                (run_id, relative_path, scanned.asset_id, "Changed source policy is error", timestamp),
            )

    @staticmethod
    def _mark_absent(connection: sqlite3.Connection, observed: set[str], timestamp: str) -> set[str]:
        changed: set[str] = set()
        rows = connection.execute(
            "SELECT id, relative_path, current_source_version_id, absent_since FROM source_paths"
        ).fetchall()
        for row in rows:
            if row["relative_path"] in observed or row["absent_since"] is not None:
                continue
            connection.execute(
                "UPDATE source_paths SET absent_since = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
            connection.execute(
                "UPDATE source_versions SET status = 'absent' WHERE id = ?",
                (row["current_source_version_id"],),
            )
            changed.add(row["relative_path"])
        return changed
