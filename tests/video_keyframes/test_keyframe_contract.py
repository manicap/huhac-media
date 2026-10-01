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
