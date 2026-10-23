# Media Connector — bezpečnostní návrh

**Stav:** PROPOSED / NOT IMPLEMENTED

## Trust boundaries

Nedůvěryhodné jsou názvy, cesty, MIME typy, metadata, checksums i obsah ze
zdroje. Connector data nekóduje ani nespouští. Síť, mount a zdroj se mohou změnit
mezi discovery a čtením; každé otevření proto znovu ověřuje identitu a hranice.

## Lokální adaptér

- Kořen zdroje je explicitní a kanonizovaný.
- Enumerace nenásleduje directory ani file symlinky.
- Každé otevření používá path confinement a kontrolu symlink/reparse-point
  escape; lexikální prefix není dostatečný.
- Relativní cesty s `..`, absolutním prefixem, alternate data streamem, device
  názvem nebo NUL jsou odmítnuty.
- TOCTOU riziko se omezuje handle-based kontrolou, kde ji OS podporuje, a
  kontrolou verze před/po čtení. Na platformě bez potřebné primitive se operace
  musí fail-closed nebo být označena jako nepodporovaná.
- Zdroj se nikdy nemaže, nepřejmenovává ani nemění.

## Google Drive adaptér

- Výchozí OAuth scope je pouze `drive.readonly`; širší scope vyžaduje nové
  rozhodnutí.
- Authorization Code + PKCE nebo device flow; klientské tajemství vložené do
  desktopové aplikace se nepovažuje za tajné.
- Refresh token se ukládá do OS credential store, ne do JSON configu, manifestu,
  logu ani Git repozitáře.
- Logy redigují Authorization hlavičky, tokeny, cookies a signed download URL.
- TLS se ověřuje; neomezené redirecty, neznámé hosty a vypnutí validace
  certifikátu jsou zakázané.
- API retry respektuje `Retry-After`, kvóty a bounded exponential backoff.
- Shared Drive musí být explicitně povolen ve zdrojovém profilu. Shortcut se
  buď bezpečně resolvuje s detekcí cyklu, nebo odmítne.

## Cílový zápis

- Logická cesta se mapuje pod jediný schválený delivery root; kolize po Unicode
  normalizaci a case-foldingu jsou explicitní chyba nebo deterministické
  přejmenování zaznamenané v manifestu.
- Platí limity na počet položek, velikost položky, celkový objem, dobu přenosu a
  souběžnost. Nedostatek místa selže před publikací.
- Dočasné soubory mají nejmenší praktická oprávnění a nejsou zpřístupněny jako
  hotové médium.
- Publikace je atomická na stejném filesystemu; přes-filesystemové přejmenování
  se nesmí vydávat za atomické.
- Existující neznámý soubor nebo adresář se nepřepisuje.

## Tajné a osobní údaje

Zdrojové ID, názvy souborů a Drive metadata mohou být osobní údaje. Reporty a
manifesty obsahují jen minimum nutné pro audit a retry. Diagnostický export musí
mít samostatnou redakční politiku. Retence, export a odstranění connector state
jsou před implementací Google Drive otevřené otázky.

## Oddělení od ostatních komponent

Connector nemá oprávnění zapisovat workspace ani číst ingest SQLite. Neimportuje
interní Python API Media Ingestu. Budoucí integrace probíhá přes výslovně
schválenou veřejnou hranici a nesmí obcházet existující zamykání či SHA-256
identitu Ingestu.
