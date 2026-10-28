# Kritická architektonická revize systému Projektů

- **Úkol:** TASK-STUDIO-003
- **Datum auditu:** 2026-10-28
- **Auditovaný základ:** `feature/studio-shell`, HEAD
  `9b4d8ca284a7b2814061ba13c94243f813ad6ca3` plus necommitnutý prototyp
  TASK-STUDIO-002
- **Stav dokumentu:** **ANALÝZA / DOPORUČENÍ, ČEKÁ NA SCHVÁLENÍ**
- **Rozsah:** read-only revize; tento dokument nemění žádný schválený kontrakt
  ani nepovoluje implementaci

## 1. Executive summary

Základní hypotéza je správná: Projekt má být Studio-owned pracovní celek,
oddělený od Session, události, workspace katalogu i processor-owned výsledků.
Média se mají připojovat odkazem, nikoli kopírováním, a dočasný GUI kontext nemá
být zaměněn za trvalá projektová data.

Současný návrh v `PROJECT_CONTRACT.md` však ještě není produkční kontrakt. Chybí
mu zejména:

- přesné vymezení identity projektu a vazby na jeden workspace;
- lifecycle aktivní/archivovaný, obnova a pravidla duplikace;
- transakční model mnoho-na-mnoho vazeb a optimistic concurrency;
- chování při zmizení assetu, změně obsahu nebo odpojeném úložišti;
- oddělení katalogového média od fyzické kopie a od nekatalogové přílohy;
- bezpečný model pracovního adresáře, zálohy, migrace a obnovy;
- autoritativní writer a API hranice pro ostatní moduly.

### Jednoznačné doporučení

Pro Project v1 doporučuji **samostatnou Studio-owned SQLite databázi na lokálním
filesystemu, vlastněnou jediným backendovým procesem**, s transakčními migracemi,
foreign keys, integer revizí projektového agregátu a explicitním backup/export
API. JSON má být přenosný export, nikoli primární source of truth. Rozšíření
Media Desk user store nedoporučuji.

Projekt v1 má:

1. mít neprůhledné serverem vytvořené ID nezávislé na názvu a cestě;
2. patřit právě jednomu `workspace_id`;
3. mít neunikátní název, popis, poznámky, štítky a stav `active|archived`;
4. odkazovat katalogová média přes `asset_id = sha256:<hash>`;
5. ponechat chybějící/offline vazby jako diagnostické placeholdery;
6. mít plochou strukturu bez pevných typů a podprojektů;
7. používat revizi pro optimistic concurrency, ne plnou historii verzí;
8. volitelný pracovní adresář evidovat jen jako host-local externí vazbu;
9. nikdy automaticky nekopírovat, nepřejmenovávat ani nemazat média či adresář;
10. držet dočasný výběr médií pouze v GUI kontextu.

Před implementací je nutné schválit minimálně způsob persistence, scope jednoho
workspace, lifecycle bez hard delete, politiku externích zdrojů a rozsah exportu.

## 2. Ověřený současný stav

### 2.1 Implementace, kontrakt a návrh nejsou totéž

| Oblast | Ověřený stav | Klasifikace |
|---|---|---|
| Studio Shell | React Router, statický registr, Zustand ID kontext a dva moduly | **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO** |
| Projektová data | Pouze konstanty v `syntheticDataSource.ts`; bez writeru a persistence | **EXPERIMENTÁLNÍ DEMO** |
| `PROJECT_CONTRACT.md` | Projekt + vazba projekt–médium, bez lifecycle a persistence | **PROPOSED / NOT IMPLEMENTED** |
| Media Desk API | Jeden startup `WorkspaceSnapshot`; stránkovaný read-only katalog a detail assetu | **IMPLEMENTOVÁNO** |
| Media Desk user data | Per-workspace JSON schema 2 pro názvy, události, intervaly a ruční přiřazení | **IMPLEMENTOVÁNO, MEDIA DESK-OWNED** |
| Workspace contract v1 | UUID workspace, obsahové asset ID, zdrojové verze a image/video katalog | **VEŘEJNÝ IMPLEMENTOVANÝ KONTRAKT** |
| Session Grouper | Immutable processor-owned časové seskupení; session není událost | **IMPLEMENTOVÁNO** |
| Media Desk Event | User-owned časová interpretace Session relací a ručních výjimek | **IMPLEMENTOVÁNO, NENÍ PROJEKT** |
| Normalizer | Explicitní immutable read-only snapshot; nečte Media Desk user data | **IMPLEMENTOVÁNO, PROCESSOR-OWNED** |

### 2.2 Studio v0.1

