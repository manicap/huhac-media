# Media Transfer — detailní implementační plán

**Stav:** PROPOSED / BLOCKED ON MC-ADR-001 APPROVAL

**Runtime:** NOT IMPLEMENTED

Plán vychází z [TRANSFER_ADR.md](TRANSFER_ADR.md). Neautorizuje implementaci.

## Veřejná a interní rozhraní

### Navržené JSON CLI

```powershell
media-connector transfer preflight `
  --workspace '<workspace>' `
  --media-storage '<storage>' `
  --state-root '<connector-state>' `
  --transfer-work-root '<same-filesystem-staging>' `
  --selection '<selection-v1.json>'

media-connector transfer run `
  --workspace '<workspace>' `
  --media-storage '<storage>' `
  --state-root '<connector-state>' `
  --transfer-work-root '<same-filesystem-staging>' `
  --selection '<selection-v1.json>' `
  --operation-id '<uuid>' `
  --yes
```

Oba příkazy vracejí právě jeden verzovaný JSON envelope. Preflight je read-only
vůči zdroji, Media Storage, workspace a persistentní state. Skutečný run zopakuje
validace pod writer lockem a teprve potom smí vytvořit state/staging. Přesné
schema a stabilní error codes vzniknou v první dokumentačním commitu etapy.

`selection-v1` obsahuje `workspace_id`, adapter kind, source ID a vybrané
`object_id + expected version_token`. Neobsahuje cílové cesty. Adapter runtime
poskytne bezpečný `open_read(object_id, expected_version)`; rozšíření MC1
adapter contractu musí zachovat read-only zdroj.

### Interní porty

- `SourceReader`: stat/version/open stream bez mutací;
- `ContentHasher`: streaming SHA-256 a nezávislý staged-file verify;
- `CompatibilityClassifier`: canonical suffix a ingest-ready rozhodnutí;
- `TransferRepository`: privátní state transakce bez znalosti Ingest DB;
- `StagingStore`: confined partial creation, flush/fsync a recovery;
- `ContentStore`: inspect, verify-existing a atomic no-replace publish;
- `LibraryLock` a `ContentLock`;
- `TransferReportWriter`: atomické, redigované JSON reporty mimo Media Storage.

## Etapy implementace

### T0 — kontrakty a kompatibilitní profil

1. Schválit MC-ADR-001.
2. Zmrazit JSON envelope, `selection-v1`, error codes a stavový automat.
3. Vytvořit Ingest Compatibility Profile v1 s canonical suffix mappingem.
4. Přidat fixture matrix všech podporovaných image/video formátů proti skutečnému
   `detect_media` a metadata refinement; runtime Connector nesmí importovat
   privátní Ingest Python API.

Akceptace: extensionless MTS/M2TS nesmí projít jako ingest-ready; každý
publikovatelný fixture musí Ingest rozpoznat ve fyzickém CAS layoutu.

### T1 — path preflight, locks a state schema

1. Validovat `workspace_id`, přesné oddělení roots a same-filesystem staging.
2. Fail-closed klasifikovat filesystem capabilities.
3. Implementovat versioned Connector SQLite migraci a OS writer lock.
4. Implementovat entity source/observation/run/item/object/link/event.
5. Preflight nesmí nic vytvořit ani měnit.

Akceptace: overlap, symlink/reparse escape, network/unknown FS, cizí state DB,
kolize knihovny a druhý writer mají stabilní chyby a nulové vedlejší účinky.

### T2 — read-only stream a izolovaný staging

1. Rozšířit local adapter o bezpečný `open_read` s expected version.
2. Streamovat do unikátního item stagingu, počítat SHA-256 a velikost.
3. Ověřit source version před/po a provést druhý SHA-256 pass staged payloadu.
4. Flush/fsync souboru a zaznamenat `verified_staged` před publish.

