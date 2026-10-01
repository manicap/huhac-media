from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any


_EXIF_DATETIME = re.compile(
    r"^(?P<date>\d{4}:\d{2}:\d{2}) (?P<time>\d{2}:\d{2}:\d{2})(?P<sub>\.\d+)?(?P<offset>[+-]\d{2}:?\d{2})?$"
)
_OFFSET = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):?(?P<minutes>\d{2})$")


def _value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _offset(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = _OFFSET.match(value.strip())
    if not match:
        return None
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
        return None
    return f"{match.group('sign')}{hours:02d}:{minutes:02d}"


def _subseconds(value: Any) -> str | None:
    if value in (None, ""):
        return None
    rendered = str(value).strip().removeprefix(".")
    return rendered if rendered.isdigit() else None


def _normalize(
    value: Any, offset: Any = None, subseconds: Any = None
) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    external_offset = _offset(offset)
    match = _EXIF_DATETIME.match(value.strip())
    if match:
        rendered = f"{match.group('date').replace(':', '-')}T{match.group('time')}"
        normalized_subseconds = _subseconds(subseconds)
        rendered += match.group("sub") or (
            f".{normalized_subseconds}" if normalized_subseconds else ""
        )
        timezone_offset = _offset(match.group("offset")) or external_offset
        if timezone_offset:
            rendered += timezone_offset
        return rendered, timezone_offset
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    rendered = parsed.isoformat()
    timezone_offset = parsed.strftime("%z") or None
    if timezone_offset:
        timezone_offset = timezone_offset[:3] + ":" + timezone_offset[3:]
    elif external_offset:
        timezone_offset = external_offset
        rendered += external_offset
    return rendered, timezone_offset


def _timezone_metadata(
    exif: dict[str, Any], ffprobe: dict[str, Any] | None
) -> tuple[str, str] | None:
    candidates: list[tuple[str, Any]] = []
    for key, value in exif.items():
        group, _, leaf = key.partition(":")
        normalized_leaf = re.sub(r"[^a-z]", "", leaf.casefold())
        if group in {"ExifIFD", "Keys", "QuickTime", "Composite"} and (
            normalized_leaf in {"offsettimeoriginal", "offsettime", "timezone"}
            or normalized_leaf.endswith("timezone")
            or normalized_leaf.endswith("utcoffset")
        ):
            candidates.append((key, value))
    format_tags = ((ffprobe or {}).get("format") or {}).get("tags") or {}
    for key, value in format_tags.items():
        normalized_key = re.sub(r"[^a-z]", "", key.casefold())
        if normalized_key.endswith("timezone") or normalized_key.endswith("utcoffset"):
            candidates.append((f"ffprobe:format.tags.{key}", value))
    for source, value in candidates:
        if normalized := _offset(value):
            return normalized, source
    return None


def _with_local_offset(
    normalized: tuple[str, str | None], timezone_metadata: tuple[str, str] | None
) -> tuple[str, str | None, str | None]:
    rendered, source_offset = normalized
    if source_offset != "+00:00" or timezone_metadata is None:
        return rendered, source_offset, None
    local_offset, offset_source = timezone_metadata
    parsed = datetime.fromisoformat(rendered)
    match = _OFFSET.match(local_offset)
    assert match is not None
    delta = timedelta(
        hours=int(match.group("hours")), minutes=int(match.group("minutes"))
    )
    if match.group("sign") == "-":
        delta = -delta
    localized = parsed.astimezone(timezone(delta))
    return localized.isoformat(), local_offset, offset_source


def select_capture_datetime(
    exif: dict[str, Any], ffprobe: dict[str, Any] | None, filesystem_mtime: str
) -> dict:
    image_candidates = [
        (
            "Composite:SubSecDateTimeOriginal",
            _value(exif, "Composite:SubSecDateTimeOriginal"),
            _value(exif, "ExifIFD:OffsetTimeOriginal"),
            None,
        ),
        (
            "ExifIFD:DateTimeOriginal",
            _value(exif, "ExifIFD:DateTimeOriginal", "EXIF:DateTimeOriginal"),
            _value(
                exif,
                "ExifIFD:OffsetTimeOriginal",
                "EXIF:OffsetTimeOriginal",
                "EXIF:TimeZoneOffset",
            ),
            _value(exif, "ExifIFD:SubSecTimeOriginal", "EXIF:SubSecTimeOriginal"),
        ),
        (
            "Composite:SubSecCreateDate",
            _value(exif, "Composite:SubSecCreateDate"),
            _value(exif, "ExifIFD:OffsetTimeDigitized"),
            None,
        ),
        (
            "ExifIFD:CreateDate",
            _value(exif, "ExifIFD:CreateDate", "EXIF:CreateDate"),
            _value(exif, "ExifIFD:OffsetTimeDigitized", "EXIF:OffsetTimeDigitized"),
            _value(exif, "ExifIFD:SubSecTimeDigitized", "EXIF:SubSecTimeDigitized"),
        ),
    ]
    for source, value, offset, subseconds in image_candidates:
        if normalized := _normalize(value, offset, subseconds):
            rendered, timezone_offset = normalized
            return {
                "datetime": rendered,
                "source": source,
                "timezone_offset": timezone_offset,
                "filesystem_fallback": False,
            }

    video_candidates = [
        ("QuickTime:CreationDate", _value(exif, "QuickTime:CreationDate")),
        ("Keys:CreationDate", _value(exif, "Keys:CreationDate")),
        ("QuickTime:CreateDate", _value(exif, "QuickTime:CreateDate")),
    ]
    format_tags = ((ffprobe or {}).get("format") or {}).get("tags") or {}
    video_candidates.append(
        ("ffprobe:format.tags.creation_time", format_tags.get("creation_time"))
    )
    timezone_metadata = _timezone_metadata(exif, ffprobe)
    normalized_video = [
        (source, normalized)
        for source, value in video_candidates
        if (normalized := _normalize(value))
    ]
    for source, normalized in normalized_video:
        if normalized[1] is None:
            continue
        rendered, timezone_offset, offset_source = _with_local_offset(
            normalized, timezone_metadata
        )
        return {
            "datetime": rendered,
            "source": (
                f"{source}; timezone={offset_source}" if offset_source else source
            ),
            "timezone_offset": timezone_offset,
            "filesystem_fallback": False,
        }
    for source, normalized in normalized_video:
        rendered, timezone_offset = normalized
        return {
            "datetime": rendered,
            "source": source,
            "timezone_offset": timezone_offset,
            "filesystem_fallback": False,
        }

    normalized = _normalize(filesystem_mtime)
    return {
        "datetime": normalized[0] if normalized else filesystem_mtime,
        "source": "filesystem:mtime",
        "timezone_offset": normalized[1] if normalized else None,
        "filesystem_fallback": True,
    }
