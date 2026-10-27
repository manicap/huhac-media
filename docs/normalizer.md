# Metadata Normalizer v1

> **N3 IMPLEMENTED 2026-10-26.** Media Desk reads an explicitly selected immutable
> snapshot, validates it without importing Normalizer internals, builds exact
> facet indexes, and composes an effective view with separately owned user names
> and events. Enrichment and Quality Processor remain planned/absent.

## Status and scope

**N1 — IMPLEMENTED.** Identity, source facts, safe scalar conversion, technical
and capture metadata, provenance, immutable snapshots, and CLI.

**N2 — IMPLEMENTED.** Explicit Session Grouper, Video Keyframes, Vision, Faces,
and optional Faces Clustering selections; per-input projections; exact semantic
facets; and analysis completeness.

**N3 — IMPLEMENTED.** Media Desk adapter, exact normalized filters, diagnostics,
and the effective user-assertion overlay are implemented without changing N2 or
any upstream producer.

The accepted boundary is [ADR-N1](ADR-N1-normalizer-contract.md), including its
N2 extension. The repository-root `HUHAC_NORMALIZER_V1_DESIGN_2026-10-26.md`
remains the broader design record.

## Inputs, ownership, and selection

Normalizer reads only documented public JSON: `workspace.json`, the referenced
catalog and per-asset metadata, and explicitly selected processor results. It
never reads ingest SQLite, original media, opaque raw metadata, model APIs, or
Media Desk user data. It only checks that public preview/keyframe references
are confined files; it does not decode them.

N2 configuration accepts these SHA-256 selections:

- Session Grouper configuration plus optional logical input fingerprint;
- Video Keyframes configuration;
- Vision configuration;
- Faces configuration;
- optional Faces Clustering configuration plus optional logical input.

Aggregate processors may omit the logical input only when exactly one valid
candidate exists. Multiple valid candidates are `ambiguous` and block
publication. When downstream video analysis is requested without a keyframe
selection, multiple compatible keyframe configurations are likewise blocking;
Normalizer never chooses by timestamp. A selected but absent path is
`input_unavailable`, not a configuration error or `success_empty`.

Every selected JSON document contributes its byte SHA-256 to
`input_set_fingerprint`. Missing, unreadable, invalid, and ambiguous inputs use
explicit sentinels. `configuration_fingerprint` includes the N2 recipe and all
selections. This preserves deterministic rebuilds when whitespace or any other
upstream JSON byte changes.

## Output contract

N2 retains the N1 immutable layout:

```text
analysis/normalizer/normalizer-v1/
  <configuration_fingerprint>/
    <input_set_fingerprint>/
      manifest.json
      assets/<sha-prefix>/<sha256>.json
```

Publication uses a sibling staging directory, fsynced asset documents,
manifest-last creation, and atomic directory replacement. Complete matching
snapshots are reused; an incomplete or conflicting destination is rejected.
History is never cleaned automatically. N1 manifests remain readable.

Each `NormalizedAsset v1` keeps the nine stable sections:

- `identity`, `technical`, and capture data preserve N1 source facts;
- `temporal.session_candidates[]` preserves session interval, operational day,
  boundary/confidence, membership confidence/reason, timestamp evidence, and
  aggregate provenance; unassigned reasons remain in completeness;
- `semantic.observations[]` preserves one image-preview or video-keyframe
  observation, including keyframe time and both configuration fingerprints;
- `semantic.facets` trims values, groups only exact Unicode-casefold variants,
  chooses a deterministic display value, and retains observation provenance;
- `people.vision_people_observations[]` stays separate from
  `people.face_observations[]`;
- Faces observations contain per-input detection counts, detector confidence,
  and references, but no embeddings, landmarks, or boxes;
- `people.detected_face_count` is the image-preview detection count for an
  image and always `null` for video;
- `people.anonymous_cluster_refs[]` identifies anonymous memberships only;
  neither cluster IDs nor `core` status identify a person;
- sessions are not events, and N2 creates no event name or candidate.

Completeness statuses are `success_nonempty`, `success_empty`, `not_analyzed`,
`failed`, `not_applicable`, `input_unavailable`, `ambiguous`, `invalid`, and
`unknown`. Vision/Faces video input status is also retained per keyframe.

## CLI

All commands accept `--json`. Typical explicit selection:

```powershell
normalizer plan --workspace 'D:\Media\_processing' `
  --session-fingerprint <sha256> --session-input <sha256> `
  --keyframes-fingerprint <sha256> `
  --vision-fingerprint <sha256> --faces-fingerprint <sha256> `
  --faces-clustering-fingerprint <sha256> --faces-clustering-input <sha256>

normalizer analyze --workspace 'D:\Media\_processing' `
  --keyframes-fingerprint <sha256> `
  --vision-fingerprint <sha256> --faces-fingerprint <sha256> --json

normalizer status --workspace 'D:\Media\_processing' --json
```

`plan` is read-only and reports selections, expected inputs, state counts,
blocking ambiguity, fingerprints, and predicted reuse. `analyze` projects all
valid inputs while retaining per-input failures and publishes only when
selection is unambiguous. `status` is read-only and validates historical
snapshots, including analyzed/unprocessed counts, conflicts, and namespace
size.

Exit codes are `0` complete success, `1` partial data, ambiguity in `plan`, or
invalid history, `2` usage/public-contract error (including ambiguous
`analyze`), `3` fatal output/I/O error, and `130` interrupt.

## Tests and known limits

```powershell
python -m pytest tests/normalizer -q
```

Tests use isolated synthetic public workspaces based on the actual producer v1
envelopes. They cover N1 preservation, all N2 processors, per-keyframe
observations, exact facets, completeness distinctions, byte-sensitive input
identity, ambiguity, immutable reuse, fault injection, and forbidden private
inputs.

N2 performs no inference, synonym/translation enrichment, quality score,
identity recognition, event naming, database, or orchestration. N3 indexing is
owned by Media Desk and does not alter Normalizer output. Producer contract
changes and retention remain outside Normalizer v1.
