from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

from huhac_media.config import ImageConfig
from huhac_media.domain.errors import MediaError
from huhac_media.domain.models import ScannedFile
from huhac_media.storage.atomic import atomic_target


PREVIEW_PROCESSOR_VERSION = "image-preview-v1"


class PreviewFallback(Protocol):
    def render_preview(self, source: Path, target: Path, max_dimension: int, quality: int) -> None: ...


def preview_fingerprint(config: ImageConfig) -> str:
    recipe = {
        "processor": PREVIEW_PROCESSOR_VERSION,
        "max_dimension": config.max_dimension,
        "format": config.format.lower(),
        "quality": config.quality,
        "allow_upscale": config.allow_upscale,
        "transparent_background": config.transparent_background,
    }
    return hashlib.sha256(json.dumps(recipe, sort_keys=True).encode("utf-8")).hexdigest()


def preview_path(work_path: Path, sha256: str) -> Path:
    return work_path / "previews" / "images" / sha256[:2] / f"{sha256}.jpg"


class PreviewGenerator:
    def __init__(self, config: ImageConfig, fallback: PreviewFallback | None = None):
        self.config = config
        self.fallback = fallback

    def create(self, scanned: ScannedFile, target: Path) -> None:
        with atomic_target(target) as temporary:
            try:
                self._pillow(scanned.absolute_path, temporary)
            except (OSError, UnidentifiedImageError) as exc:
                if self.fallback is None:
                    raise MediaError(
                        "PREVIEW_DECODE_FAILED", str(exc), phase="preview"
                    ) from exc
                self.fallback.render_preview(
                    scanned.absolute_path,
                    temporary,
                    self.config.max_dimension,
                    self.config.quality,
                )
            try:
                with Image.open(temporary) as generated:
                    generated.verify()
            except (OSError, UnidentifiedImageError) as exc:
                raise MediaError(
                    "PREVIEW_VALIDATION_FAILED", str(exc), phase="preview"
                ) from exc

    def _pillow(self, source: Path, target: Path) -> None:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            if self.config.allow_upscale and max(image.size) < self.config.max_dimension:
                ratio = self.config.max_dimension / max(image.size)
                image = image.resize(
                    (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                    Image.Resampling.LANCZOS,
                )
            else:
                image.thumbnail(
                    (self.config.max_dimension, self.config.max_dimension),
                    Image.Resampling.LANCZOS,
                )
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background_value = 0 if self.config.transparent_background == "black" else 255
                background = Image.new("RGB", rgba.size, (background_value,) * 3)
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.save(
                target,
                format="JPEG",
                quality=self.config.quality,
                optimize=False,
                progressive=False,
            )

