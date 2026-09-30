# Data model

The core model distinguishes a stable source path, a version of the content
observed at that path, and an asset identified by SHA-256. A single asset can be
referenced by multiple source versions. Runs and independently versioned stages
record resumable processing state.

The concrete SQLite schema and sidecar schemas will be documented when their
implementations land.

