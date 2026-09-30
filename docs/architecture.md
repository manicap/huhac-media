# Architecture

The M1 pipeline is layered as CLI, application services, domain model, media
adapters, and persistence. The intended flow is `scan -> plan -> confirm ->
ingest -> report`. Originals are always opened read-only.

SQLite is the authoritative transactional state. Atomically written JSON
sidecars are portable metadata artifacts. Derived files are addressed by the
asset SHA-256 and kept outside the source tree except for the explicitly
excluded workspace directory.

Details will be expanded alongside the corresponding implementation.

## Processing state

Each asset stage has `pending`, `processing`, `success`, or `failed` state and
tracks its processor version and configuration fingerprint. A crash therefore
cannot turn a partially written artifact into successful work. The schema also
keeps source-path history instead of overwriting a previous asset association.

## Discovery and identity

The scanner walks INPUT recursively without following directory links. It
excludes the resolved WORK subtree rather than matching a directory name.
Detection uses binary signatures where available and a maintained candidate
extension list for formats such as RAW and transport streams. Metadata probing
later validates and enriches the formal format. Every supported candidate is
hashed in full; a size or mtime change during hashing yields `UNSTABLE_SOURCE`.

The pure planner compares scan results with an immutable catalog snapshot. The
same planner drives dry-run and real ingest. `known`, `new`, and `changed` are
exclusive classifications; exact duplicate and previous failure are additional
flags and may overlap those classifications.
