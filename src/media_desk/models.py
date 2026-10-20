from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Artifact:
    token: str
    path: Path
    authorization_root: Path
    media_type: str
    kind: str


@dataclass(frozen=True)
class ProcessorResult:
    processor: str
    version: str
    configuration_fingerprint: str
    model: Any
    created_at: str | None
    result: dict[str, Any]


@dataclass(frozen=True)
class SessionReference:
    session_id: str
    start: str | None
    end: str | None
    confidence: str | None
    configuration_fingerprint: str


@dataclass(frozen=True)
class FaceClusterReference:
    cluster_id: str
    status: str
    member_count: int
    configuration_fingerprint: str


@dataclass
class Asset:
    asset_id: str
    sha256: str
    media_type: str
    format: str
    mime_type: str
    size_bytes: int
    availability: str
    source_name: str
    capture_time: str | None
    capture_source: str | None
    technical: dict[str, Any]
    preview: Artifact | None
    preview_status: str
    original: Artifact | None
    sessions: list[SessionReference] = field(default_factory=list)
    vision: list[ProcessorResult] = field(default_factory=list)
    faces: list[ProcessorResult] = field(default_factory=list)
    face_clusters: list[FaceClusterReference] = field(default_factory=list)

    @property
    def original_online(self) -> bool:
        return self.original is not None


@dataclass(frozen=True)
class WorkspaceSnapshot:
    root: Path
    workspace_id: str
    contract_version: int
    generated_at: str | None
    assets: tuple[Asset, ...]
    artifacts: dict[str, Artifact]
    keyframe_fingerprint: str | None
