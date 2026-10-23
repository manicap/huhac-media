# HUHÁČ Media Connector

**Stav:** ARCHITECTURAL DIRECTION ACCEPTED / MC1 AUTHORIZED

**Implementace:** ABSENT

**Vývojová větev:** `feature/media-connector`

**Výchozí commit:** `0433703ad88293c03000dbd1cd4197fbd2e2a51e`

Media Connector je navrhovaná samostatná komponenta pro bezpečné získávání médií
z lokálního souborového systému a Google Drive. Tento adresář zatím obsahuje
pouze návrh. Neexistuje runtime balíček, CLI, databáze, síťová integrace ani
napojení na Media Ingest.

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
- [STATUS.md](STATUS.md) — skutečný stav a podklady auditu.

## Terminologie

Oficiálním názvem komponenty je **Media Connector**. Pojem **Media Collector**
je vyhrazen jen případné budoucí interní funkci převzetí médií.
