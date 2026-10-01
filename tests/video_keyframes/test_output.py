import json
import os

import pytest

from video_keyframes.models import KeyframeConfig
from video_keyframes.output import configuration_fingerprint, result_path
from video_keyframes.service import prepare_workspace


def test_configuration_fingerprint_covers_model_and_threshold() -> None:
    default = configuration_fingerprint(KeyframeConfig())

    assert default == configuration_fingerprint(KeyframeConfig())
    assert default != configuration_fingerprint(KeyframeConfig(coverage_similarity=0.9))
    assert default != configuration_fingerprint(KeyframeConfig(clip_model="different"))


def test_result_path_is_asset_scoped_and_deterministic(keyframe_workspace_factory) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    prepared = prepare_workspace(workspace_path, KeyframeConfig())
    asset = prepared.workspace.assets[0]
    target = result_path(
        prepared.workspace, prepared.configuration_fingerprint, asset
    )

    assert target == prepared.plans[0].output_path
    assert target.relative_to(workspace_path).as_posix() == (
        "analysis/video-keyframes/video-keyframes-v1/"
        f"{prepared.configuration_fingerprint}/{asset.sha256[:2]}/{asset.sha256}.json"
    )


def test_failed_or_incomplete_result_is_not_reused(keyframe_workspace_factory) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    prepared = prepare_workspace(workspace_path, KeyframeConfig())
    target = prepared.plans[0].output_path
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"status": "failed"}), encoding="utf-8")

    repeated = prepare_workspace(workspace_path, KeyframeConfig())

    assert repeated.plans[0].action == "process"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks are unavailable")
def test_output_namespace_cannot_escape_workspace_through_symlink(
    keyframe_workspace_factory, tmp_path
) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (workspace_path / "analysis").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink is not permitted")

    with pytest.raises(ValueError, match="escapes the workspace"):
        prepare_workspace(workspace_path, KeyframeConfig())
