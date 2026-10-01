import json
from pathlib import Path

import pytest

from session_grouper.cli import main


pytestmark = pytest.mark.integration


def capture(value: str, source: str = "EXIF:DateTimeOriginal") -> dict:
    return {
        "datetime": value,
        "source": source,
        "timezone_offset": None,
        "filesystem_fallback": source == "filesystem:mtime",
    }


def test_cli_dry_run_write_repeat_and_configuration_versioning(
    workspace_factory, capsys
) -> None:
    workspace = workspace_factory(
        [
            {"name": "photo", "capture": capture("2026-09-26T23:50:00")},
            {
                "name": "video",
                "media_type": "video",
                "capture": capture("2026-09-27T00:10:00", "QuickTime:CreateDate"),
            },
            {"name": "unknown", "capture": None},
        ]
    )

    assert main(["analyze", "--workspace", str(workspace), "--dry-run"]) == 0
    assert not (workspace / "analysis").exists()
    assert "DRY RUN" in capsys.readouterr().out

    assert main(["analyze", "--workspace", str(workspace), "--json"]) == 0
    first_report = json.loads(capsys.readouterr().out)
    first_output = Path(first_report["output"])
    first_bytes = first_output.read_bytes()
    first_mtime = first_output.stat().st_mtime_ns
    payload = json.loads(first_bytes)

    assert payload["result_schema_version"] == 1
    assert payload["processor"] == {
        "name": "session-grouper",
        "version": "session-grouper-v1",
    }
    assert payload["model"] is None
    assert payload["result"]["summary"] == {
        "session_count": 1,
        "assigned_asset_count": 2,
        "unassigned_asset_count": 1,
    }
    assert payload["result"]["sessions"][0]["media_types"] == {
        "image": 1,
        "video": 1,
    }

    assert main(["analyze", "--workspace", str(workspace), "--json"]) == 0
    second_report = json.loads(capsys.readouterr().out)
    assert second_report["reused"] is True
    assert first_output.read_bytes() == first_bytes
    assert first_output.stat().st_mtime_ns == first_mtime

    assert (
        main(
            [
                "analyze",
                "--workspace",
                str(workspace),
                "--max-gap-hours",
                "7",
                "--json",
            ]
        )
        == 0
    )
    changed_report = json.loads(capsys.readouterr().out)
    assert changed_report["configuration_fingerprint"] != first_report[
        "configuration_fingerprint"
    ]
    assert changed_report["output"] != first_report["output"]


def test_cli_returns_contract_error_for_incompatible_workspace(
    workspace_factory, capsys
) -> None:
    workspace = workspace_factory([], contract_version=2)

    assert main(["analyze", "--workspace", str(workspace)]) == 2
    assert "Unsupported workspace contract version" in capsys.readouterr().out
