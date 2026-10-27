# Video Keyframe Extractor v1

Video Keyframe Extractor is an independent consumer of the Media Ingest public
workspace contract. For each available video asset it creates a small,
standardized set of representative JPEG frames for later processors such as
Vision, Faces, or OCR.

V1 is not a scene or shot detector. It does not classify camera motion,
occlusion, image quality, people, text, semantics, events, or sessions. It only
performs regular temporal sampling, CLIP embedding, within-video redundancy
reduction, and representative-frame selection.

## Responsibility boundary

The processor reads only:

- `workspace.json`;
- the referenced `metadata/catalog.json`;
- public catalog fields, including `source_root` and `sources[]`;
- one active original source for each selected asset, read-only.

It selects only catalog entries where `media_type == "video"` and
`availability == "available"`. It does not import `huhac_media`, open ingest
SQLite, use `asset_stages`, modify originals, write under `metadata/`, or touch
another processor namespace. All output belongs below
`analysis/video-keyframes/`.

The physical source path is resolved from the public contract as
`source_root / relative_path`. Paths are validated against traversal and
symlink escape. When several active sources exist, the first accessible source
in deterministic `(relative_path, source_version_id)` order is used. Before
decoding, its SHA-256 is compared with the catalogued asset identity so changed
source bytes cannot be published under the wrong asset.

## V1 algorithm

### Temporal sampling

The default `sampling_interval_s` is `1.0`. Sampling positions are
`0, interval, 2 * interval, ...` strictly before the ffprobe duration. Each
sample is requested by timestamp rather than frame number, so variable-frame-
rate video does not change the sampling basis. The requested timestamp relative
to the source video is retained in output provenance.

This is regular coverage sampling only. It does not inspect or estimate shot
boundaries.

### Image representation

FFmpeg decodes the requested timestamp and applies its default display-matrix
autorotation. The scale filter uses a no-upscale bounding box and preserves
aspect ratio:

```text
scale=w='min(768,iw)':h='min(768,ih)':
  force_original_aspect_ratio=decrease:force_divisible_by=2
```

Pillow then publishes a standardized non-progressive JPEG with:

- sRGB representation and embedded sRGB profile;
- EXIF orientation normalization where present;
- maximum width and height of 768 pixels;
- no upscaling;
- preserved aspect ratio;
- default JPEG quality 90 and fixed 4:2:0 subsampling.

The same representation is used for CLIP input and persistent keyframes.

### CLIP embedding

V1 uses OpenCLIP with:

```text
model:      ViT-B-32-quickgelu
pretrained: openai
device:     CPU
```

OpenCLIP 3.3.0 declares `quick_gelu: true` for the `openai` pretrained tag.
The corrected default therefore uses the matching `ViT-B-32-quickgelu`
architecture. It resolves to the same OpenAI checkpoint as `ViT-B-32`; no new
weights are required. The earlier `ViT-B-32/openai` configuration remains
available only for explicit reuse of legacy results.

Embeddings are L2-normalized. Cosine similarity is therefore their scalar
product. Model and pretrained identities, execution device, representation
settings, sampling recipe, selection recipe, and thresholds are all included
in the configuration fingerprint.

### Coverage reduction and representative selection

Coverage is computed independently inside one video asset. Frames from
different assets are never compared or merged.

The configurable default `coverage_similarity` is `0.85`. It is a versioned v1
working value, not a universal property or recommended constant of CLIP.

V1 repeatedly chooses the candidate covering the greatest number of currently
uncovered samples at or above the threshold. Equal coverage is resolved by the
lowest sample index. Newly covered samples form a disjoint coverage group.

The coverage candidate is not automatically the keyframe. For each group, v1
L2-normalizes the mean embedding and selects the real group member with maximum
similarity to that centroid. Equal scores use the lowest sample index. No
synthetic image is generated.

## Temporary and persistent artifacts

Decoded PNGs and all regular sampled JPEGs live in a temporary directory and
are removed on success, ordinary failure, and handled interruption. They are
not long-term processor output.

Only selected keyframe JPEGs and one per-asset result JSON are persistent. An
interrupted run without a valid success envelope is never reusable. The next
run recomputes it. The processor never deletes originals, ingest previews,
metadata, or another processor's data.

## Output contract

The deterministic per-asset result follows the workspace processor convention:

```text
analysis/video-keyframes/video-keyframes-v1/
  <configuration-fingerprint>/
    <sha-prefix>/
      <sha256>.json
      <sha256>/keyframes/keyframe-0000.jpg
```

The JSON uses the documented result envelope:

```json
{
  "result_schema_version": 1,
  "workspace_contract_version": 1,
  "workspace_id": "uuid",
  "asset_id": "sha256:<sha256>",
  "sha256": "<sha256>",
  "processor": {
    "name": "video-keyframes",
    "version": "video-keyframes-v1"
  },
  "model": {
    "framework": "OpenCLIP",
    "name": "ViT-B-32-quickgelu",
    "version": "openai",
    "pretrained": "openai",
    "device": "cpu"
  },
  "configuration": {},
  "configuration_fingerprint": "<sha256>",
  "created_at": "ISO-8601 UTC timestamp",
  "status": "success",
  "error": null,
  "result": {
    "source": {},
    "sampling": {},
    "coverage_similarity": 0.85,
    "keyframes": []
  }
}
```

