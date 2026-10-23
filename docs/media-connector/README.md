# HUHÁČ Media Connector

**Stav:** MC1 IMPLEMENTED / COMPLETE

**Implementace:** read-only Local Discovery CLI

**Vývojová větev:** `feature/media-connector`

**Výchozí commit:** `0433703ad88293c03000dbd1cd4197fbd2e2a51e`

Media Connector je samostatná komponenta pro připojování zdrojů. MC1 implementuje
pouze bezpečnou read-only enumeraci lokálního adresáře. Google Drive, transfer,
staging, databáze a napojení na Media Ingest nejsou implementované.

## Spuštění MC1

```powershell
python -m pip install -e ".[dev]"
media-connector local-discovery `
  --workspace 'C:\HUHAC\Workspace' `
  --source-root 'D:\Incoming' `
  --page-size 1000
```

Alternativně lze použít `python -m media_connector`. Výstup je vždy jeden JSON
objekt. Při stránkování předejte hodnotu `page.next_cursor` pomocí `--cursor`.

## Schválené hranice zadání

- jeden klient odpovídá jedné samostatné mediální knihovně;
- komponenta nespravuje více klientů, nepřepíná knihovny a nefederuje je;
- lokální a Google Drive adaptér jsou oddělené od společné logiky;
- workspace contract v1 zůstává beze změny;
- Media Connector nesmí číst ani zapisovat interní SQLite Media Ingestu;
- Media Desk, Media Ingest a analytické procesory se v této etapě nemění.

## Dokumenty návrhu

- [ARCHITECTURE.md](ARCHITECTURE.md) — komponenty, datový tok a ownership;
- [ADAPTER_CONTRACT.md](ADAPTER_CONTRACT.md) — společné rozhraní adaptérů;
- [HANDOFF_AND_RECOVERY.md](HANDOFF_AND_RECOVERY.md) — předání médií, stav a
  zotavení;
- [SECURITY.md](SECURITY.md) — bezpečnostní hranice a oprávnění;
- [DECISIONS.md](DECISIONS.md) — přijaté hranice, návrhy a otevřené otázky;
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — rozsah MC1 a akceptace;
- [MC1_JSON_CONTRACT.md](MC1_JSON_CONTRACT.md) — veřejné JSON CLI schema;
- [ROADMAP.md](ROADMAP.md) — dokončená a odložená etapa;
- [STATUS.md](STATUS.md) — skutečný stav a podklady auditu.

## Terminologie

Oficiálním názvem komponenty je **Media Connector**. Pojem **Media Collector**
je vyhrazen jen případné budoucí interní funkci převzetí médií.
