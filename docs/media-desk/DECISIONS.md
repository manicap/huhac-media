# HUHÁČ Media Desk — registr architektonických rozhodnutí

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

**Rozhodnutí aktualizována:** 2026-10-23 po schválení D-017 až D-020

Stavy: **ACCEPTED** je závazná hranice, **IMPLEMENTED** je doložená skutečnost,
**TARGET** je odsouhlasený výsledek bez hotové implementace, **PROPOSED** čeká na
schválení a **REJECTED** se nemá realizovat.

| ID | Rozhodnutí | Stav | Důvod / důkaz |
|---|---|---|---|
| D-001 | Veřejný workspace kontrakt v1 je kompatibilitní hranice; ingest SQLite není veřejné API. | **ACCEPTED + IMPLEMENTED** | `docs/workspace-contract.md`; `src/media_desk/contract.py:475`; `src/huhac_media/storage/database.py:11` |
| D-002 | Media Desk je read-only vůči workspace a originálům; smí zapisovat pouze lokální instance config. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/config.py:164`; `tests/media_desk/test_settings.py:73` |
| D-003 | Jedna běžící instance používá jeden workspace a snapshot se aktivuje při startu. | **IMPLEMENTED** | `src/media_desk/config.py:71`; `src/media_desk/web.py:204-212` |
| D-004 | Precedence je CLI → ENV → explicitní TOML → profil → default, pro každý parametr zvlášť. | **IMPLEMENTED** | `src/media_desk/config.py:52-67`, `tests/media_desk/test_media_desk_settings_config.py:59` |
| D-005 | Změna workspace z UI vyžaduje restart; žádný HTTP restart ani částečný hot-swap. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/web.py:361-365` |
| D-006 | Media Storage, Workspace, lokální instance config a budoucí uživatelská data jsou různé vrstvy. | **ACCEPTED** | odpovídá dnešnímu ownership; uživatelská vrstva je dosud **ABSENT** |
| D-007 | Tři provozní scénáře A/B/C jsou cílový workflow. | **TARGET** | aktuální pokrytí je A absent, B implemented v přechodném rozsahu S2a, C implemented |
| D-008 | Cizí `source_root` se kvůli prohlížení nikdy automaticky nepřepisuje do sdíleného katalogu. | **ACCEPTED** | chrání více hostitelů a veřejnou historii; dnešní Media Desk katalog nezapisuje |
| D-009 | Interní ingest DB logicky patří k workspace; multi-host zápis přes SMB/NFS je nepodporovaný. Budoucí síťový model musí mít jediného writera a bezpečný backup. | **ACCEPTED** | schváleno 2026-10-22; SQLite WAL a host lock: `src/huhac_media/storage/database.py:24-28`, `src/huhac_media/storage/workspace.py:89-129` |
| D-010 | Media Desk nebude dostávat SQLite jen „pro budoucnost“. | **ACCEPTED** | M1.3 potřebuje pouze config; `rg sqlite src/media_desk` nemá produkční DB použití |
| D-011 | S2a zavede lokální read-only mapping originálů pouze pro Media Desk, vázaný na `workspace_id` a přesnou původní hodnotu `source_root`. Mapping zůstane v per-user configu, použije path confinement, ochranu proti symlink escape a reprezentativní SHA-256 vzorek; běžný start neprovede full rehash. | **ACCEPTED + IMPLEMENTED** | `src/media_desk/originals.py`, `config.py`, `contract.py`, `web.py`; přechodný kompatibilní adapter pro v1, nikoli definitivní storage architektura |
| D-012 | Prázdný workspace bude v budoucnu zakládat samostatné ingest-owned rozhraní oddělené od importu a analýzy; Media Desk nebude přímo vytvářet producer-owned soubory. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-22; zachovává ownership ingestu |
| D-013 | Přenosné výběry/hodnocení/kolekce budou oddělené od inferenčních výstupů i lokálního configu. | **TARGET**, formát **PROPOSED** | dnes neimplementováno |
| D-014 | Přímé editování `metadata/catalog.json` nebo změna `workspace_contract_version` kvůli mappingu. | **REJECTED pro nejbližší etapu** | porušilo by historii a kompatibilitu procesorů |
| D-015 | Documentation First & Documentation Sync je závazný projektový proces. | **ACCEPTED + IMPLEMENTED** | `AGENTS.md`, `docs/development.md`; zavedeno 2026-10-22 v commitu `defb316` |
| D-016 | S2a.1 odděluje katalogem autorizovanou source reference od aktuálně ověřeného originálu. Startup nesmí kvůli registraci provádět per-asset `resolve`/`stat`/`open`; confinement, symlink escape a otevření se provedou request-scoped při každém GET/Range. Staré tokeny se vážou na epochu aktivního rootu. | **ACCEPTED + IMPLEMENTED** | `models.py`, `contract.py`, `web.py`; finální profil a bezpečnostní důkazy v `S2A1_STARTUP_PERFORMANCE.md` |
| D-017 | Označení S2b se použije pro ingest-owned inicializaci nového archivu; dříve stejně označené rozšíření shared storage resolveru zůstane odložené bez čísla. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-23; viz `S2B_DESIGN.md` |
| D-018 | Jedinou veřejnou integrační hranicí S2b bude verzované JSON CLI `huhac-media init`; Media Desk nebude importovat privátní ingest Python API ani parsovat textové hlášky. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-23; zachová producer ownership a procesní hranici |
| D-019 | Ready prázdný workspace v1 obsahuje SQLite workspace row a init run, prázdný atomický katalog `assets: []` a manifest publikovaný jako poslední readiness bod. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-23; dnešní samostatný bootstrap není Desk-ready |
| D-020 | S2b zakáže oba směry překryvu Media Storage/Workspace a povolí workspace pouze na prokazatelně lokálním filesystemu; network i unknown workspace FS fail-closed. Jde o bezpečnostní omezení etapy S2b, nikoli definitivní omezení Media Pipeline. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-23; přenosná knihovna a případné centrální metadata zůstávají otevřeným tématem |

## Vyhodnocení otázek E1–E10

- **E1 — IMPLEMENTED:** cesty, precedence, atomický profil, restart a ochrany HTTP
  jsou doloženy v D-003 až D-005 a `ARCHITECTURE.md`.
- **E2 — PARTIAL/UNVERIFIED:** ingest umí v rámci plného runu vytvořit i prázdný
  workspace, ale nemá samostatný veřejný init kontrakt a audit cestu nespustil.
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

Detailní návrh initu je v [S2B_DESIGN.md](S2B_DESIGN.md). D-017 až D-020 byly
schváleny 2026-10-23 a implementace S2b je autorizována; dokud neprojde akceptací,
zůstávají rozhodnutí ve stavu TARGET, nikoli IMPLEMENTED.
