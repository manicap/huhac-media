# S2b — detailní implementační plán inicializace nového archivu

**Stav:** **COMPLETE — ověření v [S2B_VERIFICATION.md](S2B_VERIFICATION.md)**

**Připraveno:** 2026-10-23

**Návrh:** [S2B_DESIGN.md](S2B_DESIGN.md)

**Failure model:** [S2B_FAILURE_MATRIX.md](S2B_FAILURE_MATRIX.md)

Tento dokument je zachovaný prováděcí plán dokončené implementace. Každý work
package měl vlastní stop podmínku, cílené testy a dokumentační synchronizaci;
výsledek je v [S2B_VERIFICATION.md](S2B_VERIFICATION.md).

## 1. Rozsah a invarianty

Budoucí implementace smí:

- vytvořit nový prázdný Media Storage adresář;
- přes ingest-owned CLI vytvořit prázdný workspace v1;
- uložit hotovou workspace cestu do existujícího per-user Media Desk profilu;
- vyžádat restart a poté zobrazit 0 médií.

Nesmí:

- skenovat nebo hashovat Media Storage;
- importovat, přesouvat, kopírovat či mazat originály;
- volat `IngestService.execute` nebo procesory;
- měnit asset schema či `workspace_contract_version: 1`;
- povolit workspace SQLite na network/unknown filesystemu;
- měnit S2a mapping, origin tokeny, lazy GET/Range nebo procesory;
- zavést hot-swap či více aktivních workspace.

## 2. Navržené veřejné CLI

### 2.1 Preflight

```powershell
huhac-media init `
  --storage 'D:\HUHAC\Media' `
  --workspace 'C:\HUHAC\Workspaces\main' `
  --preflight --json
```

Požadavky:

- žádný filesystem zápis;
- oba parametry povinné, absolutní a omezené délkou;
- canonical paths, existence/empty state, overlap, symlink/reparse, parent
  identity, write capability, free-space advisory a filesystem classification;
- vygeneruje operation ID a výsledek `preflight_ok` nebo `rejected`;
- `warnings` nesmějí být vydávány za bezpečnostní záruku.

### 2.2 Confirmed init

```powershell
huhac-media init `
  --storage 'D:\HUHAC\Media' `
  --workspace 'C:\HUHAC\Workspaces\main' `
  --operation-id '00000000-0000-0000-0000-000000000000' `
  --yes --json
