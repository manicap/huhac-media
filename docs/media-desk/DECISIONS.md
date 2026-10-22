# HUHÁČ Media Desk — registr architektonických rozhodnutí

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

**Rozhodnutí aktualizována:** 2026-10-22 po schválení D-011, D-012 a D-009

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
| D-007 | Tři provozní scénáře A/B/C jsou cílový workflow. | **TARGET** | uživatelsky odsouhlasený baseline; aktuální pokrytí je A absent, B partial, C implemented |
| D-008 | Cizí `source_root` se kvůli prohlížení nikdy automaticky nepřepisuje do sdíleného katalogu. | **ACCEPTED** | chrání více hostitelů a veřejnou historii; dnešní Media Desk katalog nezapisuje |
| D-009 | Interní ingest DB logicky patří k workspace; multi-host zápis přes SMB/NFS je nepodporovaný. Budoucí síťový model musí mít jediného writera a bezpečný backup. | **ACCEPTED** | schváleno 2026-10-22; SQLite WAL a host lock: `src/huhac_media/storage/database.py:24-28`, `src/huhac_media/storage/workspace.py:89-129` |
| D-010 | Media Desk nebude dostávat SQLite jen „pro budoucnost“. | **ACCEPTED** | M1.3 potřebuje pouze config; `rg sqlite src/media_desk` nemá produkční DB použití |
| D-011 | S2a zavede lokální read-only mapping originálů pouze pro Media Desk, vázaný na `workspace_id` a přesnou původní hodnotu `source_root`. Mapping zůstane v per-user configu, použije path confinement, ochranu proti symlink escape a reprezentativní SHA-256 vzorek; běžný start neprovede full rehash. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-22; přechodný kompatibilní adapter pro v1, nikoli definitivní storage architektura |
| D-012 | Prázdný workspace bude v budoucnu zakládat samostatné ingest-owned rozhraní oddělené od importu a analýzy; Media Desk nebude přímo vytvářet producer-owned soubory. | **ACCEPTED/TARGET — NOT IMPLEMENTED** | schváleno 2026-10-22; zachovává ownership ingestu |
| D-013 | Přenosné výběry/hodnocení/kolekce budou oddělené od inferenčních výstupů i lokálního configu. | **TARGET**, formát **PROPOSED** | dnes neimplementováno |
| D-014 | Přímé editování `metadata/catalog.json` nebo změna `workspace_contract_version` kvůli mappingu. | **REJECTED pro nejbližší etapu** | porušilo by historii a kompatibilitu procesorů |
| D-015 | Documentation First & Documentation Sync je závazný projektový proces. | **ACCEPTED + IMPLEMENTED** | `AGENTS.md`, `docs/development.md`; zavedeno 2026-10-22 v commitu `defb316` |

## Vyhodnocení otázek E1–E10

- **E1 — IMPLEMENTED:** cesty, precedence, atomický profil, restart a ochrany HTTP
  jsou doloženy v D-003 až D-005 a `ARCHITECTURE.md`.
- **E2 — PARTIAL/UNVERIFIED:** ingest umí v rámci plného runu vytvořit i prázdný
  workspace, ale nemá samostatný veřejný init kontrakt a audit cestu nespustil.
- **E3 — ACCEPTED/TARGET, ABSENT V KÓDU:** D-011 schvaluje lokální adapter jen
  pro Media Desk. Společné použití procesory zůstává mimo S2a.
- **E4 — ACCEPTED/TARGET:** před uložením mappingu proběhne strukturální kontrola
  a deterministický reprezentativní SHA-256 vzorek. Výsledek musí být označen jako
  vzorková, nikoli úplná kontrola integrity. Samotný název/cesta není identita.
- **E5 — ACCEPTED OMEZENÍ:** multi-host zápis je nepodporovaný. Konkrétní budoucí
  single-writer/backup deployment zůstává **UNVERIFIED**; viz RFC.
- **E6 — IMPLEMENTED (negativní zjištění):** Media Desk má config, ne SQLite.
- **E7 — TARGET/PROPOSED:** uživatelská data mají být přenosná a oddělená, ale
  schema, writer, záloha i verzování nejsou rozhodnuty.
- **E8 — PARTIAL:** nedostupný workspace má bezpečný non-ready stav a config se
  nemaže. Mapping-specific retry/rollback dosud neexistuje.
- **E9 — IMPLEMENTED pro M1.3:** loopback/Host/Origin/CSRF/body/field ochrany jsou
  v `src/media_desk/web.py:264-303`. Budoucí setup musí stejný model zachovat a
  nesmí přidat obecný file browser/read endpoint.
- **E10 — PROPOSED:** adapter může zachovat v1 bez rehash/AI; kontrakt v2 je až
  možnost pro sdílenou, více-konzumentovou storage abstrakci po samostatném ADR.

## Stav schválení a další brána

D-011, D-012 a omezení D-009 byly schváleny 2026-10-22. Detailní implementační
plán S2a je v [S2A_IMPLEMENTATION_PLAN.md](S2A_IMPLEMENTATION_PLAN.md). S2a zatím
není implementována; zahájení kódu vyžaduje samostatný pokyn. Writer deployment
musí být navržen a schválen před jakoukoli síťovou zapisující etapou.