Each keyframe records its relative location, timestamp, source video asset ID
and SHA-256, processor version, model/pretrained identity, configuration
fingerprint, JPEG dimensions and color space, coverage candidate, and member
sample indices. The result records the chosen source version and relative path,
video duration, sampling interval, and sampled-frame count.

Failed assets receive an atomic `status: "failed"` envelope with a structured
error and null result. Other video assets continue. A success envelope is
written only after all referenced keyframes exist.

## Idempotence and reuse

The configuration fingerprint is SHA-256 over canonical JSON containing every
v1 setting that changes result meaning. Asset SHA-256 supplies the input
identity and output suffix.

The corrected `ViT-B-32-quickgelu/openai` default has fingerprint
`1b339d6eb4fd53c926338d2f93b0894afbbb473d7b0dd49d5f5b63b2b882783a` with
otherwise default v1 settings. Legacy `ViT-B-32/openai` results retain their
original fingerprint
`4046e8696c035f5753c3ec08aa0d71a8bf5e4821c7403c79d83813b308e890d1`.
Both remain isolated below their respective fingerprint directories and use
the same public result schema and processor version.

Once both configurations exist for an asset, downstream consumers deliberately
require an explicit keyframe fingerprint instead of choosing one arbitrarily.
For example, Media Desk, Vision, and Faces accept
`--keyframe-fingerprint 1b339d6eb4fd53c926338d2f93b0894afbbb473d7b0dd49d5f5b63b2b882783a`
for the corrected configuration. No Media Desk profile is changed
automatically.

An existing result is reused only when its schema, contract version, asset,
processor, model, complete configuration, fingerprint, success status, and all
referenced keyframe files validate. Reuse performs no source decode, ffprobe,
FFmpeg, or CLIP inference. Failed, malformed, incomplete, or missing results are
retried.

Result JSON and individual publication steps are atomic. Temporary staging is
kept within the processor's own output scope or the operating-system temporary
directory.

## CLI

Install the processor dependencies without requesting a CUDA-specific build:

```powershell
python -m pip install -e ".[video-keyframes]"
```

Analyze a workspace:

```powershell
video-keyframes analyze --workspace 'D:\Media\_processing'
```

Select one or more explicit video assets by repeating `--asset-id`:

```powershell
video-keyframes analyze --workspace 'D:\Media\_processing' `
  --asset-id 'sha256:<64 lowercase hex characters>' `
  --asset-id 'sha256:<64 lowercase hex characters>'
```

The selector is optional. Without it, all available video assets retain the
existing behavior. Repeated IDs are deduplicated and the selected assets are
processed in deterministic SHA-256 order. Every selected ID must use the
canonical lowercase `sha256:<64 hex>` form, exist in the public catalog, refer
to a video, and be available. Invalid selections fail before processing or
output creation. Selection does not enter the configuration fingerprint: it
only limits which independently identified per-asset results are planned, so
existing compatible results keep their normal reuse behavior.

Read-only planning without FFmpeg, ffprobe, model loading, or CLIP inference:

```powershell
video-keyframes analyze --workspace 'D:\Media\_processing' --dry-run
video-keyframes analyze --workspace 'D:\Media\_processing' --dry-run --json
```

`--asset-id` works identically with `--dry-run --json`, allowing a selected
pilot set to be validated without FFmpeg, ffprobe, model loading, inference, or
writes.

Configure the v1 sampling and coverage parameters:

```powershell
video-keyframes analyze --workspace 'D:\Media\_processing' `
  --sampling-interval-s 1.0 --coverage-similarity 0.85
```

The matching QuickGELU architecture is the default. To inspect or reuse
results made by the earlier mismatched configuration without overwriting them:

```powershell
video-keyframes analyze --workspace 'D:\Media\_processing' `
  --clip-model ViT-B-32
```

`--max-dimension`, `--jpeg-quality`, `--clip-model`, `--ffmpeg`, and
`--ffprobe` are also available. `python -m video_keyframes` provides the same
CLI. `--clip-model` is intentionally limited to the corrected default and the
legacy architecture; both use the `openai` pretrained tag.

Exit codes follow the repository convention:

- `0`: success, complete reuse, or successful dry-run;
- `1`: one or more per-asset failures;
- `2`: invalid configuration or incompatible/malformed public contract;
- `3`: missing dependency or fatal operating-system failure.
- `130`: interrupted with Ctrl+C before a complete result was published.

## Dependencies

- FFmpeg for timestamp-based frame decoding and orientation handling;
- ffprobe for source duration;
- OpenCLIP (`open_clip_torch`) with model `ViT-B-32-quickgelu`, pretrained
  `openai`;
- PyTorch with CPU execution supported and used by v1;
- Pillow for standardized JPEG publication;
- NumPy for normalized embeddings and deterministic selection.

Ordinary tests use fake adapters and do not download a CLIP model or decode a
long video. External tests exercise the real FFmpeg boundary separately.

## Known limitations

- Fixed-interval sampling can miss very brief visual changes between samples.
- No scene or shot detection.
- No quality, blur, occlusion, or camera-motion classification.
- No face recognition, OCR, semantic interpretation, event identity, or
  session changes.
- No cross-video similarity or coverage.
- No GPU/CUDA-specific installation or acceleration workflow.
- No global retention/lifecycle manager or orchestration.
- Pillow's generated sRGB ICC profile can differ byte-for-byte between runs
  even when the decoded JPEG pixels at the same timestamp are identical. This
  does not affect an already published result's reuse, but persistent JPEG
  bytes are not currently reproducible across fresh processing runs.
