from huhac_media.media.capture_time import select_capture_datetime


FILESYSTEM_TIME = "2026-09-30T00:00:00+00:00"


def test_grouped_exif_original_with_offset_has_priority() -> None:
    result = select_capture_datetime(
        {
            "ExifIFD:DateTimeOriginal": "2026:09:26 21:34:12",
            "ExifIFD:OffsetTimeOriginal": "+02:00",
        },
        {"format": {"tags": {"creation_time": "2020-01-01T00:00:00Z"}}},
        FILESYSTEM_TIME,
    )
    assert result == {
        "datetime": "2026-09-26T21:34:12+02:00",
        "source": "ExifIFD:DateTimeOriginal",
        "timezone_offset": "+02:00",
        "filesystem_fallback": False,
    }


def test_composite_original_preserves_subseconds_and_offset() -> None:
    result = select_capture_datetime(
        {
            "Composite:SubSecDateTimeOriginal": "2026:09:26 21:18:02.738+02:00",
            "ExifIFD:DateTimeOriginal": "2026:09:26 21:18:02",
            "ExifIFD:OffsetTimeOriginal": "+02:00",
            "ExifIFD:SubSecTimeOriginal": 738,
        },
        None,
        FILESYSTEM_TIME,
    )
    assert result == {
        "datetime": "2026-09-26T21:18:02.738+02:00",
        "source": "Composite:SubSecDateTimeOriginal",
        "timezone_offset": "+02:00",
        "filesystem_fallback": False,
    }


def test_grouped_exif_original_combines_separate_subseconds() -> None:
    result = select_capture_datetime(
        {
            "ExifIFD:DateTimeOriginal": "2026:09:26 21:18:02",
            "ExifIFD:SubSecTimeOriginal": "0738",
        },
        None,
        FILESYSTEM_TIME,
    )
    assert result["datetime"] == "2026-09-26T21:18:02.0738"
    assert result["source"] == "ExifIFD:DateTimeOriginal"
    assert result["filesystem_fallback"] is False


def test_video_prefers_explicit_utc_timestamp_over_unzoned_quicktime() -> None:
    result = select_capture_datetime(
        {"QuickTime:CreateDate": "2026:09:26 19:20:55"},
        {"format": {"tags": {"creation_time": "2026-09-26T19:20:55Z"}}},
        FILESYSTEM_TIME,
    )
    assert result == {
        "datetime": "2026-09-26T19:20:55+00:00",
        "source": "ffprobe:format.tags.creation_time",
        "timezone_offset": "+00:00",
        "filesystem_fallback": False,
    }


def test_video_utc_timestamp_is_rendered_in_available_local_offset() -> None:
    result = select_capture_datetime(
        {
            "QuickTime:CreateDate": "2026:09:26 19:20:55",
            "Keys:AndroidTimeZone": "+0200",
        },
        {
            "format": {
                "tags": {
                    "creation_time": "2026-09-26T19:20:55.000000Z",
                    "com.vendor.utc_offset": "+0200",
                }
            }
        },
        FILESYSTEM_TIME,
    )
    assert result == {
        "datetime": "2026-09-26T21:20:55+02:00",
        "source": "ffprobe:format.tags.creation_time; timezone=Keys:AndroidTimeZone",
        "timezone_offset": "+02:00",
        "filesystem_fallback": False,
    }


def test_unzoned_quicktime_without_offset_remains_explicitly_unzoned() -> None:
    result = select_capture_datetime(
        {"QuickTime:CreateDate": "2026:09:26 19:20:55"},
        None,
        FILESYSTEM_TIME,
    )
    assert result == {
        "datetime": "2026-09-26T19:20:55",
        "source": "QuickTime:CreateDate",
        "timezone_offset": None,
        "filesystem_fallback": False,
    }


def test_filesystem_fallback_is_used_only_without_capture_time() -> None:
    result = select_capture_datetime({}, None, FILESYSTEM_TIME)
    assert result == {
        "datetime": FILESYSTEM_TIME,
        "source": "filesystem:mtime",
        "timezone_offset": "+00:00",
        "filesystem_fallback": True,
    }
