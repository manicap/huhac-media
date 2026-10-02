from __future__ import annotations

from pathlib import Path

import numpy as np


def read_image(path: Path):
    """Decode an image without passing a Windows path through OpenCV."""
    import cv2

    try:
        encoded = np.fromfile(str(path), dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"Cannot read image: {path}: {exc}") from exc
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Cannot decode a three-channel image: {path}")
    return image


def write_image(path: Path, image, *, extension: str = ".jpg", params=None) -> None:
    """Encode then publish an image using Unicode-safe NumPy file I/O."""
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(extension, image, params or [])
    if not ok:
        raise ValueError(f"Cannot encode image for {path}")
    try:
        encoded.tofile(str(path))
    except OSError as exc:
        raise ValueError(f"Cannot write image: {path}: {exc}") from exc
