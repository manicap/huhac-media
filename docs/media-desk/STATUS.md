# HUHÁČ Media Desk — aktuální stav

**Auditováno:** 2026-10-27

**Větev:** `codex/media-desk-working-library-v1`

**Implementační commity S2a:** `cafcdb7`, `5b0b497`, `333571a`, `afff7f5`

**Implementační commity S2a.1:** `921f48c`, `18c0919`

**Implementační commity S2b:** `88b94fb`, `9e65e47`, `52d7b00`, `d64b0a3`, `fd6f51f`, `da416df`

**Stav aktualizován:** 2026-10-26; Správa akcí a časová navigace v1.4 implementována

> **IMPLEMENTOVÁNO DNES** — M1 až M1.3, S2a, S2a.1 a S2b: read-only galerie nad
> jedním workspace v1, virtualizovaná knihovna, kalendář a časová navigace, branding a
> bezpečně uložená lokální cesta k workspace i host-local mapování originálů.
> Aktivní workspace a mapping se načítají při
> startu procesu. Důkazy jsou níže a v [auditu](AUDIT_2026-10.md).

> **NADÁLE MIMO ROZSAH** — import, orchestrace procesorů, obecná správa lifecycle
> úložišť, přenosná metadata a síťový workspace writer. Varianty vyžadují nové
> rozhodnutí v [RFC](SETUP_STORAGE_RFC.md).

> **IMPLEMENTED 2026-10-26 — Normalizer v1 / N3.** Explicitly selected immutable
> snapshot is validated and loaded once. Unified detail, exact facets,
> completeness and provenance are read-only projections. Targeted N3 tests:
> 19 passed, 1 skipped; combined Media Desk + Normalizer: 127 passed, 7 skipped.
>
> Final synthetic Windows benchmark (1,000 assets / 30 requests): off/on startup
> 2779.5/5198.8 ms, Python peak 5.28/19.63 MiB, batch p50 11.41/13.48 ms;
> exact-facet no-match p50 4.94 ms. Development measurement, not an SLA; see
> [N3_PERFORMANCE.md](N3_PERFORMANCE.md).

> **IMPLEMENTED 2026-10-27 — HUHÁČ Launcher v0.2.** Samostatné Tkinter okno
> spravuje explicitní workspace profily, izolované user-data roots, per-profile
> port a bezpečný výběr veřejného Normalizer snapshotu. Spouští pouze Media Desk
> na pevném loopback bindu, ověřuje `/health`, vlastní přesně jeden child proces a
> odmítá cizí listener. Osobní konfigurace je mimo checkout v
> `%LOCALAPPDATA%\HUHAC\Launcher\launcher.toml`; Git obsahuje pouze distribuční
> příklad. 43 cílených launcher testů prošlo.

> **HISTORICAL BASELINE 2026-10-27 — HUHÁČ Studio v0.1.** Isolated
> React/TypeScript/Vite shell with static Projects and Media Library modules,
> Zustand ID context, React Router navigation, TanStack Query data boundary and
> synthetic data only. This baseline is superseded by the connected workflow
> described below; processor orchestration and Launcher integration remain
> **ABSENT**. Evidence and startup instructions: `docs/studio/` and `studio/src/`.

> **IMPLEMENTED 2026-10-28 — Project Core v1 + Studio Project workflow.** Samostatný `huhac_studio`
> FastAPI writer vlastní host-local versioned SQLite, host-level single-writer
> lock, projekty jednoho workspace, ploché tags, archive/restore, revision
> conflicts a transakční media links na katalogové `asset_id`. Vazby přežijí
> nedostupný katalog nebo originál. React moduly Projekty a Mediální knihovna
> používají skutečné API; syntetická data zůstávají pouze v testech. Media Desk,
> workspace, mediální soubory a procesory nebyly změněny.

> **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO 2026-10-28 — Studio adaptivní galerie a video.**
> React knihovna zachovává poměr stran, zobrazuje technická metadata a nativně
> přehrává nejvýše jeden explicitně vyžádaný katalogový video originál. Sdílená
> hlasitost/mute je browser-local; přepnutí videa, datasetu, projektu, workspace
> nebo modulu přehrávač uklidí. `huhac_studio` poskytuje pouze read-only opaque-token
> video endpoint s HTTP Range a kontrolou source-root confinement; bez transcodování,
> kopírování médií nebo zápisu do Media Desk/workspace.

## Etapy

