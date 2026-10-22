# HUHÁČ Media Desk — registr architektonických rozhodnutí

**Auditováno:** 2026-10-22

**Větev:** `mediadesk`

**Auditovaný commit:** `4397b9289de8689ed9282d9cbce842f3de4a60c2`

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
| D-009 | Interní ingest DB logicky patří k workspace; současný multi-host zápis přes SMB/NFS není podporovaný cíl. | **ACCEPTED** | SQLite WAL a host lock: `src/huhac_media/storage/database.py:24-28`, `src/huhac_media/storage/workspace.py:89-129` |
| D-010 | Media Desk nebude dostávat SQLite jen „pro budoucnost“. | **ACCEPTED** | M1.3 potřebuje pouze config; `rg sqlite src/media_desk` nemá produkční DB použití |
| D-011 | První mapping má být lokální adaptér vázaný na `workspace_id` a původní `source_root`, použitý jen pro read-only Media Desk. | **PROPOSED** | nejmenší změna bez migrace; čeká na schválení |
| D-012 | Nový workspace má zakládat úzké ingest-owned init rozhraní, ne Media Desk přímými zápisy. | **PROPOSED** | zachová ownership; čeká na návrh rollbacku a schválení |
| D-013 | Přenosné výběry/hodnocení/kolekce budou oddělené od inferenčních výstupů i lokálního configu. | **TARGET**, formát **PROPOSED** | dnes neimplementováno |
| D-014 | Přímé editování `metadata/catalog.json` nebo změna `workspace_contract_version` kvůli mappingu. | **REJECTED pro nejbližší etapu** | porušilo by historii a kompatibilitu procesorů |

## Vyhodnocení otázek E1–E10

- **E1 — IMPLEMENTED:** cesty, precedence, atomický profil, restart a ochrany HTTP
  jsou doloženy v D-003 až D-005 a `ARCHITECTURE.md`.
- **E2 — PARTIAL/UNVERIFIED:** ingest umí v rámci plného runu vytvořit i prázdný
  workspace, ale nemá samostatný veřejný init kontrakt a audit cestu nespustil.
- **E3 — ABSENT:** žádný override neexistuje. D-011 je nejmenší návrh; společné
  použití procesory zůstává otevřené.
- **E4 — PROPOSED:** strukturální kontrola všech aktivních relativních cest,
  deterministický reprezentativní SHA vzorek a volitelný full verify. Samotný
  název/cesta není identita. Politika duplicitních source versions není schválena.
- **E5 — UNVERIFIED:** podporovaný NAS writer model není vybrán; viz RFC.
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

## Schvalovací brána

Před implementací S2a je nutné výslovně schválit nebo upravit D-011 a validační
hranice v RFC. D-012 musí být schváleno před bootstrap etapou a writer deployment
před jakoukoli síťovou zapisující etapou; mohou zatím zůstat odložené. Tento audit
žádný návrh neimplementuje.