`StudioState` obsahuje pouze `workspaceId`, `projectId`, `selectedMediaIds` a
`activeModuleId`. Změna projektu smaže výběr; změna workspace smaže projekt i
výběr. Přepnutí modulu výběr zachová. To je správný základ pro dočasný kontext.

Store ale přijímá libovolný string jako projekt a neověřuje existenci, workspace
ani archivaci. To je v syntetickém prototypu přijatelné, ale produkční stav musí
být validován serverovou projekcí. Po restartu dnes není projektový kontext
perzistentní.

### 2.3 Konflikty prototypu s produkčními kontrakty

1. `MediaSummary.kind` připouští `audio` a `graphic`, zatímco workspace contract
   v1 veřejně podporuje jen `image` a `video`. Jde o demo abstrakci, nikoli
   důkaz podpory těchto katalogových typů.
2. `MediaSummary.projectIds` je pohodlná reverzní projekce, ale autoritativní
   vztah nesmí být zapisován do assetu nebo veřejného katalogu.
3. `ProjectSummary.mediaCount` je odvozená hodnota a v produkčním modelu se má
   počítat dotazem; uložená kopie by se mohla rozcházet s vazbami.
4. Syntetická ID jako `project-tour` nejsou návrh stabilní produkční identity.
5. `StudioDataSource` je pouze read port. Chybí command port, revize a konflikt.

### 2.4 Identity, které již existují

- `workspace_id` je UUID vytvořené jednou při inicializaci workspace.
- `asset_id` je deterministicky `sha256:<64 lowercase hex>` a identifikuje obsah.
- dvě stejné fyzické kopie mají stejné asset ID;
- přejmenování nebo přesun stejného obsahu asset ID nemění;
- změna bajtů vytváří jiné asset ID;
- `source_version_id` identifikuje konkrétní zdrojovou verzi/cestu, nikoli médium;
- Session ID je odvozené z membership/timestampů a může se po nové analýze změnit;
- Media Desk Event ID je `event-<uuid4 hex>` a patří do jiného store.

Projekt má odkazovat na obsahové asset ID, nikoli na cestu, source version,
Session ID nebo Normalizer fingerprint. Protože existence obsahu je ověřována
v konkrétním katalogu, úplná reference je logicky `(workspace_id, asset_id)`.
V Project v1 poskytne `workspace_id` projekt a vazba uloží samotné `asset_id`.

### 2.5 Hranice existujících vlastníků

- Ingest vlastní workspace manifest, katalog, metadata a privátní SQLite.
- Procesory vlastní jen `analysis/<processor>/...` a immutable výsledky.
- Media Desk vlastní svůj host-local schema 2 user store.
- Studio musí vlastnit projektové entity a vazby ve vlastním namespace/store.
- Ostatní moduly smějí číst projekci nebo posílat příkazy přes Studio project
  service; nesmějí importovat databázové tabulky ani zapisovat store přímo.

## 3. Architektonická rizika

| Priorita | Riziko | Praktický dopad | Doporučená kontrola |
|---|---|---|---|
| P0 | Neurčený source of truth | Dva moduly mohou zapisovat nekompatibilní vztahy | Jeden Studio project writer a veřejné API |
| P0 | Záměna assetu, cesty a souboru | Přesun nebo offline disk rozbije projekt či připojí špatný obsah | Odkaz `(workspace_id, asset_id)`, cesty pouze jako zdroj/binding |
| P0 | Rozšíření Media Desk store | Smíchání Event a Project lifecycle, konfliktní migrace a ownership | Samostatná Studio DB |
| P1 | Whole-file JSON s mnoha vazbami | Velké přepisy, hrubá revize, obtížná integrita a obnova | SQLite transakce, FK, indexy |
| P1 | Neplatný nebo archivovaný aktivní projekt | Moduly mohou pracovat se stale kontextem | Serverová validace + invalidace kontextu |
| P1 | Automatické odstranění chybějících vazeb | Dočasný offline stav způsobí ztrátu uživatelských dat | Zachovat unresolved link a diagnostiku |
| P1 | Volná absolutní cesta v API | Path traversal, junction escape nebo únik host path | Host-local binding, canonical validation, žádný obecný file endpoint |
| P1 | Zaměnění output artefaktu za katalogové médium | Projekt odkáže ephemeral processor output bez stabilního lifecycle | Explicitní ingest/promotion před katalogovým linkem |
| P2 | Pevné typy a hierarchie bez chování | Předčasné migrace, složité UI a projektový management | Plochý projekt + štítky |
| P2 | Přenos SQLite prostým kopírováním za běhu | Nekonzistentní backup s WAL | SQLite backup API a verzovaný export |

