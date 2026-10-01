from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from video_keyframes import SUPPORTED_WORKSPACE_CONTRACT_VERSION
from video_keyframes.models import SourceReference, VideoAsset, WorkspaceInput


class ContractError(ValueError):
    pass


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing {label}: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Invalid {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"Invalid {label}: expected a JSON object")
    return payload


def _relative_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"Invalid {label}: expected a relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractError(f"Invalid {label}: path must stay inside its root")
    target = root.joinpath(*pure.parts).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ContractError(f"Invalid {label}: path escapes its root")
    return target


def _asset_identity(entry: dict[str, Any]) -> tuple[str, str]:
    asset_id = entry.get("asset_id")
    sha256 = entry.get("sha256")
    if not isinstance(asset_id, str) or not isinstance(sha256, str):
        raise ContractError("Invalid asset catalog: asset identity is missing")
    if (
        len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
        or asset_id != f"sha256:{sha256}"
    ):
        raise ContractError(f"Invalid asset identity: {asset_id}")
    return asset_id, sha256


def _select_source(
    source_root: Path, sources: object, asset_id: str
) -> tuple[SourceReference | None, str | None]:
    if not isinstance(sources, list):
        raise ContractError(f"Invalid sources for {asset_id}: expected an array")
    active: list[tuple[str, str, Path]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ContractError(f"Invalid source for {asset_id}: expected an object")
        if source.get("status") != "active":
            continue
        source_version_id = source.get("source_version_id")
        relative_path = source.get("relative_path")
        if not isinstance(source_version_id, str) or not source_version_id:
            raise ContractError(f"Invalid active source_version_id for {asset_id}")
        target = _relative_path(
            source_root, relative_path, f"active source path for {asset_id}"
        )
        active.append((str(relative_path), source_version_id, target))
    for relative_path, source_version_id, target in sorted(
        active, key=lambda item: (item[0], item[1])
    ):
        if target.is_file():
            return SourceReference(source_version_id, relative_path, target), None
    return None, "no_accessible_active_source"


def load_workspace(workspace_path: Path) -> WorkspaceInput:
    workspace = workspace_path.resolve(strict=True)
    if not workspace.is_dir():
        raise ContractError(f"Workspace is not a directory: {workspace}")
    manifest = _read_json(workspace / "workspace.json", "workspace manifest")
    version = manifest.get("workspace_contract_version")
    if version != SUPPORTED_WORKSPACE_CONTRACT_VERSION:
        raise ContractError(
            f"Unsupported workspace contract version: {version!r}; "
            f"expected {SUPPORTED_WORKSPACE_CONTRACT_VERSION}"
        )
    workspace_id = manifest.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ContractError("Invalid workspace manifest: missing workspace_id")
    catalog_path = _relative_path(
        workspace, manifest.get("asset_catalog"), "asset_catalog"
    )
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != version:
        raise ContractError("Asset catalog contract version does not match workspace.json")
    if catalog.get("workspace_id") != workspace_id:
        raise ContractError("Asset catalog workspace_id does not match workspace.json")
    source_root_value = catalog.get("source_root")
    if not isinstance(source_root_value, str) or not source_root_value:
        raise ContractError("Invalid asset catalog: missing source_root")
    source_root = Path(source_root_value)
    if not source_root.is_absolute():
        raise ContractError("Invalid asset catalog: source_root must be absolute")
    source_root = source_root.resolve(strict=False)
    entries = catalog.get("assets")
    if not isinstance(entries, list):
        raise ContractError("Invalid asset catalog: assets must be an array")

    assets: list[VideoAsset] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractError("Invalid asset catalog: asset entry must be an object")
        asset_id, sha256 = _asset_identity(entry)
        if asset_id in seen:
            raise ContractError(f"Invalid asset catalog: duplicate asset_id {asset_id}")
        seen.add(asset_id)
        if entry.get("media_type") != "video" or entry.get("availability") != "available":
            continue
        source, issue = _select_source(source_root, entry.get("sources"), asset_id)
        assets.append(VideoAsset(asset_id, sha256, source, issue))

    assets.sort(key=lambda asset: asset.sha256)
    return WorkspaceInput(
        workspace=workspace,
        workspace_id=workspace_id,
        contract_version=version,
        source_root=source_root,
        assets=tuple(assets),
    )
