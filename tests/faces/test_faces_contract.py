from __future__ import annotations

import sqlite3

from faces.contract import load_workspace

from conftest import IMAGE_SHA, KEYFRAME_FP, VIDEO_SHA


def test_loader_uses_public_preview_and_keyframe_contract(workspace_factory):
    workspace = workspace_factory()
    loaded = load_workspace(workspace)
    assert [item.kind for item in loaded.inputs] == ["image_preview", "video_keyframe"]
    image, video = loaded.inputs
    assert image.sha256 == IMAGE_SHA
    assert image.provenance["location"].endswith(f"{IMAGE_SHA}.jpg")
    assert video.sha256 == VIDEO_SHA
    assert video.provenance["timestamp_s"] == 1.25
    assert video.keyframe_configuration_fingerprint == KEYFRAME_FP


def test_loader_never_reads_ingest_sqlite(workspace_factory, monkeypatch):
    workspace = workspace_factory()
    state = workspace / "state" / "catalog.sqlite3"
    state.parent.mkdir()
    state.write_bytes(b"not sqlite")
    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite read")),
    )
    assert len(load_workspace(workspace).inputs) == 2


def test_missing_public_preview_is_an_issue(workspace_factory):
    loaded = load_workspace(workspace_factory(preview=False, keyframes=False))
    assert {issue.code for issue in loaded.issues} == {
        "MISSING_IMAGE_PREVIEW",
        "MISSING_KEYFRAME_RESULT",
    }