Dalším rizikem je duplicitní `workspace_id` připojené současně z více fyzických
kopií workspace. Registry musí pro jeden profil vyžadovat nejvýše jednu aktivní
binding cestu pro dané workspace ID nebo stav označit jako konflikt.

## 4. Co bych na současném návrhu změnil a proč

### 4.1 Nenavrhovat persistenci podle syntetických DTO

**Problém:** `projectIds` uvnitř media DTO a `mediaCount` uvnitř projektu jsou
obousměrné denormalizované kopie téhož vztahu.

**Důsledek:** každý zápis musí atomicky opravit více dokumentů; při chybě vznikne
jiný počet médií v kartě a jiná membership v knihovně.

**Varianty:** autoritativní pole na médiu, autoritativní pole na projektu, nebo
samostatná relation table.

**Doporučení:** relation table `project_media_link`; `projectIds` a počet médií
generovat pouze jako query projekci.

**Složitost:** nízká ve SQLite, střední až vysoká v JSON.

### 4.2 Projektovou referenci vždy svázat s workspace

**Problém:** samotné `mediaId` neříká, v kterém katalogu je obsah dostupný.
SHA-256 může existovat ve více workspaces a jeden z nich může být offline.

**Důsledek:** globální vyhledávání podle hashe může otevřít jinou fyzickou kopii
nebo vytvořit nejasný stav při přepnutí workspace.

**Varianty:** globální asset registry, explicitní `(workspace_id, asset_id)`, nebo
path-based reference.

**Doporučení:** Project v1 patří právě jednomu workspace a všechny jeho media
links jsou implicitně scoped tímto `workspace_id`. Cross-workspace projekt
odložit do samostatné budoucí vrstvy.

**Složitost:** nízká; současně výrazně zjednoduší integritu a GUI kontext.

### 4.3 Nepoužít Media Desk schema 2 jako projektový store

**Problém:** schema 2 je jeden per-workspace JSON vlastněný Media Deskem a jeho
revize pokrývá názvy, události a assignments.

**Důsledek:** projektový zápis by blokoval či konfliktoval s Event editací,
migrace by spojila dva lifecycles a Studio by převzalo cizí ownership.

**Varianty:** rozšířit schema 2, samostatný Studio JSON, samostatná Studio SQLite.

**Doporučení:** samostatná SQLite. Media Desk může později projekty pouze číst
přes API/projekci, nikoli přímým importem store.

**Složitost:** střední implementace, ale nižší dlouhodobá údržba.

### 4.4 Rozlišit katalogové médium a nekatalogový zdroj

**Problém:** audio, font, designový soubor, URL a pracovní adresář nejsou assety
workspace contract v1. Jejich vložení do `MediaSummary` by předstíralo ingest
podporu a stabilní obsahovou identitu.

**Důsledek:** nejasné preview, dostupnost, kopírování, deduplikace a záloha.

**Varianty:** rozšířit workspace contract, ignorovat nekatalogové soubory, nebo
zavést oddělený `ProjectResource`.

**Doporučení:** v1 ponechat `ProjectMediaLink` pouze pro katalogová image/video
média a přidat úzký external-resource model pro file/directory/URL reference.
Žádný managed attachment store ani implicitní import v první etapě.

**Složitost:** střední; je nutná offline/relink diagnostika, ale ownership zůstane
čitelný. Rozšíření workspace contractu by bylo výrazně složitější.

### 4.5 Doplnit lifecycle a concurrency před write API

**Problém:** návrh má `revision`, ale neurčuje, co ji mění, jak se řeší konflikt,
archivace nebo obnova.

**Důsledek:** dva panely nebo taby si mohou přepsat vazby; archivovaný projekt
může zůstat aktivní a přijímat další média.

**Varianty:** last-write-wins, per-record revisions, nebo aggregate revision.

**Doporučení:** integer revision celého projektového agregátu. Každý command
požaduje očekávanou revizi a v jedné transakci ji zvýší. Konflikt vrátí HTTP 409.
Archivovaný projekt je read-only; restore je explicitní command.

**Složitost:** nízká až střední; pro single-user v1 je aggregate revision
dostatečná a jednodušší než event sourcing.

### 4.6 Nezavádět pevné typy ani strom projektů

**Problém:** „událost“, „kampaň“ a „kreativní projekt“ zatím nemají rozdílná
pravidla. Typ „událost“ se navíc terminologicky střetává s Media Desk Event.

**Důsledek:** enum a parent/child vazby by vytvořily migrace, cykly, dědičnost
oprávnění a navigaci bez ověřené uživatelské hodnoty.

**Varianty:** enum, open vocabulary kind, štítky, nebo žádná klasifikace.

