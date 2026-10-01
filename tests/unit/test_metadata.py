from pathlib import Path, PurePosixPath

import pytest

from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile
from huhac_media.media.metadata import MetadataExtractor


class FakeProbe:
    def __init__(self, result):
        self.result = result

    def probe(self, path):
        return self.result


def scanned(media_type: MediaType, media_format: str = "X") -> ScannedFile:
    return ScannedFile(
        Path("x"), PurePosixPath("x"), "x", 1, 0, media_type, media_format, None, "a" * 64
    )


def test_missing_exif_is_not_an_error() -> None:
    result = MetadataExtractor(FakeProbe({})).extract(scanned(MediaType.IMAGE))
    assert result.normalized["capture"]["filesystem_fallback"] is True
    assert result.normalized["technical"]["camera_model"] is None


def test_reliable_exiftool_format_is_preserved() -> None:
    result = MetadataExtractor(
        FakeProbe({"File:FileType": "JPEG", "File:MIMEType": "image/jpeg"})
    ).extract(scanned(MediaType.IMAGE))
    assert result.normalized["detected"] == {"format": "JPEG", "mime_type": "image/jpeg"}


@pytest.mark.parametrize("media_format", ["JPEG", "HEIC"])
def test_grouped_exif_capture_is_normalized_for_image_formats(media_format: str) -> None:
    result = MetadataExtractor(
        FakeProbe(
            {
                "File:FileType": media_format,
                "File:MIMEType": "image/heic" if media_format == "HEIC" else "image/jpeg",
                "ExifIFD:DateTimeOriginal": "2026:09:26 21:18:02",
                "ExifIFD:OffsetTimeOriginal": "+02:00",
                "ExifIFD:SubSecTimeOriginal": 738,
            }
        )
    ).extract(scanned(MediaType.IMAGE, media_format))

    assert result.normalized["capture"] == {
        "datetime": "2026-09-26T21:18:02.738+02:00",
        "source": "ExifIFD:DateTimeOriginal",
        "timezone_offset": "+02:00",
        "filesystem_fallback": False,
    }


def test_video_streams_are_normalized() -> None:
    ffdata = {
        "format": {"format_name": "mov,mp4", "duration": "2.5", "bit_rate": "1000"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
        ],
    }
    result = MetadataExtractor(FakeProbe({}), FakeProbe(ffdata)).extract(scanned(MediaType.VIDEO))
    technical = result.normalized["technical"]
    assert technical["video_codec"] == "h264"
    assert technical["audio_present"] is True
    assert technical["sample_rate"] == 48000
