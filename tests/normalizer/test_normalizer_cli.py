from __future__ import annotations

import json

from normalizer.cli import main


def _files(root):
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_plan_and_status_are_read_only(workspace_factory, capsys):
    root = workspace_factory()
    before = _files(root)
    assert main(["plan", "--workspace", str(root), "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["read_only"] is True
    assert plan["asset_count"] == 2
    assert before == _files(root)
    assert main(["status", "--workspace", str(root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["read_only"] is True
    assert status["snapshot_count"] == 0
    assert before == _files(root)


def test_analyze_cli_writes_then_reuses_and_status_validates(workspace_factory, capsys):
    root = workspace_factory()
    assert main(["analyze", "--workspace", str(root), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["reused"] is False
    assert first["summary"]["asset_count"] == 2
    assert main(["analyze", "--workspace", str(root), "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["reused"] is True
    assert main(["status", "--workspace", str(root), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["valid_snapshot_count"] == 1
    assert status["invalid_snapshot_count"] == 0
    assert status["size_bytes"] > 0


def test_cli_exit_codes_for_contract_partial_and_snapshot_conflict(workspace_factory, tmp_path, capsys):
    assert main(["plan", "--workspace", str(tmp_path / "missing")]) == 2
    assert "does not exist" in capsys.readouterr().out

    partial_root = workspace_factory([{"name": "missing", "metadata": None}])
    assert main(["analyze", "--workspace", str(partial_root), "--json"]) == 1
    partial = json.loads(capsys.readouterr().out)
    assert partial["summary"]["input_issue_count"] == 1

    conflict_root = workspace_factory()
    assert main(["analyze", "--workspace", str(conflict_root), "--json"]) == 0
    written = json.loads(capsys.readouterr().out)
    manifest = __import__("pathlib").Path(written["output"]) / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    assert main(["analyze", "--workspace", str(conflict_root)]) == 3
    assert "conflicts" in capsys.readouterr().out
