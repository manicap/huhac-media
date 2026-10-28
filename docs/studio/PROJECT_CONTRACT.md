# Project Core v1 — schválený kontrakt

**Stav:** **ACCEPTED + IMPLEMENTED 2026-10-28 (TASK-STUDIO-004)**. Tento dokument
definuje závaznou hranici v1; důkazy jsou v `src/huhac_studio` a `tests/studio`.

Projekt je Studio-owned pracovní celek. Není Media Desk Event, Session Grouper
Session, workspace ani fyzický adresář. Jeden projekt patří právě jednomu
`workspace_id` a může odkazovat libovolný počet katalogových médií bez kopie
originálu. Stejné médium může být v několika projektech.

## Vlastnictví a persistence

- Source of truth je samostatná SQLite v host-local Studio profile data rootu,
  nikdy v checkoutu ani uvnitř processor-owned workspace.
- Databázi zapisuje jediný autoritativní FastAPI Project service. Ostatní moduly
  používají jeho query/command API a SQLite přímo neotevírají.
- Project service nikdy nezapisuje Media Desk user store, veřejný katalog,
  ingest SQLite ani `analysis/<processor>/`.
- SQLite běží na lokálním filesystemu s `foreign_keys=ON`, `busy_timeout`, WAL,
  `synchronous=FULL`, verzovanými migracemi a kontrolou integrity při startu.
- JSON není primární store. Přenosný JSON export/import je odložen do další etapy.

## Project

| Pole | Pravidlo |
|---|---|
| `project_id` | serverem generované `project-<uuid4 hex>`, immutable |
| `workspace_id` | povinné ID jednoho registrovaného workspace, immutable v1 |
| `title` | trimovaný plain text 1–240 znaků; názvy nejsou unikátní |
| `description` | volitelný plain text, nejvýše 2 000 znaků |
| `notes` | volitelný plain text, nejvýše 20 000 znaků |
| `tags` | ploché display labels; case-folded klíč je unikátní v projektu |
| `status` | `active` nebo `archived` |
| `revision` | integer od 1; zvýší se při každé změně agregátu |
| `created_at`, `updated_at` | serverové UTC timestampy |
| `archived_at` | UTC timestamp právě tehdy, když je projekt archived |

Projekt v1 nemá povinný typ, enum klasifikaci, hierarchii ani parent/child vazbu.
Archivovaný projekt je read-only kromě explicitního restore. Hard delete není
součástí v1. Archive i restore zachovají všechny vazby a nikdy nemění média.

## ProjectMediaLink

| Pole | Pravidlo |
|---|---|
| `project_id` | FK na Project |
| `asset_id` | `sha256:<64 lowercase hex>`; s project ID tvoří identitu vazby |
| `role` | `source`, `reference` nebo `deliverable`; default `reference` |
| `note` | volitelný plain text nejvýše 2 000 znaků |
| `position` | volitelné nezáporné stabilní pořadí; není identita |
| `created_at`, `updated_at` | serverové UTC timestampy |

Nová vazba se vytvoří pouze po ověření assetu v aktuálním katalogu stejného
workspace. Pozdější zmizení assetu, unavailable stav katalogu nebo offline
originál vazbu nesmaže. Query vrací diagnostický stav; odstranění vazby provede
jen explicitní command. Změna bajtů znamená nové `asset_id` a nepřesměruje
existující vazbu automaticky.

Project metadata a existující links zůstávají čitelné i bez připojeného katalogu.
V offline režimu nelze vytvořit nový projekt pro neověřený workspace ani přidat
novou media link.

Audio, fonty, designové soubory a jiné nekatalogové položky nejsou vydávány za
workspace asset. External resources, pracovní adresáře a jejich host-local
bindingy jsou odloženy do další etapy.

## Revize a transakce

Každá mutace existujícího projektu vyžaduje očekávanou integer revision. Při
neshodě se nic nezapíše a API vrátí HTTP 409 s aktuální revizí. Změna projektu,
tagů nebo media links proběhne v jedné SQLite transakci a zvýší revision právě
jednou. Revision je concurrency token, nikoli audit log nebo historie verzí.

## Veřejná API v1

| Metoda a cesta | Účel |
|---|---|
| `GET /api/studio/session` | CSRF relace a dostupné workspace identity |
| `GET /api/studio/workspaces/{workspace_id}/media` | stránkovaná read-only projekce katalogu |
| `GET /api/studio/artifacts/{token}` | autorizované immutable preview katalogu |
| `GET /api/studio/workspaces/{workspace_id}/projects` | list active/archived projektů |
| `POST /api/studio/workspaces/{workspace_id}/projects` | vytvořit active projekt |
| `GET /api/studio/projects/{project_id}` | detail, tags, revision a odvozené počty |
| `PATCH /api/studio/projects/{project_id}` | změnit metadata/tags s revision |
| `POST /api/studio/projects/{project_id}/archive` | archivovat s revision |
| `POST /api/studio/projects/{project_id}/restore` | obnovit s revision |
| `GET /api/studio/projects/{project_id}/media` | vazby s katalogovou diagnostikou |
| `POST /api/studio/projects/{project_id}/media-links` | transakční batch add |
| `PATCH /api/studio/projects/{project_id}/media-links/{asset_id}` | role/note/position |
| `DELETE /api/studio/projects/{project_id}/media-links/{asset_id}` | odstranit pouze vazbu |
| `POST /api/studio/maintenance/backup` | konzistentní SQLite backup do Studio profile rootu |

API nepřijímá klientské ID projektu, timestampy, status při create, odvozené
počty, filesystem paths ani SQL. Write endpointy jsou loopback-only a chráněné
validací Host/Origin, omezením těla a CSRF tokenem.

## Odložené oblasti

- external file/directory/URL resources a pracovní adresář;
- portable JSON export/import a managed attachment bundle;
- hard delete, plná historie, audit log a projektová hierarchie;
- cross-workspace projekty, multi-user writer a síťová SQLite;
- změny Media Desk, Launcheru, workspace contractu nebo procesorů.
