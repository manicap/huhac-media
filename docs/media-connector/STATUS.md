# Media Connector — stav

**Aktualizováno:** 2026-10-23

**Větev:** `feature/media-connector`

**MC1:** IMPLEMENTED / COMPLETE

**Local Media Transfer:** IMPLEMENTED / WINDOWS VERIFIED

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

## Media Transfer implementace

- veřejné JSON-only CLI `transfer preflight`, `transfer run` a `transfer recover`;
- read-only preflight bez vytvoření DB, stagingu nebo cílových adresářů;
- SHA-256 jako jediná content identity a deterministický Compatibility Profile v1;
- same-filesystem privátní staging, streaming hash, file fsync a nezávislý rehash;
- CAS `objects/sha256/<prefix>/<hash>/payload.<canonical-suffix>`;
- Windows `MoveFileExW` a Linux `renameat2(RENAME_NOREPLACE)` backend bez overwrite;
- plný rehash existujícího objektu před dedup vazbou;
- lokální SQLite svázaná s `workspace_id`, single-writer OS lock a write-ahead stav;
- recovery verified stagingu i pádu po publish před SQLite potvrzením bez zdroje;
- redigovaný přenositelný provenance manifest mimo Media Storage;
- samostatná hranice vůči Ingestu bez jeho automatického spuštění.

## Zachované hranice

Workspace contract v1, Media Desk, Media Ingest, ingest SQLite a analytické
procesory nebyly změněny. Media Storage dostala pouze Connector-owned CAS
originály. Balíček `media_connector` neimportuje
`media_desk` ani `huhac_media`.

## Ověření

- `50 passed, 4 skipped` — Media Connector unit, CLI, integrita, deduplikace,
  confinement a fault-injection recovery testy na Windows;
- `2 passed` — cílené integrační testy nezměněného Ingest scanneru nad JPEG a
  MTS v CAS rootu;
- `3 passed` — existující scanner integrační regrese;
- crash body po staged verify a po publish před SQLite commit jsou obnoveny bez
  dostupného zdroje;
- corrupt/malformed existující cíl končí fail-closed bez overwrite;
- zdrojový byte hash, cesta a `mtime_ns` zůstávají po transferu beze změny.

### Integrační smoke — 2026-10-23

Izolovaný úplný tok init → Local Discovery → Local Transfer → Media Ingest →
Media Desk je **VERIFIED** na Windows a lokálním filesystemu. Devět syntetických
vstupů (JPEG s obsahovou duplicitou, PNG, WebP, TIFF, AVI, MP4, MOV a MKV)
vytvořilo osm fyzických CAS objektů a osm katalogových assetů. Čtyři obrazové
náhledy byly validní, Media Desk načetl všech osm assetů a video HTTP Range
vrátil 206. SHA-256, velikost a `mtime_ns` všech externích zdrojů zůstaly
nezměněné. Naměřené fáze: init preflight 0,683 s; init 1,118 s; discovery
0,428 s; Transfer preflight 0,520 s; Transfer 1,538 s; Ingest 13,236 s; Media
Desk 0,692 s.

Úplný protokol, matice formátů a hranice důkazu jsou v
[TRANSFER_INTEGRATION_SMOKE.md](TRANSFER_INTEGRATION_SMOKE.md). Nativní
`ffprobe` nebyl na hostu dostupný, proto video metadata v tomto smoke běhu
poskytl deterministický stub; tato část není vydávána za produkční ověření
dekodéru videa.

Skipped testy jsou dva skutečné symlink scénáře bez Windows privilege 1314 a
dva POSIX-only názvové scénáře. Nejsou vydávány za úspěšně ověřené.

## Známá omezení

- Google Drive, OAuth a automatická orchestrace Ingestu jsou **ABSENT**;
- nativní Linux testy jsou **UNVERIFIED**;
- WSL distribuce není na testovacím hostu instalována; Linux backend proto nebyl
  vydáván za otestovaný;
- SMB/NFS/NAS a jiné síťové nebo nejednoznačné filesystemy jsou odmítnuté;
- RAW formáty závislé pouze na příponě a nejednoznačný CR3-like ISO-BMFF jsou
  Compatibility Profile v1 odmítnuty;
- lokální SQLite není multi-host databáze; přenos na jiný host vyžaduje explicitní
  zálohu se shodným `workspace_id`, jinak se použije nový lokální stav;
- automatická retence/cleanup partial stagingu a integritních důkazů není součástí;
- stránkování znovu prochází celý strom a není konzistentní snapshot;
- Discovery obsah, MIME ani skutečný media typ nečte; až Transfer ověřuje vybrané
  soubory;
- Discovery verze `size + mtime_ns` není obsahová identita; Transfer jí používá
  jen jako change guard a identitu určí vlastním SHA-256;
- výkon velmi velkých discovery stromů a reálné offline NAS chyby nejsou změřené;
- absolutní source root je součást lokálního JSON výstupu a může být citlivý.

## Výkonové měření

Opakovatelný benchmark je `tests/media_connector/benchmark_transfer.py`. Na
testovacím Windows hostu a lokálním disku naměřil pro 64 MiB objekt:

- finální ověřovací běh: publish `1,674 s` / `38,23 MiB/s`, dedup `1,791 s` /
  `35,73 MiB/s`;
- dva předchozí běhy: publish `17,66–41,37 MiB/s`, dedup `40,03–44,05 MiB/s`.

Rozptyl zahrnuje filesystem cache a hostitelské bezpečnostní skenování. Publish
záměrně čte data ze zdroje, znovu ze stagingu a po publikaci; dedup navíc plně
ověřuje existující objekt. Čísla nejsou tvrzením o výkonu Linuxu nebo NAS.
