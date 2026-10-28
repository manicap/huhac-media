# huhac-media

> **Implemented 2026-10-26:** Normalizer v1 / N3 read-only integration in Media
> Desk, including explicit snapshot fingerprints, unified detail, exact facets,
> completeness diagnostics, and preserved user-data ownership. Enrichment and
> Quality Processor remain planned.

`huhac-media` is a local, Windows-oriented media workspace pipeline. The stable
checkpoint currently contains seven implemented components:

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
- **Metadata Normalizer v1 / N1–N2** deterministically projects public ingest
  facts plus explicitly selected Session, Keyframes, Vision, Faces, and
  anonymous-cluster results into provenance-rich immutable snapshots.
- **Media Desk** provides the read-only gallery, Normalizer N3 unified detail
  and exact facets, local workspace/originals
  configuration, S2b orchestration of producer-owned empty archive setup, and
  a local working library with stable names, events and lazy in-card playback.

OCR, cross-asset Similarity, Quality, Audio, enrichment, a Media Collector,
and orchestration are future work and are not implemented.

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

Plan and publish a basic normalized metadata snapshot:

```powershell
normalizer plan --workspace 'D:\Media\_processing'
normalizer analyze --workspace 'D:\Media\_processing'
normalizer status --workspace 'D:\Media\_processing'
```

Select N2 upstream results explicitly when required:

```powershell
normalizer analyze --workspace 'D:\Media\_processing' `
  --keyframes-fingerprint <sha256> `
  --vision-fingerprint <sha256> --faces-fingerprint <sha256>
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

### Windows launcher for Media Desk

The repository includes **HUHÁČ Launcher v0.2**, a small Tkinter window for
managing isolated workspace profiles, selecting an existing validated Normalizer
snapshot, choosing a per-profile port, and starting or stopping Media Desk without
PowerShell. After the project `.venv` is prepared, double-click
`HUHAC-Launcher.cmd`. It never starts ingest or analysis processors. See
[docs/launcher.md](docs/launcher.md) for operation and safety details. Personal
profiles stay outside the checkout in `%LOCALAPPDATA%\HUHAC\Launcher`; the
versioned `config/launcher.example.toml` is used only to seed a missing config.

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
- [Metadata Normalizer v1](docs/normalizer.md): N1 source facts plus N2 upstream
  projections, exact facets, provenance, completeness, snapshots, and CLI.
- [ADR-N1](docs/ADR-N1-normalizer-contract.md): accepted ownership,
  fingerprint, publication, and forward-compatibility decisions.
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
- [HUHÁČ Launcher v0.2](docs/launcher.md): Windows profile/snapshot/port GUI for
  one owned, loopback-only Media Desk child process.

SQLite, logs, run state, locks, and ingest Python APIs are internal. Consumers
start at `workspace.json`, follow `metadata/catalog.json`, and write only under
their own `analysis/<processor>/` namespace.

### Experimental HUHÁČ Studio prototype

An isolated React/TypeScript orchestrator is available under [`studio/`](studio/)
on the Studio development branch. Its Projects and Media Library modules use the
Project Core v1 loopback API; synthetic data remains only in frontend tests.
Project Core lives under `src/huhac_studio` and writes only its isolated
host-local SQLite. It does not replace or modify Media Desk, Launcher profiles,
workspaces, media files, or processor outputs. See
[docs/studio/README.md](docs/studio/README.md).

## Clean runtime bundle

Create a portable runtime ZIP without tests, development dependencies, Git
metadata, documentation sources, caches, virtual environments, local media, or
generated output:

```powershell
.\scripts\build-runtime-bundle.cmd
```

The result is written to `dist/huhac-media-runtime-<version>.zip`. It contains
one validated Python wheel, `config.example.toml`, the third-party model notice,
an installation guide, and a SHA-256 manifest. The wheel includes all runtime
Python packages and the Media Desk HTML/CSS/JavaScript assets. Building fails if
development-only paths or Python bytecode enter the wheel or outer ZIP.

## Project status

Media Ingest Tool v1, Session Grouper v1, Video Keyframe Extractor v1, Vision
Processor v1, Faces Processor v1, Metadata Normalizer v1/N1–N2, and Media Desk
through Normalizer N3 are implemented. The remaining future processors and
storage stages stay out of scope.
