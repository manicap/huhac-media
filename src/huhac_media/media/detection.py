from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from huhac_media.domain.enums import MediaType


@dataclass(frozen=True)
class Detection:
    media_type: MediaType
    format: str | None
    mime_type: str | None


IMAGE_EXTENSIONS = {
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".png": ("PNG", "image/png"),
    ".webp": ("WEBP", "image/webp"),
    ".heic": ("HEIC", "image/heic"),
    ".heif": ("HEIF", "image/heif"),
    ".tif": ("TIFF", "image/tiff"),
    ".tiff": ("TIFF", "image/tiff"),
    ".cr2": ("CR2", "image/x-canon-cr2"),
    ".cr3": ("CR3", "image/x-canon-cr3"),
    ".nef": ("NEF", "image/x-nikon-nef"),
    ".arw": ("ARW", "image/x-sony-arw"),
    ".dng": ("DNG", "image/x-adobe-dng"),
}

VIDEO_EXTENSIONS = {
    ".mp4": ("MP4", "video/mp4"),
    ".mov": ("MOV", "video/quicktime"),
    ".mkv": ("MKV", "video/x-matroska"),
    ".avi": ("AVI", "video/x-msvideo"),
    ".mts": ("MTS", "video/mp2t"),
    ".m2ts": ("M2TS", "video/mp2t"),
}


def _signature(header: bytes) -> Detection | None:
    if header.startswith(b"\xff\xd8\xff"):
        return Detection(MediaType.IMAGE, "JPEG", "image/jpeg")
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return Detection(MediaType.IMAGE, "PNG", "image/png")
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return Detection(MediaType.IMAGE, "TIFF", "image/tiff")
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return Detection(MediaType.IMAGE, "WEBP", "image/webp")
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return Detection(MediaType.VIDEO, "AVI", "video/x-msvideo")
    if header.startswith(b"\x1aE\xdf\xa3"):
        return Detection(MediaType.VIDEO, "MKV", "video/x-matroska")
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return Detection(MediaType.IMAGE, "HEIC", "image/heic")
        if brand == b"qt  ":
            return Detection(MediaType.VIDEO, "MOV", "video/quicktime")
        return Detection(MediaType.VIDEO, "MP4", "video/mp4")
    return None


def detect_media(path: Path) -> Detection:
    try:
        with path.open("rb") as stream:
            header = stream.read(32)
    except OSError:
        header = b""
    detected = _signature(header)
    if detected is not None:
        return detected
    suffix = path.suffix.casefold()
    if suffix in IMAGE_EXTENSIONS:
        format_name, mime = IMAGE_EXTENSIONS[suffix]
        return Detection(MediaType.IMAGE, format_name, mime)
    if suffix in VIDEO_EXTENSIONS:
        format_name, mime = VIDEO_EXTENSIONS[suffix]
        return Detection(MediaType.VIDEO, format_name, mime)
    return Detection(MediaType.UNSUPPORTED, None, None)

