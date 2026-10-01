from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import io
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from video_keyframes.models import KeyframeConfig, SampledFrame
from video_keyframes.tools import FFmpeg, FFprobe


def sampling_timestamps(duration_s: float, interval_s: float) -> tuple[float, ...]:
    if duration_s <= 0 or interval_s <= 0:
        raise ValueError("duration and sampling interval must be positive")
    duration = Decimal(str(duration_s))
    interval = Decimal(str(interval_s))
    count = int((duration / interval).to_integral_value(rounding=ROUND_CEILING))
    return tuple(float(interval * index) for index in range(count))


def _srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def standardize_jpeg(
    source: Path, target: Path, max_dimension: int, quality: int
) -> tuple[int, int]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        profile = image.info.get("icc_profile")
        if profile:
            try:
                source_profile = ImageCms.ImageCmsProfile(io.BytesIO(profile))
                image = ImageCms.profileToProfile(
                    image, source_profile, ImageCms.createProfile("sRGB"), outputMode="RGB"
                )
            except (OSError, ValueError, ImageCms.PyCMSError):
                image = image.convert("RGB")
        else:
            image = image.convert("RGB")
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        image.save(
            target,
            format="JPEG",
            quality=quality,
            optimize=False,
            progressive=False,
            subsampling=2,
            icc_profile=_srgb_profile(),
        )
        return image.size


def sample_video(
    source: Path,
    directory: Path,
    config: KeyframeConfig,
    ffprobe: FFprobe,
    ffmpeg: FFmpeg,
) -> tuple[float, tuple[SampledFrame, ...]]:
    duration = ffprobe.duration(source)
    timestamps = sampling_timestamps(duration, config.sampling_interval_s)
    frames: list[SampledFrame] = []
    for index, timestamp in enumerate(timestamps):
        decoded = directory / f"decoded-{index:06d}.png"
        sampled = directory / f"sample-{index:06d}.jpg"
        ffmpeg.extract_png(source, timestamp, decoded, config.max_dimension)
        width, height = standardize_jpeg(
            decoded, sampled, config.max_dimension, config.jpeg_quality
        )
        decoded.unlink()
        frames.append(SampledFrame(index, timestamp, sampled, width, height))
    return duration, tuple(frames)
