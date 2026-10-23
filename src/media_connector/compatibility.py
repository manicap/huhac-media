from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from media_connector.errors import ConnectorError


PROFILE_ID = "ingest-compatibility-v1"
CANONICAL_SUFFIXES = frozenset({"jpg", "png", "tif", "webp", "avi", "mkv", "heic", "mov", "mp4", "mts", "m2ts"})


@dataclass(frozen=True, slots=True)
class CompatibleFormat:
    name: str
    canonical_suffix: str


def _iso_brand(header: bytes) -> CompatibleFormat | None:
    if len(header) < 12 or header[4:8] != b"ftyp":
        return None
    brand = header[8:12]
    if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
        return CompatibleFormat("HEIC", "heic")
    if brand == b"qt  ":
        return CompatibleFormat("MOV", "mov")
    if brand == b"crx ":
        return None
    return CompatibleFormat("MP4", "mp4")


def classify_content(path: Path) -> CompatibleFormat:
    try:
        with path.open("rb") as stream:
            header = stream.read(1024)
    except OSError as exc:
        raise ConnectorError("STAGED_READ_FAILED", "staged payload cannot be read", 4, True) from exc
    detected: CompatibleFormat | None = None
    if header.startswith(b"\xff\xd8\xff"):
        detected = CompatibleFormat("JPEG", "jpg")
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = CompatibleFormat("PNG", "png")
    elif header.startswith((b"II*\x00", b"MM\x00*")):
        detected = CompatibleFormat("TIFF", "tif")
    elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        detected = CompatibleFormat("WEBP", "webp")
    elif header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        detected = CompatibleFormat("AVI", "avi")
    elif header.startswith(b"\x1aE\xdf\xa3"):
        detected = CompatibleFormat("MKV", "mkv")
    else:
        detected = _iso_brand(header)
    if detected is None and len(header) >= 376 and all(header[offset] == 0x47 for offset in (0, 188, 376)):
        detected = CompatibleFormat("MTS", "mts")
    if detected is None and len(header) >= 389 and all(header[offset] == 0x47 for offset in (4, 196, 388)):
        detected = CompatibleFormat("M2TS", "m2ts")
    if detected is None:
        raise ConnectorError(
            "FORMAT_NOT_INGEST_COMPATIBLE",
            "content format is unknown or ambiguous without trusting its filename",
            4,
            False,
        )
    return detected
