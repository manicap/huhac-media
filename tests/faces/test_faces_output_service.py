from __future__ import annotations

import json

import numpy as np
import pytest

from faces.inference import clip_bbox, l2_normalize
from faces.models import FaceDetection, FacesConfig
from faces.output import configuration_fingerprint
from faces.service import execute_prepared, prepare_workspace


class FakeDetector:
    def __init__(self):
        self.calls = 0

    def detect(self, image):
        self.calls += 1
        bbox = clip_bbox((-2.0, 2.0, 13.0, 15.0), image.shape[1], image.shape[0])
        assert bbox is not None
        return (
            FaceDetection(
                bbox,
                0.9123456789,
                ((3.1, 4.2), (8.3, 4.4), (6.0, 7.0), (4.0, 10.0), (8.0, 10.0)),
            ),
        )


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, crop):
        self.calls += 1
        return l2_normalize(np.arange(1, 257, dtype=np.float32))


def test_threshold_is_versioned_in_configuration_fingerprint():
    default = configuration_fingerprint(FacesConfig())
    assert default == configuration_fingerprint(FacesConfig())
    assert default != configuration_fingerprint(FacesConfig(score_threshold=0.71))
    assert default != configuration_fingerprint(FacesConfig(nms_threshold=0.31))
    assert default != configuration_fingerprint(
        FacesConfig(embedding_model_precision="FP16")
    )


def test_deterministic_per_face_result_preserves_provenance(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), FacesConfig())
    result = execute_prepared(
        prepared, dry_run=False, detector=FakeDetector(), embedder=FakeEmbedder()
    )
    assert (result.processed, result.failed, result.detected_faces) == (1, 0, 1)
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    face = payload["result"]["faces"][0]
    assert payload["input"] == prepared.plans[0].visual_input.provenance
    assert face["provenance"] == prepared.plans[0].visual_input.provenance
    assert face["face_id"] == "face-0000"
    assert face["bbox"] == {"x": 0, "y": 2, "width": 11, "height": 15}
    assert face["confidence"] == 0.91234568
    assert [item["name"] for item in face["landmarks"]] == [
        "right_eye",
        "left_eye",
        "nose_tip",
        "right_mouth",
        "left_mouth",
    ]
    assert len(face["embedding"]) == 256

    first_result = payload["result"]
    forced = prepare_workspace(prepared.workspace.workspace, FacesConfig(), force=True)
    execute_prepared(
        forced, dry_run=False, detector=FakeDetector(), embedder=FakeEmbedder()
    )
    repeated = json.loads(forced.plans[0].output_path.read_text(encoding="utf-8"))
    assert repeated["result"] == first_result


@pytest.mark.integration
def test_second_run_reuses_without_detection_or_embedding(workspace_factory):
    workspace = workspace_factory()
    first = prepare_workspace(workspace, FacesConfig())
    detector = FakeDetector()
    embedder = FakeEmbedder()
    first_result = execute_prepared(
        first, dry_run=False, detector=detector, embedder=embedder
    )
    assert first_result.processed == 2
    second = prepare_workspace(workspace, FacesConfig())
    assert all(plan.action == "reuse" for plan in second.plans)
    unused_detector = FakeDetector()
    unused_embedder = FakeEmbedder()
    second_result = execute_prepared(
        second,
        dry_run=False,
        detector=unused_detector,
        embedder=unused_embedder,
    )
    assert second_result.reused == 2
    assert unused_detector.calls == unused_embedder.calls == 0


def test_dry_run_does_not_decode_infer_or_write(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), FacesConfig())
    detector = FakeDetector()
    embedder = FakeEmbedder()
    result = execute_prepared(
        prepared, dry_run=True, detector=detector, embedder=embedder
    )
    assert result.processed == 0
    assert detector.calls == embedder.calls == 0
    assert all(not plan.output_path.exists() for plan in prepared.plans)
