# Media Connector — architektonický návrh

**Stav dokumentu:** PROPOSED / AWAITING APPROVAL

**Runtime stav:** NOT IMPLEMENTED

## Účel a hranice

Media Connector získává bajty a zdrojovou provenienci z externího nebo lokálního
zdroje. Nerozpoznává obsah, nevytváří asset identity Media Ingestu, nespouští
metadata, preview ani AI procesory a nevytváří či nemění workspace.

Jedna instalace/profil konektoru obsluhuje právě jednu knihovnu jednoho klienta.
Profil může později obsahovat více zdrojů stejné knihovny, například lokální
složku i Google Drive, ale nemůže přepínat mezi knihovnami. Za kanonickou
identitu knihovny je navrženo použít `workspace_id`, načtené pouze read-only z
veřejného `workspace.json`. Toto navázání čeká na schválení v MC-Q02.

## Navržené vrstvy

```text
CLI / budoucí UI boundary
        |
        v
Connector application service
  discovery -> plan -> transfer -> verify -> publish delivery
        |                         |
        |                         +--> connector-owned state and manifests
        v
SourceAdapter contract
  +-- LocalFilesystemAdapter
  `-- GoogleDriveAdapter
        |
        v
read-only source APIs / source files

published immutable delivery
        |
        v
explicit handoff boundary (no automatic orchestration in initial stages)
        |
        v
Media Ingest INPUT
```

Společná vrstva vlastní plánování, omezení objemu, názvové kolize, retry,
ověření přenosu, stav běhu a publikaci. Adaptér vlastní pouze zdrojově specifické
načtení objektů, stránkování, verze a čtecí stream. Adaptér nerozhoduje o cílové
cestě, nezapisuje manifest a nevolá Media Ingest.

## Oddělení adaptérů

### Lokální souborový systém

Lokální adaptér dostane explicitní kořen zdroje, enumeruje bez následování
symlinků a každý otevřený soubor znovu omezí na tento kořen. Zdroj je pouze pro
čtení. Stabilní identifikátor objektu musí být definován přenositelně; samotná
absolutní cesta ani inode nejsou dostatečná dlouhodobá identita. Pro první etapu
je proto navržena složená observační identita `relative_path + size + mtime_ns`
a její změna znamená novou verzi pozorování, nikoli obsahovou identitu.

### Google Drive

Google Drive adaptér používá oficiální API, stránkování a opaque Drive file ID.
`version_token` je odvozen ze zdrojových verzovacích údajů (`version`,
`modifiedTime`, případně checksum), nikoli z názvu souboru. Adaptér řeší shared
drives, shortcuts a cloud-native dokumenty explicitně; žádný z těchto typů se
nesmí tiše vydávat za běžný binární soubor. Export Google dokumentů vyžaduje
samostatnou schválenou politiku a v počátečním rozsahu je odmítnut.

Autentizace, tokeny a síťové retry zůstávají uvnitř adaptéru. Doménové objekty
nesmějí obsahovat access ani refresh token.

## Ownership a kompatibilita

| Oblast | Vlastník | Přístup Connectoru |
|---|---|---|
| Zdrojové soubory / Drive objekty | uživatel / poskytovatel | read-only |
| Connector config, journal a manifesty | Media Connector | read/write |
| Publikovaná delivery média | k rozhodnutí MC-Q03 | pouze řízené vytvoření |
| `workspace.json`, `metadata/`, `state/` | Media Ingest | žádný zápis |
| `state/catalog.sqlite3` | Media Ingest | žádný přístup |
| `analysis/` | jednotlivé procesory | žádný přístup |

Media Connector nevytváří pole workspace contractu a nepřekládá svůj manifest
za katalog v1. Existující Media Ingest nadále přijímá adresář `INPUT`, sám
provádí SHA-256 a publikuje katalog. Connector nesmí považovat zdrojový checksum
nebo svůj transfer checksum za `asset_id`.

## Navržený handoff

Společná vrstva publikuje neměnnou delivery: adresář médií a oddělený verzovaný
Connector manifest. Publikace nastane až po ověření všech úspěšných položek.
Media Ingest dostane explicitně pouze adresář s médii jako `INPUT`; manifest
není součást workspace contractu v1 a Ingest jej v první integraci neparsuje.
Automatické spuštění Ingestu není součást prvních etap.

Přesné umístění delivery — uvnitř Media Storage, nebo v samostatném stagingu s
pozdější propagací — je otevřená ownership otázka MC-Q03. Do jejího schválení
nesmí implementace zapisovat originály do Media Storage.

## Deployment model

Navržen je jeden aktivní writer konektoru na knihovnu. Connector state musí být
lokální, nesdílený přes SMB/NFS a oddělený od workspace i ingest SQLite.
Google Drive i zdrojový lokální disk mohou být dočasně nedostupné; tento stav
nesmí zrušit konfiguraci ani již publikovanou delivery.

Multi-client management, centrální služba, federace, více aktivních writerů,
obousměrná synchronizace a mazání zdrojů jsou mimo rozsah.
