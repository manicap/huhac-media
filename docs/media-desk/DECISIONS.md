# HUHÁČ Media Desk — registr architektonických rozhodnutí

**Auditováno:** 2026-10-27

**Větev:** `codex/media-desk-working-library-v1`

**Výchozí commit konsolidace:** `288b9e6221459c074d80016518a4fbaa8bc90aa4`

**Rozhodnutí aktualizována:** 2026-10-28 po schválení Project Core v1 a D-029

Stavy: **ACCEPTED** je závazná hranice, **IMPLEMENTED** je doložená skutečnost,
**TARGET** je odsouhlasený výsledek bez hotové implementace, **PROPOSED** čeká na
schválení a **REJECTED** se nemá realizovat.

| ID | Rozhodnutí | Stav | Důvod / důkaz |
|---|---|---|---|
| D-001 | Veřejný workspace kontrakt v1 je kompatibilitní hranice; ingest SQLite není veřejné API. | **ACCEPTED + IMPLEMENTED** | `docs/workspace-contract.md`; `src/media_desk/contract.py:475`; `src/huhac_media/storage/database.py:11` |
| D-002 | Media Desk je read-only vůči workspace a originálům; zapisovat smí jen lokální instance config a schválená Media Desk-owned uživatelská data mimo workspace. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/config.py`; `src/media_desk/user_data.py`; `tests/media_desk/test_working_library.py` |
| D-003 | Jedna běžící instance používá jeden workspace a snapshot se aktivuje při startu. | **IMPLEMENTED** | `src/media_desk/config.py:71`; `src/media_desk/web.py:204-212` |
| D-004 | Precedence je CLI → ENV → explicitní TOML → profil → default, pro každý parametr zvlášť. | **IMPLEMENTED** | `src/media_desk/config.py:52-67`, `tests/media_desk/test_media_desk_settings_config.py:59` |
| D-005 | Změna workspace z UI vyžaduje restart; žádný HTTP restart ani částečný hot-swap. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/web.py:361-365` |
| D-006 | Media Storage, Workspace, lokální instance config a uživatelská data jsou různé vrstvy. | **ACCEPTED + IMPLEMENTED V LOKÁLNÍM ROZSAHU** | `library-data/<workspace_id>.json` vlastní Media Desk; přenosná synchronizace zůstává mimo rozsah |
| D-007 | Tři provozní scénáře A/B/C jsou cílový workflow. | **TARGET** | aktuální pokrytí je A absent, B implemented v přechodném rozsahu S2a, C implemented |
| D-008 | Cizí `source_root` se kvůli prohlížení nikdy automaticky nepřepisuje do sdíleného katalogu. | **ACCEPTED** | chrání více hostitelů a veřejnou historii; dnešní Media Desk katalog nezapisuje |
| D-009 | Interní ingest DB logicky patří k workspace; multi-host zápis přes SMB/NFS je nepodporovaný. Budoucí síťový model musí mít jediného writera a bezpečný backup. | **ACCEPTED** | schváleno 2026-10-22; SQLite WAL a host lock: `src/huhac_media/storage/database.py:24-28`, `src/huhac_media/storage/workspace.py:89-129` |
| D-010 | Media Desk nebude dostávat SQLite jen „pro budoucnost“. | **ACCEPTED** | M1.3 potřebuje pouze config; `rg sqlite src/media_desk` nemá produkční DB použití |
| D-011 | S2a zavede lokální read-only mapping originálů pouze pro Media Desk, vázaný na `workspace_id` a přesnou původní hodnotu `source_root`. Mapping zůstane v per-user configu, použije path confinement, ochranu proti symlink escape a reprezentativní SHA-256 vzorek; běžný start neprovede full rehash. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/originals.py`, `config.py`, `contract.py`, `web.py`; přechodný kompatibilní adapter pro v1, nikoli definitivní storage architektura |
| D-012 | Prázdný workspace zakládá samostatné ingest-owned rozhraní oddělené od importu a analýzy; Media Desk přímo nevytváří producer-owned soubory. | **ACCEPTED + IMPLEMENTED** | `huhac-media init`; `src/huhac_media/services/archive_init.py` |
| D-013 | Přenosné výběry/hodnocení/kolekce budou oddělené od inferenčních výstupů i lokálního configu. | **TARGET**, formát **PROPOSED** | dnes neimplementováno |
| D-014 | Přímé editování `metadata/catalog.json` nebo změna `workspace_contract_version` kvůli mappingu. | **REJECTED pro nejbližší etapu** | porušilo by historii a kompatibilitu procesorů |
| D-015 | Documentation First & Documentation Sync je závazný projektový proces. | **ACCEPTED + IMPLEMENTED** | `AGENTS.md`, `docs/development.md`; zavedeno 2026-10-22 v commitu `defb316` |
| D-016 | S2a.1 odděluje katalogem autorizovanou source reference od aktuálně ověřeného originálu. Startup nesmí kvůli registraci provádět per-asset `resolve`/`stat`/`open`; confinement, symlink escape a otevření se provedou request-scoped při každém GET/Range. Staré tokeny se vážou na epochu aktivního rootu. | **ACCEPTED + IMPLEMENTED** | `models.py`, `contract.py`, `web.py`; finální profil a bezpečnostní důkazy v `S2A1_STARTUP_PERFORMANCE.md` |
| D-017 | Označení S2b se používá pro ingest-owned inicializaci nového archivu; dříve stejně označené rozšíření shared storage resolveru zůstává odložené bez čísla. | **ACCEPTED + IMPLEMENTED** | S2b dokončena 2026-10-23 |
| D-018 | Jedinou veřejnou integrační hranicí S2b je verzované JSON CLI `huhac-media init`; Media Desk neimportuje privátní ingest Python API ani neparsuje textové hlášky. | **ACCEPTED + IMPLEMENTED** | `archive_setup.py` spouští pevný argument list a validuje přesné JSON schema |
| D-019 | Ready prázdný workspace v1 obsahuje SQLite workspace row a init run, prázdný atomický katalog `assets: []` a manifest publikovaný jako poslední readiness bod. | **ACCEPTED + IMPLEMENTED** | `archive_init.py`; integrační crash/retry testy |
| D-020 | S2b zakazuje oba směry překryvu Media Storage/Workspace a povoluje workspace pouze na prokazatelně lokálním filesystemu; network i unknown workspace FS fail-closed. Jde o bezpečnostní omezení etapy S2b, nikoli definitivní omezení Media Pipeline. | **ACCEPTED + IMPLEMENTED PRO S2b** | filesystem policy a testy; přenosná knihovna a centrální metadata zůstávají otevřené |

| D-021 | Pracovní knihovna v1 ukládá stabilní katalogizační názvy a uživatelské akce atomicky do per-user JSON mimo workspace. Connector provenance smí být přečtena pouze při jednorázové projekci; requesty ani restart se na privátní Connector stav nevážou. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/user_data.py`; jednoznačné `logical_path` nebo perzistentní `VID/IMG`; akce mapují jednu či více Session Grouper relací |
| D-022 | Otevření originálu v Průzkumníku je lokální Windows POST akce bez klientské cesty. Použije pouze aktivní katalogový asset, request-scoped confinement/symlink kontrolu a stávající loopback/Host/Origin/CSRF hranici. | **ACCEPTED + IMPLEMENTED** | `POST /api/assets/{sha256}/reveal`; `tests/media_desk/test_working_library.py` |
| D-023 | Session Grouper relace je pouze časový podklad; Media Desk může jednu relaci rozdělit do více uživatelských akcí pomocí intervalů `[start, end)`. Spolehlivý capture start určuje automatické přiřazení, ruční asset výjimka má přednost. | **ACCEPTED + IMPLEMENTED** | schema 2 v `user_data.py`; atomický split/posun sdílené hranice; revizní ochrana; cílené testy |
| D-024 | Normalizer N3 je explicitní read-only startup projekce; fingerprintový výběr nikdy nepoužívá čas vytvoření a user store zůstává oddělený. | **ACCEPTED + IMPLEMENTED** | `normalizer_adapter.py`, `effective_view.py`, `test_normalizer_integration.py` |
| D-025 | Launcher v0.1 ovládá pouze jeden jím vytvořený loopback Media Desk child proces. Readiness dokládá `/health`; obsazený port ani proces po restartu launcher nepřebírá a stop nikdy necílí podle názvu/portu. | **ACCEPTED + IMPLEMENTED** | `src/huhac_launcher`, `tests/launcher`, `docs/launcher.md`; schváleno TASK-LAUNCH-001 |
| D-026 | Launcher v0.2 používá více explicitních profilů s odděleným workspace, Media Desk user-data rootem, portem a snapshoty; stále vlastní nejvýše jeden child. | **ACCEPTED + IMPLEMENTED** | TASK-LAUNCH-003; `src/huhac_launcher/config.py`, `snapshots.py` |
| D-027 | Osobní Launcher konfigurace nepatří do Git historie. Aktivní schema 2 TOML je v host-local user configu; verzovaný neosobní příklad smí atomicky založit pouze chybějící konfiguraci a nikdy nepřepisuje existující profil. | **ACCEPTED + IMPLEMENTED** | TASK-GIT-001; `default_launcher_config_path`, `initialize_launcher_config`, `config/launcher.example.toml` |
| D-028 | Studio v0.1 je statický React modulární shell s ID-only kontextem a zachovává ownership Media Desk, workspace a procesorů; produkční projektový writer ani multi-workspace backend nejsou schváleny. | **ACCEPTED TARGET + EXPERIMENTALLY IMPLEMENTED** | TASK-STUDIO-002; `studio/src`, `docs/studio` |
| D-029 | Project v1 je Studio-owned agregát v samostatné host-local SQLite. Jediný FastAPI writer spravuje ploché projekty jednoho workspace, tags, archive/restore, integer revision a odkazy na katalogové `asset_id`; nikdy nezapisuje Media Desk store ani workspace. | **ACCEPTED + IMPLEMENTED** | TASK-STUDIO-004; `src/huhac_studio`, `tests/studio`, `docs/studio/PROJECT_CONTRACT.md` |

