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
paletu. Oficiální logo je bílé, proto zůstává zelená odděleným funkčním akcentem
pro fokus, aktivní navigaci a primární akce; není prezentována jako barva loga.

## Vizuální fixture

Baseline i výsledné screenshoty používají stejný izolovaný workspace v
`output/m1-2-visual/workspace`: 72 syntetických assetů, čtyři poměry stran,
fotografie a videa, online/offline originály, roky 2024–2026 a nedůvěryhodná či
chybějící data. Fixture neobsahuje soukromá ani produkční média.

```powershell
.\.venv\Scripts\python.exe output\m1-2-visual\create_fixture.py
.\.venv\Scripts\python.exe -m media_desk --workspace "output\m1-2-visual\workspace" --host 127.0.0.1 --port 8877
```

Screenshoty před změnou jsou v `output/m1-2-visual/before`, průběžné po redesignu
v `output/m1-2-visual/after` a finální s logem v `output/m1-2-visual/final`.
Složka `output` je lokální testovací výstup a není
součástí commitu.

## Oficiální branding

Oficiální logo dodal uživatel jako `01_huhac_logo.png`. Beze změny obrazových dat
je uloženo jako `src/media_desk/static/huhac-logo.png` a v topbaru se vykresluje
proporčně ve výšce 34 px. Text „Media Desk“ zůstává jako označení produktu;
na úzkých obrazovkách se skrývá, samotné logo zůstává viditelné.

Zdrojový PNG má rozměry 1672 × 941 px, režim RGBA, neobsahuje vložená metadata
a jeho SHA-256 je
`dc4a8d6a9969a0f94a87676e8bb8552238f618b2d9c59edb858e3cd0201d9e66`.
Jde o rastrový soubor bez aktivního obsahu, skriptů nebo externích odkazů.
Právo k použití v projektu vychází z přímého dodání uživatelem; samostatná
licenční deklarace nebyla přiložena.
