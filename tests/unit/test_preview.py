from pathlib import Path, PurePosixPath

from PIL import Image

from huhac_media.config import ImageConfig
from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile
from huhac_media.media.preview import PreviewGenerator, preview_fingerprint


def scanned(path: Path) -> ScannedFile:
    stat = path.stat()
    return ScannedFile(path, PurePosixPath(path.name), path.name, stat.st_size, stat.st_mtime_ns,
                       MediaType.IMAGE, "JPEG", "image/jpeg", "a" * 64)


def test_preview_respects_orientation_and_does_not_upscale(tmp_path: Path) -> None:
    source = tmp_path / "oriented.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (4, 2), "red").save(source, exif=exif)
    target = tmp_path / "preview.jpg"

    PreviewGenerator(ImageConfig(max_dimension=10)).create(scanned(source), target)

    with Image.open(target) as image:
        assert image.size == (2, 4)


def test_preview_downscales_and_composites_transparency(tmp_path: Path) -> None:
    source = tmp_path / "alpha.png"
    Image.new("RGBA", (100, 50), (255, 0, 0, 0)).save(source)
    target = tmp_path / "preview.jpg"
    PreviewGenerator(ImageConfig(max_dimension=20, transparent_background="black")).create(
        scanned(source), target
    )
    with Image.open(target) as image:
        assert image.size == (20, 10)
        assert image.mode == "RGB"
        assert max(image.getpixel((0, 0))) < 10


def test_recipe_fingerprint_changes_with_configuration() -> None:
    assert preview_fingerprint(ImageConfig(quality=90)) != preview_fingerprint(ImageConfig(quality=80))

