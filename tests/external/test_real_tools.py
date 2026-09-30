from pathlib import Path

import pytest
from PIL import Image

from huhac_media.tools.exiftool import ExifTool
from huhac_media.tools.ffmpeg import FFmpeg


pytestmark = pytest.mark.external


def test_exiftool_reads_synthetic_jpeg(tmp_path: Path) -> None:
    tool = ExifTool()
    if not tool.available():
        pytest.skip("ExifTool is not installed")
    image = tmp_path / "synthetic.jpg"
    Image.new("RGB", (8, 6), "red").save(image)
    raw = tool.probe(image)
    assert raw.get("File:MIMEType") == "image/jpeg"


def test_ffmpeg_fallback_creates_preview(tmp_path: Path) -> None:
    tool = FFmpeg()
    if not tool.available():
        pytest.skip("FFmpeg is not installed")
    source = tmp_path / "source.png"
    target = tmp_path / "target.jpg"
    Image.new("RGB", (32, 16), "blue").save(source)
    tool.render_preview(source, target, 8, 90)
    with Image.open(target) as image:
        assert image.size == (8, 4)
