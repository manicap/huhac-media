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

The eventual CLI entry point is `huhac-media`. Current command availability is
reported by `huhac-media --help`.

See [architecture](docs/architecture.md), [data model](docs/data-model.md), and
[development](docs/development.md) for project internals.

