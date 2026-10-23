# Media Connector — registr rozhodnutí a otázek

**Stav návrhu:** AWAITING APPROVAL

Stavy: **ACCEPTED/TARGET** je hranice výslovně daná schváleným zadáním;
**PROPOSED** čeká na schválení; **OPEN** vyžaduje volbu; **IMPLEMENTED** by
vyžadovalo existující kód a důkaz — takové rozhodnutí zde zatím není.

| ID | Rozhodnutí | Stav |
|---|---|---|
| MC-D001 | Jeden klient = jedna knihovna; žádný multi-client management, přepínání ani federace. | **ACCEPTED/TARGET** |
| MC-D002 | Lokální a Google Drive adaptér jsou oddělené od společné orchestrace. | **ACCEPTED/TARGET** |
| MC-D003 | Workspace contract v1 a ingest SQLite zůstávají nedotčené; Connector neimportuje interní API Ingestu. | **ACCEPTED/TARGET** |
| MC-D004 | Zdrojové adaptéry jsou read-only a předávají společné vrstvě stream a zdrojovou provenienci. | **PROPOSED** |
| MC-D005 | Předávací jednotka je neměnná delivery s vlastním verzovaným manifestem; manifest není workspace katalog. | **PROPOSED** |
| MC-D006 | Connector vede vlastní lokální single-writer stav oddělený od Workspace, Media Storage a ingest DB. | **PROPOSED** |
| MC-D007 | Google Drive používá nejmenší scope `drive.readonly` a refresh token ukládá pouze do OS credential store. | **PROPOSED** |
| MC-D008 | První etapy automaticky nespouštějí Media Ingest; handoff je explicitní. | **PROPOSED** |
| MC-D009 | Získaný zdrojový checksum ani transfer SHA-256 není `asset_id`; obsahovou identitu nadále vlastní Ingest. | **PROPOSED** |

## Otázky vyžadující schválení

- **MC-Q01 — Název komponenty:** nahrazuje Media Connector dosavadní budoucí
  pojem Media Collector v globální dokumentaci?
- **MC-Q02 — Identita knihovny:** má profil Connectoru používat existující
  `workspace_id` jako jedinou kanonickou `library_id`, načítanou read-only?
- **MC-Q03 — Ownership originálů:** publikuje Connector immutable delivery přímo
  do vyhrazeného namespace Media Storage, nebo nejdřív do odděleného stagingu a
  kdo provede propagaci? Toto rozhodnutí blokuje jakýkoli cílový zápis.
- **MC-Q04 — Stavová persistence:** je schválená privátní lokální SQLite s jedním
  writerem, nebo je pro první produkční rozsah požadován jiný journal?
- **MC-Q05 — Provenience:** postačí v první integraci connector manifest vedle
  delivery, když jej současný Ingest nepublikuje do catalog v1, nebo je nutné
  navrhnout budoucí kompatibilní veřejné propojení?
- **MC-Q06 — Kolize cest:** preferuje se fail-closed, nebo deterministické
  přejmenování při Windows/Unicode/case-fold kolizi?
- **MC-Q07 — Google cloud-native dokumenty:** mají být trvale mimo rozsah, nebo
  později exportovány podle samostatné formátové politiky?
- **MC-Q08 — Retence:** jak dlouho uchovávat delivery, manifesty, checkpointy a
  redigované reporty; kdo smí provést explicitní cleanup?

Dokud nejsou MC-Q03 a MC-Q04 schválené, lze bezpečně implementovat pouze
read-only discovery a dry-run kontrakty bez přenosu a perzistentního journalu.
