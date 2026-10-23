# HUHÁČ Media Connector

**Stav:** ARCHITECTURAL PROPOSAL / AWAITING APPROVAL

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
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — navržené etapy a akceptace;
- [STATUS.md](STATUS.md) — skutečný stav a podklady auditu.

## Terminologický rozpor k rozhodnutí

Současný [system overview](../system-overview.md) používá pracovní název
**Media Collector** pro dosud neimplementovanou komponentu se stejnou základní
odpovědností. Tento návrh doporučuje, aby **Media Connector** tento budoucí pojem
nahradil. Globální dokumentace zatím nebyla přepsána, protože přejmenování čeká
na architektonické schválení (MC-Q01 v [DECISIONS.md](DECISIONS.md)).
