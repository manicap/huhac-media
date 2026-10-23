# Media Connector — handoff, stav synchronizace a zotavení

**Architektonické invarianty:** ACCEPTED/TARGET

**Transfer runtime:** IMPLEMENTED PRO LOCAL / WINDOWS VERIFIED

Tento dokument popisuje implementované hranice lokálního Transferu. Layout,
persistence a transakční mechanismus schvaluje MC-D017 a MC-ADR-001.

Posuzovaný konkrétní návrh je v [TRANSFER_ADR.md](TRANSFER_ADR.md); detailní
testovací a realizační pořadí v
[TRANSFER_IMPLEMENTATION_PLAN.md](TRANSFER_IMPLEMENTATION_PLAN.md).

## Povinné invarianty

- Všechny současné i budoucí externí zdroje a adaptéry jsou vždy read-only.
- Discovery pouze inventarizuje a vybírá kandidáty; nepřebírá originál.
- Transfer pořizuje vlastní kopii přes soukromý staging a ověřuje její úplnost
  a identitu obsahu.
- Do Media Storage se publikuje pouze dokončený a ověřený originál.
- Nedokončený, částečný nebo neověřený transfer není platné médium.
- Media Ingest přijímá výhradně publikované lokální originály z Media Storage.
- Spuštění Ingestu je samostatná operace; úspěch Transferu jej automaticky
  nespouští.
- Deduplikace Transferu je podle identity obsahu a umožňuje více zdrojových
  referencí k jednomu převzatému originálu.
- Zdrojové reference, observations a historie transferů jsou metadata oddělená
  od souborů originálů.
- Externí originál se nikdy neupravuje, nepřejmenovává, nepřesouvá ani nemaže.

## Implementovaný delivery model

Jednotkou práce je transfer run s UUID. Pracovní bajty vznikají pouze v
soukromém stagingu. Publikace do Media Storage nastane až po úplném přenosu a
ověření; publikovaný originál se následně nepřepisuje.

```text
connector-state/                   # lokální evidence svázaná s workspace_id
  connector-state.sqlite3
  .transfer.lock
  manifests/<operation-id>.json

transfer-work/staging/<run-id>/
  <item-id>.partial/                # nikdy není platné médium

Media Storage/objects/sha256/<prefix>/<sha256>/
  payload.<canonical-suffix>        # pouze ověřený lokální originál
```

Connector state nesmí být ve workspace, v `analysis/`, Media Storage ani vložen
do originálů. SQLite je privátní, lokální, single-writer a zcela oddělená od
ingest DB. Stabilní veřejný kontrakt je JSON CLI a provenance manifest, nikoli DB
schema.

## Implementovaný provenance manifest

`huhac.media-connector.provenance` v1 je kontrakt Connectoru, nikoli rozšíření
workspace contractu v1. Odděleně eviduje:

- `contract`, `contract_version`, `workspace_id` a `run_id`;
- zdrojové reference, jejich version token a logickou cestu bez absolutního rootu;
- vazbu více zdrojových referencí na content identity převzatého originálu;
- výslednou relativní cestu v Media Storage, velikost a ověřovací hash;
- dokončený stav, Compatibility Profile, velikost a CAS relativní cestu.

Absolutní externí cesty, OAuth tokeny a dočasné signed URL se nepublikují.
Transfer content identity se nesmí automaticky vydávat za ingest `asset_id`;
Media Ingest obsah znovu hashovat musí.

## Stavový automat

```text
pending -> transferring -> verified_staged -> publishing
   |            |                |                |
   +------------+----------------+----------------+-> failed / interrupted
                                                    -> published
                                                    -> deduplicated_existing
                                                    -> recovered_published
```

Přechod na `verified_staged` smí nastat až
po uzavření streamu, kontrole očekávané velikosti/verze a výpočtu content
identity. `complete` znamená publikovaný ověřený originál a evidenci; neznamená,
že proběhl Ingest.

## Zotavení

- Každá kopie používá unikátní `.partial` umístění mimo publikovaný namespace.
- Restart rozpozná nedokončený běh; nic automaticky nemaže ani nepublikuje.
- Retry znovu použije jen prokazatelně ověřené části se shodnou zdrojovou verzí
  a hashem, jinak přenos zopakuje do nového stagingu.
- Nedostupný zdroj ponechá konfiguraci i checkpoint a vrátí retryable stav.
- Změna objektu během přenosu nic nepublikuje a vytvoří `SOURCE_CHANGED`.
- Odstranění objektu ze zdroje nemaže dříve převzatý originál z Media Storage.
- Neznámé cílové soubory se nepřepisují ani neadoptují.
- Opakovaný publish stejné content identity je ověřený dedup/no-op nebo
  konflikt; nikdy implicitní overwrite.

## Povinné oddělené předání Media Ingestu

Teprve po úspěšné publikaci může samostatná operace předat příslušný lokální
Media Storage root dnešnímu Media Ingestu jako `INPUT`. Externí source root ani
staging nejsou platným Ingest vstupem. Connector Ingest automaticky nespouští a
nevyhodnocuje jeho privátní stav.

Media Ingest nadále vlastní SHA-256 `asset_id`, deduplikaci svého katalogu a
publikaci workspace contractu. Propojení Connector source/transfer provenience
s veřejným katalogem vyžaduje samostatný budoucí integrační kontrakt bez změny
workspace contract v1 a bez čtení ingest SQLite.
