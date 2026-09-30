# Development

## Environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Install ExifTool and FFmpeg (which includes ffprobe) separately and make their
executables available on `PATH`.

## Tests

```powershell
pytest
pytest -m integration
pytest -m external
```

The default suite excludes integration and external tests. Run the nearest unit
test first, relevant integration tests next, and external tests only for changes
that touch real tool integration or before completing M1.

Never commit `.venv`, real user media, local configuration, credentials, or a
runtime workspace.

