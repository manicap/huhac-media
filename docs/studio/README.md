# HUHÁČ Studio v0.1 – vývojový prototyp

**Stav k 2026-10-27:** **EXPERIMENTÁLNĚ IMPLEMENTOVÁNO** na větvi
`feature/studio-shell`. Nejde o produkční náhradu Media Desk ani o nový writer
workspace.

Studio v0.1 ověřuje statický React/TypeScript shell se dvěma nezávislými moduly:
**Projekty** a **Mediální knihovna**. Veškerá doménová data prototypu jsou
syntetická a žijí pouze v paměti prohlížeče. Prototyp nečte ani nezapisuje
produkční workspace, Media Desk user store, katalog, SQLite nebo výstupy
procesorů.

## Spuštění

Požadavky: aktuální Node.js a npm. Z kořene worktree:

```powershell
cd studio
npm install
npm run dev
```

Vite poslouchá pouze na `http://127.0.0.1:5173`. Produkční ověření:

```powershell
npm test
npm run build
```

Výstup buildu vznikne v ignorovaném `studio/dist/`.

## Funkční scénář

1. Modul Projekty vybere pracovní projekt a uloží pouze jeho stabilní ID.
2. Mediální knihovna ihned zobrazí syntetická média přiřazená projektu.
3. Výběr médií přežije přepnutí mezi moduly.
4. Skutečná změna projektu smaže starý výběr médií.
5. Změna workspace smaže aktivní projekt i výběr.
6. Navigace sama neprovádí žádný doménový ani trvalý zápis.

Panely registrovaných modulů zůstávají během navigace připojené, takže lokální
UI stav (například filtr projektů nebo hustota knihovny) zůstane zachovaný.
Každý panel chrání samostatný error boundary; chyba jednoho modulu nesloží shell.

## Struktura frontendu

```text
studio/
  src/app/                  shell, statický registr, modulový kontrakt
  src/context/              Zustand store pracovního kontextu
  src/data/                 veřejný read-only adapter a syntetická data
  src/modules/projects/     veřejný vstup, komponenta a testy Projektů
  src/modules/media-library/ veřejný vstup, komponenta a testy knihovny
  src/test/                 společný testovací harness
```

Podrobný audit a hranice jsou v [ARCHITECTURE.md](ARCHITECTURE.md), veřejné
rozhraní modulů v [MODULE_CONTRACT.md](MODULE_CONTRACT.md) a pouze navržený
projektový kontrakt v [PROJECT_CONTRACT.md](PROJECT_CONTRACT.md). Výsledky
ověření jsou v [VERIFICATION.md](VERIFICATION.md).

## Omezení v0.1

- **ABSENT:** backend Studia, projektová databáze a projektové write API;
- **ABSENT:** napojení na produkční Media Desk API a více workspace v jednom backendu;
- **ABSENT:** autentizace, synchronizace, procesor orchestrace a realtime stavy;
- **ABSENT:** detail média, pokročilé filtry, dynamický plugin loader a Scene Forge;
- **UNVERIFIED:** integrace produkčního buildu do FastAPI a Launcheru.

## Doporučená další etapa

Nejdříve schválit vlastnictví a perzistenci projektového kontraktu. Potom přidat
úzký FastAPI read-only Studio adapter pro workspace summary a stránkovaný katalog,
aniž by se měnil workspace contract v1. Projektový writer, multi-workspace registry
a úprava Launcheru patří až do samostatných rozhodnutí a úkolů.
