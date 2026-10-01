# Media Ingest Tool v1

Media Ingest is a standalone local producer of standardized media workspaces.
It discovers media, identifies unique binary content, extracts metadata, creates
deterministic image previews, and publishes a versioned JSON contract for
independent consumers.

It does not know about Huháč, events, bands, people, social scoring, or future
Vision, Faces, OCR, Quality, Similarity, and Audio processing. Its responsibility
ends at the workspace boundary.

## Identity and history

The data model deliberately separates three concepts:

```text
SOURCE (a relative path under INPUT)
  -> SOURCE VERSION (the bytes observed at that path at a point in history)
    -> ASSET (unique binary content identified by SHA-256)
```

An asset ID is `sha256:<64 lowercase hexadecimal characters>`. Multiple source
versions can reference the same asset, so identical copies are processed once.

- An exact duplicate is another observed source reference to the same asset.
- A rename or move creates new source provenance but preserves asset identity.
- Changed bytes at an existing source path create or reactivate a different
  source version and asset; the former version becomes `superseded`.
- A formerly current source not seen after a complete scan becomes `absent`.
- Historical assets and source versions are retained rather than deleted.

The `changed_source_policy` is `reprocess` by default. Setting it to `error`
records the changed identity and an error but does not process that changed
source in the run.

## Scan and preflight

INPUT is scanned recursively in deterministic name order. Directory and file
symlinks are not followed. If WORK is inside INPUT, its resolved subtree is
excluded. Originals are opened only for detection, hashing, and metadata or
preview decoding; they are never modified.

Binary signatures take precedence when recognized. Candidate extensions are:

- images: JPEG, PNG, WebP, HEIC/HEIF, TIFF, CR2, CR3, NEF, ARW, and DNG;
- video: MP4, MOV, MKV, AVI, MTS, and M2TS.

Other files are reported as unsupported and do not receive asset IDs. ExifTool
may refine the initially detected format and MIME type during metadata
extraction. Hashing reads the complete file and compares its size and mtime
before and after; a change during hashing is reported as `UNSTABLE_SOURCE`.

The same planner drives dry-run and real ingest. `known`, `new`, and `changed`
are exclusive source classifications. `exact duplicate` and `previous failure`
are additional flags and can overlap them.

## Metadata

ExifTool runs as:

```text
exiftool -j -G1 -a -s -n <source>
```

It supplies grouped raw metadata for images and video. ffprobe additionally
supplies video format and stream data. Absolute source filenames and directories
are removed before raw JSON is stored. Normalized metadata and raw tool output
are written separately, preserving provenance without exposing absolute source
paths in raw sidecars.

The normalized asset document contains:

- `detected`: tool-refined format and MIME type;
- `capture`: normalized timestamp, source, timezone offset, and the
  `filesystem_fallback` marker;
- `technical`: media-specific dimensions, camera/exposure or stream facts;
- `raw_metadata`: relative references to opaque ExifTool/ffprobe JSON;
- `stages`: published ingest-stage recipe, status, output, and error facts.

### Capture-time precedence

For image metadata, the first valid value wins in this order:

1. `Composite:SubSecDateTimeOriginal`;
2. `ExifIFD:DateTimeOriginal`, combined with
   `ExifIFD:OffsetTimeOriginal` and `ExifIFD:SubSecTimeOriginal`;
3. `Composite:SubSecCreateDate`;
4. `ExifIFD:CreateDate`, combined with the corresponding digitized offset and
   subsecond fields.

Legacy `EXIF:*` aliases are accepted as compatibility fallbacks. Standard EXIF
and Composite values are preferred over vendor-specific tags. Valid fractional
seconds and offsets are retained.

For video, candidates are QuickTime creation fields followed by ffprobe
`format.tags.creation_time`. All valid candidates with an explicit timezone are
considered before any unzoned candidate. When an explicit UTC instant and a
separate trustworthy timezone/UTC-offset field are available, the instant is
represented in that fixed local offset and both sources are recorded, for
example:

```text
ffprobe:format.tags.creation_time; timezone=Keys:AndroidTimeZone
```

An unzoned timestamp remains unzoned when no trustworthy offset exists. Only
when no valid capture/create timestamp exists does normalization use filesystem
mtime and publish `source: filesystem:mtime` with
`filesystem_fallback: true`.

The current metadata stage recipe is `metadata-v2`. Stage recipes are versioned
so a normalization change can recompute metadata without changing asset
identity or rerunning unrelated successful stages. Older recipe rows may remain
in internal history; the current public asset document reports the active
result.

## Image previews

M1 generates deterministic, non-progressive JPEG previews for image assets.
Defaults are a maximum long side of 768 pixels, quality 90, no upscale, retained
aspect ratio, EXIF orientation applied, and transparent pixels composited on
black. The background can be configured as black or white.

Pillow is the primary decoder. If it cannot decode an image and FFmpeg is
available, FFmpeg is used as a fallback. HEIC/HEIF takes a two-step path: decode
the first visual frame to a temporary PNG, then scale and encode that decoded
frame. This avoids combining incompatible simple and complex filters for tiled
HEIC streams. The generated JPEG is decoded for validation before an atomic
replace. Video previews and keyframes are not part of v1.

Preview reuse is keyed by asset identity, `image-preview-v1`, and a fingerprint
of all image settings. Changing a relevant setting produces a new recipe; an
unchanged successful preview is skipped when its output still exists.

## Resume, failure isolation, and atomicity

Metadata and preview stages have independent `pending`, `processing`,
`success`, and `failed` state. A failed stage does not stop unrelated assets.
The next run retries failures and work left in `processing`; matching successful
stages with existing artifacts are reused.

