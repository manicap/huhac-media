# Data model

The core model distinguishes a stable source path, a version of the content
observed at that path, and an asset identified by SHA-256. A single asset can be
referenced by multiple source versions. Consumers process assets, not source
paths: duplicates and renames therefore do not repeat analysis for unchanged
content, while changed bytes produce a different asset identity. Runs and
independently versioned ingest stages record resumable producer state.

## Public projection

`metadata/catalog.json` is the public projection of this model. It contains one
entry per asset, regardless of source count, together with all source-version
references and their `active`, `superseded`, or `absent` status. An asset is
`available` when at least one source reference is active in the latest published
catalog; otherwise it is retained as `unavailable` for history and existing
derived artifacts.

Each catalog entry points to its normalized asset metadata document and, when
one exists, its image preview. Videos legitimately have a null preview. Files
that scan as unsupported never receive an asset ID and do not appear in the
catalog.

## Internal SQLite tables

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
config_fingerprint)`, so completed ingest work is reused only when its recipe
matches. Table names, columns, migrations, and SQLite itself are private ingest
implementation details, not a compatibility surface for consumers.

Portable source and asset sidecars are separate from this transactional state.
Only the artifacts explicitly named by the workspace contract are consumer API;
source sidecars remain producer-owned supporting evidence.

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

ExifTool's `FileType` and `MIMEType` replace extension-based candidates when
available. Raw ExifTool and ffprobe documents are stored by asset under
`metadata/raw/<shard>/`; normalized asset documents and source-version documents
are separate. Neither source identity nor asset identity depends on an absolute
path or filename.