```

Požadavky:

- bez `--yes` nic nezapíše a vrátí cancellation;
- preflight se celý zopakuje; klientský výsledek není důvěryhodný;
- operation ID musí být UUID a slouží ke korelaci/retry, ne jako autorizační
  token;
- stdout je jeden versioned JSON envelope, stderr omezená diagnostika;
- žádný shell, prompt ani barevný text v `--json` režimu;
- přesné exit codes z návrhu.

## 3. Work packages a logické commity

### WP0 — schválení a contract test fixtures

**Cíl:** uzamknout schválené body návrhu před kódem.

Budoucí změny:

- `docs/media-desk/DECISIONS.md`: změnit navržená rozhodnutí S2b na ACCEPTED;
- `docs/workspace-contract.md`: upřesnit, že ready inicializovaný workspace má
  prázdný katalog; kontrakt v1 a asset schema zůstávají stejné;
- `docs/media-ingest.md`: dokumentovat nový `init` CLI a jeho non-goals;
- uložit malé JSON fixtures pro validní empty manifest/catalog a CLI envelope.

**Stop:** pokud schválení změní CLI hranici, ready definici nebo network policy,
aktualizovat návrh před implementací.

### WP1 — čistý read-only preflight

**Navržené soubory:**

- nový `src/huhac_media/services/archive_init.py` — request/result model a čistý
  preflight;
- nový `src/huhac_media/storage/filesystem_policy.py` — canonicalizace, overlap,
  symlink/reparse a local/network/unknown klasifikace;
- `src/huhac_media/cli.py` — parser `init`, zatím jen preflight JSON;
- nové `tests/unit/test_archive_init_preflight.py`;
- nové `tests/unit/test_filesystem_policy.py`.

Testy po WP1:

- neexistující a existující prázdné cíle;
- neprázdný storage/workspace;
- equality a oba směry containment;
- relativní, control/NUL, nadlimitní a neexistující parent;
- file místo adresáře, permission failure;
- symlink directory/file a Windows reparse fixture podle platformy;
- local/network/unknown policy s fake classifierem;
- read-only invariant: žádný target, temp, marker ani config po preflightu;
- JSON schema a deterministické error codes.

**Commit:** `Add read-only archive init preflight`.

### WP2 — ingest-owned init service a crash-safe publikace

**Navržené soubory:**

- `src/huhac_media/services/archive_init.py` — confirmed state machine;
- nový `src/huhac_media/storage/init_operation.py` — fixed marker, reservation,
  lock, phase record a recovery;
- `src/huhac_media/storage/workspace.py` — sdílené low-level directory/layout
  helpers; dnešní plný ingest nesmí regresně změnit chování;
- `src/huhac_media/storage/catalog.py` — explicitní zápis/finalizace init run;
- `src/huhac_media/storage/contract.py` — publikace validního empty catalogu přes
  existující atomický writer;
- `src/huhac_media/services/reporting.py` — init report bez scan/plan/stages;
- `src/huhac_media/cli.py` — actual `--yes --json`;
- nové `tests/integration/test_archive_init.py`;
- nové `tests/integration/test_archive_init_recovery.py`.

Povinné failure injection body:

1. po storage `mkdir`;
2. po workspace reservation/markeru;
3. po adresářovém layoutu;
4. po SQLite schema;
5. po workspace row;
6. po startu init run;
7. po reportu;
8. po empty catalog publish;
9. po run finish;
10. po manifest publish před marker finalizací.

Každý test ověří přesné zbytky, stejné ID při retry, žádné smazání a stav z
failure matrix. Test souběhu spustí dvě operace nad stejným cílem a prokáže
jednoho writera a jeden `workspace_id`.

Další invarianty:

- storage zůstává bez médií a bez SHA/open scanů;
- prázdný katalog je přijat všemi existujícími public-contract konzumenty;
- manifest je publikován poslední;
- `initialize_workspace()` před lockem se nepoužije v nové cestě;
- hotový validní cíl vrátí `ready_existing` bez změny byte/mtime.

**Commit:** `Add crash-safe ingest-owned archive initialization`.

### WP3 — Media Desk setup orchestrace a security boundary

**Navržené soubory:**

- nový `src/media_desk/archive_setup.py` — pevné spuštění ingest CLI, JSON schema,
  timeout/output limity a in-memory confirmation nonce;
- `src/media_desk/web.py` — pouze dva chráněné POST endpointy;
- `src/media_desk/templates/settings.html` nebo nový
  `templates/archive_setup.html` — dvě akce „Založit“/„Připojit“;
- minimální `src/media_desk/static/main.css` pouze pokud je nutné;
- `src/media_desk/config.py` pouze pro použití stávajícího atomického save po
  úspěchu, bez nového workspace schema;
- nové `tests/media_desk/test_archive_setup.py`;
- rozšíření `tests/media_desk/test_settings.py`.

Povinné testy:

- loopback bind + loopback Host + same-origin Origin + CSRF;
- LAN bind, cizí Host/Origin, chybějící/užitý/expirující nonce;
- oversized, duplicate a unexpected fields;
- subprocess argument list bez shellu a bez klientem dodaných flags/executable;
- invalid/oversized stdout a neznámé CLI schema;
- preflight nevytváří soubor;
- confirm znovu validuje a odmítne stale kolizi;
- init není dostupný při `workspace_editable == false`;
- původní profil zůstane byte-for-byte při init/validation/config save chybě;
- ready archive zůstane použitelný při config save chybě;
- úspěch uloží cestu, odstraní nepatřičný starý S2a mapping stejným pravidlem
  jako dnešní změna workspace a vyžádá restart;
- žádný HTTP endpoint nelistuje, nečte ani nemaže obecné cesty.

**Commit:** `Add protected Media Desk archive setup flow`.

### WP4 — empty UI, restart a kompatibilita

**Navržené soubory:**

- případně pouze šablony pro srozumitelný 0-media stav; stávající
  `load_workspace()` už `assets: []` přijímá;
- integrační fixture propojující skutečný init CLI a Media Desk;
- dokumentace spuštění a recovery.

Test scénáře:

- nový storage + nový workspace → validní empty catalog → 0 médií;
- existující prázdné adresáře → totéž;
- restart → stejné `workspace_id`, žádné nové runy ani zápisy;
- validní existující workspace → connect, nikoli init;
- empty workspace funguje v Overview, Library, Calendar, Relations a API;
- UI nenabízí import/AI, které neexistují;
- M1.3 precedence a restart behavior;
- S2a offline/mapping, S2a.1 token/GET/Range a virtualizace bez regrese.

**Commit:** `Verify empty archive workflow and compatibility`.

### WP5 — dokumentační sync a finální verifikace

Aktualizovat podle skutečného výsledku:

- `docs/media-desk/{STATUS,ARCHITECTURE,DECISIONS,ROADMAP,README}.md`;
- `docs/{workspace-contract,media-ingest,architecture,data-model}.md` pouze tam,
  kde chování skutečně vzniklo;
- oba S2b návrhové dokumenty označit IMPLEMENTED jen po splnění akceptace;
- příkazy, JSON envelope, failure recovery a známé limity.

**Commit:** `Document completed S2b archive initialization`.

## 4. Cílená testovací strategie

Po jednotlivých WP spouštět jen nejbližší unit/integration testy. Plnou vhodnou
FAST regresi spustit jednou po poslední změně. External/AI/modelové testy nejsou
potřeba, protože init nesmí volat nástroje ani procesory.

Minimální finální matice:

| Oblast | Povinné ověření |
|---|---|
| Ingest unit | preflight, policy, JSON schema, state machine |
| Ingest integration | empty init, retry po všech crash points, concurrency, idempotence |
| Contract | Media Desk + Session Grouper + Video Keyframes + Vision + Faces přijmou empty catalog bez práce |
| Media Desk security | Host/Origin/CSRF/loopback/body/nonce/subprocess |
| Media Desk workflow | 0 médií, config save/restart, precedence, connect existing |
| Cross-platform | syntetické Windows/POSIX cesty a nativní Windows + Linux smoke, pokud dostupný |
| Filesystem | local success; fake network/unknown reject; skutečný SMB/NFS jen pokud je bezpečně dostupný, jinak explicitně neověřeno |
| Read-only/non-goal | 0 scan/hash/tool/processor calls, žádná změna originálů |
| Regrese | M1.3, S2a mapping/offline, S2a.1 GET/Range/tokens, galerie |

Měření inicializace zaznamená p50/p95 alespoň pro nový a již-ready cíl a počet
filesystem operací. Neexistuje důvod škálovat podle počtu souborů ve storage,
protože neprázdný storage je odmítnut a žádný scan se nespouští.

## 5. Akceptační kritéria

S2b lze označit dokončenou pouze pokud:

1. Veřejný init vlastní Media Ingest a Media Desk nevytváří producer-owned
   workspace soubory.
2. Preflight je prokazatelně bez zápisu a actual init vše opakuje pod lockem.
3. Ready workspace má jedno stabilní ID v manifestu, SQLite a katalogu,
   `workspace_contract_version: 1` a `assets: []`.
4. Media Desk po restartu zobrazí běžnou prázdnou knihovnu bez importu/AI.
5. Init nevolá scan, SHA, metadata, preview, AI ani práci s originály.
6. Neprázdné neznámé cíle, overlap, symlink/reparse, network/unknown workspace a
   současný writer jsou fail-closed.
7. Všechny crash pointy mají otestovaný bezpečný retry nebo explicitní manual
   action bez automatického mazání.
8. Opakování nad hotovým cílem nezmění ID, katalog, DB ani run count.
9. Config se uloží až po postcondition validaci; chyba configu nepoškodí hotový
   archiv ani původní profil.
10. CLI/ENV/explicit config precedence, S2a, S2a.1, Range a veřejní konzumenti
    zůstanou kompatibilní.
11. Nativní Windows test projde; nativní Linux smoke projde, nebo je jeho
    neprovedení výslovně uvedeno jako limit před schválením release.
12. Dokumentace rozlišuje IMPLEMENTED, ACCEPTED, PROPOSED a UNVERIFIED podle
    skutečnosti.

## 6. Rizika a stop conditions

- Nelze-li spolehlivě vytvořit cross-platform directory identity/no-follow
  adapter, actual web init se neotevře a návrh se vrátí k bezpečnostnímu review.
- Vyžaduje-li empty catalog změnu major contractu, S2b se zastaví; tento návrh
  předpokládá kompatibilní v1 projekci ověřenou dnešními readery.
- Pokud init musí zapisovat workspace na network/unknown FS, je nutné nejprve
  samostatně schválit single-writer/backup deployment; S2b tuto bránu neobchází.
- Pokud by Media Desk musel importovat privátní ingest API, znovu se rozhodne
  integrační hranice; výchozí návrh je pouze JSON CLI.
- Jakýkoli požadavek na import nebo procesory je nová etapa, nikoli rozšíření
  tohoto plánu.

## 7. Dokumenty, které se v návrhové fázi nemění

`docs/workspace-contract.md` a `docs/media-ingest.md` nadále popisují skutečnou
implementaci. Jejich budoucí změny jsou vyjmenované ve WP0/WP5, ale nesmí být
provedeny tak, aby dnes tvrdily existenci neimplementovaného `init`.
