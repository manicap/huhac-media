from __future__ import annotations

from datetime import datetime
import re
from typing import Any


_EXIF_DATETIME = re.compile(
    r"^(?P<date>\d{4}:\d{2}:\d{2}) (?P<time>\d{2}:\d{2}:\d{2})(?P<sub>\.\d+)?(?P<offset>[+-]\d{2}:?\d{2})?$"
)


def _value(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize(value: Any, offset: Any = None) -> tuple[str, str | None] | None:
    if not isinstance(value, str):
        return None
    match = _EXIF_DATETIME.match(value.strip())
    if match:
        rendered = f"{match.group('date').replace(':', '-') }T{match.group('time')}"
        if match.group("sub"):
            rendered += match.group("sub")
        timezone_offset = str(offset or match.group("offset") or "") or None
        if timezone_offset:
            if len(timezone_offset) == 5 and timezone_offset[3] != ":":
                timezone_offset = timezone_offset[:3] + ":" + timezone_offset[3:]
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
    return rendered, timezone_offset


def select_capture_datetime(exif: dict[str, Any], ffprobe: dict[str, Any] | None, filesystem_mtime: str) -> dict:
    candidates = [
        (
            "EXIF:DateTimeOriginal",
            _value(exif, "EXIF:DateTimeOriginal"),
            _value(exif, "EXIF:OffsetTimeOriginal", "EXIF:TimeZoneOffset"),
        ),
        ("EXIF:CreateDate", _value(exif, "EXIF:CreateDate"), _value(exif, "EXIF:OffsetTimeDigitized")),
        ("QuickTime:CreateDate", _value(exif, "QuickTime:CreateDate", "QuickTime:CreationDate"), None),
    ]
    if ffprobe:
        format_tags = ffprobe.get("format", {}).get("tags", {})
        candidates.append(("ffprobe:format.tags.creation_time", format_tags.get("creation_time"), None))
    for source, value, offset in candidates:
        normalized = _normalize(value, offset)
        if normalized:
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

