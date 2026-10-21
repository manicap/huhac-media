# Media Desk M1.2 – profesionální UI

Datum implementace: 2026-10-21. Výchozí commit: `ae22f857c5da765b307ad9a79835b68e282eaf28`.

## Vlastnictví stylů

- `media-desk.css` obsahuje design tokeny, obecnou typografii, stavy, panely a detail aktiva.
- `shell.css` vlastní topbar, sidebar a rozložení Přehledu, Kalendáře a Časových relací.
- `library.css` vlastní výhradně toolbar, časovou navigaci, hustotu a dlaždice Knihovny.
- `library.js` čte geometrii dlaždic z CSS proměnných `--tile-min`,
  `--tile-row-height` a `--tile-gap`; nemá samostatné natvrdo zadané rozměry.

Základní tokeny definují 52px topbar, 176px otevřený sidebar, 48px sbalenou
lištu, 18px desktopový okraj, jednotné mezery 4–20px, radiusy a neutrální tmavou
paletu. Akcent zůstává dočasně stávající; finální odstín se určí až podle
oficiálního loga dodaného uživatelem.

## Vizuální fixture

Baseline i výsledné screenshoty používají stejný izolovaný workspace v
`output/m1-2-visual/workspace`: 72 syntetických assetů, čtyři poměry stran,
fotografie a videa, online/offline originály, roky 2024–2026 a nedůvěryhodná či
chybějící data. Fixture neobsahuje soukromá ani produkční média.

```powershell
.\.venv\Scripts\python.exe output\m1-2-visual\create_fixture.py
.\.venv\Scripts\python.exe -m media_desk --workspace "output\m1-2-visual\workspace" --host 127.0.0.1 --port 8877
```

Screenshoty před změnou jsou v `output/m1-2-visual/before`, výsledné v
`output/m1-2-visual/after`. Složka `output` je lokální testovací výstup a není
součástí commitu.

## Neuzavřený branding

Oficiální logo HUHÁČ nebylo při této fázi k dispozici. Topbar je připravený pro
malý proporčně zachovaný logo asset, ale zatím používá původní textový název.
Finální branding, barevné sladění a poslední vizuální akceptace zůstávají
blokované dodáním a bezpečnostní kontrolou oficiálního souboru.
