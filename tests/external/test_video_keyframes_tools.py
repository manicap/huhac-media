from pathlib import Path

import pytest
from PIL import Image

from video_keyframes.tools import CommandRunner, FFmpeg


pytestmark = pytest.mark.external


def test_real_ffmpeg_extracts_bounded_oriented_sample(tmp_path: Path) -> None:
    ffmpeg = FFmpeg()
    if not ffmpeg.available():
        pytest.skip("FFmpeg is not installed")
    source = tmp_path / "source.mp4"
    CommandRunner().run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=120x240:d=1",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        timeout=60,
    )
    target = tmp_path / "frame.png"

    ffmpeg.extract_png(source, 0.0, target, 768)

    with Image.open(target) as image:
        assert image.size == (120, 240)