Akceptace: zdrojové bajty, jméno, časy a oprávnění zůstanou nezměněné; source
change, read error, disk full a interrupt nikdy nevytvoří publikovaný objekt.

### T3 — content store, dedup a atomická publikace

1. Vytvořit canonical CAS path výhradně z SHA-256 a compatibility suffixu.
2. Implementovat Windows/Linux atomic no-replace backend a directory durability.
3. Existující objekt vždy plně ověřit před dedup vazbou.
4. Publikovat nový objekt, fsync parent a dokončit state transition.
5. Neznámý/malformed/mismatching cíl fail-closed bez overwrite.

Akceptace: dvě source reference se stejnými bajty vytvoří jeden payload a dvě
metadata vazby; paralelní race skončí jedním publish a jedním ověřeným dedupem.

### T4 — recovery a fault injection

Vložit deterministické crash body před/po každé state/filesystem hraně. Recovery
zpracuje `transferring`, `verified_staged` a `publishing`, ale nic automaticky
nemaže. Crash po fyzickém publish před DB commit se smí adoptovat pouze po full
hash verify očekávaného cíle.

Akceptace: restart nikdy nepublikuje partial, nepřepíše existující objekt ani
neztratí již commitnutou source-content vazbu. Výpadek zdroje/disku je retryable,
pokud chyba není integritní.

### T5 — handoff a nezměněný Media Ingest

1. Vydat redigovaný transfer/provenance manifest mimo Media Storage.
2. Ukončit Transfer bez automatického spuštění Ingestu.
3. Samostatným integračním testem spustit dnešní Ingest s Media Storage jako
   `INPUT` a explicitním odděleným workspace.
4. Ověřit v public catalog v1 shodný SHA-256 a CAS `relative_path` bez přímého
   čtení ingest SQLite z Connectoru.

Akceptace: Ingest nikdy neuvidí staging/state/manifest, workspace contract zůstane
v1 a původní externí path je dostupný v Connector manifestu, ne fingovaný v
Ingest katalogu.

### T6 — dokumentace a provozní ověření

Synchronizovat STATUS, DECISIONS, ARCHITECTURE, ROADMAP, recovery runbook a CLI
návod. Změřit transfer throughput, druhý verify pass, dedup-existing rehash a
10k/100k state operace. Windows a nativní Linux jsou povinné; NAS zůstane
nepodporovaný, dokud neprojde samostatnou kvalifikací atomicity/durability.

## Povinná testovací matice

| Oblast | Testy |
|---|---|
| Immutability | byte hash, size, mtime a source path před/po; žádný rename/delete/write |
| Formáty | JPEG/PNG/WebP/HEIC/TIFF/RAW/MP4/MOV/MKV/AVI/MTS/M2TS CAS fixtures |
| Integrita | source změna, staged bit flip, truncation, target corruption, hash mismatch |
| Atomicita | process kill na každém crash bodu, disk full, fsync/rename failure |
| Deduplikace | stejný source znovu, dva názvy, dva adaptéry, concurrent same hash |
| Cesty | traversal, absolute path, symlink, junction, reparse, Unicode/case collision |
| Souběh | druhý writer, různé hashe, stejný hash, stale lock, unsupported multi-host |
| Recovery | orphan partial, verified stage, published/no DB commit, unavailable source |
| Ingest | dnešní CLI nad CAS rootem, v1 catalog, nezměněný SQLite ownership |
| Ochrana dat | unknown final object, existing mismatch a cizí state se nikdy nepřepíší |

## Commity navržené pro budoucí realizaci

1. kontrakty, error codes a compatibility fixtures;
2. Connector state schema, preflight a locks;
3. read-only source stream a verified staging;
4. CAS publish a dedup;
5. recovery/fault injection;
6. Ingest interoperability a finální documentation sync.

Po každém commitu se spustí pouze relevantní sada. AI/procesorové testy nejsou
součástí Transferu. Implementace se po dokončení Transferu zastaví; Google Drive
není automatická následující etapa.
