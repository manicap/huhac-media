from pathlib import Path, PurePosixPath

from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile
from huhac_media.media.metadata import MetadataExtractor


class FakeProbe:
    def __init__(self, result):
        self.result = result

    def probe(self, path):
        return self.result


def scanned(media_type: MediaType) -> ScannedFile:
    return ScannedFile(
        Path("x"), PurePosixPath("x"), "x", 1, 0, media_type, "X", None, "a" * 64
    )


def test_missing_exif_is_not_an_error() -> None:
    result = MetadataExtractor(FakeProbe({})).extract(scanned(MediaType.IMAGE))
    assert result.normalized["capture"]["filesystem_fallback"] is True
    assert result.normalized["technical"]["camera_model"] is None


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

