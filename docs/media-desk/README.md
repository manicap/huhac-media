# Media Desk M1

Media Desk M1 is a local, read-only web gallery for one existing Huháč media
workspace. It starts at `workspace.json`, requires public workspace contract
version 1, follows `metadata/catalog.json`, and never reads ingest SQLite.

M1 shows paginated image/video cards, public metadata, source names, capture
time, technical facts, probable time-continuity sessions, completed Vision
descriptions, and anonymous Faces results. Image cards use published ingest
previews. Video cards use one complete compatible Video Keyframe v1 result.

## Install

Python 3.11 or newer is required. Media Desk has its own optional dependency
group, so installing it does not add web dependencies to the five processors.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[media-desk]"
```

### Linux shell

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[media-desk]'
```

## Start

The default bind is loopback-only (`127.0.0.1`).

Windows:

```powershell
media-desk --workspace 'D:\Media\_processing'
```

Linux:

```bash
media-desk --workspace '/mnt/media/_processing'
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). The equivalent
module command is `python -m media_desk --workspace PATH`.

Configuration precedence is CLI, environment, TOML, then defaults. Supported
environment variables are `MEDIA_DESK_WORKSPACE`, `MEDIA_DESK_HOST`,
`MEDIA_DESK_PORT`, and `MEDIA_DESK_KEYFRAME_FINGERPRINT`. A TOML example is in
[`media-desk.example.toml`](media-desk.example.toml):

```powershell
media-desk --config .\docs\media-desk\media-desk.example.toml
```

When several valid Video Keyframe v1 configurations exist, Media Desk does not
pick one arbitrarily. Restart with the exact fingerprint:

```powershell
media-desk --workspace 'D:\Media\_processing' `
  --keyframe-fingerprint '<64 lowercase hex characters>'
```

## Synthetic demo

The demo contains generated color cards only—no real media or model is needed.

Windows:

```powershell
python -m media_desk.demo .\.media-desk-demo
media-desk --workspace .\.media-desk-demo
```

Linux:

```bash
python -m media_desk.demo ./.media-desk-demo
media-desk --workspace ./.media-desk-demo
```

The demo deliberately marks originals offline while keeping previews and
metadata browsable.

## HTTP surface

- `GET /` — gallery with `media_type`, `q`, `page`, and `page_size` filters;
- `GET /assets/{sha256}` — asset detail;
- `GET /api/assets` and `GET /api/assets/{sha256}` — public metadata views;
- `GET /artifacts/{opaque-token}` — only artifacts registered from validated
  public paths and authorized active originals;
- `GET /health` — workspace readiness.

Original video responses support one HTTP byte range per request. The browser
therefore does not need to load a complete video before seeking. Preview and
keyframe images use lazy loading in the gallery.

## Security and read-only behavior

Media Desk holds an in-memory snapshot and performs no workspace writes. It
does not import processor internals, open `state/catalog.sqlite3`, create cache
files in the workspace, or modify public JSON, previews, analysis, or
originals. Artifact URLs contain server-created opaque tokens rather than file
paths. Workspace-relative paths reject traversal and resolved symlink escapes;
only public preview/keyframe namespaces and validated active originals can be
served.

Keep the default loopback bind. Binding to a LAN address is an explicit
operator choice and M1 has no authentication or TLS.

## Tests

Install test dependencies and run the focused suite:

```powershell
python -m pip install -e ".[media-desk-dev]"
pytest tests/media_desk
```

The tests use synthetic bytes and JSON only. They cover valid and invalid
contracts, missing artifacts, offline originals, ambiguous keyframe
fingerprints, all five existing component outputs, filtering, pagination,
range responses, traversal attempts, safe browser errors, and preservation of
every workspace file's content, size, and modification time.

## Known M1 limitations

- One workspace per server process; no multi-workspace library.
- Snapshot refresh requires a restart after processors publish new output.
- No authentication; loopback is the safe default and LAN exposure is not an
  M1 deployment mode.
- No import, upload, processing orchestration, favorites, ratings, collections,
  storage remapping, relocation, or editor integration.
- Multiple analysis configurations are displayed with their fingerprints;
  video thumbnail selection requires an explicit keyframe fingerprint.
- Original availability is checked on the backend host. A browser client does
  not receive or reinterpret host filesystem paths.
- Session relationships are labelled as probable time continuity, never as
  identified events. Faces clusters remain anonymous similarity groups.

The governing scope and later milestones are recorded in
[`CONTRACT.md`](CONTRACT.md). M2–M5 are not implemented.
