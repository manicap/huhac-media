# Media Transfer — integrační smoke test

**Stav:** VERIFIED — Windows, lokální filesystem

**Datum ověření:** 2026-10-23

**Ověřený základ:** `3f046902735e7cdad4b0d5e25fcffa31a7c006b6`

## Rozsah a izolace

Test proběhl pomocí opakovatelného skriptu
`tests/media_connector/integration_smoke.py`. Všechna zdrojová média, Media
Storage, workspace, Connector SQLite i staging byly vytvořeny v novém
dočasném adresáři `huhac-connector-smoke-*`. Po běhu byl celý adresář odstraněn.
Produkční archiv ani uživatelská média nebyly použity.

Ověřený tok byl:

1. read-only preflight a potvrzené `huhac-media init`;
2. read-only `media-connector local-discovery`;
3. read-only Transfer preflight a potvrzený Local Transfer;
4. samostatné spuštění `huhac-media ingest` nad Media Storage;
5. kontrola veřejného katalogu, obrazových náhledů a CAS cest;
6. otevření knihovny přes Media Desk a ověření HTTP Range videa.

## Syntetická média a výsledek

| Vstup | Kanonická přípona CAS | Ingest | Náhled |
|---|---:|---:|---:|
| JPEG + byte-identická kopie pojmenovaná `.jpeg` | `.jpg` | ano | ano |
| PNG | `.png` | ano | ano |
| WebP | `.webp` | ano | ano |
| TIFF | `.tif` | ano | ano |
| AVI/MJPEG | `.avi` | ano | bez obrazového preview |
| MP4/mp4v | `.mp4` | ano | bez obrazového preview |
| MOV/mp4v | `.mov` | ano | bez obrazového preview |
| MKV/MJPEG | `.mkv` | ano | bez obrazového preview |

Devět vstupních souborů vytvořilo osm různých SHA-256 identit, osm fyzických
`payload.*` objektů a osm položek katalogu. Druhý název stejného JPEG byl
vykázán jako `deduplicated_existing`; nevznikla druhá fyzická kopie. Veřejný
`workspace_contract_version` zůstal `1` a všechny aktivní katalogové zdroje
směřovaly do `objects/sha256/`.

Před a po celém toku byl pro každý externí soubor porovnán SHA-256, velikost a
`mtime_ns`. Snapshoty byly shodné: Connector zdroje neupravil, nepřejmenoval,
nepřesunul ani nesmazal.

Media Desk vygenerovaný workspace otevřel úspěšně: `/health`, `/`, `/library` a
`/api/assets` vrátily HTTP 200, API obsahovalo osm médií, obrazový preview
endpoint vrátil HTTP 200 a video Range `bytes=0-99` vrátil HTTP 206 se 100 bajty.

## Skutečné časy jednoho ověřovacího běhu

Měřeno `time.perf_counter()` na lokálním Windows hostu:

| Fáze | Čas |
|---|---:|
| init preflight | 0,683 s |
| init | 1,118 s |
| Local Discovery | 0,428 s |
| Transfer preflight | 0,520 s |
| Transfer | 1,538 s |
| Media Ingest | 13,236 s |
| Media Desk kontrola | 0,692 s |

Časy jsou smoke měření malých syntetických souborů, nikoli kapacitní benchmark.
Nezahrnují síťové úložiště ani cold-cache záruku.

## Použité nástroje a hranice důkazu

- obrazová metadata a náhledy: skutečný ExifTool;
- syntetická videa: OpenCV 5.0.0 s jeho FFmpeg backendem;
- video metadata: izolovaný deterministický `ffprobe` stub vracející platný
  JSON, protože na hostu nebyl dostupný nativní `ffprobe`;
- tvorba video náhledů nebyla požadována ani simulována; konfigurace záměrně
  odkazovala na nedostupný `ffmpeg` a katalog správně ponechal video preview
  jako `null`.

Výsledek tedy ověřuje rozpoznání přípon, content-addressed fyzické uložení,
scanner Ingestu, katalog, obrazové náhledy a přístup Media Desku. Neprokazuje
produkční dekódování video metadat nativním `ffprobe` ani generování video
keyframes. Dřívější cílený automatický integrační test navíc pokrývá JPEG a MTS
v CAS rootu; MTS/M2TS, HEIC a RAW nebyly v tomto úplném smoke toku ověřeny
reálnými externími nástroji.

## Opakování

Z kořene worktree s instalovanými vývojovými závislostmi:

```powershell
$env:PYTHONPATH = 'src'
python tests/media_connector/integration_smoke.py 'C:\cesta\k\ExifTool.exe'
```

Skript skončí nenulově při změně zdroje, chybě deduplikace, neočekávané
kanonické příponě, chybě katalogu/preview nebo neúspěšném otevření Media Deskem.
