from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
from typing import Any

from session_grouper import SUPPORTED_WORKSPACE_CONTRACT_VERSION
from session_grouper.models import (
    AssetObservation,
    GroupingConfig,
    TimestampConfidence,
    TimestampEvidence,
)


STRONG_TIMESTAMP_SOURCES = {
    "EXIF:DateTimeOriginal",
    "QuickTime:CreateDate",
    "ffprobe:format.tags.creation_time",
}


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceInput:
    workspace: Path
    workspace_id: str
    contract_version: int
    catalog_location: str
    catalog_generated_at: str | None
    catalog_run_id: str | None
    observations: tuple[AssetObservation, ...]


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


def _resolve_public_path(workspace: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ContractError(f"Invalid {label}: expected a relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractError(f"Invalid {label}: path must stay inside the workspace")
    target = workspace.joinpath(*pure.parts).resolve(strict=False)
    if target != workspace and workspace not in target.parents:
        raise ContractError(f"Invalid {label}: path escapes the workspace")
    return target


def _timestamp(
    capture: object, config: GroupingConfig
) -> tuple[TimestampEvidence | None, str | None]:
    if not isinstance(capture, dict):
        return None, "missing_capture_metadata"
    value = capture.get("datetime")
    if not isinstance(value, str) or not value:
        return None, "missing_capture_timestamp"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "invalid_capture_timestamp"
    wall_time = parsed.replace(tzinfo=None)
    if not config.min_year <= wall_time.year <= config.max_year:
        return None, "suspicious_capture_timestamp"
    fallback = capture.get("filesystem_fallback") is True
    source = capture.get("source") if isinstance(capture.get("source"), str) else None
    if fallback or source == "filesystem:mtime":
        confidence = TimestampConfidence.LOW
    elif source in STRONG_TIMESTAMP_SOURCES:
        confidence = TimestampConfidence.STRONG
    else:
        confidence = TimestampConfidence.MEDIUM
    offset = capture.get("timezone_offset")
    return (
        TimestampEvidence(
            value=value,
            wall_time=wall_time,
            source=source,
            timezone_offset=offset if isinstance(offset, str) else None,
            filesystem_fallback=fallback,
            confidence=confidence,
        ),
        None,
    )


def load_workspace(workspace_path: Path, config: GroupingConfig) -> WorkspaceInput:
    config.validate()
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
    catalog_location = manifest.get("asset_catalog")
    catalog_path = _resolve_public_path(workspace, catalog_location, "asset_catalog")
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != version:
        raise ContractError("Asset catalog contract version does not match workspace.json")
    if catalog.get("workspace_id") != workspace_id:
        raise ContractError("Asset catalog workspace_id does not match workspace.json")
    assets = catalog.get("assets")
    if not isinstance(assets, list):
        raise ContractError("Invalid asset catalog: assets must be an array")

    observations: list[AssetObservation] = []
    seen: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict):
            raise ContractError("Invalid asset catalog: asset entry must be an object")
        asset_id = entry.get("asset_id")
        sha256 = entry.get("sha256")
        media_type = entry.get("media_type")
        if not isinstance(asset_id, str) or not isinstance(sha256, str):
            raise ContractError("Invalid asset catalog: asset identity is missing")
        if (
            len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or asset_id != f"sha256:{sha256}"
        ):
            raise ContractError(f"Invalid asset identity: {asset_id}")
        if asset_id in seen:
            raise ContractError(f"Invalid asset catalog: duplicate asset_id {asset_id}")
        seen.add(asset_id)
        if media_type not in {"image", "video"}:
            raise ContractError(f"Invalid media_type for {asset_id}: {media_type!r}")
        availability = entry.get("availability")
        if availability not in {"available", "unavailable"}:
            raise ContractError(f"Invalid availability for {asset_id}: {availability!r}")
        metadata_location = entry.get("metadata_location")
        if metadata_location is not None and not isinstance(metadata_location, str):
            raise ContractError(f"Invalid metadata_location for {asset_id}")
        evidence = None
        issue = "metadata_not_published"
        if metadata_location is not None:
            metadata_path = _resolve_public_path(
                workspace, metadata_location, f"metadata_location for {asset_id}"
            )
            try:
                metadata = _read_json(metadata_path, f"asset metadata for {asset_id}")
                evidence, issue = _timestamp(metadata.get("capture"), config)
            except ContractError:
                issue = "metadata_unreadable"
        observations.append(
            AssetObservation(
                asset_id=asset_id,
                sha256=sha256,
                media_type=media_type,
                availability=availability,
                metadata_location=(
                    metadata_location if isinstance(metadata_location, str) else None
                ),
                timestamp=evidence,
                timestamp_issue=issue,
            )
        )

    observations.sort(key=lambda item: item.asset_id)
    return WorkspaceInput(
        workspace=workspace,
        workspace_id=workspace_id,
        contract_version=version,
        catalog_location=str(catalog_location),
        catalog_generated_at=(
            catalog.get("generated_at") if isinstance(catalog.get("generated_at"), str) else None
        ),
        catalog_run_id=(
            catalog.get("generated_by_run_id")
            if isinstance(catalog.get("generated_by_run_id"), str)
            else None
        ),
        observations=tuple(observations),
    )
