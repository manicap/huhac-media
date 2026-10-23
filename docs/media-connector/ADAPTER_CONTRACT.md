# Media Connector — společné rozhraní adaptérů

**Stav:** PROPOSED / NOT IMPLEMENTED

Rozhraní odděluje zdrojové protokoly od plánování a cílového zápisu. Níže je
logický kontrakt, nikoli dnes existující Python API.

## Operace

```text
probe(source_config) -> ProbeResult
list_page(cursor, page_size) -> ObjectPage
stat(object_id) -> SourceObject
open_read(object_id, expected_version) -> ReadableBinary
close() -> None
```

- `probe` je read-only a ověří dosažitelnost, oprávnění a schopnosti adaptéru;
- `list_page` vrací deterministickou stránku a opaque pokračovací cursor;
- `stat` načte aktuální zdrojovou verzi bez otevření obsahu;
- `open_read` musí odmítnout objekt, jehož verze se od plánování změnila;
- adaptér nevytváří cílové soubory, databázi ani workspace artefakty.

## Společné datové typy

`SourceObject` obsahuje nejméně:

```json
{
  "adapter_kind": "local|google_drive",
  "source_id": "profile-scoped stable source identifier",
  "object_id": "adapter opaque identifier",
  "version_token": "adapter opaque observed version",
  "logical_path": "relative display and planning path",
  "object_kind": "file|folder|shortcut|cloud_document",
  "size_bytes": 123,
  "modified_at": "ISO-8601 timestamp or null",
  "media_type_hint": "provider MIME value or null",
  "source_checksum": {
    "algorithm": "md5",
    "value": "hex"
  }
}
```

`source_checksum` je volitelný a pouze zdrojový údaj. Nesmí být přeznačen na
SHA-256 asset identity Media Ingestu. `logical_path` není důvěryhodná filesystem
cesta; společná vrstva ji normalizuje a mapuje do cílového namespace.

`ObjectPage` obsahuje `items`, `next_cursor` a snapshot/consistency metadata,
pokud je poskytovatel nabízí. Cursor je neprůhledný a může být uložen pouze pro
stejný adaptér, zdroj a verzi konfigurace.

`ProbeResult` rozlišuje nejméně `ready`, `authentication_required`, `offline`,
`permission_denied`, `invalid_configuration` a `unsupported_source`. Textové
hlášení není strojový kontrakt; každá chyba nese stabilní kód, retryability a
bezpečná strukturovaná fakta.

## Capabilities

Adaptér deklaruje podporu checksumu, konzistentního snapshotu, rozsahového
čtení, shared drives, shortcuts a cloud exportu. Společná logika nesmí schopnost
odhadovat podle názvu adaptéru. Nepodporovaná schopnost vede k explicitnímu
výsledku, ne k tichému fallbacku.

## Verze a změny během čtení

Plán zachytí `object_id` a `version_token`. Před a po transferu se ověří, že
zdrojová verze zůstala stejná. Změna vrací retryable `SOURCE_CHANGED`; částečný
soubor se nepublikuje. Lokální adaptér kontroluje minimálně velikost a přesný
mtime před/po čtení. Google Drive používá poskytovatelem garantovaný identifikátor
verze a případný checksum.

## Stabilita budoucího API

První implementace může používat interní Python protocol, ale veřejnou hranicí
má být verzovaný JSON výstup CLI. Přímý import adaptéru jinou komponentou není
navržen jako veřejný kontrakt. Přesné JSON schema a chybové kódy musí být před
implementací CLI schváleny a pokryty contract testy.
