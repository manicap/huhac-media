# Faces Processor v1

Faces v1 is an independent consumer of the public media-workspace contract. It
does not import `huhac_media`, read ingest SQLite, open image originals, modify
producer-owned artifacts, or write outside `analysis/faces/`.

## Inputs

The processor starts at `workspace.json`, validates workspace contract version
1, follows `metadata/catalog.json`, and selects only available assets:

- an image asset uses the JPEG named by public `preview_location`;
- a video asset uses persistent JPEGs from one complete, compatible
  `video-keyframes-v1` result.

If more than one compatible keyframe configuration exists, the caller must
choose one with `--keyframe-fingerprint`. Missing previews or keyframe results
are explicit skipped-input issues. Paths are constrained to the workspace.

## Detection and embedding

Detection uses OpenCV `FaceDetectorYN` with the official
`face_detection_yunet_2023mar.onnx` model. The versioned defaults are score
threshold `0.70`, NMS threshold `0.30`, and `top_k=5000`. For every accepted
face, Faces v1 records the clipped integer bounding box, detector confidence,
and YuNet's five landmarks in this order: right eye, left eye, nose tip, right
mouth corner, left mouth corner.

Bounding boxes are clipped to decoded image boundaries before slicing. Empty,
negative, outside-only, and non-finite boxes are rejected. Windows paths never
pass through OpenCV's filename API: images are read with `numpy.fromfile` plus
`cv2.imdecode`; the shared image writer uses `cv2.imencode` plus
`numpy.ndarray.tofile`.

Embedding uses Intel Open Model Zoo
`face-reidentification-retail-0095` through OpenVINO on CPU. The clipped,
unaligned face crop is resized to `128 x 128`, retained in BGR order, passed as
`1 x 3 x 128 x 128`, flattened from the model's 256-value output, and
L2-normalized. V1 intentionally does not perform landmark alignment.

## Per-input output and provenance

The configuration fingerprint is SHA-256 over canonical JSON containing the
detector and embedding model identities, thresholds, device, dimensions, color
order, OpenVINO model precision, explicit `alignment: none`, recipe, and result
schema version. A changed meaning therefore gets a distinct path.

```text
analysis/faces/faces-v1/<configuration-fingerprint>/
  <sha-prefix>/<sha256>/image-preview.json
  <sha-prefix>/<sha256>/video-keyframes/
    <keyframe-configuration-fingerprint>/<keyframe-id>.json
```

Each atomic JSON envelope identifies the workspace, asset, visual input,
models, complete configuration, and fingerprint. Every face has a deterministic
`face-0000`-style ID, bbox, confidence, five named landmarks, normalized 256D
embedding, and its own copy of the visual-input provenance. That provenance
retains the public preview location or the
keyframe ID, location, timestamp, source video identity, upstream processor
version, and upstream configuration fingerprint.

A prior result is reused only if its success envelope, workspace and asset
identity, exact input provenance, models, complete configuration, fingerprint,
image result, and all face records validate. Failed, malformed, missing, or
forced results are recomputed. JSON publication uses fsync and atomic replace.

## Clustering

Clustering is a separate command. It reads successful Faces v1 results for an
explicit Faces configuration fingerprint and never loads YuNet or OpenVINO.
Embeddings are normalized again defensively and compared by cosine similarity.

V1 uses deterministic agglomerative complete-link clustering. Two clusters can
merge only when the minimum similarity across every cross-cluster face pair is
at least the versioned default `0.70`. The highest complete-link similarity is
merged first and deterministic member order resolves ties. There is no attach,
expansion, or second phase. Multi-face clusters have `status: "core"`;
singletons remain `status: "uncertain"`. IDs such as `face-cluster-0000` are
anonymous and do not assert a person's identity.

Aggregate output is stored atomically at:

```text
analysis/faces/faces-clustering-v1/
  <cluster-configuration-fingerprint>/<logical-input-fingerprint>.json
```

The logical input fingerprint covers workspace identity, the source Faces
fingerprint, every face identity, and every embedding. The cluster
configuration fingerprint covers cosine distance semantics, complete-link,
threshold, explicit absence of expansion, recipe, and schema version. An exact
successful result is reusable.

## CLI

Install runtime dependencies:

```powershell
python -m pip install -e ".[faces]"
```

Model weights are not vendored. Obtain only the official files documented in
[`THIRD_PARTY_MODELS.md`](../THIRD_PARTY_MODELS.md), then analyze:

```powershell
faces analyze --workspace 'D:\Media\_processing' `
  --yunet-model 'D:\Models\face_detection_yunet_2023mar.onnx' `
  --reid-model 'D:\Models\face-reidentification-retail-0095\FP32\face-reidentification-retail-0095.xml'
```

Read-only planning performs no decoding or model loading:

```powershell
faces analyze --workspace 'D:\Media\_processing' --dry-run --json
```

Run clustering with the fingerprint printed by `faces analyze`:

```powershell
faces cluster --workspace 'D:\Media\_processing' `
  --faces-fingerprint '<64 lowercase hex characters>'
```

`--score-threshold`, `--nms-threshold`, `--top-k`, `--reid-precision`, and
`--similarity-threshold` expose the versioned working parameters. Both commands
also accept `--force`, `--dry-run`, and `--json`. `python -m faces` is
equivalent.

## Real acceptance checkpoint

The 2026-10-03 acceptance run used the official YuNet 2023mar ONNX weights and
the FP32 Intel Open Model Zoo `face-reidentification-retail-0095` IR through
OpenVINO CPU. The public workspace supplied 12 image previews and five
persistent keyframes from four video assets. All 17 visual inputs succeeded
without a skipped or failed input and produced 20 faces: 19 from image previews
and one from a video keyframe.

Every published face had an in-bounds clipped bbox, five landmarks, a 256D
embedding, and matching per-face input provenance. Serialized embedding norms
ranged from `0.999999940` to `1.000000068`. A second identical analyze run
reused all 17 results without loading the models or changing result content or
timestamps.

At the default cosine complete-link threshold `0.70`, the 20 embeddings formed
19 anonymous clusters: one two-member core cluster and 18 uncertain
singletons. The core pair similarity was `0.929446051`; the highest remaining
complete-link candidate was `0.381183556`. A second identical clustering run
reused the same logical-input result without rewriting it.

## Explicit non-goals and limitations

- no names, automatic identity assignment, or person identification;
- no age, gender, emotion, OCR, or quality inference;
- no landmark alignment in v1, although the embedding model's official
  documentation says aligned frontal crops produce its best results;
- no cluster expansion or attachment phase;
- video coverage is limited to persistent upstream keyframes;
- the `0.70` detector and clustering thresholds are versioned working defaults,
  not universal accuracy guarantees; dataset-specific false positives, misses,
  and uncertain singletons remain possible;
- anonymous clusters are similarity groups, not verified real-world identities.
