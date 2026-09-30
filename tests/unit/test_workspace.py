from pathlib import Path

import pytest

from huhac_media.domain.errors import FatalError
from huhac_media.storage.workspace import initialize_workspace, validate_paths


def test_work_must_not_contain_input(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    with pytest.raises(ValueError, match="contain INPUT"):
        validate_paths(input_path, tmp_path)


def test_nonempty_unknown_workspace_is_rejected(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "unrelated.txt").write_text("data", encoding="utf-8")
    with pytest.raises(FatalError, match="unrecognized"):
        initialize_workspace(work)
