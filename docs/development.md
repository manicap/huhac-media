# Development

## Environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install ExifTool and FFmpeg (which includes ffprobe) separately and make their
executables available on `PATH`.

The Python package lives under `src/huhac_media`. Unit, integration, and
external tests are kept in matching directories under `tests`. Runtime state is
always written to the selected workspace, never into package directories.

## Tests

```powershell
pytest
pytest -m integration
pytest -m external
pytest tests/session_grouper
pytest tests/video_keyframes
```

The default suite excludes integration and external tests. Run the nearest unit
test first, relevant integration tests next, and external tests only for changes
that touch real tool integration or before completing M1.

Never commit `.venv`, real user media, local configuration, credentials, or a
runtime workspace.

Session Grouper is a separate package under `src/session_grouper`. Its tests use
only synthetic public-contract fixtures. Production code in this package must
not import `huhac_media`, open ingest SQLite, or write outside its own
`analysis/session-grouper/` namespace.

Video Keyframe Extractor is a separate package under `src/video_keyframes`.
Production code must not import `huhac_media`, read ingest SQLite, or write
outside `analysis/video-keyframes/`. Unit and integration tests use fake
ffprobe, FFmpeg, and embedding adapters; external tests must not download the
OpenCLIP model.

Before each logical commit, run the nearest tests, the relevant wider suite,
`git diff`, `git diff --cached`, and `git status`. Commit only source,
documentation, and synthetic fixtures; push only tested commits to the current
branch without force operations.
