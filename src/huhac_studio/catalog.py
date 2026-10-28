from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class CatalogArtifact:
    token: str
    path: Path
    authorization_root: Path
    media_type: str


class WorkspaceCatalog(Protocol):
    def workspace_state(self, workspace_id: str) -> str:
        """Return available, unavailable, or unknown."""

    def asset(self, workspace_id: str, asset_id: str) -> CatalogAsset | None: ...

    def workspace_ids(self) -> Sequence[str]: ...

    def assets(self, workspace_id: str) -> Sequence[CatalogAsset]: ...

    def artifact(self, token: str) -> CatalogArtifact | None: ...


class InMemoryWorkspaceCatalog:
    """Small public port implementation; production adapters may wrap snapshots."""

    def __init__(
        self,
        workspaces: Mapping[str, Mapping[str, CatalogAsset]],
        *,
        unavailable_workspaces: set[str] | None = None,
        artifacts: Mapping[str, CatalogArtifact] | None = None,
    ) -> None:
        self._workspaces = {key: dict(value) for key, value in workspaces.items()}
        self._unavailable = frozenset(unavailable_workspaces or ())
        self._artifacts = dict(artifacts or {})

    @classmethod
    def from_snapshots(cls, snapshots: Mapping[str, object]) -> InMemoryWorkspaceCatalog:
        workspaces: dict[str, dict[str, CatalogAsset]] = {}
        artifacts: dict[str, CatalogArtifact] = {}
        for workspace_id, snapshot in snapshots.items():
            assets = {}
            for asset in getattr(snapshot, "assets"):
                assets[asset.asset_id] = CatalogAsset(
                    asset_id=asset.asset_id,
                    media_type=asset.media_type,
                    availability=asset.availability,
                    original_access_state=asset.original_access_state,
                    display_name=asset.display_name,
                    source_name=asset.source_name,
                    capture_time=asset.capture_time,
                    preview_token=asset.preview.token if asset.preview else None,
                )
            workspaces[workspace_id] = assets
            for token, artifact in getattr(snapshot, "artifacts").items():
                artifacts[token] = CatalogArtifact(
                    token=token,
                    path=artifact.path,
                    authorization_root=artifact.authorization_root,
                    media_type=artifact.media_type,
                )
        return cls(workspaces, artifacts=artifacts)

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
