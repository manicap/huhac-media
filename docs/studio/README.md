# HUHÁČ Studio v0.1 – vývojový prototyp

**Stav k 2026-10-28:** **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO** na větvi
`feature/studio-shell`. Nejde o produkční náhradu Media Desk ani o nový writer
workspace.

Studio obsahuje React/TypeScript shell se dvěma nezávislými moduly: **Projekty**
a **Mediální knihovna**. Produkční adapter čte katalog a zapisuje projekty přes
Project Core API. Zustand drží pouze ID pracovního kontextu; serverová data
spravuje TanStack Query. Syntetická data zůstávají pouze v testech. Studio nikdy
nezapisuje workspace, Media Desk user store, mediální soubory ani výstupy procesorů.

## Spuštění

Požadavky: aktuální Node.js a npm a Python prostředí s `.[studio]`. Z kořene
worktree pro vývoj se dvěma procesy:

```powershell
cd studio
npm install
npm run dev
```

V druhém terminálu spusťte Project Core na portu 8878; Vite proxy předává `/api`:

```powershell
huhac-studio --workspace 'D:\Media\_processing'
```

Vite poslouchá pouze na `http://127.0.0.1:5173`. Produkční ověření:

```powershell
npm test
npm run build
```

Výstup buildu vznikne v ignorovaném `studio/dist/`.

Po buildu lze použít jednodušší single-origin provoz:

```powershell
huhac-studio --workspace 'D:\Media\_processing' --frontend studio/dist
```

Studio je potom na `http://127.0.0.1:8878/` a FastAPI obsluhuje i `/api`.

## Funkční scénář

1. Modul Projekty vytváří, vybírá, upravuje, archivuje a obnovuje skutečné projekty.
2. Mediální knihovna přepíná mezi celým katalogem a médii aktivního projektu.
3. Vybraná katalogová média lze připojit a vazby lze odebrat bez změny souborů.
4. Výběr médií přežije přepnutí mezi moduly; změna projektu nebo workspace jej smaže.
5. Write operace používají aktuální revision přes `If-Match`; konflikt 409 je
   zobrazen česky a nabízí načtení aktuální verze.
6. Navigace sama neprovádí žádný doménový ani trvalý zápis.
7. Karty zachovávají poměr stran média, zobrazují typ, rozlišení, délku a
   stav katalogového odkazu na originál. Stav `Neověřený` je záměrně lazy:
   skutečná dostupnost souboru se ověří až po Play. Video se potom přehrává
   nativním HTML5 přehrávačem přímo v kartě; další Play předchozí přehrávač ukončí.
8. Hlasitost a mute jsou sdílené mezi videi a ukládají se do `localStorage`;
   výchozí hlasitost je 50 %. Odchod z knihovny, změna projektu/workspace nebo
   přepnutí datasetu přehrávání ukončí.
9. Galerie používá lehké justified flex řádky. Zdrojové i DOM pořadí je zároveň
   vizuálním pořadím zleva doprava a následně shora dolů. Skutečný poměr stran
   určuje šířku karty a náhled se neořezává; pohodlná a kompaktní hustota mění
   cílovou výšku řádku a mezery, nikoli obsah na nečitelnou miniaturu.
10. Po výběru médií je při scrollování trvale dostupná kontextová lišta s počtem,
    přidáním/odebráním a zrušením výběru. Při aktivním videu se lišta přesune k
    hornímu okraji pracovní plochy, aby nepřekryla nativní ovládání přehrávače.

Panely registrovaných modulů zůstávají během navigace připojené, takže lokální
UI stav (například filtr projektů nebo hustota knihovny) zůstane zachovaný.
Každý panel chrání samostatný error boundary; chyba jednoho modulu nesloží shell.

## Struktura frontendu

```text
studio/
  src/app/                  shell, statický registr, modulový kontrakt
  src/context/              Zustand store pracovního kontextu
  src/data/                 Project Core API adapter a syntetická testovací data
  src/playback/             browser-local preference hlasitosti a mute
  src/modules/projects/     veřejný vstup, komponenta a testy Projektů
  src/modules/media-library/ veřejný vstup, komponenta a testy knihovny
  src/test/                 společný testovací harness
```