**Doporučení:** ploché projekty a jednoduché štítky. Hierarchii nebo explicitní
project relations přidat až podle reálného scénáře, který nelze vyřešit
mnoho-na-mnoho vazbami médií.

**Složitost:** nízká; štítky vyžadují jen normalizaci a unikátnost uvnitř projektu.

### 4.7 Pracovní adresář chápat jako externí binding, ne vlastnictví

**Problém:** „projekt má adresář“ neříká, zda jej Studio vytváří, spravuje,
zálohuje nebo maže. Absolutní Windows cesta není přenositelná identita.

**Důsledek:** kolize názvů, smazání cizích dat, junction escape, nefunkční export
a falešný dojem, že databázový backup obsahuje i soubory.

**Varianty:** Studio-managed storage, externí reference, nebo kombinace.

**Doporučení:** v1 pouze explicitní host-local externí directory binding.
Studio adresář nevytváří, nerekurzivně neskenuje, nekopíruje ani nemaže. Při
transferu je binding unresolved a uživatel jej znovu naváže.

**Složitost:** nízká pro bezpečný reference-only režim; managed storage odložit.

### 4.8 Validovat aktivní kontext proti serverové projekci

**Problém:** dnešní `setProject` přijme libovolné ID a aktivní stav nezná revizi
ani status.

**Důsledek:** po archivaci v jiném tabu nebo po přepnutí profilu může modul
pracovat se stale projektem a výběrem.

**Varianty:** důvěřovat klientovi, držet celý projekt v globálním store, nebo
držet jen ID a validovat Query projekcí.

**Doporučení:** zachovat ID-only context, ale každé ID resolve přes project query.
Neexistující, archivovaný nebo workspace-mismatched projekt atomicky zruší
aktivní projekt i media selection.

**Složitost:** nízká; navazuje na současné TanStack Query rozhraní.

### 4.9 Co je na současném návrhu dostatečné

Bez zásadní změny je vhodné zachovat:

- Projekt jako samostatný pracovní celek, nikoli přejmenovanou Session/Event;
- mnoho projektů na jedno médium bez fyzické kopie;
- oddělené processor-owned analýzy;
- explicitní import/promote operaci pro nový katalogový obsah;
- společný kontext obsahující pouze stabilní ID;
- reset výběru při skutečné změně projektu a kompletní reset při změně workspace;
- zachování výběru při pouhém přepnutí modulu;
- statický modulový kontrakt a oddělenou doménovou logiku modulů.

## 5. Porovnání variant persistence

### 5.1 Souhrn

| Kritérium | Studio JSON | Studio SQLite + export | Rozšíření Media Desk JSON |
|---|---|---|---|
| Implementační start | nejjednodušší | střední | zdánlivě jednoduchý |
| Atomické změny více vazeb | celý soubor | nativní transakce | celý sdílený soubor |
| Relační integrita | pouze aplikační kód | FK, UNIQUE, CHECK | aplikační kód |
| Concurrency | globální revize | aggregate revision + transakce | konflikt s Event revizí |
| Rostoucí počet vazeb | whole-file rewrite | indexované dotazy | whole-file rewrite |
| Migrace | ruční transformace dokumentu | transakční schema migrations | spojení dvou domén |
| Backup | snadná kopie v klidu | backup API / portable export | kopie, ale míchá data Media Desk |
| Poškození | může ztratit celý store | integrity check + page backup | ohrozí i názvy a Events |
| Přenositelnost | dobrá | export dobrý; DB také přenositelná v klidu | vázaná na Media Desk profil |
| Budoucí rozšíření | rychle křehne | dobré | nejhorší ownership |

### 5.2 Varianta A — samostatný Studio JSON

**Silné stránky:** velmi čitelný, snadno exportovatelný, navazuje na existující
atomic-replace vzor. Pro malý single-user prototyp je zcela dostačující.

**Slabé stránky:** každá změna přepisuje projekty i vazby; unikátnost a FK jsou
jen ruční validace; globální revize způsobuje zbytečné konflikty; částečná obnova
po poškození je obtížná.

**Migrační riziko:** s růstem modelu vzniká jeden velký dokument a pozdější
přechod do DB musí rozdělit embedded collections bez ztráty revizí.

**Údržba a rozšiřitelnost:** nízká zpočátku, střední až vysoká po přidání tags,
resources, archive filtrů a stránkování.

**Verdikt:** vhodné pro demo, nikoli preferované pro Project v1.

### 5.3 Varianta B — samostatná Studio SQLite + JSON export

**Silné stránky:** transakce, foreign keys, uniqueness, indexy, stránkování,
bezpečné batch linking, transakční migrace a cílené revize. DB nezasahuje do
workspace ani Media Desk ownership.

