# Vision Processor v1

Vision Processor v1 is an independent consumer of the public Media Ingest
workspace contract and completed Video Keyframe Extractor v1 results. It
extracts general, visually supported facts into a stable data shape without
creating a controlled vocabulary or domain ontology.

## Inputs and responsibility boundary

For an available image asset, Vision reads only the JPEG named by the public
catalog's `preview_location`. It does not open the original image. For an
available video asset, it reads only persistent JPEG keyframes referenced by a
complete compatible `video-keyframes-v1` success result. It never opens or
decodes a video, samples frames, or invokes FFmpeg.

Vision validates all workspace-relative paths, upstream asset identities,
keyframe identities, timestamps, processor provenance, configuration
fingerprints, and referenced files. A missing image preview or missing,
invalid, or ambiguous keyframe result is reported explicitly; there is no
fallback to ingest SQLite or other internal state. If several valid upstream
keyframe configurations exist, select one with `--keyframe-fingerprint`.

## Model and prompt

The default adapter calls Ollama at `http://localhost:11434` with
`minicpm-v4.6:latest`. Both endpoint and model are configurable. Vision checks
that Ollama and the requested model are available before pending inference and
never downloads a model automatically. The endpoint is an execution location,
not part of the semantic configuration fingerprint.

The versioned neutral prompt requests only objective visual evidence. It
prohibits identification of people, venue, band, event, or inferred location;
text transcription or guessing; quality assessment; and social-media scoring.
It may record that text, a sign, logo, poster, or chalkboard exists without
claiming what it says.

## Canonical result

Each visual input produces this canonical content shape:

```json
{
  "scene": "indoor gathering",
  "people": {"approx_count": 3, "crowd": false},
  "activities": ["standing"],
  "objects": ["table"],
  "environment": ["indoor"],
  "visual_attributes": ["warm lighting"],
  "tags": ["people", "interior"],
  "description": "Several people are standing near a table indoors."
}
```

`scene` and `description` are strings. `people.approx_count` is a non-negative
integer or null, and `people.crowd` is boolean. The remaining fields are arrays
of strings and may be empty. Values use free descriptive language. Synonym
mapping, domain terms, and ontology are reserved for a future Normalizer.

After strict JSON parsing and schema validation, Vision permits only safe
technical normalization: whitespace trimming, exact list deduplication,
removal of empty list strings, decimal integer strings to integers, and
`"true"`/`"false"` to booleans. It never converts semantic phrases. If output
remains invalid, the default single repair attempt supplies the prior raw
response, validation errors, and schema while forbidding new facts.

Every attempt's raw model response and validation errors are retained for
audit. A success also stores the canonical validated result. Exhausted repair
attempts produce an explicit failed envelope and no canonical result; other
inputs continue.

## Output, provenance, and reuse

Outputs are atomic and live only below the Vision namespace:

```text
analysis/vision/vision-v1/<vision-configuration-fingerprint>/
  <sha-prefix>/<asset-sha256>/image-preview.json
  <sha-prefix>/<video-sha256>/video-keyframes/
    <video-keyframe-configuration-fingerprint>/<keyframe-id>.json
```

Each envelope records schema and workspace contract versions, workspace and
asset identity, Vision processor/model/configuration provenance, input kind,
input provenance, creation time, status/error, all raw attempts, and the
canonical result when successful. Video input provenance retains upstream
processor/fingerprint, keyframe ID, location, and timestamp.

The Vision fingerprint is canonical SHA-256 over processor and prompt recipes,
result schema version, model name, generation parameters (`temperature`,
`num_ctx`, `num_predict`), and `max_repair_attempts`. A result is reused only
when the complete success envelope, exact input provenance, configuration, and
canonical schema validate. Failed, malformed, or incomplete results are
retried. Reuse does not contact Ollama.

## CLI

```powershell
vision analyze --workspace 'D:\Media\_processing' --dry-run
vision analyze --workspace 'D:\Media\_processing' --dry-run --json
vision analyze --workspace 'D:\Media\_processing'
```

Useful options include `--model`, `--endpoint`, `--temperature`, `--num-ctx`,
`--num-predict`, `--max-repair-attempts`, and `--keyframe-fingerprint`.
Dry-run only reads contracts and existing results: it neither contacts Ollama
nor writes analysis artifacts.

## Out of scope

Vision v1 does not implement a Normalizer, ontology, Faces, recognition, OCR,
Quality, Similarity, Audio/ASR, event or identity inference, video/session
aggregation, Knowledge/Index, search, lifecycle management, collection, or
editor/story generation.
