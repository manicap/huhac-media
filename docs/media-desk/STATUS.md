# HUHÁČ Media Desk — aktuální stav

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Implementační commity S2a:** `cafcdb7`, `5b0b497`, `333571a`, `afff7f5`

**Implementační commity S2a.1:** `921f48c`, `18c0919`

**Implementační commity S2b:** `88b94fb`, `9e65e47`, `52d7b00`, `d64b0a3`, `fd6f51f`, `da416df`

**Stav aktualizován:** 2026-10-23; S2b dokončena

> **IMPLEMENTOVÁNO DNES** — M1 až M1.3, S2a, S2a.1 a S2b: read-only galerie nad
> jedním workspace v1, virtualizovaná knihovna, kalendář a časová navigace, branding a
> bezpečně uložená lokální cesta k workspace i host-local mapování originálů.
> Aktivní workspace a mapping se načítají při
> startu procesu. Důkazy jsou níže a v [auditu](AUDIT_2026-10.md).

> **NADÁLE MIMO ROZSAH** — import, orchestrace procesorů, obecná správa lifecycle
> úložišť, přenosná metadata a síťový workspace writer. Varianty vyžadují nové
> rozhodnutí v [RFC](SETUP_STORAGE_RFC.md).

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
| Běžný opakovaný start | **IMPLEMENTED** | `src/media_desk/config.py:100`, `src/media_desk/web.py:204`, `tests/media_desk/test_settings.py:73` | Nedostupná cesta nezpůsobí zápis ani automatickou opravu. |
| Uživatelská data (výběry, hodnocení, kolekce) | **ABSENT** | `docs/media-desk/README.md` | Není úložiště ani databáze Media Desku. |
| Více workspace v jednom procesu | **ABSENT** | `src/media_desk/config.py:71` | Jeden `Settings.workspace` a jeden startup snapshot. |

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

Cílená S2b sada: **53 passed, 4 skipped** za 32,93 s. Finální FAST sada:
**200 passed, 7 skipped, 48 deselected** za 18,32 s. S2a/S2b symlink testy
jsou na tomto Windows hostu přeskočeny bez oprávnění symlink vytvořit; povinné
POSIX varianty zůstávají v testech. Reprodukovatelné finální 10k měření je v
`S2A1_STARTUP_PERFORMANCE.md`. Windows i POSIX `source_root` jsou pokryty
parametrizovaným testem na Windows hostu. Nativní Linux běh zde nebyl dostupný
(není instalovaná WSL distribuce).