Actual ingest holds a non-blocking workspace lock. JSON artifacts, reports, the
catalog, metadata, and previews are published by atomic replacement. A catalog
reader therefore sees the previous complete catalog or the new complete one,
not a partially written file.

Every actual run creates a report and effective configuration snapshot under
`runs/` plus a UTF-8 log under `logs/`. Normal run status is `success` or
`partial`; fatal and interrupted runs are recorded when possible. A later run
recovers stale `running` state as interrupted.

## Public workspace contract

The public entry point is `workspace.json`. A consumer validates
`workspace_contract_version`, follows `asset_catalog`, and enumerates the
`assets` array in `metadata/catalog.json`. It never needs SQLite.

The catalog provides one record per unique asset, including identity, media
facts, availability, source-version provenance, and relative locations of
normalized metadata and an optional preview. `preview_location` is non-null
only when a validated JPEG exists; null is normal for video or a failed image
preview. `source_root` plus an active source `relative_path` identifies an
original when a consumer genuinely needs it.

The exact required fields, versioning policy, path rules, and processor output
conventions are defined in [workspace-contract.md](workspace-contract.md).

### Public versus internal

Public producer artifacts are:

- `workspace.json`;
- `metadata/catalog.json`;
- normalized asset documents referenced by `metadata_location`;
- opaque raw metadata documents referenced by `raw_metadata`;
- validated JPEGs referenced by `preview_location`.

SQLite, its tables (including `asset_stages`), source-sidecar lifecycle, run
reports, logs, locks, temporary files, migrations, and Python APIs are internal.
Consumers must not use them as compatibility surfaces or modify producer-owned
files.

## Workspace layout

```text
_processing/
|-- workspace.json                         # public entry point
|-- state/
|   `-- catalog.sqlite3                    # internal transactional state
|-- metadata/
|   |-- catalog.json                       # public asset enumeration
|   |-- assets/<sha-prefix>/<sha256>.json  # public normalized metadata
|   |-- raw/<sha-prefix>/...json           # public only when referenced
|   `-- sources/<source-version-id>.json   # internal producer sidecars
|-- previews/images/<sha-prefix>/<sha256>.jpg
|-- analysis/                              # independent processor ownership
|-- runs/<timestamp>_<run-id>/
|   |-- report.json
|   `-- effective-config.json
|-- logs/
|-- tmp/
`-- locks/
```

## Installation and CLI

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Read-only preflight of the default `<INPUT>/_processing` workspace:

```powershell
huhac-media ingest --input 'D:\Media' --dry-run
```

Ingest after interactive confirmation:

```powershell
huhac-media ingest --input 'D:\Media'
```

Non-interactive ingest and explicit workspace:

```powershell
huhac-media ingest --input 'D:\Media' --work 'E:\Workspaces\media' --yes
```

Reuse an existing workspace without the reuse notice:

```powershell
huhac-media ingest --input 'D:\Media' --yes --no-warn-existing-workdir
```

Allocate the next `_processing_001`, `_processing_002`, and so on:

```powershell
huhac-media ingest --input 'D:\Media' --new-workspace --yes
```

Use a TOML configuration file:

```powershell
huhac-media ingest --config .\huhac.toml --dry-run
huhac-media ingest --config .\huhac.toml --yes
```

[`config.example.toml`](../config.example.toml) documents the supported keys:
`input`, optional `work`, `interactive`, `warn_existing_workdir`,
`changed_source_policy`, image preview settings, and the three tool executable
names. Relative paths are resolved from the configuration file directory.
Explicit CLI input/work and interaction flags override their TOML values.
Machine-specific configurations should remain untracked.

Dry-run scans, hashes, and compares with existing read-only state. It does not
create or upgrade a workspace, write logs, reports, SQLite, or artifacts.
Without `--yes`/`--non-interactive`, real ingest asks for confirmation after
preflight and before workspace creation or mutation.

## Dependencies

- Python 3.11 or newer and Pillow are runtime requirements.
- ExifTool is required for an actual ingest containing supported media.
- ffprobe is required for an actual ingest containing video.
- FFmpeg is optional for formats Pillow decodes itself, but preview fallback for
  HEIC/HEIF and supported RAW candidates may fail without it.

Executable names or paths can be configured in `[tools]`. External processes
run without a shell, with timeouts, bounded diagnostics, checked exit codes, and
UTF-8 replacement decoding.

## Exit codes and diagnostics

- `0`: success, no-op, or successful dry-run;
- `1`: completed with one or more media/stage failures, or a dry-run scan error;
- `2`: CLI usage or configuration error;
- `3`: fatal infrastructure or workspace error;
- `4`: interactive cancellation;
- `130`: Ctrl+C interruption.

Preflight reports known, new, changed, duplicate, and previously failed inputs.
Failed stages retain an error code and bounded tool diagnostics and are retried
on a later run. A partial run still publishes all successfully available work
and an atomic catalog.

## Testing

```powershell
pytest                                      # FAST unit tests
pytest -m integration                       # filesystem/SQLite/CLI integration
pytest -m external                          # real ExifTool and FFmpeg
```

External tests are deliberately separate because they require installed native
tools and exercise real command-line behavior rather than fake adapters.

## Known limitations

- No video preview or keyframe extraction.
- No AI, OCR, faces, similarity, quality, or audio analysis.
- No event identification or domain interpretation.
- No cloud/external-source collector.
- Originals remain in place; `source_root` is machine-local.
- No shared orchestrator or processor registry.
