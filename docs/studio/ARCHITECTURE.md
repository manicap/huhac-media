# HUHÁČ Studio – audit a architektura prototypu

## Ověřený stav výchozího systému

Audit byl proveden nad commitem `9b4d8ca284a7b2814061ba13c94243f813ad6ca3`.

| Oblast | Ověřená skutečnost | Důsledek pro Studio |
|---|---|---|
| Media Desk backend | FastAPI načte při startu jeden validovaný `WorkspaceSnapshot`; poskytuje HTML a read-only JSON katalog/detail (`/api/assets`, `/api/assets/{sha256}`, index, locate, calendar). | Katalog lze později obalit read-only adapterem, ale současný proces není multi-workspace Studio backend. |
| Media Desk frontend | Serverové Jinja šablony a vlastní CSS/JavaScript jsou těsně navázané na dnešní stránky a index. | Nepřenáší se mechanicky do Reactu; Media Desk zůstává funkční samostatná aplikace. |
| User data | Media Desk atomicky vlastní lokální JSON schema 2 pro názvy, události, intervaly a ruční přiřazení. | Projekt není událost. Prototyp tento store nečte ani nemění. |
| Sessions a Normalizer | Session je machine-generated časová relace; Normalizer je explicitní immutable read-only startup projekce. | Projekt se z nich automaticky nevytváří a analytická data zůstávají processor-owned. |
| Veřejný workspace | `workspace.json` a katalog v1 jsou hranice mezi ingestem, procesory a konzumenty; asset má stabilní identitu. | Budoucí knihovna může použít existující asset ID bez kopie média a bez změny kontraktu v1. |
| Launcher v0.2 | Profily spouštějí nejvýše jeden přímo vlastněný loopback Media Desk child; cizí proces nepřebírají. | Prototyp Launcher nemění. Budoucí start Studia vyžaduje samostatné rozhodnutí o host procesu. |

### Co lze převzít beze změn

- veřejný workspace contract v1 a stabilní identity médií;
- read-only validační adaptéry Media Desk pro workspace, artefakty a Normalizer;
- FastAPI jako budoucí host statického buildu a úzkých Studio API;
- Launcher ownership, loopback a profilovou izolaci jako bezpečnostní princip.

### Co lze obalit adapterem

- stránkovaný katalog a detail Media Desk pro budoucí read-only knihovnu;
- workspace health a summary;
- serverem autorizované preview/artifact URL.

### Co vyžaduje nové schválené API

- projekt a mnoho-na-mnoho vazba projekt–médium;
- writer, revize, konflikty a záloha projektových dat;
- registry více workspace, pokud má jeden Studio proces přepínat mezi nimi;
- sjednocené API pro provozní stavy a případnou pozdější orchestraci.

Skutečné překážky jsou absence vlastnictví projektových dat a dnešní
single-workspace lifecycle backendu. Analytické procesory, ingest SQLite,
Normalizer snapshoty ani současný Launcher kvůli prototypu měnit není potřeba.

## Implementovaná architektura v0.1

```text
React Router URL
      |
StudioShell -- statický ModuleRegistry -- ModuleErrorBoundary
      |                         |                   |
      +---- Zustand ID context  +--- Projekty      +--- Mediální knihovna
                    |                    \          /
                    +------------- StudioDataSource
                                      |
                     Project Core FastAPI + read-only katalog
                                      |
                     Studio SQLite   workspace contract v1
```

- **React + TypeScript + Vite:** izolovaný frontend a produkční build.
- **React Router:** adresovatelná navigace `/modules/<id>`.
- **Zustand:** malý store s atomickými invarianty resetu; neobsahuje katalogové objekty.
- **TanStack Query:** jednotná asynchronní hranice dat, cache klíče podle workspace a
  projektu, loading/error stavy a snadno vyměnitelný budoucí HTTP adapter. Session
  se načítá bez HTTP cache a znovu při focusu; změna serverového `runtime_id`
  odstraní ostatní Studio query cache.
- **Statický registr:** žádné dynamické načítání kódu ani mikrofrontend runtime.

