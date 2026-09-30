from pathlib import Path

import pytest

from huhac_media.domain.enums import MediaType
from huhac_media.media.hashing import UnstableSourceError
from huhac_media.services.scanner import Scanner


pytestmark = pytest.mark.integration


def test_recursive_scan_excludes_workspace_and_keeps_unicode(tmp_path: Path) -> None:
    input_path = tmp_path / "vstup"
    nested = input_path / "kapela Žluťoučký"
    work = input_path / "_processing"
    nested.mkdir(parents=True)
    work.mkdir()
    (nested / "fotka.jpg").write_bytes(b"\xff\xd8\xffpayload")
    (nested / "notes.txt").write_text("ignore", encoding="utf-8")
    (work / "preview.jpg").write_bytes(b"\xff\xd8\xffgenerated")

    items = Scanner().scan(input_path, work)

    assert [item.relative_path.as_posix() for item in items] == [
        "kapela Žluťoučký/fotka.jpg",
        "kapela Žluťoučký/notes.txt",
    ]
    assert items[0].media_type == MediaType.IMAGE
    assert items[0].sha256 is not None
    assert items[1].media_type == MediaType.UNSUPPORTED


def test_unstable_source_is_reported_and_batch_continues(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8\xffa")
    (tmp_path / "b.jpg").write_bytes(b"\xff\xd8\xffb")

    def hasher(path: Path) -> str:
        if path.name == "a.jpg":
            raise UnstableSourceError("changed")
        return "b" * 64

    items = Scanner(hasher=hasher).scan(tmp_path)
    assert items[0].error_code == "UNSTABLE_SOURCE"
    assert items[1].sha256 == "b" * 64

