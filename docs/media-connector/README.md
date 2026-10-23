# HUHÁČ Media Connector

**Stav:** MC1 + LOCAL MEDIA TRANSFER IMPLEMENTED

**Implementace:** read-only Local Discovery a ověřený lokální Media Transfer CLI

**Vývojová větev:** `feature/media-connector`

**Výchozí commit:** `0433703ad88293c03000dbd1cd4197fbd2e2a51e`

Media Connector je samostatná komponenta pro připojování zdrojů. MC1 implementuje
bezpečnou read-only enumeraci lokálního adresáře. Media Transfer pořídí vlastní
ověřenou kopii do SHA-256 content-addressed Media Storage; Google Drive ani
automatické spuštění Media Ingestu implementované nejsou.

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

## Media Transfer

Transfer používá samostatné příkazy `transfer preflight`, `transfer run` a
`transfer recover`. Přesné parametry, selection schema a chyby jsou v
[TRANSFER_JSON_CONTRACT.md](TRANSFER_JSON_CONTRACT.md). Všechny uvedené rooty
musí existovat; staging musí být na stejném lokálním filesystemu jako Media
Storage a nesmí se překrývat se zdrojem, workspace ani state rootem.

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
- [TRANSFER_ADR.md](TRANSFER_ADR.md) — schválená architektura Media Transferu;
- [TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md) — realizace,
  rozhraní a akceptační testy Transferu;
- [TRANSFER_JSON_CONTRACT.md](TRANSFER_JSON_CONTRACT.md) — implementovaný veřejný
  CLI kontrakt Transferu;
- [TRANSFER_INTEGRATION_SMOKE.md](TRANSFER_INTEGRATION_SMOKE.md) — izolované
  ověření toku init, Discovery, Transfer, Ingest a Media Desk;
- [STATUS.md](STATUS.md) — skutečný stav a podklady auditu.

## Terminologie

Oficiálním názvem komponenty je **Media Connector**. Pojem **Media Collector**
je vyhrazen jen případné budoucí interní funkci převzetí médií.
