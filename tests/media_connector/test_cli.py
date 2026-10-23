from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

from media_connector.cli import main

TEST_WORKSPACE_ID = "12345678-1234-5678-1234-567812345678"


def _json_output(capsys) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def test_cli_success_contract(workspace: Path, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "photo.jpg").write_bytes(b"not-read")

    result = main(
        [
            "local-discovery",
            "--workspace",
            str(workspace),
            "--source-root",
            str(source),
            "--page-size",
            "1",
        ]
    )

    assert result == 0
    payload = _json_output(capsys)
    assert payload["contract"] == "huhac.media-connector.local-discovery"
    assert payload["contract_version"] == 1
    assert payload["status"] == "success"
    assert payload["library"] == {"workspace_id": TEST_WORKSPACE_ID}
    assert payload["capabilities"] == {
        "consistent_snapshot": False,
        "content_checksum": False,
        "content_read": False,
        "pagination": True,
    }
    assert payload["page"]["items"][0]["logical_path"] == "photo.jpg"
    assert payload["error"] is None


def test_cli_error_is_single_json_object(workspace: Path, tmp_path: Path, capsys) -> None:
    result = main(
        [
            "local-discovery",
            "--workspace",
            str(workspace),
            "--source-root",
            str(tmp_path / "missing"),
        ]
    )
    assert result == 3
    payload = _json_output(capsys)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SOURCE_NOT_FOUND"
    assert payload["error"]["retryable"] is True
    assert payload["page"] is None


def test_cli_argument_error_is_json(capsys) -> None:
    assert main(["local-discovery"]) == 2
    payload = _json_output(capsys)
    assert payload["error"]["code"] == "INVALID_ARGUMENT"


def test_cli_rejects_source_workspace_overlap(workspace: Path, capsys) -> None:
    assert (
        main(
            [
                "local-discovery",
                "--workspace",
                str(workspace),
                "--source-root",
                str(workspace),
            ]
        )
        == 2
    )
    payload = _json_output(capsys)
    assert payload["error"]["code"] == "SOURCE_WORKSPACE_OVERLAP"


def test_connector_has_no_media_desk_or_ingest_imports() -> None:
    package = Path(__file__).parents[2] / "src" / "media_connector"
    imported_roots: set[str] = set()
    for source in package.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
    assert "media_desk" not in imported_roots
    assert "huhac_media" not in imported_roots


def test_pyproject_registers_connector_entry_point() -> None:
    project_root = Path(__file__).parents[2]
    payload = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["scripts"]["media-connector"] == "media_connector.cli:main"
