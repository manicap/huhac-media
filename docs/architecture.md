# Architecture

The M1 pipeline is layered as CLI, application services, domain model, media
adapters, and persistence. The intended flow is `scan -> plan -> confirm ->
ingest -> report`. Originals are always opened read-only.

SQLite is the authoritative transactional state. Atomically written JSON
sidecars are portable metadata artifacts. Derived files are addressed by the
asset SHA-256 and kept outside the source tree except for the explicitly
excluded workspace directory.

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

## Metadata adapters

External commands run without a shell, with explicit argument arrays, UTF-8
replacement decoding, bounded diagnostics, timeouts, and checked exit codes.
ExifTool supplies grouped raw metadata for all media; ffprobe adds video format
and stream data. Absolute source filenames are removed from raw artifacts.
Normalization is tolerant of missing fields and always stores capture-time
provenance, including an explicit filesystem fallback marker.

## Image previews

Pillow applies EXIF orientation, preserves aspect ratio, avoids upscaling by
default, composites transparency on the configured black or white background,
and writes a non-progressive JPEG. FFmpeg is an optional decoder fallback.
Preview identity includes the asset SHA-256 plus a fingerprint of processor
version and image settings. Output is validated before an atomic replace.

## Ingest and resume

After confirmation, the application initializes a versioned workspace and
takes a non-blocking OS file lock. Discovery is committed before content stages.
Each stage is marked `processing`, writes and validates its artifact, and only
then becomes `success`. On the next invocation, unfinished runs become
`interrupted` and processing stages become retryable. A successful stage is
skipped only when its matching artifact still exists. Media-stage errors are
recorded and isolated; remaining assets continue.

Each actual run immediately creates an atomic report with `running` status and a
dedicated UTF-8 log. Normal completion replaces the report with `success` or
`partial`; caught fatal errors and interrupts are recorded as `fatal` or
`interrupted`. The next invocation also closes a prior report left in `running`
state after an uncatchable process or machine failure.

For safety, WORK may be inside INPUT (where it is excluded) or completely
separate, but it may not equal or contain INPUT. A non-empty directory without a
valid workspace manifest is not silently adopted. Existing recognized
workspaces and empty target directories are reusable.

Future processor artifacts belong under
`analysis/<processor>/<processor-version>/...`. They use the same content
address and provenance pattern but remain independent of source evidence and of
each other; removing or recomputing one processor cannot damage ingest state.
