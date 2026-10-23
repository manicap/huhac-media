# Media Connector — architektura

**Architektonický směr:** ACCEPTED

**MC1 runtime:** IMPLEMENTED

**Local Media Transfer runtime:** IMPLEMENTED / WINDOWS VERIFIED

## Účel a identita

Media Connector je samostatný CLI modul pro bezpečné získávání informací a v
budoucnu médií z různých zdrojů. Oficiální název komponenty je Media Connector.
Pojem Media Collector je vyhrazen pouze případné budoucí interní funkci převzetí
bajtů.

Jedna instance/profil obsluhuje jednu knihovnu jednoho klienta. Kanonickou
identitou knihovny je `workspace_id`, který Connector načítá read-only z
veřejného `workspace.json`. Connector nepřepíná klienty ani knihovny.

## Komponentové hranice

```text
media-connector CLI
        |
        v
common discovery service
        |
        v
SourceAdapter contract
  +-- LocalFilesystemAdapter       # MC1
  `-- GoogleDriveAdapter           # budoucí samostatná etapa

MC1 output: versioned JSON on stdout only
```

Media Connector neimportuje Media Desk ani interní Python API Media Ingestu.
Nevstupuje do ingest SQLite. `workspace.json` čte pouze kvůli verzi veřejného
kontraktu a `workspace_id`; nečte katalog ani nepřepisuje žádný workspace
artefakt.

## MC1 — read-only Local Discovery

MC1 přijme cestu k existujícímu workspace a explicitní lokální zdrojový kořen.
Ověří workspace contract v1 a UUID knihovny, bezpečně enumeruje běžné soubory a
vrátí jednu deterministickou stránku JSON výsledku.

MC1:

- provádí pouze metadata operace (`lstat`/`stat`, bezpečnou enumeraci);
- neotevírá a nehashuje obsah souborů;
- nenásleduje symlinky, junctions ani jiné reparse points;
- nic nezapisuje do zdroje, workspace, Media Storage ani lokální databáze;
- nemění názvy a nevytváří staging či manifest na disku;
- neposuzuje, zda je soubor podporované médium — to zůstává odpovědností
  Media Ingestu;
- nepředstavuje `size_bytes + mtime_ns` jako obsahovou identitu.

### Vrstvy MC1

```text
cli.py
  JSON envelope, stabilní exit codes, argument validation
service.py
  workspace identity + adapter orchestration
workspace.py
  minimální read-only workspace contract v1 reader
adapters/base.py
  společný Protocol a doménové typy
adapters/local.py
  confinement, deterministic walk, pagination, cursor
```

Přímé importy těchto Python tříd jsou interní. Veřejným kontraktem MC1 je pouze
CLI popsané v [MC1_JSON_CONTRACT.md](MC1_JSON_CONTRACT.md). Implementace je v
`src/media_connector/` a nemá import dependency na `media_desk` ani
`huhac_media`.

## Oddělení budoucích adaptérů

Společný adaptér vrací zdrojové objekty, schopnosti a stabilní strojové chyby.
Neřeší cílový zápis ani orchestraci Ingestu. Lokální adaptér používá relativní
cesty a filesystem metadata. Budoucí Google Drive adaptér použije opaque Drive
ID a provider version; běžné soubory, shortcuts a cloud-native dokumenty budou
explicitně rozdílné typy.

Všechny adaptéry bez výjimky zpřístupňují externí zdroj pouze read-only.
Zdrojové API nesmí obsahovat mutační operace. Lokální ani cloudový originál se
neupravuje, nepřejmenovává, nepřesouvá a nemaže.

## Povinné převzetí a handoff

```text
EXTERNAL SOURCE (read-only)
        |
        v
DISCOVERY (inventory + candidate selection)
        |
        v
TRANSFER (own copy into private staging)
        |
        v
VERIFY (complete bytes + content identity)
        |
        v
PUBLISH TO MEDIA STORAGE (valid local original)
        |
        v
SEPARATE MEDIA INGEST OPERATION
```

Transfer zapisuje do samostatného same-filesystem stagingu a až po dvojím
SHA-256 ověření publikuje vlastní kopii do Media Storage. Nedokončené nebo
neověřené bajty nejsou viditelné jako platné médium. Implementovaný mechanismus
používá SHA-256 CAS, platformní atomic no-replace rename, lokální single-writer
SQLite a write-ahead recovery podle [MC-ADR-001](TRANSFER_ADR.md).

Převzetí do Media Storage je povinnou podmínkou handoffu. Media Ingest nesmí v
Connector workflow zpracovávat externí source root, cloud mount ani dočasný
staging. Dostává pouze publikované lokální originály z Media Storage a spouští
se samostatnou operací nezávislou na Transferu.

Content identity Transferu umožňuje, aby více externích zdrojových
referencí ukazovalo na jediný převzatý originál. Evidence zdrojů, observations
a transfer historie bude oddělena od samotných originálních souborů. Přesné
Veřejná vazba provenience na Ingest zůstává budoucím integračním kontraktem; nesmí měnit
workspace contract v1 ani používat ingest SQLite.

Media Ingest i nadále sám provede SHA-256, určí `asset_id` a publikuje workspace
contract. Transfer content identity nesmí být bez schváleného kontraktu vydávána
za ingest `asset_id`. Automatické spuštění Ingestu ani integrace do Media Desku
nejsou součástí MC1.

## Ownership

| Oblast | Vlastník | MC1 přístup |
|---|---|---|
| Každý externí zdroj | uživatel / poskytovatel | vždy read-only |
| `workspace.json` | Media Ingest | read-only identity |
| Ostatní workspace soubory a ingest SQLite | Media Ingest | žádný |
| Media Storage | knihovna / Transfer writer | MC1 žádný; Transfer pouze ověřená atomická publikace |
| Connector state a manifesty | Media Connector | lokální single-writer SQLite a redigovaný přenositelný manifest |
| stdout JSON | Media Connector | jediný výstup |
| Media Desk a `analysis/` | jejich komponenty | žádný |
