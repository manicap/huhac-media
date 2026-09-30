from pathlib import Path

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
    output = capsys.readouterr().out
    assert "Images ................. 1" in output
    assert "New .................... 1" in output
    assert "DRY RUN" in output

