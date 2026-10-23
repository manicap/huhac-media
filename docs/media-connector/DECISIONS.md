# Media Connector — registr rozhodnutí a otázek

**Aktualizováno:** 2026-10-23 po schválení MC-D017

Stavy: **ACCEPTED/TARGET** je závazná schválená hranice;
**PROPOSED** čeká na schválení; **OPEN** vyžaduje budoucí volbu;
**IMPLEMENTED** vyžaduje existující kód a ověření.

| ID | Rozhodnutí | Stav |
|---|---|---|
| MC-D001 | Oficiální název samostatné komponenty je **Media Connector**. „Media Collector“ smí být jen případná budoucí interní funkce převzetí médií. | **ACCEPTED/TARGET** |
| MC-D002 | Jeden klient = jedna samostatná knihovna. Stabilní identita knihovny je `workspace_id`. Multi-client management, přepínání a federace jsou mimo rozsah. | **ACCEPTED/TARGET** |
| MC-D003 | Media Connector je samostatný CLI modul nezávislý na Media Desku. | **ACCEPTED + IMPLEMENTED PRO MC1** |
| MC-D004 | Zdrojové adaptéry jsou read-only a oddělené od společné logiky přes společný kontrakt. | **ACCEPTED + IMPLEMENTED PRO LOCAL** |
| MC-D005 | Workspace contract v1 zůstává beze změny. Connector nečte ingest SQLite, neimportuje interní API Ingestu a nezapisuje workspace. | **ACCEPTED + IMPLEMENTED PRO MC1** |
| MC-D006 | MC1 obsahuje pouze read-only Local Discovery. Neobsahuje převzetí médií, staging, databázi, OAuth ani změny workspace. | **ACCEPTED + IMPLEMENTED** |
| MC-D007 | Budoucí převzetí médií musí použít samostatný bezpečný staging před publikací do Media Storage. Transakční mechanismus, writer a persistence zatím nejsou schválené. | **ACCEPTED/TARGET + OPEN DETAIL** |
| MC-D008 | MC1 nemaže, nepřejmenovává ani nepřepisuje zdrojové soubory a neotvírá jejich obsah. | **ACCEPTED + IMPLEMENTED** |
| MC-D009 | Provenience a vazba na Media Ingest budou budoucí samostatný integrační kontrakt bez změny workspace contract v1. | **ACCEPTED/TARGET** |
| MC-D010 | Google Drive je samostatná pozdější etapa. Běžné soubory a cloud-native dokumenty mají rozdílné chování a nesmějí se tiše zaměnit. | **ACCEPTED/TARGET** |
| MC-D011 | Veřejná hranice MC1 je verzovaný JSON-only CLI kontrakt `media-connector local-discovery`; přímý Python import jiné komponenty není veřejné API. | **ACCEPTED + IMPLEMENTED** |
| MC-D012 | MC1 používá `relative_path + size_bytes + mtime_ns` pouze jako observační verzi. Nehashuje obsah a nevytváří ingest `asset_id`. | **ACCEPTED + IMPLEMENTED** |
| MC-D013 | Každý současný i budoucí externí zdroj je pro Media Connector striktně read-only. Connector zdrojové originály nikdy neupravuje, nepřejmenovává, nepřesouvá ani nemaže. | **ACCEPTED/TARGET; IMPLEMENTED PRO MC1** |
| MC-D014 | Povinný tok je `Connector → Discovery → Transfer → ověřená publikace do Media Storage`. Media Ingest smí dostat pouze lokálně převzaté a ověřené originály z Media Storage; přímý ingest externího zdroje není podporovaný handoff. | **ACCEPTED + IMPLEMENTED PRO LOCAL** |
| MC-D015 | Nedokončený nebo neověřený transfer není platné médium a nesmí být publikován. Spuštění Media Ingestu je samostatná operace nezávislá na Transferu. | **ACCEPTED + IMPLEMENTED PRO LOCAL** |
| MC-D016 | Transfer deduplikuje podle identity obsahu: více externích zdrojů může odkazovat na jediný převzatý originál. Evidence zdrojů a historie transferů je oddělena od originálních souborů. | **ACCEPTED + IMPLEMENTED PRO LOCAL** |
| MC-D017 | Media Transfer použije SHA-256 content-addressed Media Storage, same-filesystem staging, privátní Connector state a atomic no-replace publikaci podle [MC-ADR-001](TRANSFER_ADR.md). SHA-256 je jediná identita objektu; kanonická přípona je pouze deterministická Ingest-kompatibilní reprezentace. Stejné bajty mají právě jeden fyzický originál bez ohledu na zdrojový název nebo příponu. | **ACCEPTED + IMPLEMENTED PRO LOCAL; LINUX UNVERIFIED** |

## Stav dříve otevřených otázek

- **MC-Q01 — RESOLVED BY MC-D017:** same-filesystem staging, write-ahead stav a
  atomic no-replace publish;
- **MC-Q02 — RESOLVED BY MC-D017:** privátní lokální SQLite, single writer;
- **MC-Q03 — RESOLVED FOR LOCAL TRANSFER:** provenance manifest v1 a privátní
  historie bez změny workspace contractu v1; přímé propojení do katalogu Ingestu
  zůstává mimo rozsah;
- **MC-Q04 — RESOLVED BY MC-D017:** SHA-256 CAS a fail-closed při neshodě;
- **MC-Q05 — Google Drive:** OAuth, shared drives, shortcuts, exportní politika
  cloud-native dokumentů a retence tokenů;
- **MC-Q06 — retence:** životní cyklus budoucích deliveries, manifestů,
  checkpointů a diagnostických reportů.

MC-Q05 a MC-Q06 neblokují dokončený Local Transfer. Blokují pouze příslušné
budoucí cloudové a retenční etapy.

Schválený detail rozhodnutí MC-D017 je v
[TRANSFER_ADR.md](TRANSFER_ADR.md) a prováděcí kroky v
[TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md). Implementace
nesmí měnit Media Ingest, jeho SQLite, Media Desk ani workspace contract v1.
