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

Discovery is idempotent: an unchanged path updates `last_seen` data but does not
create another source version. A new path sharing an existing SHA-256 creates a
new source path/version linked to the existing asset. Changed content creates or
reactivates a version for the new asset and supersedes the formerly current
version. The `error` policy still records the new identity, preventing old
results from being presented as current, but records a processing error.

After a complete scan, unseen current paths become `absent`; unsuccessful or
interrupted scans never apply this transition. Records are retained rather than
deleted.

Asset metadata contains separate `capture` and `technical` objects. Capture
stores the normalized ISO timestamp, source tag, timezone offset when known, and
whether filesystem mtime was used. Image technical data includes dimensions,
orientation, camera/lens/exposure data and optional GPS. Video data includes
container, duration, dimensions, frame rate, codec, bitrate, rotation, and audio
stream facts. Missing source fields remain null and are never inferred.
