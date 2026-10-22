# HUHÁČ Media Desk — aktuální stav

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Implementační commity S2a:** `cafcdb7`, `5b0b497`, `333571a`, `afff7f5`

**Stav aktualizován:** 2026-10-22; S2a dokončena

> **IMPLEMENTOVÁNO DNES** — M1 až M1.3 a S2a: read-only web nad jedním existujícím
> workspace v1, virtualizovaná knihovna, kalendář a časová navigace, branding a
> bezpečně uložená lokální cesta k workspace i host-local mapování originálů.
> Aktivní workspace a mapping se načítají při
> startu procesu. Důkazy jsou níže a v [auditu](AUDIT_2026-10.md).

> **CÍLOVÝ WORKFLOW, DOSUD NEIMPLEMENTOVÁNO** — webové založení nového archivu a správa lifecycle
> úložišť. Tři schválené uživatelské scénáře jsou cílem, nikoli tvrzením o dnešní
> funkčnosti. Varianty vyžadují rozhodnutí v [RFC](SETUP_STORAGE_RFC.md).

## Etapy

| Etapa | Stav | Důkaz | Poznámka |
|---|---|---|---|
| M1: read-only galerie | **IMPLEMENTED** | `src/media_desk/contract.py:475`, `src/media_desk/web.py:184`, `tests/media_desk/test_media_desk_contract.py:12` | Čte veřejný kontrakt v1, ne ingest SQLite. |
| M1.1: virtualizace, navigátor, kalendář | **IMPLEMENTED** | `src/media_desk/static/library.js:18`, `src/media_desk/static/library.js:127`, `tests/media_desk/test_web.py:44`, `tests/media_desk/test_views.py:48` | Stav/anchor je oddělen podle `workspace_id`. |
| M1.1.1: desktop layout | **IMPLEMENTED** | `src/media_desk/static/library.js:6`, `src/media_desk/static/library.js:283` | Jediný scroll root galerie je `.app-main`. |
| M1.2: profesionální UI a branding | **IMPLEMENTED** | `src/media_desk/templates/base.html:13`, `src/media_desk/static/huhac-logo.png`, commit `7da319a` | Logo je lokální statický asset. |
| M1.3: nastavení jednoho workspace | **IMPLEMENTED** | `src/media_desk/config.py:17`, `src/media_desk/config.py:87`, `src/media_desk/web.py:311`, `tests/media_desk/test_settings.py:73` | Ukládá jen per-user TOML; aktivace po restartu. |
| Nový archiv z webu | **ABSENT** | setup přijímá jen existující workspace: `src/media_desk/workspace_status.py:28` | Media Desk nevytváří workspace ani Media Storage. |
| Přemapování originálů pro jiný host/OS | **IMPLEMENTED** | `src/media_desk/originals.py`, `contract.py`, `web.py`; `tests/media_desk/test_settings.py` | UI mapping validuje nejvýše 16členným SHA-256 vzorkem, atomicky uloží a po restartu bezpečně použije. |
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
- **LIMIT:** 10k syntetický katalog na tomto Windows hostu vyžadoval 18,13 s pro
  explicitní validaci a 22,95 s pro vytvoření aplikace kvůli confinement kontrole každé
  dostupné cesty; startup provedl 0 hashů.
- **ABSENT:** web neumí vytvořit Media Storage nebo nový workspace a nespouští
  ingest ani procesory.
- **DECIDED/TARGET:** veřejný `workspace_contract_version: 1` a historická data se
  v následující etapě nesmějí měnit ani migrovat bez zvláštního schválení.
- **UNVERIFIED:** přímý zapisující provoz ingest SQLite/WAL na konkrétním SMB/NFS
  serveru není v tomto auditu kvalifikován jako podporovaný deployment.

## Stav testů

Finální FAST sada po S2a: **179 passed, 5 skipped, 33 deselected** za 29,63 s.
S2a symlink testy jsou na tomto Windows hostu přeskočeny bez oprávnění symlink
vytvořit; povinné POSIX varianty zůstávají v testech. Reprodukovatelné 10k měření
`tests/media_desk/benchmark_s2a.py`: validace **18 134 ms**, 16 SHA-256 volání;
startup aplikace **22 951 ms**, 0 SHA-256 volání; online **10 000/10 000** originálů.
Windows i POSIX `source_root` jsou pokryty parametrizovaným end-to-end testem na
Windows hostu. Nativní Linux běh zde nebyl dostupný (není instalovaná WSL distribuce).
