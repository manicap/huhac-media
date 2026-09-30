# Huháč Media Pipeline

Huháč Media Pipeline is a local Windows-oriented tool for read-only discovery,
cataloguing, metadata extraction, and preprocessing of photo and video archives.

Milestone M1 is under active development. AI analysis, OCR, face recognition,
similarity search, video scene detection, and audio analysis are planned work and
are not part of M1.

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

See [architecture](docs/architecture.md), [data model](docs/data-model.md), and
[development](docs/development.md) for project internals.
