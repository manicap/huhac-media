from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class CatalogAsset:
    asset_id: str
    media_type: str
    availability: str = "available"
    original_access_state: str = "unchecked"
    display_name: str = ""
    source_name: str = ""
    capture_time: str | None = None
    preview_token: str | None = None
    width: int | None = None
    height: int | None = None
    rotation: int | None = None
    duration_seconds: float | None = None
    mime_type: str = "application/octet-stream"
    size_bytes: int | None = None
    original_token: str | None = None


@dataclass(frozen=True)
class CatalogArtifact:
    token: str
    path: Path
    authorization_root: Path
    media_type: str


@dataclass(frozen=True)
class CatalogOriginal:
    token: str
    asset_id: str
    media_kind: str
    relative_paths: tuple[str, ...]
    source_root: Path
    catalog_source_root: str
    workspace_id: str
    media_type: str
    binding_epoch: str
    expected_size: int | None = None


class WorkspaceCatalog(Protocol):
    def workspace_state(self, workspace_id: str) -> str:
        """Return available, unavailable, or unknown."""

    def asset(self, workspace_id: str, asset_id: str) -> CatalogAsset | None: ...

    def workspace_ids(self) -> Sequence[str]: ...

    def assets(self, workspace_id: str) -> Sequence[CatalogAsset]: ...

    def artifact(self, token: str) -> CatalogArtifact | None: ...

    def original(self, token: str) -> CatalogOriginal | None: ...


class InMemoryWorkspaceCatalog:
    """Small public port implementation; production adapters may wrap snapshots."""

    def __init__(
        self,
        workspaces: Mapping[str, Mapping[str, CatalogAsset]],
        *,
        unavailable_workspaces: set[str] | None = None,
        artifacts: Mapping[str, CatalogArtifact] | None = None,
        originals: Mapping[str, CatalogOriginal] | None = None,
    ) -> None:
        self._workspaces = {key: dict(value) for key, value in workspaces.items()}
        self._unavailable = frozenset(unavailable_workspaces or ())
        self._artifacts = dict(artifacts or {})
        self._originals = dict(originals or {})

    @classmethod
    def from_snapshots(cls, snapshots: Mapping[str, object]) -> InMemoryWorkspaceCatalog:
        workspaces: dict[str, dict[str, CatalogAsset]] = {}
        artifacts: dict[str, CatalogArtifact] = {}
        originals: dict[str, CatalogOriginal] = {}
        for workspace_id, snapshot in snapshots.items():
            assets = {}
            for asset in getattr(snapshot, "assets"):
                technical = asset.technical if isinstance(asset.technical, dict) else {}
                width = _positive_int(technical.get("width"))
                height = _positive_int(technical.get("height"))
                rotation = _rotation(technical.get("rotation"))
                duration_seconds = _positive_float(technical.get("duration_seconds"))
                original = asset.original
                assets[asset.asset_id] = CatalogAsset(
                    asset_id=asset.asset_id,
                    media_type=asset.media_type,
                    availability=asset.availability,
                    original_access_state=asset.original_access_state,
                    display_name=asset.display_name,
                    source_name=asset.source_name,
                    capture_time=asset.capture_time,
                    preview_token=asset.preview.token if asset.preview else None,
                    width=width,
                    height=height,
                    rotation=rotation,
                    duration_seconds=duration_seconds,
                    mime_type=asset.mime_type,
                    size_bytes=asset.size_bytes,
                    original_token=original.token if original else None,
                )
                if original is not None:
                    originals[original.token] = CatalogOriginal(
                        token=original.token,
                        asset_id=asset.asset_id,
                        media_kind=asset.media_type,
                        relative_paths=original.relative_paths,
                        source_root=original.source_root,
                        catalog_source_root=original.catalog_source_root,
                        workspace_id=original.workspace_id,
                        media_type=original.media_type,
                        binding_epoch=original.binding_epoch,
                        expected_size=asset.size_bytes,
                    )
            workspaces[workspace_id] = assets
            for token, artifact in getattr(snapshot, "artifacts").items():
                artifacts[token] = CatalogArtifact(
                    token=token,
                    path=artifact.path,
                    authorization_root=artifact.authorization_root,
                    media_type=artifact.media_type,
                )
        return cls(workspaces, artifacts=artifacts, originals=originals)

    def workspace_state(self, workspace_id: str) -> str:
        if workspace_id in self._unavailable:
            return "unavailable"
        return "available" if workspace_id in self._workspaces else "unknown"

    def asset(self, workspace_id: str, asset_id: str) -> CatalogAsset | None:
        if self.workspace_state(workspace_id) != "available":
            return None
        return self._workspaces[workspace_id].get(asset_id)

    def workspace_ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self._workspaces) | set(self._unavailable)))

    def assets(self, workspace_id: str) -> tuple[CatalogAsset, ...]:
        if self.workspace_state(workspace_id) != "available":
            return ()
        return tuple(self._workspaces[workspace_id].values())

    def artifact(self, token: str) -> CatalogArtifact | None:
        return self._artifacts.get(token)

    def original(self, token: str) -> CatalogOriginal | None:
        return self._originals.get(token)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    converted = int(value)
    return converted if converted > 0 and converted == value else None


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if converted > 0 and math.isfinite(converted) else None


def _rotation(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = int(value)
    if converted != value:
        return None
    return converted % 360
