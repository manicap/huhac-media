from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class KeyframeConfig:
    sampling_interval_s: float = 1.0
    coverage_similarity: float = 0.85
    max_dimension: int = 768
    jpeg_quality: int = 90
    clip_model: str = "ViT-B-32"
    clip_pretrained: str = "openai"
    device: str = "cpu"
    sampling_recipe: str = "timestamp-seek-v1"
    selection_recipe: str = "greedy-coverage-centroid-v1"

    def validate(self) -> None:
        if self.sampling_interval_s <= 0:
            raise ValueError("sampling_interval_s must be positive")
        if not -1.0 <= self.coverage_similarity <= 1.0:
            raise ValueError("coverage_similarity must be between -1 and 1")
        if self.max_dimension < 1:
            raise ValueError("max_dimension must be positive")
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if self.device != "cpu":
            raise ValueError("Video Keyframe Extractor v1 supports only CPU execution")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SourceReference:
    source_version_id: str
    relative_path: str
    absolute_path: Path


@dataclass(frozen=True)
class VideoAsset:
    asset_id: str
    sha256: str
    source: SourceReference | None
    source_issue: str | None = None


@dataclass(frozen=True)
class WorkspaceInput:
    workspace: Path
    workspace_id: str
    contract_version: int
    source_root: Path
    assets: tuple[VideoAsset, ...]


@dataclass(frozen=True)
class AssetPlan:
    asset: VideoAsset
    output_path: Path
    action: str


@dataclass(frozen=True)
class SampledFrame:
    index: int
    timestamp_s: float
    path: Path
    width: int
    height: int


@dataclass(frozen=True)
class CoverageSelection:
    coverage_candidate_index: int
    representative_index: int
    member_indices: tuple[int, ...]
