from __future__ import annotations

from pathlib import Path
import os
import json

import pytest

from media_desk.contract import ContractError, load_workspace


def test_loads_valid_workspace_and_all_five_component_outputs(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    video = workspace_builder.add_asset(2, "video")
    fingerprint = "a" * 64
    workspace_builder.add_keyframes(video, fingerprint)
    workspace_builder.add_analysis(image, fingerprint)
    root = workspace_builder.publish()

    snapshot = load_workspace(root)

    assert snapshot.contract_version == 1
    assert len(snapshot.assets) == 2
    loaded_image = next(asset for asset in snapshot.assets if asset.media_type == "image")
    loaded_video = next(asset for asset in snapshot.assets if asset.media_type == "video")
    assert loaded_image.preview is not None
    assert loaded_image.vision and loaded_image.faces and loaded_image.sessions
    assert loaded_image.face_clusters[0].cluster_id == "face-cluster-0000"
    assert loaded_video.preview is not None
    assert loaded_video.preview.kind == "keyframe"


def test_rejects_unsupported_contract(workspace_builder) -> None:
    workspace_builder.add_asset(1)
    root = workspace_builder.publish(version=2)

    with pytest.raises(ContractError, match="Unsupported workspace contract version"):
        load_workspace(root)


def test_missing_preview_preserves_metadata(workspace_builder) -> None:
    workspace_builder.add_asset(1, preview=False)
    root = workspace_builder.publish()

    asset = load_workspace(root).assets[0]

    assert asset.preview is None
    assert asset.capture_time is not None
    assert asset.preview_status == "Preview missing"


def test_offline_original_is_explicit(workspace_builder) -> None:
    workspace_builder.add_asset(1, original=False)
    root = workspace_builder.publish()

    asset = load_workspace(root).assets[0]

    assert not asset.original_online
    assert asset.preview is not None


def test_multiple_keyframe_fingerprints_require_explicit_selection(workspace_builder) -> None:
    video = workspace_builder.add_asset(1, "video")
    first, second = "a" * 64, "b" * 64
    workspace_builder.add_keyframes(video, first, second)
    root = workspace_builder.publish()

    ambiguous = load_workspace(root).assets[0]
    selected = load_workspace(root, second).assets[0]

    assert ambiguous.preview is None
    assert "Multiple keyframe configurations" in ambiguous.preview_status
    assert selected.preview is not None
    assert second in selected.preview.token


def test_catalog_path_traversal_is_rejected(workspace_builder) -> None:
    root = workspace_builder.publish()
    (root / "workspace.json").write_text(
        '{"workspace_contract_version":1,"workspace_id":"workspace-test","asset_catalog":"../secret.json"}',
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="path must stay inside"):
        load_workspace(root)


def test_preview_symlink_escape_is_not_served(workspace_builder, tmp_path: Path) -> None:
    entry = workspace_builder.add_asset(1, preview=False)
    root = workspace_builder.publish()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    preview = root / entry["preview_location"]
    preview.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, preview)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows host")

    asset = load_workspace(root).assets[0]

    assert asset.preview is None


def test_foreign_platform_source_root_stays_browsable_offline(workspace_builder) -> None:
    workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    catalog_path = root / "metadata/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["source_root"] = "/mnt/archive/huhac"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    asset = load_workspace(root).assets[0]

    assert asset.preview is not None
    assert not asset.original_online
