# huhac-media

`huhac-media` is a local, Windows-oriented media workspace pipeline. The stable
checkpoint currently contains six implemented components:

- **Media Ingest Tool v1** scans immutable originals, tracks source history,
  deduplicates content by SHA-256, extracts metadata, creates image previews,
  and publishes a versioned JSON workspace contract.
- **Session Grouper v1** independently consumes that public contract and groups
  available assets into probable time-continuity sessions. A session is not an
  identified event.
- **Video Keyframe Extractor v1** independently samples available video assets,
  removes within-video visual redundancy with OpenCLIP, and publishes
  standardized representative JPEG frames.
- **Vision Processor v1** analyzes public image previews and persistent video
  keyframes through a configurable Ollama vision model, preserving raw model
  output and a strictly validated canonical result.
- **Faces Processor v1** detects and embeds faces in those same public visual
  inputs, then independently clusters embeddings into anonymous groups.
- **Media Desk** provides the read-only gallery, local workspace/originals
  configuration, and S2b orchestration of producer-owned empty archive setup.

The semantic Normalizer, OCR, cross-asset Similarity, Quality, Audio,
event interpretation, Media Connector acquisition beyond MC1, and orchestration are future work and
are not implemented.

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

Initialize a new empty archive without scanning or importing media:

```powershell
huhac-media init --storage 'D:\HUHAC\Media' --workspace 'C:\HUHAC\Workspace' --preflight --json
# Confirm with the operation_id returned by preflight:
huhac-media init --storage 'D:\HUHAC\Media' --workspace 'C:\HUHAC\Workspace' --operation-id '<UUID>' --yes --json
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
- [Video Keyframe Extractor v1](docs/video-keyframes.md): timestamp sampling,
  standardized frames, OpenCLIP coverage, per-asset output, and CLI.
- [Vision Processor v1](docs/vision.md): preview/keyframe inputs, Ollama,
  canonical schema, repair, provenance, and reuse.
- [Faces Processor v1](docs/faces.md): YuNet detection, OpenVINO embeddings,
  deterministic complete-link clustering, provenance, and reuse.
- [Third-party models](THIRD_PARTY_MODELS.md): official weight sources and
  licenses for optional model-backed processors.
- [Media workspace contract](docs/workspace-contract.md): the public JSON
  compatibility boundary and processor ownership rules.
- [System overview](docs/system-overview.md): implemented components, future
  pipeline, architectural decisions, handoff, and milestones.
- [Architecture](docs/architecture.md) and [data model](docs/data-model.md):
  internal design rationale.
- [Development](docs/development.md): environment, test suites, and contribution
  safeguards.
- [Media Desk M1–M1.3 + S2a–S2b](docs/media-desk/README.md): read-only local
  gallery, per-user workspace setup, host-local originals mapping, safe empty
  archive initialization, architecture, security, and limitations.

SQLite, logs, run state, locks, and ingest Python APIs are internal. Consumers
start at `workspace.json`, follow `metadata/catalog.json`, and write only under
their own `analysis/<processor>/` namespace.

## Project status

Media Ingest Tool v1, Session Grouper v1, Video Keyframe Extractor v1, Vision
Processor v1, Faces Processor v1, and Media Desk through S2b are implemented.
The remaining future processors and storage stages stay out of scope.
