from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NormalizerConfig:
    normalization_rules: str = "normalized-asset-n2"
    safe_conversion_policy: str = "safe-scalars-v1"
    include_unavailable_assets: bool = True
    result_schema_version: int = 1
    session_configuration_fingerprint: str | None = None
    session_logical_input_fingerprint: str | None = None
    keyframes_configuration_fingerprint: str | None = None
    vision_configuration_fingerprint: str | None = None
    faces_configuration_fingerprint: str | None = None
    faces_clustering_configuration_fingerprint: str | None = None
    faces_clustering_logical_input_fingerprint: str | None = None

    def validate(self) -> None:
        if self.normalization_rules not in {"normalized-asset-n1", "normalized-asset-n2"}:
            raise ValueError("normalization_rules must be normalized-asset-n1 or normalized-asset-n2")
        if self.safe_conversion_policy != "safe-scalars-v1":
            raise ValueError("Normalizer N1 requires safe_conversion_policy safe-scalars-v1")
        if self.result_schema_version != 1:
            raise ValueError("Normalizer N1 requires result_schema_version 1")
        if not isinstance(self.include_unavailable_assets, bool):
            raise ValueError("include_unavailable_assets must be a boolean")
        fingerprint_fields = (
            "session_configuration_fingerprint",
            "session_logical_input_fingerprint",
            "keyframes_configuration_fingerprint",
            "vision_configuration_fingerprint",
            "faces_configuration_fingerprint",
            "faces_clustering_configuration_fingerprint",
            "faces_clustering_logical_input_fingerprint",
        )
        for name in fingerprint_fields:
            value = getattr(self, name)
            if value is not None and (
                len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
        if self.normalization_rules == "normalized-asset-n1" and any(
            getattr(self, name) is not None for name in fingerprint_fields
        ):
            raise ValueError("normalized-asset-n1 cannot select N2 upstream results")
        if self.session_logical_input_fingerprint and not self.session_configuration_fingerprint:
            raise ValueError("session logical input requires a session configuration fingerprint")
        if self.faces_clustering_configuration_fingerprint and not self.faces_configuration_fingerprint:
            raise ValueError("faces clustering requires a faces configuration fingerprint")
        if self.faces_clustering_logical_input_fingerprint and not self.faces_clustering_configuration_fingerprint:
            raise ValueError("faces clustering logical input requires a clustering configuration fingerprint")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def upstream_selection(self) -> dict[str, Any]:
        return {
            "session_grouper": {
                "configuration_fingerprint": self.session_configuration_fingerprint,
                "logical_input_fingerprint": self.session_logical_input_fingerprint,
            },
            "video_keyframes": {
                "configuration_fingerprint": self.keyframes_configuration_fingerprint,
            },
            "vision": {"configuration_fingerprint": self.vision_configuration_fingerprint},
            "faces": {"configuration_fingerprint": self.faces_configuration_fingerprint},
            "faces_clustering": {
                "configuration_fingerprint": self.faces_clustering_configuration_fingerprint,
                "logical_input_fingerprint": self.faces_clustering_logical_input_fingerprint,
            },
        }


@dataclass(frozen=True)
class InputIssue:
    asset_id: str
    code: str
    message: str
    location: str | None = None


@dataclass(frozen=True)
class AssetInput:
    asset_id: str
    sha256: str
    catalog_location: str
    catalog_pointer: str
    catalog: dict[str, Any]
    metadata_location: str | None
    metadata: dict[str, Any] | None
    metadata_semantic: dict[str, Any] | None
    issues: tuple[InputIssue, ...]


@dataclass(frozen=True)
class WorkspaceInput:
    workspace: Path
    workspace_id: str
    contract_version: int
    manifest_location: str
    manifest_semantic: dict[str, Any]
    catalog_location: str
    catalog_semantic: dict[str, Any]
    catalog_generated_at: str | None
    catalog_run_id: str | None
    assets: tuple[AssetInput, ...]
    upstream: dict[str, Any] = field(default_factory=dict)
    upstream_semantic: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedRun:
    workspace: WorkspaceInput
    config: NormalizerConfig
    configuration_fingerprint: str
    input_set_fingerprint: str
    output_path: Path
    reusable: bool


@dataclass(frozen=True)
class AnalysisResult:
    prepared: PreparedRun
    manifest: dict[str, Any]
    reused: bool
