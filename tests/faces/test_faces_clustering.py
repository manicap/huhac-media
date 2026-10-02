from __future__ import annotations

import json

import numpy as np
import pytest

from faces.clustering import (
    complete_link_clusters,
    execute_clustering,
    prepare_clustering,
)
from faces.inference import l2_normalize
from faces.models import ClusterConfig, FaceDetection, FacesConfig
from faces.output import configuration_fingerprint
from faces.service import execute_prepared, prepare_workspace
from faces.inference import clip_bbox


class Detector:
    def detect(self, image):
        bbox = clip_bbox((1, 1, 10, 10), image.shape[1], image.shape[0])
        assert bbox is not None
        return (FaceDetection(bbox, 0.9, ((2, 2), (7, 2), (5, 5), (3, 8), (7, 8))),)


class Embedder:
    def __init__(self):
        self.calls = 0

    def embed(self, crop):
        self.calls += 1
        return l2_normalize(np.ones(256, dtype=np.float32))


def test_complete_link_does_not_join_through_a_similarity_chain():
    # A-B and B-C are above threshold, but A-C is below it.
    a = [1.0, 0.0]
    b = [1.0, 1.0]
    c = [0.0, 1.0]
    first = complete_link_clusters([a, b, c], threshold=0.70)
    second = complete_link_clusters([a, b, c], threshold=0.70)
    assert first == second == ((0, 1), (2,))


def test_cluster_threshold_changes_fingerprint():
    from faces.output import canonical_sha256

    assert canonical_sha256(ClusterConfig().as_dict()) != canonical_sha256(
        ClusterConfig(similarity_threshold=0.71).as_dict()
    )


@pytest.mark.integration
def test_clustering_reruns_and_reuses_without_detection_embedding(workspace_factory):
    workspace = workspace_factory()
    faces_config = FacesConfig()
    analysis = prepare_workspace(workspace, faces_config)
    embedder = Embedder()
    execute_prepared(analysis, dry_run=False, detector=Detector(), embedder=embedder)
    calls_after_analysis = embedder.calls
    faces_fingerprint = configuration_fingerprint(faces_config)

    first = prepare_clustering(workspace, faces_fingerprint, ClusterConfig())
    first_result = execute_clustering(first, dry_run=False)
    assert first_result.cluster_count == 1
    payload = json.loads(first.output_path.read_text(encoding="utf-8"))
    cluster = payload["result"]["clusters"][0]
    assert cluster["status"] == "core"
    assert cluster["member_count"] == 2
    assert all(member["faces_result_location"].startswith("analysis/faces/") for member in cluster["members"])
    assert embedder.calls == calls_after_analysis

    second = prepare_clustering(workspace, faces_fingerprint, ClusterConfig())
    assert second.action == "reuse"
    reused = execute_clustering(second, dry_run=False)
    assert reused.reused is True
    assert embedder.calls == calls_after_analysis


def test_singletons_are_anonymous_and_uncertain(workspace_factory):
    workspace = workspace_factory(keyframes=False)
    faces_config = FacesConfig()
    analysis = prepare_workspace(workspace, faces_config)
    execute_prepared(analysis, dry_run=False, detector=Detector(), embedder=Embedder())
    prepared = prepare_clustering(
        workspace, configuration_fingerprint(faces_config), ClusterConfig()
    )
    execute_clustering(prepared, dry_run=False)
    payload = json.loads(prepared.output_path.read_text(encoding="utf-8"))
    cluster = payload["result"]["clusters"][0]
    assert cluster["cluster_id"] == "face-cluster-0000"
    assert cluster["status"] == "uncertain"
