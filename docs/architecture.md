# Architecture

The M1 pipeline is layered as CLI, application services, domain model, media
adapters, and persistence. The intended flow is `scan -> plan -> confirm ->
ingest -> report`. Originals are always opened read-only.

SQLite is the authoritative transactional state. Atomically written JSON
sidecars are portable metadata artifacts. Derived files are addressed by the
asset SHA-256 and kept outside the source tree except for the explicitly
excluded workspace directory.

Details will be expanded alongside the corresponding implementation.