## D-029 — Project Core v1 uses an isolated Studio-owned SQLite

**ACCEPTED + IMPLEMENTED 2026-10-28 (TASK-STUDIO-004).** Source of truth je samostatná
SQLite v host-local Studio profile data rootu a zapisuje ji jediný FastAPI
Project service. Projekt patří právě jednomu workspace, má serverové stabilní
`project-<uuid4 hex>`, neunikátní title, ploché tags, stav active/archived a
integer revision pro optimistic concurrency. Hard delete v1 není.

Media links odkazují pouze existující katalogové `asset_id` s rolemi `source`,
`reference` a `deliverable`. Pozdější nedostupnost katalogu, assetu nebo originálu
vazbu nemaže. Project service nesmí zapisovat Media Desk user-data schema 2,
workspace, ingest SQLite ani processor-owned analysis. External resources,
working directories a portable JSON export/import jsou explicitně odloženy.

## D-028 — Studio shell preserves existing ownership boundaries

**ACCEPTED TARGET + EXPERIMENTALLY IMPLEMENTED 2026-10-27
(TASK-STUDIO-002).** HUHÁČ Studio starts as a static React/TypeScript module
orchestrator. The shell owns navigation and an ID-only working context; modules
own their UI and domain logic and communicate only through public context/data
contracts. The v0.1 implementation uses synthetic in-memory data. It does not
rename Sessions or Events, introduce project persistence, write a workspace, or
change Media Desk/Launcher. A production project writer, multi-workspace backend,
and Launcher integration each require a later explicit decision.

