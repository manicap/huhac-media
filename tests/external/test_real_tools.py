from pathlib import Path

import pytest
from PIL import Image

from huhac_media.tools.exiftool import ExifTool


pytestmark = pytest.mark.external


def test_exiftool_reads_synthetic_jpeg(tmp_path: Path) -> None:
    tool = ExifTool()
    if not tool.available():
        pytest.skip("ExifTool is not installed")
    image = tmp_path / "synthetic.jpg"
    Image.new("RGB", (8, 6), "red").save(image)
    raw = tool.probe(image)
    assert raw.get("File:MIMEType") == "image/jpeg"

