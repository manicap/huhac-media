# Media Connector — architektura

**Architektonický směr:** ACCEPTED

**MC1 runtime:** NOT IMPLEMENTED (do dokončení implementační etapy)

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
CLI popsané v [MC1_JSON_CONTRACT.md](MC1_JSON_CONTRACT.md).

## Oddělení budoucích adaptérů

Společný adaptér vrací zdrojové objekty, schopnosti a stabilní strojové chyby.
Neřeší cílový zápis ani orchestraci Ingestu. Lokální adaptér používá relativní
cesty a filesystem metadata. Budoucí Google Drive adaptér použije opaque Drive
ID a provider version; běžné soubory, shortcuts a cloud-native dokumenty budou
explicitně rozdílné typy.

## Budoucí převzetí a handoff

Budoucí přenos musí nejprve zapisovat do samostatného bezpečného stagingu a až
potom publikovat do Media Storage. Přesný transakční mechanismus není schválený
a není součástí MC1. Connector manifest a provenience budou samostatný budoucí
integrační kontrakt; nebudou vydávány za workspace catalog v1.

Media Ingest i nadále sám provede SHA-256, určí `asset_id` a publikuje workspace
contract. Automatické spuštění Ingestu ani integrace do Media Desku nejsou
součástí MC1.

## Ownership

| Oblast | Vlastník | MC1 přístup |
|---|---|---|
| Lokální zdroj | uživatel | read-only metadata |
| `workspace.json` | Media Ingest | read-only identity |
| Ostatní workspace soubory a ingest SQLite | Media Ingest | žádný |
| Media Storage | knihovna / budoucí writer | žádný |
| stdout JSON | Media Connector | jediný výstup |
| Media Desk a `analysis/` | jejich komponenty | žádný |
