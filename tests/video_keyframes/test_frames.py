from pathlib import Path

from PIL import Image

from video_keyframes.frames import sampling_timestamps, standardize_jpeg
from video_keyframes.models import KeyframeConfig
from video_keyframes.tools import FFmpeg


def test_sampling_plan_is_time_based_and_excludes_duration_endpoint() -> None:
    assert sampling_timestamps(3.2, 1.0) == (0.0, 1.0, 2.0, 3.0)
    assert sampling_timestamps(0.2, 1.0) == (0.0,)
    assert sampling_timestamps(1.0, 0.4) == (0.0, 0.4, 0.8)


def test_standardized_jpeg_fits_bounding_box_without_upscaling(tmp_path: Path) -> None:
    landscape = tmp_path / "landscape.png"
    small = tmp_path / "small.png"
    Image.new("RGB", (1600, 800), "red").save(landscape)
    Image.new("RGB", (120, 240), "blue").save(small)

    landscape_size = standardize_jpeg(landscape, tmp_path / "landscape.jpg", 768, 90)
    small_size = standardize_jpeg(small, tmp_path / "small.jpg", 768, 90)

    assert landscape_size == (768, 384)
    assert small_size == (120, 240)
    for name in ("landscape.jpg", "small.jpg"):
        with Image.open(tmp_path / name) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"
            assert image.width <= 768 and image.height <= 768
            assert image.info.get("icc_profile")


class RecordingRunner:
    def __init__(self):
        self.arguments = None

    def available(self, executable: str) -> bool:
        return True

    def run(self, arguments, timeout):
        self.arguments = list(arguments)
        Path(arguments[-1]).write_bytes(b"frame")
        return ""


def test_ffmpeg_filter_has_bounding_box_and_no_upscale_guard(tmp_path: Path) -> None:
    runner = RecordingRunner()
    target = tmp_path / "frame.png"

    FFmpeg(runner=runner).extract_png(tmp_path / "video.mp4", 1.25, target, 768)

    command = runner.arguments
    assert command[command.index("-ss") + 1] == "1.250000"
    scale = command[command.index("-vf") + 1]
    assert "min(768,iw)" in scale
    assert "min(768,ih)" in scale
    assert "force_original_aspect_ratio=decrease" in scale
    assert "force_divisible_by=2" in scale


def test_configuration_defaults_match_v1_contract() -> None:
    config = KeyframeConfig()
    assert config.sampling_interval_s == 1.0
    assert config.coverage_similarity == 0.85
    assert config.max_dimension == 768
    assert config.clip_model == "ViT-B-32"
    assert config.clip_pretrained == "openai"
    assert config.device == "cpu"
