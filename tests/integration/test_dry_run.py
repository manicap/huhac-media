from pathlib import Path
import json

import pytest

from huhac_media.cli import main
from huhac_media.exit_codes import ExitCode


pytestmark = pytest.mark.integration


def test_dry_run_does_not_create_workspace(tmp_path: Path, capsys) -> None:
    media = tmp_path / "česká fotka.jpg"
    media.write_bytes(b"\xff\xd8\xffpayload")
    work = tmp_path / "_processing"

    result = main(["ingest", "--input", str(tmp_path), "--dry-run"])

    assert result == ExitCode.SUCCESS
    assert not work.exists()
    assert not (work / "metadata" / "catalog.json").exists()
    output = capsys.readouterr().out
    assert "Images ................. 1" in output
    assert "New .................... 1" in output
    assert "DRY RUN" in output


def test_dry_run_does_not_upgrade_legacy_workspace(tmp_path: Path, capsys) -> None:
    media = tmp_path / "photo.jpg"
    media.write_bytes(b"\xff\xd8\xffpayload")
    work = tmp_path / "_processing"
    work.mkdir()
    manifest = work / "workspace.json"
    legacy_payload = {"schema_version": 1, "workspace_id": "legacy-id"}
    manifest.write_text(json.dumps(legacy_payload), encoding="utf-8")
    before = manifest.read_bytes()

    result = main(["ingest", "--input", str(tmp_path), "--dry-run"])

    assert result == ExitCode.SUCCESS
    assert manifest.read_bytes() == before
    assert not (work / "metadata" / "catalog.json").exists()
    assert "DRY RUN" in capsys.readouterr().out
