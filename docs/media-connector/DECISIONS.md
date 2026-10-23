# Media Connector — registr rozhodnutí a otázek

**Aktualizováno:** 2026-10-23 po schválení směru MC1

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
| MC-D007 | Budoucí převzetí médií má použít samostatný bezpečný staging před publikací do Media Storage. Transakční mechanismus, writer a persistence zatím nejsou schválené. | **ACCEPTED/TARGET + OPEN DETAIL** |
| MC-D008 | MC1 nemaže, nepřejmenovává ani nepřepisuje zdrojové soubory a neotvírá jejich obsah. | **ACCEPTED + IMPLEMENTED** |
| MC-D009 | Provenience a vazba na Media Ingest budou budoucí samostatný integrační kontrakt bez změny workspace contract v1. | **ACCEPTED/TARGET** |
| MC-D010 | Google Drive je samostatná pozdější etapa. Běžné soubory a cloud-native dokumenty mají rozdílné chování a nesmějí se tiše zaměnit. | **ACCEPTED/TARGET** |
| MC-D011 | Veřejná hranice MC1 je verzovaný JSON-only CLI kontrakt `media-connector local-discovery`; přímý Python import jiné komponenty není veřejné API. | **ACCEPTED + IMPLEMENTED** |
| MC-D012 | MC1 používá `relative_path + size_bytes + mtime_ns` pouze jako observační verzi. Nehashuje obsah a nevytváří ingest `asset_id`. | **ACCEPTED + IMPLEMENTED** |

## Otevřené otázky mimo MC1

- **MC-Q01 — transakční staging:** přesný layout, atomická publikace, recovery a
  writer ownership budoucího stagingu;
- **MC-Q02 — persistence:** zda a jaký privátní journal použít pro budoucí
  transfery; MC1 databázi nemá;
- **MC-Q03 — provenience:** přesný budoucí handoff manifest a kompatibilní vazba
  na Media Ingest bez změny kontraktu v1;
- **MC-Q04 — kolize při publikaci:** fail-closed versus deterministické mapování
  cílových názvů; MC1 žádné cílové názvy nevytváří;
- **MC-Q05 — Google Drive:** OAuth, shared drives, shortcuts, exportní politika
  cloud-native dokumentů a retence tokenů;
- **MC-Q06 — retence:** životní cyklus budoucích deliveries, manifestů,
  checkpointů a diagnostických reportů.

Žádná z těchto otázek neblokuje MC1, protože jeho jediným výstupem je JSON na
stdout a nemění zdroj, workspace ani jiné persistentní úložiště.
