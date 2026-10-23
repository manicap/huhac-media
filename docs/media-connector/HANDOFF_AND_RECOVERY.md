# Media Connector — handoff, stav synchronizace a zotavení

**Stav:** PROPOSED / NOT IMPLEMENTED

## Delivery model

Jednotkou předání je neměnná `delivery` s UUID. Pracovní data vznikají pod
dočasným názvem; hotová delivery se zveřejní atomickým přejmenováním až po
ověření. Publikovaná delivery se nikdy nedoplňuje ani nepřepisuje.

```text
connector-state/
  profile.json
  state.sqlite3              # navrženo; ne ingest DB
  runs/<run-id>/report.json
  manifests/<delivery-id>.json

delivery-root/
  <delivery-id>.partial/
  <delivery-id>/media/...    # publikovaný neměnný snapshot
```

Umístění `delivery-root` čeká na MC-Q03. Connector state nesmí být ve workspace
ani v `analysis/`. Návrh lokální SQLite počítá s jediným writerem a lokálním
filesystemem; není to sdílená ani veřejná databáze.

## Handoff manifest

Navržený `media-connector-handoff-v1` je kontrakt Connectoru, nikoli rozšíření
workspace contractu v1. Obsahuje:

- `schema`, `delivery_id`, `library_id`, `created_at`;
- identitu a typ zdrojového profilu bez tajných údajů;
- položky se zdrojovým `object_id`, `version_token`, logickou a výslednou
  relativní cestou, velikostí a výsledným transfer SHA-256;
- stav položky a strukturovanou chybu;
- souhrny a otisk kanonického manifestu.

Absolutní lokální cesty, OAuth tokeny a dočasné signed URL se nepublikují.
Manifest nemění význam `asset_id`; Media Ingest obsah znovu hashovat musí.

## Stavový automat běhu

```text
planned -> discovering -> transferring -> verifying -> publishing -> complete
                              |              |             |
                              +--------------+-------------+-> failed
                              +------------------------------> interrupted
```

Stavy položky jsou `pending`, `transferring`, `verified`, `published`, `failed`
a `skipped_unchanged`. Přechod na `verified` nastane až po uzavření streamu,
kontrole očekávané velikosti/verze a výpočtu lokálního SHA-256. `complete`
znamená, že manifest i delivery byly publikovány; neznamená, že proběhl Ingest.

## Zotavení

- Každý download/kopie používá unikátní `.partial` soubor a atomické přejmenování.
- Restart označí nedokončený běh jako `interrupted`; nic automaticky nemaže.
- Retry znovu použije jen ověřené položky se shodnou zdrojovou verzí a cílovým
  hashem. Jinak přenos zopakuje do nového dočasného souboru.
- Nedostupný zdroj ponechá konfiguraci i checkpoint; běh skončí strukturovaným
  retryable stavem.
- Změna objektu během přenosu nic nepublikuje a vytvoří `SOURCE_CHANGED`.
- Odstranění objektu ze zdroje nemaže dříve publikované médium. Mazací a retenční
  politika není součástí návrhu.
- Neznámé soubory v cíli se nepřepisují ani neadoptují.
- Opakovaný publish stejného `delivery_id` je buď ověřený no-op, nebo konflikt;
  nikdy implicitní overwrite.

## Předání Media Ingestu

Po explicitním schválení delivery může operátor předat její neměnný `media/`
adresář dnešnímu Media Ingestu jako `INPUT`. Konektor Ingest automaticky
nespouští a nevyhodnocuje jeho privátní stav. Propojení manifestové provenience
s veřejným katalogem by měnilo komponentové kontrakty a vyžaduje samostatné
architektonické rozhodnutí.