**Slabé stránky:** potřebuje migration runner, backup postup a recovery
diagnostiku. SQLite soubor nesmí mít více writer procesů ani být podporován na
SMB/NFS jen proto, že se dá cesta otevřít.

**Migrační riziko:** dnes minimální, protože produkční projektová data neexistují.
Budoucí schema changes musí být testované na kopiích a před migrací zálohované.

**Údržba a rozšiřitelnost:** střední počáteční náklad, nízký až střední dlouhodobě.
Dobře podporuje vazby, tags, resources a query API bez změny workspace v1.

**Verdikt:** **doporučená varianta**.

### 5.4 Varianta C — rozšíření Media Desk user store

**Silné stránky:** jedna existující cesta, atomic write a revision mechanismus.

**Slabé stránky:** porušuje vlastnictví, spojuje životní cyklus Events a Projects,
zvětšuje soubor, sdílí revizi a komplikuje budoucí samostatné Studio.

**Migrační riziko:** vysoké; chyba projektové migrace by mohla poškodit existující
názvy, event intervals a assignments.

**Údržba a rozšiřitelnost:** vysoká, protože každý modul musí znát Media Desk
schema a jeho deployment.

**Verdikt:** nedoporučeno.

### 5.5 Rozhodující argument pro SQLite

Nejde primárně o počet projektů. Rozhodující je, že Project je relační agregát
s vazbami mnoho-na-mnoho, batch změnami, archivací, optimistic concurrency a
požadavkem na obnovu. SQLite tyto invarianty poskytne přímo. JSON zůstává vhodný
pro explicitní export/import a lidsky čitelný recovery artefakt.

## 6. Doporučený Project v1 kontrakt

Vše v této kapitole je **DOPORUČENÍ ČEKAJÍCÍ NA SCHVÁLENÍ**.

### 6.1 Entity a identifikátory

#### Project

| Pole | Pravidlo |
|---|---|
| `project_id` | serverem vytvořené `project-<uuid4 hex>`, immutable |
| `workspace_id` | povinné UUID existujícího/registrovaného workspace, immutable v1 |
| `title` | 1–240 znaků, trim, bez control chars, není unikátní |
| `description` | krátký volitelný text s limitem |
| `notes` | volitelný delší plain text s limitem |
| `status` | `active` nebo `archived` |
| `revision` | integer začínající 1; zvýší se při každé změně agregátu |
| `created_at`, `updated_at` | UTC timestamps generované serverem |
| `archived_at` | UTC timestamp právě tehdy, když je status archived |

ID se nikdy neodvozuje z názvu, typu, adresáře ani data. Přejmenování nemění ID.
Názvy nejsou unikátní; UI je rozliší štítky, stavem a krátkým ID.

#### ProjectTag

Jednoduchý display label plus case-folded normalized key unikátní v projektu.
Tag nemění chování aplikace. Pevný project type enum v1 nemá.

#### ProjectMediaLink

| Pole | Pravidlo |
|---|---|
| `project_id` | FK na Project |
| `asset_id` | `sha256:<64 hex>`; PK společně s project ID |
| `role` | `source`, `reference` nebo `deliverable`; default `reference` |
| `note` | volitelná poznámka specifická pro vazbu |
| `position` | volitelné stabilní pořadí, ne identita |
| `created_at`, `updated_at` | serverové UTC timestamps |

Role je kontextová: stejné video může být deliverable v projektu A a source v
projektu B. Jeden asset má v jednom projektu jednu primární roli. Další významy
lze vyjádřit poznámkou nebo pozdějšími tags, ne duplicitními řádky.

#### ProjectResource

Nekatalogová reference pro `external_file`, `external_directory` nebo `url`.
Má vlastní `resource_id`, display name, role, notes a volitelný content hash.
Není vydávána za workspace asset a nemá processor výsledky.

Host-specific file/directory locator patří do odděleného binding záznamu. Export
může přenést resource metadata a checksum, ale absolutní path se na novém hostu
neaktivuje bez explicitního relink. Jeden resource s rolí `working_directory`
smí být pro projekt aktivní nejvýše jednou.

### 6.2 Doporučená relační struktura

```mermaid
erDiagram
  PROJECT ||--o{ PROJECT_TAG : has
  PROJECT ||--o{ PROJECT_MEDIA_LINK : references
  PROJECT ||--o{ PROJECT_RESOURCE : owns_metadata_for
  PROJECT_RESOURCE ||--o{ RESOURCE_BINDING : resolves_on_host

  PROJECT {
    text project_id PK
    text workspace_id
    text title
    text status
    integer revision
    text created_at
    text updated_at
    text archived_at
  }
  PROJECT_MEDIA_LINK {
    text project_id PK_FK
    text asset_id PK
    text role
    text note
    integer position
  }
  PROJECT_RESOURCE {
    text resource_id PK
    text project_id FK
    text kind
    text role
    text display_name
    text content_sha256
  }
  RESOURCE_BINDING {
    text resource_id PK_FK
    text profile_key PK
    text locator
    text last_verified_at
  }
```

