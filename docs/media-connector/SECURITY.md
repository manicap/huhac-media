# Media Connector — bezpečnost

**MC1:** IMPLEMENTED

**Transfer a cloud bezpečnost:** PROPOSED / NOT IMPLEMENTED

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

## Budoucí staging a transfer

Schválen je pouze směr samostatného stagingu před Media Storage. Atomická
publikace, limity, recovery, writer, persistence a retence zůstávají otevřené a
v MC1 není žádný cílový zápis.

## Budoucí Google Drive

Google Drive je samostatná etapa. OAuth scope, credential store, token redakce,
TLS/retry a shared-drive politika zůstávají návrhem. Běžné soubory, shortcuts a
cloud-native dokumenty musí být explicitně odlišeny; nic z toho MC1 neobsahuje.

## Izolace komponent

Connector zapisuje nulové workspace artefakty, nečte ingest SQLite a neimportuje
interní kód Media Ingestu ani Media Desku. Budoucí provenience vyžaduje veřejný
integrační kontrakt bez změny workspace contract v1.
