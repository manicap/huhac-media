from __future__ import annotations

from pathlib import Path

import pytest

from huhac_media.storage.filesystem_policy import canonical_target, roots_overlap, validate_path_text


def test_canonical_target_preserves_missing_suffix(tmp_path: Path) -> None:
    assert canonical_target(tmp_path / "new" / "leaf") == tmp_path.resolve() / "new" / "leaf"


def test_overlap_is_symmetric(tmp_path: Path) -> None:
    parent = tmp_path / "archive"
    child = parent / "workspace"
    assert roots_overlap(parent, child)
    assert roots_overlap(child, parent)
    assert not roots_overlap(parent, tmp_path / "other")


@pytest.mark.parametrize("raw", ["relative", "../escape"])
def test_path_must_be_absolute(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_path_text(Path(raw))


def test_path_rejects_control_character(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_path_text(tmp_path / "bad\npath")
