# Media Desk M1.1

Media Desk M1.1 is a local, read-only web gallery for one existing Huháč media
workspace. It starts at `workspace.json`, requires public workspace contract
version 1, follows `metadata/catalog.json`, and never reads ingest SQLite.

M1.1 adds a compact overview, a virtualized image/video library, direct time
navigation, a year/month/day calendar, and a timeline of automatic Session
Grouper time relations. It retains completed Vision/Faces results, anonymous
clusters, explicit keyframe selection, offline originals, and HTTP Range video
playback from M1. A browser request never opens ingest SQLite, runs a processor,
decodes a video, creates a thumbnail, or changes the workspace.

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

## Navigation and HTTP surface

- `GET /` — compact overview;
- `GET /library` — virtualized library with type/search/sort/date filters;
- `GET /calendar` — year/month/day navigation over trustworthy capture dates;
- `GET /relations` — Session Grouper timeline, explicitly not an Event list;
- `GET /assets/{sha256}` — asset detail;
- `GET /api/assets?limit=50&cursor=...` — snapshot-bound batches; legacy
  `page`/`page_size` remains compatible;
- `GET /api/index` — filtered counts and available time segments;
- `GET /api/locate` — direct lookup by asset or year/month/day;
- `GET /api/calendar` and `GET /api/assets/{sha256}` — calendar/detail data;
- `GET /artifacts/{opaque-token}` — only artifacts registered from validated
  public paths and authorized active originals;
- `GET /health` — workspace readiness.

Original video responses support one HTTP byte range per request. The browser
therefore does not need to load a complete video before seeking. Preview and
keyframe images use lazy loading, identity ETags, and immutable browser caching.

The batch response contains `items`, `next_cursor`, `prev_cursor`,
`start_index`, `total_count`, and `snapshot_id`. Cursors bind the snapshot,
filters, and sort; incompatible reuse returns HTTP 409. Batch size defaults to
50 and is constrained to 10–100. The library keeps visible rows plus overscan
in the DOM and at most 12 metadata batches in its LRU cache. Anchor restoration
uses `asset_id` plus pixel offset and `/api/locate`, not preceding downloads.

## Calendar time policy

Capture timestamps retain the wall-clock date written by the source. An
explicit offset is displayed but never converted to the server timezone. A
timestamp without an offset remains timezone-naive. Filesystem mtime fallbacks
have low confidence and, together with missing/invalid timestamps, appear under
**Nezařazeno podle data**. Session years use published `operational_day`; a
session crossing midnight is never split into fake events.

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

## Known M1.1 limitations

- One workspace per server process; no multi-workspace library.
- Snapshot refresh requires a restart after processors publish new output; an
  open mismatched view receives an explicit refresh warning.
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
- Multiple valid Session Grouper results produce an ambiguous state instead of
  being guessed or merged.
- Library virtualization requires JavaScript. The API and details remain
  available without it, but thousands of fallback cards are not rendered.

The governing scope and later milestones are recorded in
[`CONTRACT.md`](CONTRACT.md). M2–M5 are not implemented.