Minimální indexy: `(workspace_id, status, updated_at)`, media links podle
`asset_id`, tags podle normalized key a resources podle project ID.

### 6.3 Pravidla integrity

1. Projekt patří právě jednomu workspace; `workspace_id` se v1 nemění.
2. Nový media link lze přidat jen po validaci asset ID v aktuálním katalogu
   stejného workspace.
3. Pozdější chybějící nebo unavailable asset link nemaže; query vrátí
   `unresolved|catalog_unavailable|original_offline` diagnostiku.
4. Změna bajtů vytvoří nový asset. Přesměrování staré vazby je explicitní command,
   nikdy automatická heuristika podle názvu/cesty.
5. Projektový store nikdy nezapisuje do workspace, Media Desk JSON ani analysis.
6. Každý write ověří očekávanou revision a proběhne v jedné DB transakci.
7. Archivovaný projekt je read-only kromě restore; nelze jej nastavit jako aktivní.
8. Archivace, restore ani budoucí odstranění projektu nemění assety, analysis,
   externí soubory nebo pracovní adresář.
9. Hard delete není součástí Project v1. Recovery probíhá restore z archivu.
10. DB běží na lokálním filesystemu s jedním writer procesem.

### 6.4 Archivace, obnovení a duplikace

- Archive nastaví status, `archived_at`, `updated_at` a zvýší revision.
- Restore vrátí active, smaže `archived_at` a zvýší revision.
- Archivovaný projekt zůstává čitelný a zachovává všechny links/resources.
- Duplicate vytvoří nové project ID, revision 1 a active stav; zkopíruje metadata,
  tags a media links. Nekopíruje soubory ani host-local directory bindings.
- Full project history/versioning není v1. Revision je concurrency token, ne
  audit log. Pravidelné backupy řeší obnovu; audit trail je případná další etapa.

### 6.5 Základní API

| Metoda a cesta | Účel |
|---|---|
| `GET /api/studio/workspaces/{workspace_id}/projects` | list/filter active/archived |
| `POST /api/studio/workspaces/{workspace_id}/projects` | vytvořit prázdný projekt |
| `GET /api/studio/projects/{project_id}` | detail + revision + odvozené počty |
| `PATCH /api/studio/projects/{project_id}` | rename/notes/tags s `If-Match` |
| `POST /api/studio/projects/{project_id}/archive` | explicitní archive command |
| `POST /api/studio/projects/{project_id}/restore` | explicitní restore command |
| `POST /api/studio/projects/{project_id}/duplicate` | nová identita bez kopie souborů |
| `GET /api/studio/projects/{project_id}/media` | batch-resolved media + unresolved položky |
| `POST /api/studio/projects/{project_id}/media-links` | batch link validovaných asset IDs |
| `PATCH /api/studio/projects/{project_id}/media-links/{asset_id}` | role/note/order |
| `DELETE /api/studio/projects/{project_id}/media-links/{asset_id}` | odstranit pouze vazbu |
| `GET/POST/PATCH /api/studio/projects/{project_id}/resources...` | explicitní external refs/relink |

Mutace přijímají očekávanou revision (`If-Match` nebo jedno konzistentní pole),
vracejí novou revision a při konfliktu HTTP 409. API nesmí přijímat klientem
vytvořené timestamps, odvozené counts ani arbitrary SQL/paths.

### 6.6 Persistence, migrace a backup

- Umístění: Studio-owned profile data root, nikoli checkout ani workspace.
- SQLite: `foreign_keys=ON`, `busy_timeout`, WAL na podporovaném lokálním FS,
  `synchronous=FULL`; jediný backend writer.
- Schema version: explicitní migration table nebo `user_version`; každá migrace
  v transakci a po bezpečné záloze.
- Startup: kontrola schema, foreign keys a přiměřený `quick_check`; chyba fail-safe
  zakáže writes, nikoli automatickou destruktivní opravu.
- Backup: SQLite backup API/VACUUM INTO při běžícím procesu; ne prosté kopírování
  hlavního souboru bez WAL.
- Portable export: verzovaný JSON manifest projektů, tags, links a resource
  metadata. Neobsahuje média ani secrets; host paths jsou vynechány nebo pouze
  neaktivní hints.