Shell zná pouze metadata modulů, jejich dostupnost a společný ID kontext. Nezná
pravidla projektového filtrování ani výběru médií. Moduly importují pouze veřejný
context/data kontrakt a nikdy interní komponenty druhého modulu.

## Sdílený kontext

Implementovaný store obsahuje `workspaceId`, `projectId`, `selectedMediaIds` a
`activeModuleId`. Akce store vynucují:

- stejný projekt je no-op;
- jiný projekt atomicky smaže výběr;
- jiný workspace atomicky smaže projekt i výběr;
- změna modulu mění pouze `activeModuleId`;
- média se přenášejí jen stabilními ID.

Velké katalogové objekty a lokální UI stav ve store nejsou. Projektový filtr a
hustota knihovny patří příslušným modulům.

Autoritativní aktivní workspace nastavuje session backendu, nikoliv klientský
picker. Online proces vrací právě připojený katalog jako `active_workspace_id`.
Offline proces vrací `active_workspace_id: null`, i když Studio SQLite obsahuje
projekty jiných workspace; frontend tím atomicky smaže projekt i výběr a uložené
workspace označí pouze jako offline evidenci. Jeden proces nadále nepřepíná
workspace za běhu.

## Stav rozhodnutí

- **ACCEPTED/TARGET:** statický modulární orchestrátor, ID-only společný kontext,
  zachování existujících backendových ownership hranic.
- **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO:** React shell a dva moduly napojené přes úzký
  TypeScript adapter na skutečný Project Core; syntetický adapter zůstává testovací.
- **ACCEPTED + IMPLEMENTED:** Project Core v1 podle D-029: samostatná Studio-owned
  SQLite, jeden FastAPI writer, jeden workspace na projekt, revision conflicts,
  archive/restore a katalogové media links bez kopírování obsahu.
- **IMPLEMENTED:** `src/huhac_studio` poskytuje versioned SQLite, host-level
  single-writer lock, Project service, read-only katalogovou projekci, bezpečné
  preview a origin-video streamy, loopback/CSRF chráněné API, konzistentní SQLite
  backup a volitelné hostování buildu Studia ze stejného originu.
- **IMPLEMENTED:** session rozlišuje `online`/`offline`, nese unikátní runtime ID,
  zakazuje HTTP cache a aktivuje pouze skutečně připojený katalog. Shell zobrazuje
  workspace ID a při změně runtime nebo workspace ruší stale query data, aktivní
  projekt, dočasný výběr a playback.
- **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO:** knihovna zachovává skutečný poměr stran
  katalogových médií, zobrazuje technická metadata a přehrává nejvýše jedno
  explicitně vyžádané video v kartě. Hlasitost a mute jsou browser-local preference;
  přehrávač se ruší při přepnutí videa, datasetu, projektu, workspace nebo modulu.
  Dostupnost katalogového originálu zůstává do prvního lazy požadavku neověřená.
  Originál je zpřístupněn jen neprůhledným katalogovým tokenem a HTTP Range
  endpointem; Studio netranscoduje a nepřijímá filesystem path od klienta.
- **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO:** adaptivní galerie skládá karty do justified
  CSS flex řádků. Zdrojové pole, DOM pořadí, React klíče a ID zůstávají stabilní
  a vizuálně se čtou zleva doprava a následně shora dolů. Poměr média předaný jako
  CSS custom property určuje flex basis bez DOM měření; změna hustoty upraví jen
  cílovou výšku řádku a mezery. Výběr nadále vlastní jediný Zustand
  `selectedMediaIds` kontext. Při neprázdném výběru modul vykreslí pevnou kontextovou
  lištu nad obsahem; běžně je u spodního okraje viewportu, při aktivním videu u
  horního, aby nepřekryla ovládání. Výplň posledního řádku brání nepřirozenému
  roztažení jeho karet; na mobilu se layout přepne do jednoho sloupce. Řešení
  neprovádí DOM měření ani virtualizaci.
- **ABSENT:** registry více současně připojených workspace v jednom procesu,
  virtualizace velké galerie, persistence GUI kontextu a integrace Launcheru.
