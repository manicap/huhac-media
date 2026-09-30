from pathlib import Path, PurePosixPath

from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile


def test_asset_id_is_content_address() -> None:
    item = ScannedFile(
        absolute_path=Path("photo.jpg"),
        relative_path=PurePosixPath("photo.jpg"),
        filename="photo.jpg",
        size_bytes=10,
        filesystem_mtime_ns=1,
        media_type=MediaType.IMAGE,
        format="JPEG",
        mime_type="image/jpeg",
        sha256="a" * 64,
    )
    assert item.asset_id == f"sha256:{'a' * 64}"