- Import nejprve validuje schema a workspace ID, potom transakčně vytvoří nové
  lokální záznamy. Konflikt project ID vyžaduje explicitní strategii.

## 7. Uživatelské scénáře

| Scénář | Chování doporučeného modelu |
|---|---|
| Koncert s plakáty, hudbou, fotkami, videi a reels | Image/video assets jsou media links; hudba/fonty/design files jsou external resources, dokud explicitní ingest nepodporuje jejich typ. Reels po explicitním ingestu mohou být deliverable link. |
| Logo EMtone ve dvaceti projektech | Dvacet relation rows na jedno asset ID, žádná kopie obsahu. |
| Kampaň s několika koncerty | Plochý campaign projekt může sdílet média s jednotlivými concert projekty. Není nutný parent/child strom. Existing Events zůstávají oddělené. |
| Projekt bez média | Validní active projekt s nulou links; žádný placeholder asset. |
| Jedno video ve třech projektech | Tři links se samostatnou rolí/poznámkou. |
| Externí disk odpojen | Links zůstávají; metadata/preview mohou fungovat, origin hlásí offline. Žádný auto-delete. |
| Přejmenování/přesun souboru | Po ingest refresh zůstává stejné obsahové asset ID. External resource path vyžaduje relink. |
| Archivace projektu | Projekt a vazby jsou read-only; média zůstávají beze změny a dostupná jiným projektům. |
| Výsledek se stane zdrojem jiného projektu | Po explicitním ingest/promotion má asset ID; v projektu A může být deliverable, v B source. |
| Přenos nebo záloha | DB backup chrání lokální stav; portable JSON přenese metadata/IDs, ne média. Na cíli se ověří stejné workspace ID a relinknou externí paths. |

### Další přehlédnuté scénáře

- Dvě fyzické kopie workspace se stejným `workspace_id` jsou současně připojené.
- Asset zmizí z nového katalogového snapshotu, ale projekt jej stále potřebuje.
- Soubor je upraven in-place a nový hash má podobný název jako starý.
- Projekt je archivován v jiném tabu právě během batch link operace.
- Dva projekty mají stejný název a jeden je archivovaný.
- Backup proběhne za běhu WAL transakce.
- Importovaný projekt odkazuje na neznámý workspace nebo assety.
- Working directory se změní na junction/symlink nebo uživatel ztratí oprávnění.
- Jedna external resource reference se přestěhuje na jiný host.
- Uživatel chce odstranit vazbu, nikoli fyzický soubor — UI musí tyto akce
  terminologicky i potvrzením rozlišit.

## 8. Integrace s GUI orchestrátorem

### 8.1 Aktivní projekt a knihovna

1. Workspace query načte registrovaný workspace.
2. Project query vrátí pouze projekty tohoto workspace.
3. Nastavení active project přijme jen existující active projekt se stejným
   workspace ID.
4. Media Library načte relation IDs a jedním batch resolution dotazem je spojí
   s aktuálním Media Desk/workspace snapshotem.
5. Chybějící asset se zobrazí jako unresolved položka, nevynechá se potichu.

Shell má dál uchovávat jen ID. Celý Project nebo katalog nepatří do Zustand.
TanStack Query drží serverové projekce a invaliduje je po příkazu.

### 8.2 Dočasný výběr

- Pouhé přepnutí modulu výběr zachová.
- Změna projektu nebo workspace výběr atomicky smaže.
- Po změně membership na serveru se selection intersectuje s aktuálními asset IDs.
- Archivace/zmizení aktivního projektu smaže project ID i selection.
- Po restartu je media selection vždy prázdný.

### 8.3 Stav po restartu

Volitelně lze uložit poslední `workspace_id`, `project_id` a route jako uživatelskou
preferenci. Při startu je backend musí znovu validovat. Pokud workspace není
registrovaný nebo projekt není active, obnoví se pouze bezpečný null kontext.
Dočasný výběr se neobnovuje.

### 8.4 Přístup ostatních modulů

Ostatní moduly používají veřejné `ProjectQueryPort` a `ProjectCommandPort`.
Project service je jediný writer. Moduly nemají přístup k SQLite ani interním
ORM/dataclass objektům. Read projection může obsahovat projekt, revision,
membership IDs a odvozené counts; commands musí být explicitní a idempotentní,
kde je to praktické.

## 9. Bezpečnost a integrita

### 9.1 HTTP a writer

- loopback-only hostování, validace Host/Origin a CSRF pro všechny writes;
- omezení body size, počtu batch IDs a délek textu;
- striktní parsing project/asset/resource ID;
- žádné přijímání absolutní path v obecném media-link endpointu;
- žádné automatické spouštění ingestu při vytvoření linku;
- logování operation ID a konfliktů bez citlivých cest.

