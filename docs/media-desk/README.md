# HUHÁČ Media Desk (M1–M1.3 + S2a)

**Dokumentace synchronizována:** 2026-10-22 na větvi `mediadesk` po implementaci S2a.

## Začni zde — aktuální autoritativní dokumentace

- [STATUS.md](STATUS.md) — co je skutečně implementováno a známé limity;
- [ARCHITECTURE.md](ARCHITECTURE.md) — ownership, data, cesty, DB a bezpečnost;
- [DECISIONS.md](DECISIONS.md) — přijatá rozhodnutí a návrhy čekající na schválení;
- [ROADMAP.md](ROADMAP.md) — pořadí dalších etap a stop-gate;
- [AUDIT_2026-10.md](AUDIT_2026-10.md) — auditní důkazy a gap analýza;
- [SETUP_STORAGE_RFC.md](SETUP_STORAGE_RFC.md) — varianty setup/storage bez implementace.
- [S2A_IMPLEMENTATION_PLAN.md](S2A_IMPLEMENTATION_PLAN.md) — schválený rozsah a
  dokončené ověření přechodného read-only mapování originálů.
- [S2A1_STARTUP_PERFORMANCE.md](S2A1_STARTUP_PERFORMANCE.md) — profil a průběh
  schválené optimalizace startupu a lazy ověřování originálů.
- [S2B_DESIGN.md](S2B_DESIGN.md),
  [S2B_FAILURE_MATRIX.md](S2B_FAILURE_MATRIX.md) a
  [S2B_IMPLEMENTATION_PLAN.md](S2B_IMPLEMENTATION_PLAN.md) — **ACCEPTED / IN
  PROGRESS** ingest-owned inicializace nového archivu.
- [Veřejný workspace kontrakt](../workspace-contract.md) a dokumentace
  [Media Ingest](../media-ingest.md), [Session Grouper](../session-grouper.md),
  [Video Keyframes](../video-keyframes.md), [Vision](../vision.md) a
  [Faces](../faces.md) — závazné hranice existujících producentů a konzumentů.

Historický [CONTRACT.md](CONTRACT.md) zachovává původní zadání M1, ale není
autoritou pro další etapy.

Media Desk is a local, read-only web gallery for one existing Huháč media
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

## Start and first setup

The default bind is loopback-only (`127.0.0.1`).

Windows:

```powershell
media-desk
```

Linux:

```bash
media-desk
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000), open **Nastavení**,
enter the existing directory that contains `workspace.json`, validate it, save,
and restart Media Desk. The equivalent module command is:

```powershell
.\.venv\Scripts\python.exe -m media_desk
```

The saved workspace is loaded automatically on later starts. The profile file
is `%APPDATA%\HUHAC\MediaDesk\config.toml` on Windows and
`${XDG_CONFIG_HOME:-~/.config}/huhac/media-desk/config.toml` on Linux. The
workspace remains read-only; only this application config is written.

### Originály na jiném hostiteli nebo OS (S2a)

Pokud je katalogový `source_root` cesta z jiného hostitele (například Windows
`D:\Archiv`, zatímco Media Desk běží na Linuxu), otevřete **Nastavení → Lokální
mapování zdroje** a zadejte lokální kořen se stejnými relativními soubory.
**Ověřit mapování** provede deterministickou SHA-256 kontrolu nejvýše 16
dostupných assetů. Jde o reprezentativní vzorek, nikoli úplnou kontrolu integrity.
**Uložit mapování** kandidáta znovu ověří a atomicky zapíše jen per-user profil;
mapování se použije po restartu.

Neúspěšná validace poslední platné mapování nezmění. Dočasně nedostupný disk nebo
NAS uložené mapování automaticky nesmaže; workspace, metadata a previews zůstanou
dostupné a mapped originály jsou dočasně offline. Běžný start SHA-256 vzorek
neopakuje. Mapping je přesně vázaný na `workspace_id` a původní text
`source_root`; není přenášen v workspace ani čten z explicitního `--config`.

Katalogová reference originálu se po startu zobrazuje jako **neověřená**. To
neznamená, že je konkrétní soubor online. Jeho aktuální existence, confinement a
symlink bezpečnost se ověří až při GET nebo video Range požadavku. Chybějící či
odpojený soubor vrátí bezpečné 404 a neovlivní prohlížení katalogu a previews.
Originální odpovědi mají `Cache-Control: no-store`; token se mění s epochou
aktivního mapped rootu.

`--workspace PATH` is still supported for temporary or managed launches. A
workspace supplied by CLI, environment, or explicit `--config` has higher
priority, so the web UI shows its source and locks profile editing.

Configuration precedence is CLI, environment, explicit TOML, per-user profile,
then defaults, independently for every setting. Supported
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
- `GET /settings` — active path, source, status and application information;
- `POST /settings/validate` — read-only validation of one submitted path;
- `POST /settings/save` — revalidation and atomic per-user config update;
- `POST /settings/originals/validate` — read-only SHA-256 sample validation;
- `POST /settings/originals/save` — revalidation and atomic profile-only mapping update;
- `POST /settings/originals/clear` — explicit removal of the local mapping;
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

Mapped originals accept only relative POSIX catalog paths without `..` or
backslashes. Candidate construction and every artifact request resolve the
filesystem path and require it to remain below the canonical local root, so a
static symlink escape is rejected. This path-based layer does not claim to solve
hostile local-filesystem TOCTOU replacement.

Keep the default loopback bind. Settings POST requests require a loopback bind,
loopback `Host`, same-origin `Origin` when present, and a SameSite/HttpOnly CSRF
cookie token. A non-loopback bind remains usable for read-only viewing when
explicitly requested, but server-side configuration changes are blocked because
M1.3 has no authentication or TLS.

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

## Known current limitations

- One workspace per server process; no multi-workspace library. A saved path
  change becomes active after restart, never through an HTTP-triggered restart
  or partial hot swap.
- Snapshot refresh requires a restart after processors publish new output; an
  open mismatched view receives an explicit refresh warning.
- No authentication; loopback is the safe default and LAN exposure is not an
  M1 deployment mode.
- No import, upload, processing orchestration, favorites, ratings, collections,
  general storage registry, relocation workflow, or editor integration. S2a
  maps one originals root only for Media Desk.
- Multiple analysis configurations are displayed with their fingerprints;
  video thumbnail selection requires an explicit keyframe fingerprint.
- Original availability is checked on the backend host. A browser client does
  not receive or reinterpret host filesystem paths.
- SHA-256 sampling does not prove full archive integrity. Unsampled or later
  changed files can become unavailable when opened. Historická S2a baseline
  canonicalizovala každý originál při startu; S2a.1 tuto kontrolu přesouvá na
  konkrétní GET/Range. Na syntetickém 10k katalogu se p50 startu snížil z
  25,77 s na 7,75 s (3,32×) a start neprovádí per-file I/O originálů. Aktuální
  metodika a omezení jsou v `S2A1_STARTUP_PERFORMANCE.md`.
- Session relationships are labelled as probable time continuity, never as
  identified events. Faces clusters remain anonymous similarity groups.
- Multiple valid Session Grouper results produce an ambiguous state instead of
  being guessed or merged.
- Library virtualization requires JavaScript. The API and details remain
  available without it, but thousands of fallback cards are not rendered.

The current state and approval gates are recorded in [`STATUS.md`](STATUS.md) and
[`DECISIONS.md`](DECISIONS.md). Historical M2–M5 in [`CONTRACT.md`](CONTRACT.md)
are not implemented and must not be started without a new approved scope.
