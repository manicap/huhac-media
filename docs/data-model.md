# Data model

The core model distinguishes a stable source path, a version of the content
observed at that path, and an asset identified by SHA-256. A single asset can be
referenced by multiple source versions. Runs and independently versioned stages
record resumable processing state.

## SQLite tables

- `workspace` identifies a workspace and its schema version.
- `assets` stores content-addressed media identified as `sha256:<hex>`.
- `source_paths` stores unique POSIX-style paths relative to INPUT.
- `source_versions` links content observed at a source path to an asset while
  retaining superseded history.
- `asset_stages` stores independently resumable, versioned processing stages.
- `runs`, `run_items`, and `errors` provide operational history and diagnostics.
- `schema_migrations` records applied schema versions.

SQLite enables foreign keys, WAL mode, a five-second busy timeout, and FULL
synchronous writes. Stage identity is `(asset_id, stage, processor_version,
config_fingerprint)`, so completed work is reused only when its recipe matches.

Portable source and asset sidecars are separate from this transactional state.