## D-024 — Normalizer N3 is an explicit read-only startup projection

**ACCEPTED + IMPLEMENTED 2026-10-26 (TASK-NORM-003).** Media Desk reads only the
public immutable path `analysis/normalizer/normalizer-v1/<config>/<input>/`.
Selection is fingerprint-based; creation time never decides. If an explicit config
contains exactly one input snapshot it may be selected unambiguously; multiple
candidates are `ambiguous`. Failure safely degrades to source Media Desk data.

Normalizer is the source/machine layer. Media Desk user data remains separate
writer-owned schema 2 and overrides only effective names or events. Session is not
an event. List API projections stay compact; full NormalizedAsset belongs to detail.

## D-026 — Launcher v0.2 profiles and snapshot selection

**ACCEPTED + IMPLEMENTED 2026-10-27 (TASK-LAUNCH-003).** Launcher configuration
schema 2 is an atomically written host-local TOML containing multiple explicit
profiles. A profile binds one workspace identity, one isolated Media Desk data root,
one loopback port and explicit Keyframes/Normalizer selections. Launcher never
chooses the newest snapshot or a random port. Normalizer discovery reads only the
public immutable namespace and delegates validity to the existing Media Desk
adapter. Removing a profile removes no workspace or Media Desk-owned data. The
backend lifecycle remains one directly owned child; this is not processor
orchestration or multi-workspace support inside one Media Desk process.

