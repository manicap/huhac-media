from __future__ import annotations

import numpy as np

from faces.image_io import read_image, write_image
from faces.inference import clip_bbox, crop_face, l2_normalize


def test_unicode_safe_image_read_and_write(tmp_path):
    target = tmp_path / "příliš žluťoučký kůň" / "obličej 日本語.jpg"
    original = np.full((11, 13, 3), (10, 20, 30), dtype=np.uint8)
    write_image(target, original)
    decoded = read_image(target)
    assert decoded.shape == original.shape
    assert np.max(np.abs(decoded.astype(int) - original.astype(int))) <= 2


def test_bbox_is_clipped_before_crop_and_invalid_boxes_are_rejected():
    bbox = clip_bbox((-2.4, 3.2, 9.8, 20.0), image_width=10, image_height=12)
    assert bbox is not None
    assert bbox.as_dict() == {"x": 0, "y": 3, "width": 8, "height": 9}
    crop = crop_face(np.zeros((12, 10, 3), dtype=np.uint8), bbox)
    assert crop.shape == (9, 8, 3)
    assert clip_bbox((20, 20, 5, 5), 10, 12) is None
    assert clip_bbox((0, 0, -1, 5), 10, 12) is None


def test_embedding_is_256d_l2_normalized():
    normalized = l2_normalize(np.arange(1, 257, dtype=np.float32))
    assert normalized.shape == (256,)
    np.testing.assert_allclose(np.linalg.norm(normalized), 1.0, atol=1e-6)
