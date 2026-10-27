import json
from pathlib import Path

import pytest

from video_keyframes.contract import ContractError, load_workspace


def test_reads_public_catalog_and_selects_deterministic_existing_active_source(
    keyframe_workspace_factory,
) -> None:
    sources = [
        {"source_version_id": "z", "relative_path": "z/video.mp4", "status": "active"},
        {"source_version_id": "a", "relative_path": "a/video.mp4", "status": "active"},
        {"source_version_id": "old", "relative_path": "old.mp4", "status": "absent"},
    ]
    workspace, _ = keyframe_workspace_factory(
        [
            {"sources": sources},
            {"media_type": "image"},
            {"availability": "unavailable"},
        ]
    )

    loaded = load_workspace(workspace)

    assert len(loaded.assets) == 1
    assert loaded.assets[0].source is not None
    assert loaded.assets[0].source.relative_path == "a/video.mp4"
    assert (workspace / "state" / "catalog.sqlite3").read_bytes() == b"must not be read"


def test_missing_active_source_is_retained_as_asset_issue(
    keyframe_workspace_factory,
) -> None:
    workspace, _ = keyframe_workspace_factory([{"create_source": False}])

    loaded = load_workspace(workspace)

    assert loaded.assets[0].source is None
    assert loaded.assets[0].source_issue == "no_accessible_active_source"


def test_explicit_asset_selection_is_deduplicated_and_deterministic(
    keyframe_workspace_factory,
) -> None:
    first_sha = "f" * 64
    second_sha = "0" * 64
    workspace, _ = keyframe_workspace_factory(
        [{"sha256": first_sha}, {"sha256": second_sha}, {}]
    )

    loaded = load_workspace(
        workspace,
        (
            f"sha256:{first_sha}",
            f"sha256:{second_sha}",
            f"sha256:{first_sha}",
        ),
    )

    assert [asset.asset_id for asset in loaded.assets] == [
        f"sha256:{second_sha}",
        f"sha256:{first_sha}",
    ]


@pytest.mark.parametrize(
    ("selected", "message"),
    [
        ("SHA256:" + "a" * 64, "Invalid selected asset ID"),
        ("sha256:" + "a" * 63, "Invalid selected asset ID"),
        ("sha256:" + "g" * 64, "Invalid selected asset ID"),
        ("sha256:" + "f" * 64, "does not exist"),
    ],
)
def test_rejects_invalid_or_missing_selected_asset(
    keyframe_workspace_factory, selected: str, message: str
) -> None:
    workspace, _ = keyframe_workspace_factory([{}])

    with pytest.raises(ContractError, match=message):
        load_workspace(workspace, (selected,))


def test_rejects_selected_non_video_asset(keyframe_workspace_factory) -> None:
    workspace, _ = keyframe_workspace_factory([{"media_type": "image"}])
    catalog = json.loads(
        (workspace / "metadata" / "catalog.json").read_text(encoding="utf-8")
    )
    asset_id = catalog["assets"][0]["asset_id"]

    with pytest.raises(ContractError, match="not a video"):
        load_workspace(workspace, (asset_id,))


def test_rejects_selected_unavailable_video(keyframe_workspace_factory) -> None:
    workspace, _ = keyframe_workspace_factory([{"availability": "unavailable"}])
    catalog = json.loads(
        (workspace / "metadata" / "catalog.json").read_text(encoding="utf-8")
    )
    asset_id = catalog["assets"][0]["asset_id"]

    with pytest.raises(ContractError, match="not available"):
        load_workspace(workspace, (asset_id,))


def test_rejects_source_path_escape(keyframe_workspace_factory) -> None:
    workspace, _ = keyframe_workspace_factory(
        [
            {
                "create_source": False,
                "sources": [
                    {
                        "source_version_id": "escape",
                        "relative_path": "../outside.mp4",
                        "status": "active",
                    }
                ],
            }
        ]
    )

    with pytest.raises(ContractError, match="stay inside"):
        load_workspace(workspace)


def test_rejects_incompatible_contract(keyframe_workspace_factory) -> None:
    workspace, _ = keyframe_workspace_factory([], contract_version=2)

    with pytest.raises(ContractError, match="Unsupported workspace contract"):
        load_workspace(workspace)


def test_package_has_no_ingest_or_sqlite_dependency() -> None:
    package = Path(__file__).parents[2] / "src" / "video_keyframes"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    assert "import huhac_media" not in source
    assert "from huhac_media" not in source
    assert "import sqlite3" not in source
    assert "state/catalog.sqlite3" not in source