| Etapa | Stav | Důkaz | Poznámka |
|---|---|---|---|
| M1: read-only galerie | **IMPLEMENTED** | `src/media_desk/contract.py:475`, `src/media_desk/web.py:184`, `tests/media_desk/test_media_desk_contract.py:12` | Čte veřejný kontrakt v1, ne ingest SQLite. |
| M1.1: virtualizace, navigátor, kalendář | **IMPLEMENTED** | `src/media_desk/static/library.js:18`, `src/media_desk/static/library.js:127`, `tests/media_desk/test_web.py:44`, `tests/media_desk/test_views.py:48` | Stav/anchor je oddělen podle `workspace_id`. |
| M1.1.1: desktop layout | **IMPLEMENTED** | `src/media_desk/static/library.js:6`, `src/media_desk/static/library.js:283` | Jediný scroll root galerie je `.app-main`. |
| M1.2: profesionální UI a branding | **IMPLEMENTED** | `src/media_desk/templates/base.html:13`, `src/media_desk/static/huhac-logo.png`, commit `7da319a` | Logo je lokální statický asset. |
| M1.3: nastavení jednoho workspace | **IMPLEMENTED** | `src/media_desk/config.py:17`, `src/media_desk/config.py:87`, `src/media_desk/web.py:311`, `tests/media_desk/test_settings.py:73` | Ukládá jen per-user TOML; aktivace po restartu. |
| Nový archiv z webu | **IMPLEMENTED** | `archive_setup.py`, `web.py`, `test_archive_setup.py` | Media Desk orchestruje veřejné ingest JSON CLI, postvaliduje a pak uloží profil. |
| Přemapování originálů pro jiný host/OS | **IMPLEMENTED** | `src/media_desk/originals.py`, `contract.py`, `web.py`; `tests/media_desk/test_settings.py` | UI mapping validuje nejvýše 16členným SHA-256 vzorkem, atomicky uloží a po restartu bezpečně použije. |
| S2a.1 lazy origin access | **IMPLEMENTED** | `models.py`, `contract.py`, `web.py`; `test_web.py`; `S2A1_STARTUP_PERFORMANCE.md` | Snapshot registruje unchecked source reference bez per-file I/O; GET/Range provádí request-scoped ověření a otevření. 10k p50: 25,77 s → 7,75 s (3,32×). |
| S2b: inicializace nového archivu | **IMPLEMENTED** | `S2B_VERIFICATION.md`; commity výše | Stabilní JSON CLI, crash-safe retry, empty v1 catalog a chráněný web setup. |
| Pracovní knihovna v1 | **IMPLEMENTED** | `src/media_desk/user_data.py`, `static/library.js`, `templates/events.html`, `tests/media_desk/test_working_library.py` | Stabilní názvy, lazy přehrávání v kartě, sdílená hlasitost, perzistentní akce a kompaktní práce s originálem. |
| Library UI Polishing v1.1 | **IMPLEMENTED; UI SUPERSEDED BY v1.2** | `static/library.js`, `static/library.css`, `tests/media_desk/test_working_library.py` | Portal menu, ovládací lišta a minutový capture čas zůstávají; barevné typové pruhy a původní placeholder nahradil redesign v1.2. |
| Redesign knihovny v1.2 | **IMPLEMENTED** | `static/library.js`, `static/library.css`, `index.py`, `web.py`, `tests/media_desk/test_working_library.py` | Neutrální typ, dominantnější preview, čas/datum/akce, trvale dostupný Detail, Play/Pauza, dodané fallback logo, responzivní 1–2 sloupce; malý desktopový režim zachovává krok 260 px a min. šířku 142 px. |
| Filmstrip UI v1.3 | **IMPLEMENTED** | `static/library.js`, `static/library.css`, `tests/media_desk/test_working_library.py` | Skutečná 9:16 obrazová plocha přes šířku karty, overlay typu a capture času, ovládání a zarovnaná patička; virtualizační krok se odvozuje od skutečné šířky sloupce. Kompaktní minimum 132 px zachovává hustotu galerie. |
| Běžný opakovaný start | **IMPLEMENTED** | `src/media_desk/config.py:100`, `src/media_desk/web.py:204`, `tests/media_desk/test_settings.py:73` | Nedostupná cesta nezpůsobí zápis ani automatickou opravu. |
| Lokální uživatelská data (názvy a akce) | **IMPLEMENTED** | `src/media_desk/user_data.py` | Atomický per-workspace JSON mimo workspace; přenosné výběry, ratingy a kolekce zůstávají **ABSENT**. |
| Více workspace v jednom procesu | **ABSENT** | `src/media_desk/config.py:71` | Jeden `Settings.workspace` a jeden startup snapshot. |
| HUHÁČ Launcher v0.2 | **IMPLEMENTED** | `src/huhac_launcher`, `tests/launcher`, `docs/launcher.md` | Více host-local profilů mimo checkout, bezpečné první založení z distribučního příkladu a validovaný snapshot/port výběr; stále jen jeden vlastněný Media Desk child. |
| HUHÁČ Studio Project Core v1 | **IMPLEMENTED; EXPERIMENTAL UI CONNECTED** | `src/huhac_studio`, `studio/src`, `tests/studio`, `docs/studio/PROJECT_CONTRACT.md` | Oddělená SQLite a FastAPI writer; žádné zápisy do Media Desk/workspace. |
| HUHÁČ Studio adaptivní galerie + video | **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO** | `studio/src/modules/media-library`, `src/huhac_studio/web.py`, `tests/studio/test_project_web.py` | Jeden lazy inline player, sdílená hlasitost, read-only Range stream; virtualizace a transcoding jsou absent. |

