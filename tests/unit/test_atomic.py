from pathlib import Path

import pytest

from huhac_media.storage.atomic import atomic_target, write_json_atomic


def test_failed_atomic_write_preserves_previous_file(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError):
        with atomic_target(target) as temporary:
            temporary.write_text("partial", encoding="utf-8")
            raise RuntimeError("crash")
    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_is_written_as_utf8(tmp_path: Path) -> None:
    target = tmp_path / "metadata.json"
    write_json_atomic(target, {"name": "Huháč"})
    assert "Huháč" in target.read_text(encoding="utf-8")

