from huhac_media.media.capture_time import select_capture_datetime


def test_exif_original_with_offset_has_priority() -> None:
    result = select_capture_datetime(
        {"EXIF:DateTimeOriginal": "2026:09:26 21:34:12", "EXIF:OffsetTimeOriginal": "+02:00"},
        {"format": {"tags": {"creation_time": "2020-01-01T00:00:00Z"}}},
        "2026-09-30T00:00:00+00:00",
    )
    assert result == {
        "datetime": "2026-09-26T21:34:12+02:00",
        "source": "EXIF:DateTimeOriginal",
        "timezone_offset": "+02:00",
        "filesystem_fallback": False,
    }


def test_filesystem_fallback_is_explicit() -> None:
    result = select_capture_datetime({}, None, "2026-09-30T00:00:00+00:00")
    assert result["source"] == "filesystem:mtime"
    assert result["filesystem_fallback"] is True

