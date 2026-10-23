# Media Connector — společné rozhraní adaptérů

**MC1 stav:** IMPLEMENTED

**Budoucí adaptéry:** TARGET / NOT IMPLEMENTED

Rozhraní odděluje zdrojový protokol od CLI a společné discovery služby. Python
`Protocol` je interní implementační hranice; veřejným API je verzovaný JSON CLI.

## Implementovaný MC1 kontrakt

```text
adapter_kind -> stable string
source_id -> source-bound identifier
capabilities -> AdapterCapabilities
list_page(page_size, cursor) -> ObjectPage
```

`LocalFilesystemAdapter` vrací jen běžné soubory. `SourceObject` obsahuje:

- `adapter_kind`, `source_id` a opaque `object_id`;
- observační `version_token` odvozený z velikosti a `mtime_ns`;
- NFC-normalizovanou relativní `logical_path` s `/` oddělovači;
- `size_bytes`, `mtime_ns` a UTC `modified_at`;
- `object_kind: file`, `media_type_hint: null` a `source_checksum: null`.

MC1 discovery neotevírá obsah a společný `SourceAdapter` Protocol proto zůstává
metadata-only. Schválený Local Transfer používá oddělený interní read-only port
`open_read(object_id, logical_path, expected_version)` konkrétního lokálního
adaptéru. Budoucí adaptéry musí dodat ekvivalentní read-only SourceReader port,
aniž by do discovery Protocolu přidaly mutační operace.

## Pagination

Cursor je URL-safe JSON token zakódovaný base64url a obsahuje contract verzi,
source ID a poslední logickou cestu. Je source-bound a validovaný, ale není
autentizační ani autorizační token. Každá stránka znovu bezpečně enumeruje celý
strom a pokračuje lexikograficky za poslední cestou.

Filesystem neposkytuje konzistentní snapshot. Přidání, odstranění nebo
přejmenování během stránek může změnit výsledek; capability
`consistent_snapshot` je proto `false`.

## Chyby a capabilities

Adapter vyhazuje interní strukturovanou `ConnectorError`. CLI ji převádí na
veřejný envelope a stabilní kódy z [MC1_JSON_CONTRACT.md](MC1_JSON_CONTRACT.md).
MC1 capabilities jsou:

```json
{
  "content_read": false,
  "content_checksum": false,
  "consistent_snapshot": false,
  "pagination": true
}
```

Budoucí Google Drive adaptér musí implementovat stejnou discovery hranici, ale
jeho opaque ID, version token, stránkování a typy cloud-native dokumentů budou
zdrojově specifické. Není součástí MC1.
