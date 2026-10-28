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

Panely registrovaných modulů zůstávají během navigace připojené, takže lokální
UI stav (například filtr projektů nebo hustota knihovny) zůstane zachovaný.
Každý panel chrání samostatný error boundary; chyba jednoho modulu nesloží shell.

## Struktura frontendu

```text
studio/
  src/app/                  shell, statický registr, modulový kontrakt
  src/context/              Zustand store pracovního kontextu
  src/data/                 Project Core API adapter a syntetická testovací data
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
projekty a vazby zůstanou čitelné s katalogovou diagnostikou, zatímco vytvoření
projektu a přidání nové media link je odmítnuto, dokud není katalog připojen.

Write API vyžaduje session CSRF token z `GET /api/studio/session`, shodný
`X-CSRF-Token`, loopback Host, shodný Origin a pro změny existujícího agregátu
také `If-Match` s integer revision. Konzistentní backup vytvoří
`POST /api/studio/maintenance/backup` uvnitř Studio profile rootu bez přijetí či
vrácení host path.
