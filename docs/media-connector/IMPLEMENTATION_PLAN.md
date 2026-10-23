# Media Connector — implementační plán

**Architektonický směr:** ACCEPTED

**Etapa MC1:** COMPLETE

**Historický rozsah:** Tento dokument popisuje uzavřenou MC1. Později schválený
a implementovaný Local Media Transfer popisuje
[TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md); původní
výluky MC1 nejsou tvrzením o dnešním stavu celé komponenty.

## Přesný rozsah MC1

MC1 přidá samostatný instalovatelný příkaz:

```powershell
media-connector local-discovery `
  --workspace 'C:\HUHAC\Workspace' `
  --source-root 'D:\Incoming' `
  --page-size 1000 `
  [--cursor '<opaque-cursor>']
```

Výstup je vždy právě jeden UTF-8 JSON objekt na stdout. Úspěch má exit code `0`,
chyba argumentu či kontraktu `2` a zdrojová/I/O chyba `3`. Text chyb se nikdy
nemusí parsovat. Přesné schema a kódy jsou v
[MC1_JSON_CONTRACT.md](MC1_JSON_CONTRACT.md).

Dodané části:

1. balíček `media_connector` nezávislý na Media Desku a Ingest internals;
2. společné immutable typy a `SourceAdapter` protocol;
3. minimální read-only validace `workspace.json` v1 a `workspace_id`;
4. bezpečný lokální adaptér s deterministickým pořadím;
5. opaque, source-bound cursor a omezená velikost stránky;
6. JSON CLI s verzovaným envelope a stabilními chybovými kódy;
7. cílené unit/CLI/security testy na Windows a platformně neutrální testy.

Výslovně mimo MC1 jsou čtení obsahu, SHA-256, detekce médií, kopie, staging,
manifest na disku, databáze, konfigurace profilu, OAuth, Google Drive, Media
Desk, spuštění Ingestu a jakákoli změna workspace.

## Realizované kroky

1. Přidat typy `SourceObject`, `ObjectPage`, `AdapterCapabilities`, warning a
   strukturovanou chybu.
2. Implementovat lokální root validaci, link/reparse odmítnutí, bezpečný walk,
   path validaci a detekci normalizačních kolizí.
3. Implementovat cursor založený na schema verzi, source ID a poslední logické
   cestě; při změně zdroje cursor odmítnout.
4. Implementovat read-only workspace identity reader bez importu Ingestu.
5. Přidat JSON-only CLI a entry point `media-connector`.
6. Ověřit nulové persistentní zápisy a synchronizovat dokumentaci se skutečným
   výsledkem.

## Akceptační testy MC1

- platný workspace v1 vrátí jeho přesné `workspace_id`;
- chybějící, malformed a unsupported workspace mají rozdílné stabilní kódy;
- prázdný zdroj vrátí úspěšnou prázdnou stránku;
- Unicode a vnořené názvy jsou deterministicky seřazené a používají `/`;
- pagination nevrací položku dvakrát a cursor je vázán na source ID;
- absolutní, traversal, NUL, Windows device/ADS a normalizačně kolidující
  logické cesty jsou odmítnuty;
- file/directory symlink a Windows reparse point nejsou následovány a jsou
  vykázány jako bezpečně přeskočené warnings;
- link/reparse source root je odmítnut;
- chybějící root, neadresář, permission error a dostupná offline OS signalizace
  mají strukturované chyby;
- source root a workspace se nesmějí překrývat žádným směrem;
- discovery neotevře obsah souboru a nemění zdroj ani workspace;
- opakované spuštění nad nezměněným stromem vrátí ekvivalentní položky;
- CLI na úspěch i chybu vytiskne právě jeden validní JSON objekt;
- import graph balíčku neobsahuje `media_desk` ani `huhac_media`.

Nativní Linux confinement zůstává **UNVERIFIED**. Reálný Windows NTFS junction
smoke proběhl; vytvoření klasického symlinku nebylo účtu povoleno a příslušné
testy jsou transparentně skipped. Reparse atribut je navíc pokryt unit testem.

## Původně následující etapy

Local staging/transfer/recovery následně schválilo MC-D017 a jsou implementované.
Google Drive discovery a automatická orchestrace Media Ingestu zůstávají
neautorizované.
