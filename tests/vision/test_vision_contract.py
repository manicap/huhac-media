from __future__ import annotations

import json
import sqlite3

from vision.contract import load_workspace

from conftest import IMAGE_SHA, KEYFRAME_FP, VIDEO_SHA, add_keyframe_result


def test_discovers_only_public_image_preview(workspace_factory):
    workspace = workspace_factory()
    loaded = load_workspace(workspace)
    image = next(item for item in loaded.inputs if item.kind == "image_preview")
    assert image.sha256 == IMAGE_SHA
    assert image.path == (workspace / image.provenance["location"]).resolve()
    assert "source" not in image.provenance


def test_discovers_video_keyframes_with_timestamp_and_provenance(workspace_factory):
    workspace = workspace_factory(keyframe_count=2)
    loaded = load_workspace(workspace)
    videos = [item for item in loaded.inputs if item.kind == "video_keyframe"]
    assert [item.input_id for item in videos] == ["keyframe-0000", "keyframe-0001"]
    assert videos[1].provenance["timestamp_s"] == 2.0
    assert videos[1].provenance["video_keyframe_configuration_fingerprint"] == KEYFRAME_FP
    assert videos[1].provenance["asset_id"] == f"sha256:{VIDEO_SHA}"


def test_missing_image_preview_is_explicit_issue(workspace_factory):
    loaded = load_workspace(workspace_factory(preview=False))
    assert not any(item.kind == "image_preview" for item in loaded.inputs)
    assert "MISSING_IMAGE_PREVIEW" in {issue.code for issue in loaded.issues}


def test_missing_video_keyframe_result_is_explicit_issue(workspace_factory):
    loaded = load_workspace(workspace_factory(keyframes=False))
    assert not any(item.kind == "video_keyframe" for item in loaded.inputs)
    assert "MISSING_KEYFRAME_RESULT" in {issue.code for issue in loaded.issues}


def test_invalid_video_keyframe_result_is_not_used(workspace_factory):
    workspace = workspace_factory(keyframes=False)
    add_keyframe_result(workspace, valid=False)
    loaded = load_workspace(workspace)
    assert not any(item.kind == "video_keyframe" for item in loaded.inputs)
    assert "INVALID_KEYFRAME_RESULT" in {issue.code for issue in loaded.issues}


def test_ambiguous_keyframe_results_require_explicit_fingerprint(workspace_factory):
    workspace = workspace_factory()
    second = "d" * 64
    add_keyframe_result(workspace, second)
    ambiguous = load_workspace(workspace)
    assert "AMBIGUOUS_KEYFRAME_RESULT" in {issue.code for issue in ambiguous.issues}
    selected = load_workspace(workspace, second)
    video = next(item for item in selected.inputs if item.kind == "video_keyframe")
    assert video.keyframe_configuration_fingerprint == second


def test_processor_does_not_read_ingest_sqlite(workspace_factory, monkeypatch):
    workspace = workspace_factory()
    state = workspace / "state" / "catalog.sqlite3"
    state.parent.mkdir()
    state.write_bytes(b"not a database")
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite read")))
    loaded = load_workspace(workspace)
    assert len(loaded.inputs) == 2
