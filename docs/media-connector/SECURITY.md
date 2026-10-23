# Media Connector — bezpečnost

**MC1:** IMPLEMENTED

**Transfer bezpečnost:** IMPLEMENTED PRO LOCAL / WINDOWS VERIFIED

**Cloud bezpečnost:** PROPOSED / NOT IMPLEMENTED

## Implementované hranice MC1

- Source root je explicitní, musí existovat jako adresář a nesmí být link ani
  Windows reparse point.
- Source root a workspace se nesmějí překrývat žádným směrem.
- Enumerace používá `lstat`/`stat` bez otevření obsahu.
- Directory a file symlinky, junctions a reparse points se nenásledují a vrací
  `LINK_SKIPPED` warning.
- Každý navštívený adresář se znovu resolve a musí zůstat pod kanonickým rootem.
- Logické cesty odmítají traversal, absolutní/oddělovací prvky, NUL, control
  znaky, ADS dvojtečku, trailing dot/space a Windows device names.
- Kolize po NFC normalizaci a case-foldingu fail-closed.
- Connector zdroje nemaže, nepřejmenovává, nepřepisuje ani nehashuje.
- Jediný výstup je JSON na stdout; MC1 nevytváří config, log, DB ani manifest.
- Cursor je pouze paginační pomůcka vázaná na source ID, ne bezpečnostní token.
- Chybová hlášení jsou bounded; neočekávaná výjimka se nepředává v tracebacku.

Filesystem se může měnit během enumerace a MC1 nedrží snapshot ani otevřené
handles souborů. Výsledek je proto bezpečný read-only observation, nikoli důkaz
integrity nebo úplnosti v jednom časovém okamžiku.

## Implementovaný staging a transfer

- Zdroj se otevírá pouze read-only po nové kontrole object ID, confinement,
  link/reparse ochrany a očekávané verze.
- Všechny rooty existují předem, vzájemně se nepřekrývají a staging sdílí
  filesystem s Media Storage.
- SHA-256 se počítá při streamování a znovu z uzavřeného staged souboru.
- Finální cesta vzniká pouze z lowercase SHA-256 a allowlisted canonical suffixu.
- Publikace přesouvá celý item adresář atomic no-replace operací; existující cíl
  se plně rehashuje a nikdy nepřepisuje.
- SQLite zapisuje `publishing` před filesystem operací; recovery adoptuje cíl až
  po plném ověření a nevyžaduje dostupný externí zdroj.
- Lokální OS lock povoluje jediného writera. Multi-host a síťové filesystemy
  nejsou podporované.
- Partial staging ani konfliktní objekt se automaticky nemažou nebo neopravují.

## Budoucí Google Drive

Google Drive je samostatná etapa. OAuth scope, credential store, token redakce,
TLS/retry a shared-drive politika zůstávají návrhem. Běžné soubory, shortcuts a
cloud-native dokumenty musí být explicitně odlišeny; nic z toho MC1 neobsahuje.

## Izolace komponent

Connector zapisuje nulové workspace artefakty, nečte ingest SQLite a neimportuje
interní kód Media Ingestu ani Media Desku. Budoucí provenience vyžaduje veřejný
integrační kontrakt bez změny workspace contract v1.
