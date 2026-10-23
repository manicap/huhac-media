# MC1 — veřejný JSON CLI kontrakt

**Stav:** ACCEPTED + IMPLEMENTED

**Contract ID:** `huhac.media-connector.local-discovery`

**Contract version:** `1`

## Příkaz a streamy

`media-connector local-discovery` přijímá `--workspace`, `--source-root`,
volitelně `--page-size` (1 až 10 000, výchozí 1 000) a opaque `--cursor`.

Na stdout vždy zapíše právě jeden JSON objekt zakončený newline. Diagnostika
určená člověku může být na stderr, ale význam výsledku je vždy plně obsažen v
JSON. `--help` je jediná textová výjimka a končí bez discovery operace.

## Úspěch

```json
{
  "contract": "huhac.media-connector.local-discovery",
  "contract_version": 1,
  "operation": "local-discovery",
  "status": "success",
  "library": {
    "workspace_id": "00000000-0000-0000-0000-000000000000"
  },
  "source": {
    "adapter_kind": "local",
    "source_id": "local-sha256:<64 lowercase hex>",
    "source_root": "canonical absolute path"
  },
  "capabilities": {
    "content_read": false,
    "content_checksum": false,
    "consistent_snapshot": false,
    "pagination": true
  },
  "page": {
    "items": [],
    "returned_count": 0,
    "next_cursor": null
  },
  "warnings": [],
  "error": null
}
```

Položka obsahuje `adapter_kind`, `source_id`, opaque `object_id`,
`version_token`, normalizovaný `logical_path`, `object_kind: "file"`,
`size_bytes`, `mtime_ns`, `modified_at` a `source_checksum: null`.

Warning obsahuje `code` a `logical_path`. MC1 definuje `LINK_SKIPPED` a
`SPECIAL_FILE_SKIPPED`. Warning neznamená, že objekt byl otevřen.

Cursor je neprůhledný URL-safe token. Klient jej nesmí měnit ani vykládat.
Adapter odmítne malformed cursor a cursor vytvořený pro jiný source root.
Filesystem neposkytuje konzistentní snapshot; změny stromu mezi stránkami mohou
změnit výsledek a `consistent_snapshot` je proto vždy `false`.

## Chyba

Chybový envelope zachová prvních pět polí a má `library`, `source`,
`capabilities` a `page` jako `null`, `warnings: []` a:

```json
{
  "error": {
    "code": "SOURCE_NOT_FOUND",
    "message": "bounded human-readable message",
    "retryable": true,
    "details": {}
  }
}
```

Stabilní kódy MC1:

| Kód | Exit | Retryable |
|---|---:|---|
| `INVALID_ARGUMENT` | 2 | false |
| `WORKSPACE_NOT_FOUND` | 2 | false |
| `WORKSPACE_INVALID` | 2 | false |
| `UNSUPPORTED_WORKSPACE_CONTRACT` | 2 | false |
| `INVALID_CURSOR` | 2 | false |
| `CURSOR_SOURCE_MISMATCH` | 2 | false |
| `SOURCE_NOT_FOUND` | 3 | true |
| `SOURCE_NOT_DIRECTORY` | 2 | false |
| `SOURCE_WORKSPACE_OVERLAP` | 2 | false |
| `SOURCE_PERMISSION_DENIED` | 3 | true |
| `SOURCE_OFFLINE` | 3 | true |
| `UNSAFE_SOURCE_ROOT` | 2 | false |
| `UNSAFE_PATH` | 3 | false |
| `PATH_COLLISION` | 3 | false |
| `SOURCE_IO_ERROR` | 3 | true |
| `INTERNAL_ERROR` | 3 | false |

`SOURCE_OFFLINE` se použije jen tehdy, když operační systém poskytne
jednoznačný offline/device/network error. Neexistující nebo momentálně
neviditelný path se bez spolehlivého důkazu hlásí jako `SOURCE_NOT_FOUND`.

## Kompatibilita

Klient musí vyžadovat známé `contract` a `contract_version`. Neznámá aditivní
pole verze 1 ignoruje. Odebrání pole, změna významu nebo chybového kódu vyžaduje
novou contract version. Tento kontrakt není workspace contract v1.
