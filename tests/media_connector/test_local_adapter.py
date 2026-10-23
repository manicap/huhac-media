from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

import pytest

from media_connector.adapters.local import (
    LocalFilesystemAdapter,
    _is_link_like,
    _validate_component,
)
from media_connector.errors import ConnectorError


def _touch(path: Path, payload: bytes = b"payload") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_empty_source_returns_empty_page(tmp_path: Path) -> None:
    adapter = LocalFilesystemAdapter(tmp_path)
    page = adapter.list_page(page_size=10, cursor=None)
    assert page.items == ()
    assert page.next_cursor is None
    assert page.warnings == ()


def test_nested_unicode_files_are_deterministic_and_metadata_only(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _touch(source / "žlutý" / "b.jpg", b"b")
    _touch(source / "a.mov", b"video")
    before = {
        path.relative_to(source).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }

    adapter = LocalFilesystemAdapter(source)
    first = adapter.list_page(page_size=10, cursor=None)
    second = adapter.list_page(page_size=10, cursor=None)

    assert [item.logical_path for item in first.items] == ["a.mov", "žlutý/b.jpg"]
    assert [item.to_dict() for item in first.items] == [
        item.to_dict() for item in second.items
    ]
    assert all(item.to_dict()["source_checksum"] is None for item in first.items)
    after = {
        path.relative_to(source).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_pagination_is_deterministic_and_cursor_is_source_bound(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    for name in ("c.jpg", "a.jpg", "b.jpg"):
        _touch(first_root / name)

    adapter = LocalFilesystemAdapter(first_root)
    page_one = adapter.list_page(page_size=2, cursor=None)
    page_two = adapter.list_page(page_size=2, cursor=page_one.next_cursor)
    assert [item.logical_path for item in page_one.items] == ["a.jpg", "b.jpg"]
    assert [item.logical_path for item in page_two.items] == ["c.jpg"]
    assert page_two.next_cursor is None

    with pytest.raises(ConnectorError) as caught:
        LocalFilesystemAdapter(second_root).list_page(
            page_size=2, cursor=page_one.next_cursor
        )
    assert caught.value.code == "CURSOR_SOURCE_MISMATCH"


@pytest.mark.parametrize("cursor", ["not base64!", "", "e30"])
def test_invalid_cursor_is_rejected(tmp_path: Path, cursor: str) -> None:
    adapter = LocalFilesystemAdapter(tmp_path)
    with pytest.raises(ConnectorError) as caught:
        adapter.list_page(page_size=1, cursor=cursor)
    assert caught.value.code == "INVALID_CURSOR"


def test_symlink_entries_are_not_followed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    _touch(outside / "secret.jpg")
    try:
        (source / "escape").symlink_to(outside, target_is_directory=True)
        (source / "file-link.jpg").symlink_to(outside / "secret.jpg")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    page = LocalFilesystemAdapter(source).list_page(page_size=10, cursor=None)
    assert page.items == ()
    assert [(warning.code, warning.logical_path) for warning in page.warnings] == [
        ("LINK_SKIPPED", "escape"),
        ("LINK_SKIPPED", "file-link.jpg"),
    ]


def test_symlink_source_root_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    with pytest.raises(ConnectorError) as caught:
        LocalFilesystemAdapter(link)
    assert caught.value.code == "UNSAFE_SOURCE_ROOT"


@pytest.mark.skipif(os.name == "nt", reason="colon is not a regular Windows filename")
def test_portability_unsafe_path_is_rejected(tmp_path: Path) -> None:
    _touch(tmp_path / "unsafe:name.jpg")
    with pytest.raises(ConnectorError) as caught:
        LocalFilesystemAdapter(tmp_path).list_page(page_size=10, cursor=None)
    assert caught.value.code == "UNSAFE_PATH"


@pytest.mark.skipif(os.name == "nt", reason="case-colliding files are not portable on Windows")
def test_casefold_collision_is_rejected(tmp_path: Path) -> None:
    _touch(tmp_path / "A.jpg")
    _touch(tmp_path / "a.jpg")
    with pytest.raises(ConnectorError) as caught:
        LocalFilesystemAdapter(tmp_path).list_page(page_size=10, cursor=None)
    assert caught.value.code == "PATH_COLLISION"


def test_reparse_attribute_is_treated_as_link() -> None:
    class FakeStat:
        st_mode = stat.S_IFDIR
        st_file_attributes = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    assert _is_link_like(FakeStat()) is True  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "component",
    ["..", "CON", "nul.txt", "bad:name", "trail.", "trail ", "bad\\name"],
)
def test_portability_unsafe_components_are_rejected(component: str) -> None:
    with pytest.raises(ConnectorError) as caught:
        _validate_component(component)
    assert caught.value.code == "UNSAFE_PATH"


def test_missing_and_non_directory_roots_have_stable_errors(tmp_path: Path) -> None:
    with pytest.raises(ConnectorError) as missing:
        LocalFilesystemAdapter(tmp_path / "missing")
    assert missing.value.code == "SOURCE_NOT_FOUND"
    file_path = tmp_path / "file"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ConnectorError) as not_directory:
        LocalFilesystemAdapter(file_path)
    assert not_directory.value.code == "SOURCE_NOT_DIRECTORY"


def test_permission_and_offline_errors_are_mapped(monkeypatch, tmp_path: Path) -> None:
    original_lstat = os.lstat

    def denied(path):
        if Path(path) == tmp_path / "denied":
            raise PermissionError(errno.EACCES, "denied")
        return original_lstat(path)

    monkeypatch.setattr(os, "lstat", denied)
    with pytest.raises(ConnectorError) as permission:
        LocalFilesystemAdapter(tmp_path / "denied")
    assert permission.value.code == "SOURCE_PERMISSION_DENIED"

    def offline(path):
        raise OSError(errno.ENODEV, "offline")

    monkeypatch.setattr(os, "lstat", offline)
    with pytest.raises(ConnectorError) as unavailable:
        LocalFilesystemAdapter(tmp_path / "offline")
    assert unavailable.value.code == "SOURCE_OFFLINE"


def test_permission_error_during_enumeration_is_structured(monkeypatch, tmp_path: Path) -> None:
    adapter = LocalFilesystemAdapter(tmp_path)

    def denied(path):
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "scandir", denied)
    with pytest.raises(ConnectorError) as caught:
        adapter.list_page(page_size=10, cursor=None)
    assert caught.value.code == "SOURCE_PERMISSION_DENIED"


def test_source_content_is_never_opened(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    media = source / "photo.jpg"
    _touch(media)
    original_open = Path.open

    def guarded_open(path: Path, *args, **kwargs):
        if path == media:
            raise AssertionError("source content must not be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    page = LocalFilesystemAdapter(source).list_page(page_size=10, cursor=None)
    assert [item.logical_path for item in page.items] == ["photo.jpg"]
