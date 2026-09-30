from pathlib import Path

from huhac_media.domain.enums import MediaType
from huhac_media.media.detection import detect_media


def test_signature_wins_over_extension(tmp_path: Path) -> None:
    path = tmp_path / "wrong.mp4"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 24)
    result = detect_media(path)
    assert result.media_type == MediaType.IMAGE
    assert result.format == "PNG"


def test_candidate_extension_supports_corrupt_media(tmp_path: Path) -> None:
    path = tmp_path / "broken.nef"
    path.write_bytes(b"not a real raw file")
    assert detect_media(path).format == "NEF"

