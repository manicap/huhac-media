# Session Grouper v1

Session Grouper is an independent consumer of the Media Ingest public workspace
contract. It groups available image and video assets into probable temporal
blocks. A session is not an event: the tool does not infer a venue, performer,
event type, people, content, or any Huháč-specific meaning.

## Responsibility boundary

Session Grouper reads only:

- `workspace.json`;
- the referenced `metadata/catalog.json`;
- each referenced public asset metadata document.

It does not import Media Ingest Python packages, read
`state/catalog.sqlite3`, use ingest `asset_stages`, modify ingest metadata, or
open original media. All writes stay below `analysis/session-grouper/`.

Workspace contract major version 1 is required. Missing or incompatible
versions, mismatched workspace IDs, unsafe public paths, and malformed catalog
structure are rejected rather than guessed.

## Timestamp provenance and confidence

The normalized asset `capture` object is preserved in output, including its
timestamp, source tag, timezone offset, and filesystem-fallback flag. V1 maps it
to four confidence levels:

- `strong`: `EXIF:DateTimeOriginal`, `QuickTime:CreateDate`, or
  `ffprobe:format.tags.creation_time`;
- `medium`: another parseable, non-filesystem capture/create source;
- `low`: `filesystem:mtime` or `filesystem_fallback: true`;
- `unusable`: absent, malformed, or outside the configured 1990–2100 range.

Strong and medium timestamps are session anchors. Low-confidence filesystem
timestamps do not create sessions. By default they remain explicitly
unassigned. With `--assign-filesystem-fallback`, a low-confidence asset is
attached only when it is within the configured tolerance of exactly one
trusted session. Attachment uses the original trusted interval, so fallback
assets cannot form a chain that absorbs increasingly distant files.

Unavailable assets and assets without usable time are also emitted under
`unassigned`, with an explicit reason. The tool never assigns an asset merely
to make every input belong somewhere.

## V1 grouping algorithm

1. Read one observation per unique asset from the public asset catalog.
2. Parse normalized capture metadata and classify timestamp confidence.
3. Select available assets with strong or medium timestamps as anchors.
4. Sort anchors by local wall-clock timestamp and then `asset_id`. Device and
   source path are deliberately not grouping boundaries.
5. Define an operational day as `timestamp - rollover_hour`, with a default
   rollover at 06:00.
6. Continue the current session when the next anchor has the same operational
   day and the gap from the previous anchor is at most eight hours.
7. Otherwise start a new session, recording whether the boundary was an
   operational-day change or a gap larger than the configured maximum.
8. Optionally attach uniquely nearby filesystem-fallback assets.
9. Sort all assigned assets chronologically, using `asset_id` as the stable tie
   breaker.

The shifted operational day means midnight is not a boundary. For example,
19:30, 23:58, 00:31, and 01:24 share an operational day. A five-hour gap from
18:00 preparation to 23:00 is accepted, while the following evening is a new
operational day. An over-eight-hour gap still splits media within one
operational day, avoiding unconditional grouping of a full 24-hour window.

Timestamps are compared as recorded local wall-clock values. Timezone offset is
retained as provenance but v1 does not estimate per-device clock corrections.
This is intentionally transparent: small camera clock differences affect order
but device identity never forces a split. Sophisticated cross-device clock
alignment is deferred to a later version.

## CLI

```text
session-grouper analyze --workspace WORKSPACE [--dry-run] [--json]
  [--rollover-hour 6]
  [--max-gap-hours 8]
  [--assign-filesystem-fallback]
  [--fallback-attach-minutes 30]
```

The command is non-interactive. Human output reports session, assigned, and
unassigned counts plus the deterministic result path. `--json` prints the same
summary as one JSON object for automation. `--dry-run` reads and computes but
does not create `analysis/` or any result file.

Exit codes:

- `0`: analysis succeeded, was reused, or dry-run succeeded;
- `2`: invalid configuration or incompatible/malformed public contract;
- `3`: output or operating-system failure.

## Output namespace and idempotence

The aggregate result is stored atomically at:

```text
analysis/session-grouper/session-grouper-v1/
  <configuration-fingerprint>/<logical-input-fingerprint>.json
```

Both fingerprints are lowercase SHA-256 values over canonical JSON. The
configuration fingerprint covers every v1 heuristic option. The logical input
fingerprint covers workspace identity, asset identity/type/availability,
metadata location, timestamp value, provenance, confidence, and timestamp
issues. Run IDs and catalog generation timestamps do not create false changes
when the logical inputs are identical.

An existing successful file at the exact deterministic path is validated and
reused without changing its bytes or mtime. A different heuristic configuration
or logical input receives a different path. New results use fsync plus atomic
replace; partially written JSON is never published.

## Output contract

The top-level envelope is:

```json
{
  "result_schema_version": 1,
  "workspace_contract_version": 1,
  "workspace_id": "uuid",
  "processor": {
    "name": "session-grouper",
    "version": "session-grouper-v1"
  },
  "model": null,
  "configuration": {},
  "configuration_fingerprint": "sha256 hex",
  "input": {
    "asset_catalog": "metadata/catalog.json",
    "catalog_generated_at": "timestamp",
    "catalog_run_id": "run id",
    "logical_fingerprint": "sha256 hex",
    "asset_count": 10
  },
  "created_at": "ISO-8601 UTC timestamp",
  "status": "success",
  "error": null,
  "result": {
    "sessions": [],
    "unassigned": [],
    "summary": {}
  }
}
```

Each session contains:

- deterministic `session_id`;
- local-wall-clock `start` and `end`;
- `operational_day` and `boundary_reason`;
- overall confidence, defined as the lowest timestamp confidence among its
  assigned assets;
- `asset_count` and media-type counts;
- chronologically ordered asset entries with asset identity, media type,
  captured time, complete timestamp provenance, assignment confidence, and
  assignment reason.

`unassigned` entries contain asset identity, media type, available timestamp
provenance when present, and a reason such as `filesystem_fallback_disabled`,
`missing_capture_timestamp`, `suspicious_capture_timestamp`,
`asset_unavailable`, or `ambiguous_filesystem_fallback`.

Downstream consumers read this JSON without importing Session Grouper Python
internals. A changed result schema or grouping semantics requires a new result
schema and/or processor version rather than silently changing v1 meaning.

## Testing

```powershell
pytest tests/session_grouper
pytest -m integration
```

Synthetic fixtures cover evening sessions, midnight rollover, the following
evening, image/video mixtures, source-independent grouping, long gaps,
filesystem fallback, missing time, deterministic ordering, idempotent reuse,
configuration fingerprints, incompatible contracts, and the prohibition on
ingest/SQLite dependencies.

## Known limits and v2 candidates

- No automatic camera clock synchronization or timezone reconciliation.
- No density-, device-, GPS-, visual-, audio-, or similarity-based evidence.
- The operational-day and gap thresholds are global rather than learned.
- Low-confidence assets outside one unambiguous nearby trusted session remain
  unassigned.
- Session IDs change when ordered membership or capture timestamps change.
- No event identification, naming, orchestration, GUI, or processor registry.