## D-027 — Launcher profiles are host-local, not distribution state

**ACCEPTED + IMPLEMENTED 2026-10-27 (TASK-GIT-001).** Aktivní konfigurace je na
Windows v `%LOCALAPPDATA%\HUHAC\Launcher\launcher.toml`. Distribuce obsahuje jen
`config/launcher.example.toml` bez osobních cest. Pokud lokální soubor chybí,
Launcher nejprve plně validuje příklad a pak jej uloží stejným atomickým zápisem
jako běžné změny profilu. Existující nebo poškozený lokální soubor se ze šablony
nikdy neopravuje ani nepřepisuje. Explicitní `--config` zůstává diagnostickou a
testovací výjimkou. Workspace, Media Desk user data a processor-owned data tento
mechanismus neotevírá k zápisu.

## Vyhodnocení otázek E1–E10

- **E1 — IMPLEMENTED:** cesty, precedence, atomický profil, restart a ochrany HTTP
  jsou doloženy v D-003 až D-005 a `ARCHITECTURE.md`.
- **E2 — IMPLEMENTED PRO S2b:** samostatné ingest-owned JSON CLI vytváří ready
  prázdný workspace bez importu a analýzy; crash/retry a webový workflow jsou
  doloženy v `S2B_VERIFICATION.md`. Nativní Linux smoke zůstává **UNVERIFIED**.
- **E3 — IMPLEMENTED PRO MEDIA DESK:** D-011 je realizováno lokálním adapterem.
  Společné použití procesory zůstává mimo S2a.
- **E4 — IMPLEMENTED:** před uložením mappingu proběhne strukturální kontrola
  a deterministický reprezentativní SHA-256 vzorek. Výsledek musí být označen jako
  vzorková, nikoli úplná kontrola integrity. Samotný název/cesta není identita.
- **E5 — ACCEPTED OMEZENÍ:** multi-host zápis je nepodporovaný. Konkrétní budoucí
  single-writer/backup deployment zůstává **UNVERIFIED**; viz RFC.
- **E6 — IMPLEMENTED (negativní zjištění):** Media Desk má config, ne SQLite.
- **E7 — TARGET/PROPOSED:** uživatelská data mají být přenosná a oddělená, ale
  schema, writer, záloha i verzování nejsou rozhodnuty.
- **E8 — IMPLEMENTED PRO S2a:** nedostupný workspace i mapped root mají bezpečný
  stav a config se automaticky nemaže; uživatel může mapping explicitně znovu
  validovat, nahradit nebo odstranit.
- **E9 — IMPLEMENTED pro M1.3/S2a:** loopback/Host/Origin/CSRF/body/field ochrany jsou
  v `src/media_desk/web.py`. Budoucí setup musí stejný model zachovat a
  nesmí přidat obecný file browser/read endpoint.
- **E10 — PROPOSED:** adapter může zachovat v1 bez rehash/AI; kontrakt v2 je až
  možnost pro sdílenou, více-konzumentovou storage abstrakci po samostatném ADR.

## Stav schválení a další brána

D-011, D-012 a omezení D-009 byly schváleny 2026-10-22. Detailní implementační
plán a výsledek S2a je v [S2A_IMPLEMENTATION_PLAN.md](S2A_IMPLEMENTATION_PLAN.md).
S2a je dokončena. Writer deployment musí být navržen a schválen před jakoukoli
síťovou zapisující etapou; dokončení S2a tuto bránu nemění.

Detailní návrh initu je v [S2B_DESIGN.md](S2B_DESIGN.md); implementace a důkazy
jsou v [S2B_VERIFICATION.md](S2B_VERIFICATION.md). D-017 až D-020 jsou splněny.
