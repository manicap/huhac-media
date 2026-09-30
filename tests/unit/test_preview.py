from pathlib import Path, PurePosixPath

from PIL import Image

from huhac_media.config import ImageConfig
from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile
from huhac_media.media.preview import PreviewGenerator, preview_fingerprint
from huhac_media.tools.ffmpeg import FFmpeg


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


def test_heic_preview_decodes_grid_before_scaling(tmp_path: Path) -> None:
    class RecordingRunner:
        def __init__(self) -> None:
            self.commands: list[tuple[str, ...]] = []

        def run(self, arguments, *, timeout: float = 60.0):
            self.commands.append(tuple(arguments))
            output_format = "PNG" if Path(arguments[-1]).suffix == ".png" else "JPEG"
            Image.new("RGB", (16, 8), "blue").save(arguments[-1], format=output_format)

    source = tmp_path / "source.heic"
    source.write_bytes(b"synthetic HEIC placeholder")
    target = tmp_path / "preview.jpg"
    runner = RecordingRunner()
    fallback = FFmpeg(runner=runner)
    stat = source.stat()
    item = ScannedFile(
        source,
        PurePosixPath(source.name),
        source.name,
        stat.st_size,
        stat.st_mtime_ns,
        MediaType.IMAGE,
        "HEIC",
        "image/heic",
        "b" * 64,
    )

    PreviewGenerator(ImageConfig(max_dimension=768), fallback).create(item, target)

    assert len(runner.commands) == 2
    decode, scale = runner.commands
    assert "-vf" not in decode
    assert decode[decode.index("-vcodec") + 1] == "png"
    assert Path(decode[-1]).name == "decoded.png"
    filter_index = scale.index("-vf")
    assert scale[filter_index + 1] == (
        "scale=768:768:force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    assert scale[scale.index("-i") + 1] == decode[-1]
    with Image.open(target) as generated:
        generated.verify()
