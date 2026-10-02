from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class FacesConfig:
    detector_model: str = "face_detection_yunet_2023mar.onnx"
    detector_framework: str = "OpenCV FaceDetectorYN"
    detector_device: str = "CPU"
    score_threshold: float = 0.70
    nms_threshold: float = 0.30
    top_k: int = 5000
    embedding_model: str = "face-reidentification-retail-0095"
    embedding_framework: str = "OpenVINO"
    embedding_model_precision: str = "FP32"
    embedding_device: str = "CPU"
    embedding_input_width: int = 128
    embedding_input_height: int = 128
    embedding_color_order: str = "BGR"
    embedding_dimensions: int = 256
    alignment: str = "none"
    processor_recipe: str = "faces-detection-embedding-v1"
    result_schema_version: int = 1

    def validate(self) -> None:
        if self.detector_model != "face_detection_yunet_2023mar.onnx":
            raise ValueError("Faces v1 requires face_detection_yunet_2023mar.onnx")
        if self.detector_device != "CPU":
            raise ValueError("Faces v1 requires CPU face detection")
        if not 0 < self.score_threshold <= 1:
            raise ValueError("score_threshold must be in (0, 1]")
        if not 0 < self.nms_threshold <= 1:
            raise ValueError("nms_threshold must be in (0, 1]")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.embedding_model != "face-reidentification-retail-0095":
            raise ValueError("Faces v1 requires face-reidentification-retail-0095")
        if self.embedding_model_precision not in {"FP16", "FP32"}:
            raise ValueError("embedding_model_precision must be FP16 or FP32")
        if self.embedding_device != "CPU":
            raise ValueError("Faces v1 requires OpenVINO CPU execution")
        if (self.embedding_input_width, self.embedding_input_height) != (128, 128):
            raise ValueError("Faces v1 requires 128x128 embedding input")
        if self.embedding_color_order != "BGR" or self.embedding_dimensions != 256:
            raise ValueError("Faces v1 requires BGR input and a 256D embedding")
        if self.alignment != "none":
            raise ValueError("Faces v1 does not perform landmark alignment")
        if self.result_schema_version != 1:
            raise ValueError("Faces v1 requires result_schema_version 1")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClusterConfig:
    similarity_threshold: float = 0.70
    metric: str = "cosine"
    linkage: str = "complete"
    expansion: str = "none"
    processor_recipe: str = "faces-complete-link-clustering-v1"
    result_schema_version: int = 1

    def validate(self) -> None:
        if not -1 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be in [-1, 1]")
        if self.metric != "cosine" or self.linkage != "complete":
            raise ValueError("Faces clustering v1 requires cosine complete-link")
        if self.expansion != "none":
            raise ValueError("Faces clustering v1 does not have an expansion phase")
        if self.result_schema_version != 1:
            raise ValueError("Faces clustering v1 requires result_schema_version 1")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VisualInput:
    asset_id: str
    sha256: str
    kind: Literal["image_preview", "video_keyframe"]
    input_id: str
    path: Path
    provenance: dict[str, Any]
    keyframe_configuration_fingerprint: str | None = None


@dataclass(frozen=True)
class InputIssue:
    asset_id: str
    sha256: str
    media_type: str
    code: str
    message: str


@dataclass(frozen=True)
class WorkspaceInput:
    workspace: Path
    workspace_id: str
    contract_version: int
    inputs: tuple[VisualInput, ...]
    issues: tuple[InputIssue, ...]


@dataclass(frozen=True)
class InputPlan:
    visual_input: VisualInput
    output_path: Path
    action: Literal["process", "reuse"]


@dataclass(frozen=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class FaceDetection:
    bbox: BoundingBox
    confidence: float
    landmarks: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class FaceRecord:
    key: str
    asset_id: str
    sha256: str
    input_kind: str
    input_id: str
    face_id: str
    result_location: str
    provenance: dict[str, Any]
    embedding: tuple[float, ...]