## Konfigurace, která dnes skutečně platí

**IMPLEMENTED.** Precedence se vyhodnocuje samostatně pro každý parametr:
CLI → environment → explicitní `--config` TOML → per-user profil → default
(`src/media_desk/config.py:52-67`, `src/media_desk/config.py:87-161`). Profil je na
Windows v `%APPDATA%\HUHAC\MediaDesk\config.toml` a na Linuxu v
`${XDG_CONFIG_HOME:-~/.config}/huhac/media-desk/config.toml`
(`src/media_desk/config.py:17-36`).

**IMPLEMENTED.** Web může měnit profilovou cestu jen tehdy, když workspace
nepřebíjí CLI, environment nebo explicitní config (`src/media_desk/config.py:82-84`).
Uložení používá dočasný soubor, `fsync` a atomické nahrazení
(`src/media_desk/config.py:164-213`). Běžící proces se nepřepíná; změna se použije
až po restartu (`src/media_desk/web.py:361-365`).

## Známé limity

- **IMPLEMENTED:** preview a metadata z přenosného workspace zůstávají dostupné,
  i když originál není dosažitelný; stav je explicitně offline.
- **IMPLEMENTED:** lokální override `source_root` pro Media Desk funguje jako
  přechodná S2a mezi Windows/POSIX cestami; není obecnou storage architekturou.
- **IMPLEMENTED:** S2a.1 odstranila per-file origin I/O ze startupu. 10k
  syntetický katalog na tomto Windows hostu má p50 `create_app` 7,75 s proti
  baseline 25,77 s (3,32×); při startupu je 0 per-file
  resolve/stat/is_file/open/SHA operací originálů.
- **IMPLEMENTED:** web umí výslovně potvrzeným ingest-owned příkazem vytvořit
  prázdný Media Storage a workspace; import ani procesory nespouští.
- **IMPLEMENTED:** S2b zachovala veřejný `workspace_contract_version: 1` a
  nemigruje historická data.
- **UNVERIFIED:** přímý zapisující provoz ingest SQLite/WAL na konkrétním SMB/NFS
  serveru není v tomto auditu kvalifikován jako podporovaný deployment.

## Stav testů

Pracovní knihovna v1 až Správa akcí a časová navigace v1.4: **76 passed,
5 skipped** v celé sadě `tests/media_desk` na Windows 2026-10-26. Přeskočené
testy jsou platformní symlink varianty. Cílené testy ověřují jednorázovou
Connector projekci, diakritiku, stabilitu názvů, event persistence/filtering,
lazy video, browser-local audio preference, viewportový menu portal, dynamickou
9:16 geometrii karty, zabezpečené otevření Průzkumníku, polouzavřený split,
ruční výjimky, revizní konflikt a restartovou perzistenci.

Cílená S2b sada: **53 passed, 4 skipped** za 32,93 s. Finální FAST sada:
**200 passed, 7 skipped, 48 deselected** za 18,32 s. S2a/S2b symlink testy
jsou na tomto Windows hostu přeskočeny bez oprávnění symlink vytvořit; povinné
POSIX varianty zůstávají v testech. Reprodukovatelné finální 10k měření je v
`S2A1_STARTUP_PERFORMANCE.md`. Windows i POSIX `source_root` jsou pokryty
parametrizovaným testem na Windows hostu. Nativní Linux běh zde nebyl dostupný
(není instalovaná WSL distribuce).
