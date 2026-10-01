import json
from pathlib import Path

import pytest

from session_grouper.contract import ContractError, load_workspace
from session_grouper.models import GroupingConfig, TimestampConfidence


def capture(value: str, source: str, fallback: bool = False) -> dict:
    return {
        "datetime": value,
        "source": source,
        "timezone_offset": None,
        "filesystem_fallback": fallback,
    }


def test_reads_only_public_contract_and_preserves_timestamp_provenance(
    workspace_factory,
) -> None:
    workspace = workspace_factory(
        [
            {
                "name": "photo",
                "capture": capture("2026-09-26T20:00:00", "EXIF:DateTimeOriginal"),
            },
            {
                "name": "video",
                "media_type": "video",
                "capture": capture("2026-09-26T20:01:00", "QuickTime:CreateDate"),
            },
            {
                "name": "fallback",
                "capture": capture(
                    "2026-09-26T20:02:00+00:00", "filesystem:mtime", True
                ),
            },
        ]
    )

    loaded = load_workspace(workspace, GroupingConfig())

    assert len(loaded.observations) == 3
    confidences = {
        item.timestamp.source: item.timestamp.confidence
        for item in loaded.observations
        if item.timestamp
    }
    assert confidences == {
        "EXIF:DateTimeOriginal": TimestampConfidence.STRONG,
        "QuickTime:CreateDate": TimestampConfidence.STRONG,
        "filesystem:mtime": TimestampConfidence.LOW,
    }
    assert (workspace / "state" / "catalog.sqlite3").read_bytes() == b"must not be read"


def test_rejects_incompatible_workspace_contract(workspace_factory) -> None:
    workspace = workspace_factory([], contract_version=2)

    with pytest.raises(ContractError, match="Unsupported workspace contract version"):
        load_workspace(workspace, GroupingConfig())


def test_rejects_catalog_path_escape(workspace_factory) -> None:
    workspace = workspace_factory([])
    (workspace / "workspace.json").write_text(
        '{"schema_version":1,"workspace_contract_version":1,'
        '"workspace_id":"test-workspace","asset_catalog":"../catalog.json"}',
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="stay inside"):
        load_workspace(workspace, GroupingConfig())


def test_rejects_asset_metadata_path_escape(workspace_factory) -> None:
    workspace = workspace_factory(
        [
            {
                "name": "photo",
                "capture": capture("2026-09-26T20:00:00", "EXIF:DateTimeOriginal"),
            }
        ]
    )
    catalog_path = workspace / "metadata" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["assets"][0]["metadata_location"] = "../../outside.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ContractError, match="stay inside"):
        load_workspace(workspace, GroupingConfig())


def test_package_has_no_ingest_or_sqlite_dependency() -> None:
    package = Path(__file__).parents[2] / "src" / "session_grouper"
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    assert "import huhac_media" not in source
    assert "from huhac_media" not in source
    assert "import sqlite3" not in source
    assert "state/catalog.sqlite3" not in source
