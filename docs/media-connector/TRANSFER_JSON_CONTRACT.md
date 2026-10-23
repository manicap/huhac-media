# Media Transfer JSON CLI contract v1

**Stav:** IMPLEMENTED

**Rozsah ověření:** nativní Windows, lokální fixed drive

Veřejnou hranicí Transferu je CLI. Python moduly, privátní SQLite a její schema
nejsou veřejné API.

## Příkazy

```powershell
media-connector transfer preflight `
  --workspace 'C:\library\workspace' `
  --media-storage 'D:\library\media' `
  --state-root 'C:\Users\user\AppData\Local\Huhac\connector-state' `
  --transfer-work-root 'D:\library-transfer-work' `
  --selection 'C:\selection-v1.json'

media-connector transfer run `
  --workspace 'C:\library\workspace' `
  --media-storage 'D:\library\media' `
  --state-root 'C:\Users\user\AppData\Local\Huhac\connector-state' `
  --transfer-work-root 'D:\library-transfer-work' `
  --selection 'C:\selection-v1.json' `
  --operation-id '9d9db593-1558-466e-a33e-ae0158939f39' `
  --yes

media-connector transfer recover `
  --workspace 'C:\library\workspace' `
  --media-storage 'D:\library\media' `
  --state-root 'C:\Users\user\AppData\Local\Huhac\connector-state' `
  --transfer-work-root 'D:\library-transfer-work'
```

Preflight je read-only a všechny jeho kořeny musí už existovat. `run` validace
zopakuje pod single-writer lockem. `recover` nepotřebuje dostupný externí zdroj;
pracuje pouze s write-ahead stavem, izolovaným stagingem a publikovaným CAS.

## Selection v1

```json
{
  "contract": "huhac.media-connector.transfer-selection",
  "contract_version": 1,
  "workspace_id": "12345678-1234-5678-1234-567812345678",
  "source": {
    "adapter_kind": "local",
    "source_id": "local-sha256:<digest>",
    "source_root": "C:\\incoming"
  },
  "items": [
    {
      "object_id": "local-path-v1:<opaque>",
      "version_token": "local-stat-v1:<size>:<mtime_ns>",
      "logical_path": "camera/photo.jpg"
    }
  ]
}
```

Selection neobsahuje cílové cesty. Hodnoty musí přesně odpovídat výsledku
`local-discovery`; Transfer znovu ověří source ID, object ID, confinement a
version token. Současná implementace záměrně podporuje pouze `local` adapter.

## Výstup

Každý příkaz vypíše právě jeden minifikovaný JSON objekt na stdout a žádný běžný
text na stderr. Envelope používá:

```json
{
  "contract": "huhac.media-connector.transfer",
  "contract_version": 1,
  "operation": "transfer-preflight|transfer-run|transfer-recover",
  "status": "success|error",
  "library": {"workspace_id": "<uuid>"},
  "source": null,
  "preflight": null,
  "run": null,
  "error": null
}
```

Úspěšná položka `transfer-run` obsahuje `status`, `content_sha256`, `size_bytes`
a CAS `relative_path`. Stav je `published` nebo `deduplicated_existing`.
Rekonciliovaná položka používá `recovered_published`. `complete` znamená pouze
dokončený Transfer, nikoli provedený Media Ingest.

## Exit codes a stabilní chyby

- `0` — úspěch;
- `2` — argument, selection, workspace nebo root konfigurace;
- `3` — zdroj je nedostupný, změněný nebo nečitelný;
- `4` — stav, integrita, staging, filesystem nebo publish selhání.

Stabilní bezpečnostní chyby zahrnují `ROOT_OVERLAP`,
`STAGING_FILESYSTEM_MISMATCH`, `UNSUPPORTED_FILESYSTEM`, `SOURCE_CHANGED`,
`FORMAT_NOT_INGEST_COMPATIBLE`, `TRANSFER_WRITER_BUSY`,
`STAGED_CONTENT_MISMATCH`, `CONTENT_OBJECT_CORRUPT_OR_COLLISION`,
`ATOMIC_PUBLISH_FAILED`, `STATE_LIBRARY_MISMATCH`,
`RECOVERY_EVIDENCE_MISSING` a `RECOVERY_EVIDENCE_INVALID`.

Chyba nikdy neopravuje, nepřepisuje ani nemaže existující CAS objekt. Partial
staging a integritní důkazy se automaticky nemažou.

## Persistence a přenositelnost

`connector-state.sqlite3` pod `state-root` je lokální provozní stav svázaný s
`workspace_id`. Není katalogem Ingestu, nesmí být sdíleným multi-host writerem a
jeho schema není veřejný kontrakt. Každý dokončený run atomicky vydá redigovaný
`manifests/<operation-id>.json`; ten neobsahuje absolutní source root ani tokeny a
je přenositelnou evidencí dokončených source-content vazeb.

Na jiném hostu lze SQLite použít pouze jako explicitně obnovenou zálohu se
shodným `workspace_id`. Bez ní se vytvoří nový lokální stav; existující objekty se
nesmějí slepě adoptovat a při opakovaném transferu se vždy plně ověří jejich hash.

## Compatibility Profile v1

Profil rozhoduje pouze podle signatury obsahu, v pevném pořadí. Podporuje JPEG,
PNG, TIFF-signature obsah, WebP, AVI, MKV, HEIC-family ISO-BMFF, MOV, běžný MP4,
MTS a M2TS. Kanonické přípony jsou pevně mapované a nejsou součástí identity.

Formáty, které současný Ingest rozlišuje pouze podle zdrojové přípony, a
nejednoznačný CR3-like ISO-BMFF se v této verzi odmítnou. Změna profilu působí
jen na nové objekty; existující payloady nepřejmenovává ani nepřemisťuje.
