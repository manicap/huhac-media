# Huháč Media Ingest

Huháč Media Ingest is a local Windows-oriented producer of standardized media
workspaces. It performs read-only discovery, cataloguing, metadata extraction,
and deterministic preprocessing of photo and video archives.

Its responsibility ends at a versioned workspace containing content-addressed
assets, provenance, normalized metadata, and image previews. AI analysis, OCR,
face recognition, similarity search, video scene detection, audio analysis, and
domain interpretation are independent consumers and are not part of this tool.

## Requirements

- Python 3.11 or newer
- ExifTool
- ffprobe (for video)
- FFmpeg when a planned preview needs its decoder

## Development installation

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The CLI can perform a read-only preflight now:

```powershell
huhac-media ingest --input 'D:\Huhac\media' --dry-run
huhac-media ingest --config .\huhac.toml --dry-run
```

Dry-run recursively discovers media, calculates content hashes, reads an
existing catalog in read-only mode, and reports known, new, changed, duplicate,
and previously failed assets. It never creates WORK or writes a log.

M1 image previews use a configurable maximum dimension (768 pixels by default),
apply EXIF orientation, preserve aspect ratio, and never upscale unless
explicitly configured. Transparent pixels are composited on black by default.

Run an unattended ingest with:

```powershell
huhac-media ingest --input 'D:\Huhac\media' --non-interactive
```

Without `--yes`/`--non-interactive`, the CLI asks for confirmation after the
read-only preflight and before creating or changing WORK. Existing workspaces
are reused and successful metadata/preview stages are skipped.

## Configuration

Copy `config.example.toml` and adjust `input`, optional `work`, interaction
policy, changed-source policy, image preview settings, and tool executable
names. Relative paths are resolved from the config file directory. Explicit CLI
values override config values. Do not commit machine-specific local configs.

Use `--new-workspace` to explicitly allocate `_processing_001`, `_002`, and so
on. It overrides a WORK path from config. Use `--no-warn-existing-workdir` to
suppress the workspace reuse notice.

## Exit codes

- `0`: success, no-op, or successful dry-run
- `1`: completed with one or more media failures
- `2`: CLI usage or configuration error
- `3`: fatal infrastructure error
- `4`: interactive cancellation
- `130`: interrupted with Ctrl+C

Every started ingest writes a machine-readable `runs/<timestamp>_<run-id>/report.json`,
an effective configuration snapshot, and a detailed UTF-8 log under `logs/`.

After an ingest, external processors discover assets through the public
`workspace.json` -> `metadata/catalog.json` contract. They must not read or
write ingest's SQLite database. Processor-owned results belong under
`analysis/<processor>/`; see the workspace contract for the required path and
provenance envelope.

See [architecture](docs/architecture.md), [data model](docs/data-model.md), and
[workspace contract](docs/workspace-contract.md). The
[development guide](docs/development.md) covers project internals.

## Independent consumers

The repository also contains Session Grouper v1, an independent consumer of the
public workspace contract. It does not import ingest services or read ingest
SQLite. Run it after a contract-aware ingest with:

```powershell
session-grouper analyze --workspace 'D:\Huhac\media\_processing'
session-grouper analyze --workspace 'D:\Huhac\media\_processing' --dry-run
```

Its temporal heuristic, output schema, confidence model, and limitations are
documented in [Session Grouper](docs/session-grouper.md).
