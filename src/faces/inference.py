from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from faces.models import BoundingBox, FaceDetection, FacesConfig


def clip_bbox(
    bbox: tuple[float, float, float, float], image_width: int, image_height: int
) -> BoundingBox | None:
    if image_width < 1 or image_height < 1 or not all(math.isfinite(value) for value in bbox):
        return None
    x, y, width, height = bbox
    if width <= 0 or height <= 0:
        return None
    left = max(0, min(image_width, math.floor(x)))
    top = max(0, min(image_height, math.floor(y)))
    right = max(0, min(image_width, math.ceil(x + width)))
    bottom = max(0, min(image_height, math.ceil(y + height)))
    if right <= left or bottom <= top:
        return None
    return BoundingBox(left, top, right - left, bottom - top)


def crop_face(image, bbox: BoundingBox):
    image_height, image_width = image.shape[:2]
    if (
        bbox.x < 0
        or bbox.y < 0
        or bbox.width <= 0
        or bbox.height <= 0
        or bbox.x + bbox.width > image_width
        or bbox.y + bbox.height > image_height
    ):
        raise ValueError("Face bounding box is outside the decoded image")
    crop = image[bbox.y : bbox.y + bbox.height, bbox.x : bbox.x + bbox.width]
    if crop.size == 0 or crop.ndim != 3 or crop.shape[2] != 3:
        raise ValueError("Face bounding box produced an invalid crop")
    return crop


def l2_normalize(values, *, dimensions: int = 256) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32).reshape(-1)
    if vector.size != dimensions or not np.isfinite(vector).all():
        raise ValueError(f"Embedding must contain {dimensions} finite values")
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        raise ValueError("Embedding has zero L2 norm")
    return vector / norm


class YuNetDetector:
    def __init__(self, model_path: Path, config: FacesConfig) -> None:
        import cv2

        if not model_path.is_file():
            raise FileNotFoundError(f"Missing YuNet model: {model_path}")
        self._detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            (320, 320),
            config.score_threshold,
            config.nms_threshold,
            config.top_k,
        )

    def detect(self, image) -> tuple[FaceDetection, ...]:
        image_height, image_width = image.shape[:2]
        self._detector.setInputSize((image_width, image_height))
        _, rows = self._detector.detect(image)
        detections: list[FaceDetection] = []
        if rows is None:
            return ()
        for row in rows:
            values = np.asarray(row, dtype=np.float64).reshape(-1)
            if values.size < 15 or not np.isfinite(values[:15]).all():
                continue
            bbox = clip_bbox(tuple(float(value) for value in values[:4]), image_width, image_height)
            confidence = float(values[14])
            if bbox is None or not 0 <= confidence <= 1:
                continue
            landmarks = tuple(
                (float(values[index]), float(values[index + 1]))
                for index in range(4, 14, 2)
            )
            detections.append(FaceDetection(bbox, confidence, landmarks))
        detections.sort(
            key=lambda item: (
                item.bbox.y,
                item.bbox.x,
                item.bbox.width,
                item.bbox.height,
                -item.confidence,
                item.landmarks,
            )
        )
        return tuple(detections)


class OpenVINOEmbedder:
    def __init__(self, model_path: Path, config: FacesConfig) -> None:
        from openvino import Core

        if not model_path.is_file():
            raise FileNotFoundError(f"Missing OpenVINO model XML: {model_path}")
        core = Core()
        self._compiled = core.compile_model(str(model_path), config.embedding_device)
        self._input = self._compiled.input(0)
        self._output = self._compiled.output(0)
        shape = tuple(int(value) for value in self._input.shape)
        if shape != (1, 3, 128, 128):
            raise ValueError(f"Unexpected embedding model input shape: {shape}")
        output_shape = tuple(int(value) for value in self._output.shape)
        if math.prod(output_shape) != config.embedding_dimensions:
            raise ValueError(f"Unexpected embedding model output shape: {output_shape}")
        self._dimensions = config.embedding_dimensions

    def embed(self, crop) -> np.ndarray:
        import cv2

        resized = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_LINEAR)
        blob = np.ascontiguousarray(resized.transpose(2, 0, 1)[None, ...], dtype=np.float32)
        result = self._compiled({self._input: blob})[self._output]
        return l2_normalize(result, dimensions=self._dimensions)