### 9.2 SQLite

- data root s uživatelskými oprávněními; databáze není v Git;
- lokální filesystem a jeden writer process; network filesystem nepodporovat
  bez samostatného ověření;
- parametrizované SQL, FK, CHECK, UNIQUE a transakce;
- backup před migrací, recovery pouze explicitně z validované zálohy;
- poškozenou DB automaticky nepřepisovat prázdnou.

### 9.3 Cesty a pracovní adresář

- binding vzniká pouze explicitním výběrem uživatele;
- server ukládá host-local locator, browser nedostane obecný filesystem endpoint;
- před každým čtením/otevřením se znovu ověří canonical path a oprávnění;
- případné servírování souboru vyžaduje request-scoped containment a ochranu
  proti symlink/junction escape;
- archive, duplicate a remove project nikdy nemažou ani nekopírují directory;
- databázový backup výslovně netvrdí, že zálohoval external resources.

### 9.4 Nedostupnost médií

Je nutné rozlišovat:

- asset není v aktuálním katalogu;
- asset je v katalogu jako unavailable;
- metadata/preview existují, ale origin je offline;
- external resource binding chybí nebo je nedostupný;
- workspace jako celek není připojený.

Žádný z těchto stavů sám o sobě nesmí smazat project link. Uživatelský command
remove-link je jediný běžný způsob odstranění vazby.

## 10. Otevřené otázky vyžadující rozhodnutí

1. **Persistence:** schválit Studio-owned SQLite + JSON export, nebo přijmout
   omezení samostatného JSON store.
2. **Workspace scope:** potvrdit, že Project v1 patří právě jednomu workspace a
   cross-workspace projects jsou mimo rozsah.
3. **ID a názvy:** potvrdit `project-<uuid4 hex>` a neunikátní názvy.
4. **Lifecycle:** potvrdit archive/restore bez hard delete v1.
5. **Klasifikace:** potvrdit ploché projekty se štítky, bez enum typů a hierarchie.
6. **Externí zdroje:** rozhodnout, zda Project v1 zahrne external resources hned,
   nebo zda první etapa podporuje jen katalogová média a working directory.
7. **Working directory:** potvrdit reference-only host-local binding bez správy
   obsahu, automatického scan/copy/delete.
8. **Přenositelnost:** určit, zda portable export přenáší pouze metadata a IDs,
   nebo zda je požadován samostatný managed attachment bundle.
9. **Datový root/profile:** určit vazbu Studio DB na budoucí Launcher/Studio profil
   a politiku více workspace v jednom procesu.
10. **Obnova posledního kontextu:** potvrdit obnovu validovaného workspace/project,
    ale vždy prázdný temporary media selection.

## 11. Navržené implementační etapy

### Etapa P0 — rozhodnutí a executable contract

- schválit výše uvedené otevřené body;
- zapsat nové ADR až po schválení;
- definovat API schemas, error codes, revision semantics a failure matrix;
- připravit testy identity, archive, conflict, missing asset a forbidden writes.

### Etapa P1 — Project core bez GUI write složitosti

- Studio-owned SQLite schema, migrace, integrity check a backup API;
- Project create/list/detail/rename/archive/restore;
- ProjectMediaLink batch add/remove/update s validací workspace katalogu;
- unresolved asset projection;
- žádný working directory writer ani managed attachments.

### Etapa P2 — napojení prototypu

- nahradit synthetic project source skutečným query adapterem;
- Projects modul: create/select/rename/archive s revizními konflikty;
- Media Library: project-filter projection a batch link/unlink;
- revalidace aktivního kontextu a restartové preference;
- zachovat stávající Media Desk a procesory beze změny.

### Etapa P3 — externí resources a portability

- external file/directory/URL references a host-local relink;
- bezpečný working directory binding;
- verzovaný JSON export/import a dokumentovaný backup/restore;
- teprve podle praxe posoudit managed attachment store.

### Etapa P4 — až podle důkazů z používání

- explicitní project relations nebo hierarchy;
- historie změn/audit log;
- cross-workspace collection;
- další katalogové typy médií;
- multi-user service a síťový writer.

Tyto funkce nejsou implicitním cílem Project v1.

## 12. Doporučený první implementační krok

Po schválení architektury implementovat nejprve **Project core service nad lokální
SQLite**: create/list/detail/archive/restore, revision conflict a vazbu na existující
asset IDs jednoho workspace. Bez pracovních adresářů, external resources,
hierarchie a bez změny Media Desk. Tato nejmenší etapa ověří rozhodující invarianty
a současně nevytvoří druhý katalog ani nový storage lifecycle.
