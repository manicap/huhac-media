# Media workspace contract

This document defines the public boundary between Huháč Media Ingest, the
producer, and independent processors such as vision, faces, OCR, quality,
audio, and indexing consumers. Contract version 1 does not require consumers to
import ingest Python code or understand its SQLite schema.

## Entry point and versioning

The entry point is `workspace.json`:

```json
{
  "asset_catalog": "metadata/catalog.json",
  "schema_version": 1,
  "workspace_contract_version": 1,
  "workspace_id": "uuid"
}
```

`workspace_contract_version` is the public contract major version. A consumer
must reject a missing or unsupported value instead of guessing. Additive fields
may appear within major version 1 and must be ignored when unknown. Removing a
required field, changing its meaning, or changing a documented path requires a
new major version.

`schema_version` is the producer's workspace-layout version. Consumers validate
the public contract version and must not infer SQLite compatibility from this
field. Existing M1 manifests that contain only `schema_version` and
`workspace_id` are upgraded additively on the next actual ingest; no workspace
deletion or media reingest is required. Dry-run never performs this upgrade.

The asset catalog is atomically replaced near the end of each actual ingest. If
an ingest terminates before publication, consumers continue to see the last
complete catalog. A new or legacy workspace may have no catalog until its first
successful or partially successful contract-aware ingest.

## Public contract

Consumers may rely on these producer-owned files:

- `workspace.json`: contract discovery, version, workspace identity.
- `metadata/catalog.json`: authoritative asset enumeration, source provenance,
  availability, and artifact locations.
- `metadata/assets/<sha-prefix>/<sha256>.json`: normalized metadata and ingest
  stage status for one asset.
- paths referenced by `raw_metadata` in an asset document: optional, opaque
  tool output; its inner schema belongs to ExifTool or ffprobe.
- a non-null `preview_location`: an existing JPEG image preview.

All paths stored in the contract use `/` separators and are relative to the
workspace, except `source_root`, which is an absolute path refreshed by ingest.
To open an original, combine `source_root` with an `active` source's
`relative_path`. Treat source paths as provenance and validate them before use.

`metadata/catalog.json` has this shape:

```json
{
  "workspace_contract_version": 1,
  "workspace_id": "uuid",
  "generated_at": "ISO-8601 UTC timestamp",
  "generated_by_run_id": "uuid",
  "source_root": "absolute input directory",
  "assets": [
    {
      "asset_id": "sha256:<64 lowercase hex characters>",
      "sha256": "<64 lowercase hex characters>",
      "size_bytes": 123,
      "media_type": "image",
      "format": "JPEG",
      "mime_type": "image/jpeg",
      "availability": "available",
      "metadata_location": "metadata/assets/ab/ab...json",
      "preview_location": "previews/images/ab/ab...jpg",
      "sources": [
        {
          "source_version_id": "uuid",
          "relative_path": "event/photo.jpg",
          "status": "active"
        }
      ]
    }
  ]
}
```

Required asset fields are `asset_id`, `sha256`, `size_bytes`, `media_type`,
`format`, `mime_type`, `availability`, `metadata_location`,
`preview_location`, and `sources`. `media_type` is `image` or `video`.
`availability` is `available` when at least one source version is active in the
published discovery snapshot and `unavailable` otherwise. Source status is
`active`, `superseded`, or `absent`.

`metadata_location` is null only when no asset metadata artifact has been
published. `preview_location` is null when there is no validated preview; this
is normal for video. A non-null artifact location names a file that existed
when the catalog was published. Consumers should still handle concurrent file
or workspace movement as an I/O error.

There is exactly one catalog entry per content identity. Two source files with
the same SHA-256 reference one asset. Renaming a source creates source
provenance but does not change the asset ID. Changing source bytes creates or
reactivates the corresponding different asset ID. Unsupported files never
appear in `assets`.

## Internal implementation detail

The following are owned by ingest and are not public APIs:

- `state/`, including `state/catalog.sqlite3`, its tables, WAL files, and
  migration numbers;
- `metadata/sources/` naming and document lifecycle;
- `runs/`, `logs/`, `tmp/`, and `locks/`;
- Python packages, classes, enums, and service interfaces;
- ingest processor-stage table rows and their database status transitions.

Consumers must not write anywhere in `workspace.json`, `state/`, `metadata/`,
`previews/`, `runs/`, `logs/`, `tmp/`, or `locks/`. Direct SQLite reads are not
supported: they couple a consumer to transactional state, may observe an
in-progress run, and prevent ingest from evolving its private schema.

## Processor-owned output

Each processor writes only beneath this deterministic namespace:

```text
analysis/<processor>/<processor-version>/<configuration-fingerprint>/
  <sha-prefix>/<sha256>.json
```

`processor` and `processor-version` must be path-safe stable identifiers. The
configuration fingerprint is the lowercase SHA-256 of a processor-defined,
canonically serialized recipe. The recipe must cover every input that changes
result meaning, including prompt version, model and model version, thresholds,
and relevant options. The file is keyed by asset SHA-256, never by source path.

A processor result uses this envelope:

```json
{
  "result_schema_version": 1,
  "workspace_contract_version": 1,
  "asset_id": "sha256:<64 lowercase hex characters>",
  "sha256": "<64 lowercase hex characters>",
  "processor": {
    "name": "vision",
    "version": "vision-v1"
  },
  "model": {
    "name": "example-model",
    "version": "4.6"
  },
  "configuration_fingerprint": "<64 lowercase hex characters>",
  "created_at": "ISO-8601 UTC timestamp",
  "status": "success",
  "error": null,
  "result": {}
}
```

`model` may be null for a processor without a model. A durable result status is
`success` or `failed`; failed output has a structured `error` and a null or
partial `result`. Absence of the exact recipe path means pending. A processor
may keep its own processing/queue state under its namespace, but that state is
not part of the ingest contract. Result files must be written by atomic replace
so readers never observe partial JSON.

To decide whether work is current, compute the desired processor version and
configuration fingerprint, construct the exact path, then validate the
envelope's asset ID, processor/model provenance, fingerprint, schema version,
and status. A different model, model version, prompt, or configuration produces
a different fingerprint/path and therefore needs independent processing.

Ingest may create the empty top-level `analysis/` directory, but it never owns,
deletes, interprets, or fabricates processor results. Processors must likewise
not put results into ingest's `asset_stages` table or asset metadata documents.

## Consumer algorithm

1. Read `workspace.json` and require `workspace_contract_version == 1`.
2. Resolve and read `asset_catalog` relative to the workspace.
3. Require the catalog version and workspace ID to match the entry point.
4. Iterate `assets` once; normally select `availability == "available"`.
5. Read `metadata_location` and optional `preview_location` as needed.
6. Choose an active source reference only when original bytes are required.
7. Compute the processor recipe fingerprint and inspect the exact analysis
   result path. Skip a valid successful result, retry or report a failed result,
   and treat an absent result as pending.

This algorithm deduplicates processing by asset identity and remains independent
of ingest's database and Python implementation.

## Known limits of version 1

- Ingest catalogs metadata and image previews but does not copy original media;
  `source_root` is therefore machine-local. Moving INPUT requires a subsequent
  ingest to refresh it, or an explicit source-root override in the consumer.
- Video assets have no ingest-generated visual preview in M1.
- There is no shared orchestrator or cross-processor registry. Each processor
  owns scheduling, locking, retention, and schema evolution inside its namespace.
