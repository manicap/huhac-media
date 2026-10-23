# Media Connector — stav

**Aktualizováno:** 2026-10-23

**Větev:** `feature/media-connector`

**MC1:** IMPLEMENTED / COMPLETE

## Implementováno

- samostatný balíček a CLI `media-connector local-discovery`;
- read-only načtení `workspace_id` z veřejného workspace contractu v1;
- lokální adaptér a společný `SourceAdapter` protocol;
- deterministická NFC-normalizovaná enumerace běžných souborů;
- source-bound cursor a stránky 1 až 10 000 položek;
- odmítnutí překryvu source/workspace, nebezpečných cest a kolizí;
- symlink/reparse skipping bez následování;
- stabilní JSON success/error envelope a chybové kódy;
- nulové čtení obsahu, hashing, persistence, staging a orchestrace.

## Zachované hranice

Workspace contract v1, Media Desk, Media Ingest, ingest SQLite, Media Storage a
analytické procesory nebyly změněny. Balíček `media_connector` neimportuje
`media_desk` ani `huhac_media`.

## Ověření

- `30 passed, 4 skipped` — cílené MC1 unit, CLI a bezpečnostní testy na Windows;
- `2 passed` — existující ingest CLI regresní test;
- `compileall` — bez chyby;
- module CLI smoke — validní jediný JSON error envelope a exit `2`;
- skutečný Windows NTFS junction — `LINK_SKIPPED`, žádná enumerace cíle;
- `git diff --check` a relativní dokumentační odkazy — kontrolují se před
  finálním commitem.

Skipped testy jsou dva skutečné symlink scénáře bez Windows privilege 1314 a
dva POSIX-only názvové scénáře. Nejsou vydávány za úspěšně ověřené.

## Známá omezení

- Google Drive, OAuth, transfer, staging, manifest, databáze a Ingest handoff
  jsou **ABSENT**;
- nativní Linux testy jsou **UNVERIFIED**;
- stránkování znovu prochází celý strom a není konzistentní snapshot;
- obsah, MIME ani skutečný media typ se nečtou a neověřují;
- observační verze `size + mtime_ns` není obsahová integrita ani asset identity;
- výkon velmi velkých stromů a reálné offline NAS chyby nejsou změřené;
- absolutní source root je součást lokálního JSON výstupu a může být citlivý.

## Media Transfer návrh

MC-ADR-001 a detailní implementační plán jsou **PROPOSED / AWAITING APPROVAL**.
Audit potvrdil kompatibilitu content-addressed Media Storage s nezměněným
Ingestem pouze při použití Ingest-kompatibilní canonical suffix politiky;
extensionless layout není obecně kompatibilní. Transfer, Connector SQLite,
staging ani publish runtime nejsou implementované.

Návrhové ověření: aktuální scanner integrační testy `3 passed`; cílený
`detect_media` probe potvrdil JPEG bez přípony, odmítnutí extensionless MTS a
závislost `.mts` na příponě. CR3-like ISO-BMFF je v první scanner fázi veden jako
MP4 i s `.cr3` a vyžaduje existující metadata refinement. Tyto výsledky jsou
zaneseny do compatibility brány MC-ADR-001, nikoli prezentovány jako nová
implementovaná schopnost.
