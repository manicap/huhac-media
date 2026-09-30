from __future__ import annotations

import sqlite3


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE workspace (
            id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
            format TEXT,
            mime_type TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            metadata_json TEXT
        );

        CREATE TABLE source_paths (
            id TEXT PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE,
            current_source_version_id TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            absent_since TEXT
        );

        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            input_path TEXT NOT NULL,
            work_path TEXT NOT NULL,
            app_version TEXT NOT NULL,
            effective_config_json TEXT NOT NULL,
            summary_json TEXT,
            fatal_error TEXT
        );

        CREATE TABLE source_versions (
            id TEXT PRIMARY KEY,
            source_path_id TEXT NOT NULL REFERENCES source_paths(id),
            asset_id TEXT NOT NULL REFERENCES assets(asset_id),
            filename TEXT NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            filesystem_mtime_ns INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'absent')),
            first_seen_run_id TEXT NOT NULL REFERENCES runs(id),
            last_seen_run_id TEXT NOT NULL REFERENCES runs(id),
            created_at TEXT NOT NULL,
            superseded_at TEXT,
            UNIQUE(source_path_id, asset_id)
        );

        CREATE TABLE asset_stages (
            asset_id TEXT NOT NULL REFERENCES assets(asset_id),
            stage TEXT NOT NULL,
            processor_version TEXT NOT NULL,
            config_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'success', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            output_path TEXT,
            error_code TEXT,
            error_message TEXT,
            PRIMARY KEY (asset_id, stage, processor_version, config_fingerprint)
        );

        CREATE TABLE run_items (
            run_id TEXT NOT NULL REFERENCES runs(id),
            relative_path TEXT NOT NULL,
            source_version_id TEXT REFERENCES source_versions(id),
            asset_id TEXT REFERENCES assets(asset_id),
            plan_kind TEXT NOT NULL,
            result_status TEXT,
            PRIMARY KEY (run_id, relative_path)
        );

        CREATE TABLE errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id),
            relative_path TEXT,
            asset_id TEXT REFERENCES assets(asset_id),
            phase TEXT NOT NULL,
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            diagnostics_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE INDEX idx_assets_sha256 ON assets(sha256);
        CREATE INDEX idx_source_paths_relative_path ON source_paths(relative_path);
        CREATE INDEX idx_source_versions_asset ON source_versions(asset_id);
        CREATE INDEX idx_source_versions_last_run ON source_versions(last_seen_run_id);
        CREATE INDEX idx_asset_stages_status ON asset_stages(status);
        CREATE INDEX idx_run_items_asset ON run_items(asset_id);
        CREATE INDEX idx_errors_run ON errors(run_id);
        """,
    ),
)


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        connection.executescript(sql)
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at) "
            "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (version,),
        )
        connection.commit()
