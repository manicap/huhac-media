from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class VisionConfig:
    model: str = "minicpm-v4.6:latest"
    think: bool = False
    temperature: float = 0.0
    num_ctx: int = 8192
    num_predict: int = 1024
    max_repair_attempts: int = 1
    prompt_recipe: str = "objective-visual-description-v2"
    processor_recipe: str = "vision-analysis-v1"
    result_schema_version: int = 1

    def validate(self) -> None:
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not isinstance(self.think, bool):
            raise ValueError("think must be a boolean")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if self.num_ctx < 1:
            raise ValueError("num_ctx must be positive")
        if self.num_predict < 1:
            raise ValueError("num_predict must be positive")
        if self.max_repair_attempts < 0:
            raise ValueError("max_repair_attempts must be non-negative")
        if self.result_schema_version != 1:
            raise ValueError("Vision v1 requires result_schema_version 1")

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