Podrobný audit a hranice jsou v [ARCHITECTURE.md](ARCHITECTURE.md), veřejné
rozhraní modulů v [MODULE_CONTRACT.md](MODULE_CONTRACT.md) a schválený cílový
projektový kontrakt v [PROJECT_CONTRACT.md](PROJECT_CONTRACT.md). Výsledky
ověření jsou v [VERIFICATION.md](VERIFICATION.md).

## Omezení

- **IMPLEMENTED:** Project Core FastAPI, Studio-owned SQLite, funkční React moduly,
  katalogová projekce a single-origin hostování buildu;
- **ABSENT:** více současně připojených workspace v jednom backendu;
- **ABSENT:** autentizace, synchronizace, procesor orchestrace a realtime stavy;
- **ABSENT:** detail média, pokročilé filtry, dynamický plugin loader a Scene Forge;
- **ABSENT:** virtualizace velké galerie; implementované flex řádky záměrně
  neměří DOM a nenačítají položky virtuálně. Chronologie je jednoznačná, ale
  portrétní karta může dosáhnout minimální šířky 150 px a poslední řádek může
  ponechat volné místo. Budoucí stránkování či virtualizace proto mohou vyžadovat
  jiný lehký layout;
- **ABSENT:** transcoding a fallback kodeky. Nepodporovaný formát/kodek hlásí
  přehrávač uživateli; originál se nikdy nekopíruje ani nemění;
- **ABSENT:** integrace Launcheru.

## Doporučená další etapa

Multi-workspace registry, Launcher integrace a rozšířené katalogové filtry
zůstávají samostatnými dalšími etapami.

## Project Core v1

Po instalaci `.[studio]` lze samostatný loopback writer spustit nad jedním
validovaným workspace:

```powershell
huhac-studio --workspace 'D:\Media\_processing'
```

Výchozí databáze je na Windows v
`%LOCALAPPDATA%\HUHAC\Studio\projects.sqlite3`; lze ji explicitně změnit přes
`--database`, ale CLI odmítne umístění uvnitř media workspace. Backend poslouchá
na `127.0.0.1:8878`, odmítá non-loopback bind a drží host-level writer lock po
celý život procesu. Připojený workspace čte veřejným Media Desk adaptérem;
workspace ani Media Desk user data nezapisuje.

Bez `--workspace` se backend spustí v bezpečném offline režimu. Existující
projekty a vazby zůstanou uložené v SQLite, ale frontend žádný uložený workspace
automaticky neaktivuje: nezobrazí katalog, aktivní projekt ani dočasný výběr.
Session jej označí jako offline evidenci. Vytvoření projektu a přidání nové media
link je odmítnuto, dokud není katalog připojen.

Každý backendový proces má právě jeden autoritativní runtime profil. Bezpečné
přepnutí proto znamená zastavit Studio, spustit je znovu s workspace vybraného
profilu a otevřít port této instance. Hlavička vždy ukazuje `Online · <workspace_id>`
nebo `Offline · bez aktivní knihovny`; hodnota pochází z
`GET /api/studio/session`, ne z browserové preference. Produkční build má být
hostován stejným FastAPI procesem přes `--frontend studio/dist`.

Při samostatném Vite vývoji proxy standardně míří na `http://127.0.0.1:8878`.
Jiný lokální Studio port musí být vybrán explicitně před startem Vite:

```powershell
$env:HUHAC_STUDIO_API_TARGET = 'http://127.0.0.1:<studio-port>'
npm run dev
```

Proměnná přijímá pouze loopback HTTP URL. Bez tohoto nastavení by jedna Vite
záložka nadále komunikovala s instancí na výchozím portu bez ohledu na to, který
jiný profil byl spuštěn.

Write API vyžaduje session CSRF token z `GET /api/studio/session`, shodný
`X-CSRF-Token`, loopback Host, shodný Origin a pro změny existujícího agregátu
také `If-Match` s integer revision. Konzistentní backup vytvoří
`POST /api/studio/maintenance/backup` uvnitř Studio profile rootu bez přijetí či
vrácení host path.
