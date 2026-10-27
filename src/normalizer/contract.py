from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from normalizer import SUPPORTED_WORKSPACE_CONTRACT_VERSION
from normalizer.models import AssetInput, InputIssue, WorkspaceInput


class ContractError(ValueError):
    """A public input is unsafe or violates workspace contract v1."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_REQUIRED_ASSET_FIELDS = {
    "asset_id",
    "sha256",
    "size_bytes",
    "media_type",
    "format",
    "mime_type",
    "availability",
    "metadata_location",
    "preview_location",
    "sources",
}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing {label}: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Invalid {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Invalid {label}: expected a JSON object")
    return value


def _safe_relative(root: Path, value: object, label: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractError(f"Invalid {label}: expected a relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ContractError(f"Invalid {label}: path must stay inside the workspace")
    target = root.joinpath(*pure.parts).resolve(strict=False)
    resolved_root = root.resolve(strict=True)
    if target == resolved_root or resolved_root not in target.parents:
        raise ContractError(f"Invalid {label}: path escapes the workspace")
    return target, pure.as_posix()


def _asset_identity(entry: dict[str, Any]) -> tuple[str, str]:
    asset_id = entry.get("asset_id")
    sha256 = entry.get("sha256")
    if (
        not isinstance(asset_id, str)
        or not isinstance(sha256, str)
        or not _SHA256.fullmatch(sha256)
        or asset_id != f"sha256:{sha256}"
    ):
        raise ContractError(f"Invalid asset identity: {asset_id!r}")
    return asset_id, sha256


def _validate_source(source: object, asset_id: str) -> dict[str, str]:
    if not isinstance(source, dict):
        raise ContractError(f"Invalid source for {asset_id}: expected an object")
    source_id = source.get("source_version_id")
    relative = source.get("relative_path")
    status = source.get("status")
    if not isinstance(source_id, str) or not source_id:
        raise ContractError(f"Invalid source_version_id for {asset_id}")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ContractError(f"Invalid source relative_path for {asset_id}")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ContractError(f"Invalid source relative_path for {asset_id}")
    if status not in {"active", "superseded", "absent"}:
        raise ContractError(f"Invalid source status for {asset_id}: {status!r}")
    return {
        "source_version_id": source_id,
        "relative_path": pure.as_posix(),
        "status": status,
    }


def _validate_catalog_entry(entry: object) -> tuple[dict[str, Any], str, str]:
    if not isinstance(entry, dict):
        raise ContractError("Invalid asset catalog: asset entry must be an object")
    missing = _REQUIRED_ASSET_FIELDS - entry.keys()
    if missing:
        raise ContractError(
            f"Invalid asset catalog entry: missing {', '.join(sorted(missing))}"
        )
    asset_id, sha256 = _asset_identity(entry)
    if isinstance(entry["size_bytes"], bool) or not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
        raise ContractError(f"Invalid size_bytes for {asset_id}")
    if entry["media_type"] not in {"image", "video"}:
        raise ContractError(f"Invalid media_type for {asset_id}")
    if entry["availability"] not in {"available", "unavailable"}:
        raise ContractError(f"Invalid availability for {asset_id}")
    if entry["format"] is not None and not isinstance(entry["format"], str):
        raise ContractError(f"Invalid format for {asset_id}")
    if entry["mime_type"] is not None and not isinstance(entry["mime_type"], str):
        raise ContractError(f"Invalid mime_type for {asset_id}")
    if not isinstance(entry["sources"], list):
        raise ContractError(f"Invalid sources for {asset_id}: expected an array")
    normalized = dict(entry)
    normalized["sources"] = sorted(
        (_validate_source(item, asset_id) for item in entry["sources"]),
        key=lambda item: (item["relative_path"], item["status"], item["source_version_id"]),
    )
    return normalized, asset_id, sha256


def _metadata_semantic(metadata: dict[str, Any]) -> dict[str, Any]:
    # raw_metadata is an opaque reference and is deliberately neither interpreted
    # nor part of N1 semantic input identity.
    return {
        key: metadata[key]
        for key in ("schema_version", "asset", "detected", "capture", "technical", "stages")
        if key in metadata
    }


def _load_metadata(
    workspace: Path, entry: dict[str, Any], asset_id: str
) -> tuple[str | None, dict[str, Any] | None, tuple[InputIssue, ...]]:
    location = entry.get("metadata_location")
    if location is None:
        return None, None, (
            InputIssue(asset_id, "MISSING_METADATA_DOCUMENT", "No metadata_location is published"),
        )
    target, normalized_location = _safe_relative(
        workspace, location, f"metadata_location for {asset_id}"
    )
    sha256 = asset_id.removeprefix("sha256:")
    expected_location = f"metadata/assets/{sha256[:2]}/{sha256}.json"
    if normalized_location != expected_location:
        raise ContractError(
            f"Invalid metadata_location for {asset_id}: expected {expected_location}"
        )
    try:
        metadata = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return normalized_location, None, (
            InputIssue(asset_id, "MISSING_METADATA_DOCUMENT", "Published metadata document is missing", normalized_location),
        )
    except (OSError, json.JSONDecodeError) as exc:
        return normalized_location, None, (
            InputIssue(asset_id, "INVALID_METADATA_DOCUMENT", f"Metadata document is not readable JSON: {exc}", normalized_location),
        )
    if not isinstance(metadata, dict):
        return normalized_location, None, (
            InputIssue(asset_id, "INVALID_METADATA_DOCUMENT", "Metadata document must be an object", normalized_location),
        )
    if metadata.get("schema_version") != 1:
        return normalized_location, None, (
            InputIssue(asset_id, "INVALID_METADATA_SCHEMA", "Metadata schema_version must be 1", normalized_location),
        )
    metadata_asset = metadata.get("asset")
    if not isinstance(metadata_asset, dict) or metadata_asset.get("asset_id") != asset_id:
        return normalized_location, None, (
            InputIssue(asset_id, "METADATA_IDENTITY_MISMATCH", "Metadata asset_id does not match the catalog", normalized_location),
        )
    return normalized_location, metadata, ()


def load_workspace_header(workspace_path: Path) -> tuple[Path, dict[str, Any]]:
    try:
        workspace = workspace_path.resolve(strict=True)
    except OSError as exc:
        raise ContractError(f"Workspace does not exist: {workspace_path}") from exc
    if not workspace.is_dir():
        raise ContractError(f"Workspace is not a directory: {workspace}")
    manifest = _read_json(workspace / "workspace.json", "workspace manifest")
    version = manifest.get("workspace_contract_version")
    if version != SUPPORTED_WORKSPACE_CONTRACT_VERSION:
        raise ContractError(
            f"Unsupported workspace contract version: {version!r}; expected 1"
        )
    workspace_id = manifest.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ContractError("Invalid workspace manifest: missing workspace_id")
    return workspace, manifest


def load_workspace(workspace_path: Path) -> WorkspaceInput:
    workspace, manifest = load_workspace_header(workspace_path)
    version = manifest["workspace_contract_version"]
    workspace_id = manifest["workspace_id"]
    catalog_path, catalog_location = _safe_relative(
        workspace, manifest.get("asset_catalog"), "asset_catalog"
    )
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != version:
        raise ContractError("Asset catalog contract version does not match workspace.json")
    if catalog.get("workspace_id") != workspace_id:
        raise ContractError("Asset catalog workspace_id does not match workspace.json")
    entries = catalog.get("assets")
    if not isinstance(entries, list):
        raise ContractError("Invalid asset catalog: assets must be an array")

    assets: list[AssetInput] = []
    seen: set[str] = set()
    semantic_entries: list[dict[str, Any]] = []
    for entry_index, raw_entry in enumerate(entries):
        entry, asset_id, sha256 = _validate_catalog_entry(raw_entry)
        if asset_id in seen:
            raise ContractError(f"Invalid asset catalog: duplicate asset_id {asset_id}")
        seen.add(asset_id)
        metadata_location, metadata, issues = _load_metadata(workspace, entry, asset_id)
        semantic_entry = {
            key: entry[key]
            for key in (
                "asset_id", "sha256", "size_bytes", "media_type", "format",
                "mime_type", "availability", "metadata_location", "preview_location", "sources"
            )
        }
        semantic_entries.append(semantic_entry)
        if metadata is not None:
            semantic_metadata = _metadata_semantic(metadata)
        elif metadata_location is not None:
            invalid_path = workspace.joinpath(*PurePosixPath(metadata_location).parts)
            try:
                semantic_metadata = {
                    "invalid_content_sha256": hashlib.sha256(
                        invalid_path.read_bytes()
                    ).hexdigest()
                }
            except OSError:
                semantic_metadata = None
        else:
            semantic_metadata = None
        assets.append(
            AssetInput(
                asset_id,
                sha256,
                catalog_location,
                f"/assets/{entry_index}",
                entry,
                metadata_location,
                metadata,
                semantic_metadata,
                issues,
            )
        )
    assets.sort(key=lambda item: item.sha256)
    manifest_semantic = {
        "workspace_contract_version": version,
        "workspace_id": workspace_id,
        "asset_catalog": catalog_location,
    }
    catalog_semantic = {
        "workspace_contract_version": version,
        "workspace_id": workspace_id,
        "generated_at": catalog.get("generated_at"),
        "generated_by_run_id": catalog.get("generated_by_run_id"),
        "assets": semantic_entries,
    }
    return WorkspaceInput(
        workspace,
        workspace_id,
        version,
        "workspace.json",
        manifest_semantic,
        catalog_location,
        catalog_semantic,
        catalog.get("generated_at") if isinstance(catalog.get("generated_at"), str) else None,
        catalog.get("generated_by_run_id") if isinstance(catalog.get("generated_by_run_id"), str) else None,
        tuple(assets),
    )
