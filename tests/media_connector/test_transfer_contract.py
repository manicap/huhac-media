from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_connector.compatibility import classify_content
from media_connector.errors import ConnectorError
from media_connector.transfer_contract import read_selection


def test_selection_contract_is_strict_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"contract": "wrong"}), encoding="utf-8")
    with pytest.raises(ConnectorError) as caught:
        read_selection(path)
    assert caught.value.code == "INVALID_SELECTION"


@pytest.mark.parametrize(
    ("first_name", "second_name", "payload", "suffix"),
    [
        ("one.jpeg", "two.jpg", b"\xff\xd8\xff" + b"x" * 1024, "jpg"),
        ("one.any", "two.png", b"\x89PNG\r\n\x1a\n" + b"x" * 1024, "png"),
        ("one.mp4", "two.mov", b"\x00\x00\x00\x18ftypisom" + b"x" * 1024, "mp4"),
    ],
)
def test_compatibility_suffix_depends_on_content_not_name(
    tmp_path: Path, first_name: str, second_name: str, payload: bytes, suffix: str
) -> None:
    first = tmp_path / first_name
    second = tmp_path / second_name
    first.write_bytes(payload)
    second.write_bytes(payload)
    assert classify_content(first).canonical_suffix == suffix
    assert classify_content(second).canonical_suffix == suffix


def test_ambiguous_extension_only_format_fails_closed(tmp_path: Path) -> None:
    raw = tmp_path / "camera.nef"
    raw.write_bytes(b"not-a-content-signature")
    with pytest.raises(ConnectorError) as caught:
        classify_content(raw)
    assert caught.value.code == "FORMAT_NOT_INGEST_COMPATIBLE"


def test_transport_stream_signature_is_deterministic(tmp_path: Path) -> None:
    payload = bytearray(600)
    for offset in (0, 188, 376):
        payload[offset] = 0x47
    first = tmp_path / "clip.bin"
    second = tmp_path / "clip.m2ts"
    first.write_bytes(payload)
    second.write_bytes(payload)
    assert classify_content(first).canonical_suffix == "mts"
    assert classify_content(second).canonical_suffix == "mts"

