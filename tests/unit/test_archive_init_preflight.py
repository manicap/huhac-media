from __future__ import annotations

import json
from pathlib import Path

import pytest

from huhac_media.cli import main
from huhac_media.services.archive_init import preflight_archive_init


def local(_: Path) -> str:
    return "local"


def test_preflight_missing_targets_is_read_only(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    workspace = tmp_path / "workspace"
    before = sorted(tmp_path.iterdir())
    result = preflight_archive_init(storage, workspace, classifier=local)
    assert result.state == "preflight_ok"
    assert not any(result.created.values())
    assert sorted(tmp_path.iterdir()) == before


@pytest.mark.parametrize("kind", ["network", "unknown"])
def test_preflight_fails_closed_for_workspace_filesystem(tmp_path: Path, kind: str) -> None:
    result = preflight_archive_init(
        tmp_path / "storage", tmp_path / "workspace", classifier=lambda _: kind
    )
    assert result.state == "rejected"
    assert result.error and result.error.code == "UNSUPPORTED_WORKSPACE_FILESYSTEM"


def test_preflight_rejects_both_overlap_directions(tmp_path: Path) -> None:
    for storage, workspace in (
        (tmp_path / "root", tmp_path / "root" / "workspace"),
        (tmp_path / "root" / "storage", tmp_path / "root"),
    ):
        result = preflight_archive_init(storage, workspace, classifier=local)
        assert result.error and result.error.code == "OVERLAPPING_ROOTS"


def test_preflight_rejects_nonempty_targets(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "foreign.txt").write_text("keep", encoding="utf-8")
    result = preflight_archive_init(storage, tmp_path / "workspace", classifier=local)
    assert result.error and result.error.code == "STORAGE_NOT_EMPTY"
    assert (storage / "foreign.txt").read_text(encoding="utf-8") == "keep"


def test_preflight_rejects_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    result = preflight_archive_init(link / "storage", tmp_path / "workspace", classifier=local)
    assert result.error and result.error.code == "PATH_IDENTITY_CHANGED"


def test_cli_emits_one_machine_readable_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([
        "init", "--storage", str(tmp_path / "storage"), "--workspace",
        str(tmp_path / "workspace"), "--preflight", "--json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert code == 0
    assert payload["schema_version"] == 1
    assert payload["state"] == "preflight_ok"
    assert payload["error"] is None
    assert output.err == ""


def test_cli_argument_error_is_also_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["init", "--storage", "missing-workspace", "--json"])
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert code == 2
    assert payload["state"] == "rejected"
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert output.err == ""
