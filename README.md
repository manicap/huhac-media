# huhac-media

`huhac-media` is a local, Windows-oriented media workspace pipeline. The stable
checkpoint currently contains two implemented components:

- **Media Ingest Tool v1** scans immutable originals, tracks source history,
  deduplicates content by SHA-256, extracts metadata, creates image previews,
  and publishes a versioned JSON workspace contract.
- **Session Grouper v1** independently consumes that public contract and groups
  available assets into probable time-continuity sessions. A session is not an
  identified event.

Vision, Faces, OCR, Similarity, Quality, Audio, event interpretation, a Media
Collector, and orchestration are future work and are not implemented.

## Quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install ExifTool and FFmpeg/ffprobe separately and make them available on
`PATH`, or configure their executable paths in TOML.

Preview an ingest without writing anything:

```powershell
huhac-media ingest --input 'D:\Media' --dry-run
```

Run ingest and then Session Grouper:

```powershell
huhac-media ingest --input 'D:\Media' --yes
session-grouper analyze --workspace 'D:\Media\_processing'
```

Both commands also work as Python modules:

```powershell
python -m huhac_media ingest --input 'D:\Media' --dry-run
python -m session_grouper analyze --workspace 'D:\Media\_processing' --dry-run
```

## Documentation

- [Media Ingest Tool v1](docs/media-ingest.md): behavior, CLI, metadata,
  previews, recovery, dependencies, and limitations.
- [Session Grouper v1](docs/session-grouper.md): timestamp confidence,
  grouping algorithm, deterministic output, CLI, and limitations.
- [Media workspace contract](docs/workspace-contract.md): the public JSON
  compatibility boundary and processor ownership rules.
- [System overview](docs/system-overview.md): implemented components, future
  pipeline, architectural decisions, handoff, and milestones.
- [Architecture](docs/architecture.md) and [data model](docs/data-model.md):
  internal design rationale.
- [Development](docs/development.md): environment, test suites, and contribution
  safeguards.

SQLite, logs, run state, locks, and ingest Python APIs are internal. Consumers
start at `workspace.json`, follow `metadata/catalog.json`, and write only under
their own `analysis/<processor>/` namespace.

## Project status

Media Ingest Tool v1 and Session Grouper v1 are implemented, tested, and
accepted on the current real workspace. Development continues from `main` as
the stable integrated state; future processors remain out of scope for this
checkpoint.
