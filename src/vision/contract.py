from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from vision import SUPPORTED_WORKSPACE_CONTRACT_VERSION
from vision.models import InputIssue, VisualInput, WorkspaceInput


class ContractError(ValueError):
    pass


_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEYFRAME_ID = re.compile(r"keyframe-[0-9]{4}")


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


def _relative_path(root: Path, value: object, label: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value:
        raise ContractError(f"Invalid {label}: expected a relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ContractError(f"Invalid {label}: path must stay inside the workspace")
    target = root.joinpath(*pure.parts).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ContractError(f"Invalid {label}: path escapes the workspace")
    return target, pure.as_posix()


def _asset_identity(entry: dict[str, Any]) -> tuple[str, str]:
    asset_id = entry.get("asset_id")
    sha256 = entry.get("sha256")
    if not isinstance(asset_id, str) or not isinstance(sha256, str):
        raise ContractError("Invalid asset catalog: asset identity is missing")
    if not _SHA256.fullmatch(sha256) or asset_id != f"sha256:{sha256}":
        raise ContractError(f"Invalid asset identity: {asset_id}")
    return asset_id, sha256


def _validate_keyframe_result(
    workspace: Path,
    workspace_id: str,
    contract_version: int,
    asset_id: str,
    sha256: str,
    fingerprint: str,
    path: Path,
) -> tuple[VisualInput, ...] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    valid = (
        payload.get("result_schema_version") == 1
        and payload.get("workspace_contract_version") == contract_version
        and payload.get("workspace_id") == workspace_id
        and payload.get("asset_id") == asset_id
        and payload.get("sha256") == sha256
        and payload.get("processor")
        == {"name": "video-keyframes", "version": "video-keyframes-v1"}
        and payload.get("configuration_fingerprint") == fingerprint
        and payload.get("status") == "success"
        and isinstance(result, dict)
        and isinstance(result.get("keyframes"), list)
        and bool(result["keyframes"])
    )
    if not valid:
        return None
    expected_directory = path.with_suffix("") / "keyframes"
    inputs: list[VisualInput] = []
    seen: set[str] = set()
    for item in result["keyframes"]:
        if not isinstance(item, dict):
            return None
        keyframe_id = item.get("keyframe_id")
        timestamp = item.get("timestamp_s")
        if (
            not isinstance(keyframe_id, str)
            or not _KEYFRAME_ID.fullmatch(keyframe_id)
            or keyframe_id in seen
            or isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or timestamp < 0
            or item.get("source_video_asset_id") != asset_id
            or item.get("source_video_sha256") != sha256
            or item.get("configuration_fingerprint") != fingerprint
        ):
            return None
        try:
            image_path, location = _relative_path(
                workspace, item.get("location"), f"keyframe location for {asset_id}"
            )
        except ContractError:
            return None
        if expected_directory.resolve(strict=False) not in image_path.parents or not image_path.is_file():
            return None
        seen.add(keyframe_id)
        provenance = {
            "kind": "video_keyframe",
            "asset_id": asset_id,
            "sha256": sha256,
            "keyframe_id": keyframe_id,
            "location": location,
            "timestamp_s": timestamp,
            "video_keyframe_processor": {
                "name": "video-keyframes",
                "version": "video-keyframes-v1",
            },
            "video_keyframe_configuration_fingerprint": fingerprint,
        }
        inputs.append(
            VisualInput(
                asset_id,
                sha256,
                "video_keyframe",
                keyframe_id,
                image_path,
                provenance,
                fingerprint,
            )
        )
    return tuple(sorted(inputs, key=lambda item: item.input_id))


def _video_inputs(
    workspace: Path,
    workspace_id: str,
    contract_version: int,
    asset_id: str,
    sha256: str,
    requested_fingerprint: str | None,
) -> tuple[tuple[VisualInput, ...] | None, InputIssue | None]:
    root = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1"
    if requested_fingerprint is not None:
        candidates = [root / requested_fingerprint / sha256[:2] / f"{sha256}.json"]
    else:
        candidates = sorted(root.glob(f"*/{sha256[:2]}/{sha256}.json")) if root.is_dir() else []
    valid: list[tuple[str, tuple[VisualInput, ...]]] = []
    for candidate in candidates:
        resolved_root = root.resolve(strict=False)
        resolved_candidate = candidate.resolve(strict=False)
        if resolved_root not in resolved_candidate.parents:
            continue
        fingerprint = candidate.parents[1].name
        if not _SHA256.fullmatch(fingerprint):
            continue
        inputs = _validate_keyframe_result(
            workspace,
            workspace_id,
            contract_version,
            asset_id,
            sha256,
            fingerprint,
            resolved_candidate,
        )
        if inputs is not None:
            valid.append((fingerprint, inputs))
    if len(valid) == 1:
        return valid[0][1], None
    if len(valid) > 1:
        return None, InputIssue(
            asset_id,
            sha256,
            "video",
            "AMBIGUOUS_KEYFRAME_RESULT",
            "Multiple compatible Video Keyframe v1 results exist; select one with --keyframe-fingerprint",
        )
    code = "INVALID_KEYFRAME_RESULT" if candidates and any(path.exists() for path in candidates) else "MISSING_KEYFRAME_RESULT"
    return None, InputIssue(
        asset_id,
        sha256,
        "video",
        code,
        "No complete compatible Video Keyframe Extractor v1 result is available",
    )


def load_workspace(
    workspace_path: Path, keyframe_fingerprint: str | None = None
) -> WorkspaceInput:
    if keyframe_fingerprint is not None and not _SHA256.fullmatch(keyframe_fingerprint):
        raise ContractError("keyframe fingerprint must be 64 lowercase hexadecimal characters")
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
            f"Unsupported workspace contract version: {version!r}; expected {SUPPORTED_WORKSPACE_CONTRACT_VERSION}"
        )
    workspace_id = manifest.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ContractError("Invalid workspace manifest: missing workspace_id")
    catalog_path, _ = _relative_path(workspace, manifest.get("asset_catalog"), "asset_catalog")
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != version:
        raise ContractError("Asset catalog contract version does not match workspace.json")
    if catalog.get("workspace_id") != workspace_id:
        raise ContractError("Asset catalog workspace_id does not match workspace.json")
    entries = catalog.get("assets")
    if not isinstance(entries, list):
        raise ContractError("Invalid asset catalog: assets must be an array")

    inputs: list[VisualInput] = []
    issues: list[InputIssue] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractError("Invalid asset catalog: asset entry must be an object")
        asset_id, sha256 = _asset_identity(entry)
        if asset_id in seen:
            raise ContractError(f"Invalid asset catalog: duplicate asset_id {asset_id}")
        seen.add(asset_id)
        if entry.get("availability") != "available":
            continue
        media_type = entry.get("media_type")
        if media_type == "image":
            try:
                preview, location = _relative_path(
                    workspace, entry.get("preview_location"), f"preview_location for {asset_id}"
                )
            except ContractError:
                preview = None
                location = None
            if preview is None or not preview.is_file():
                issues.append(
                    InputIssue(
                        asset_id,
                        sha256,
                        "image",
                        "MISSING_IMAGE_PREVIEW",
                        "The available image asset has no usable public preview_location",
                    )
                )
                continue
            provenance = {
                "kind": "image_preview",
                "asset_id": asset_id,
                "sha256": sha256,
                "location": location,
            }
            inputs.append(
                VisualInput(asset_id, sha256, "image_preview", "image-preview", preview, provenance)
            )
        elif media_type == "video":
            video_inputs, issue = _video_inputs(
                workspace,
                workspace_id,
                version,
                asset_id,
                sha256,
                keyframe_fingerprint,
            )
            if issue is not None:
                issues.append(issue)
            elif video_inputs is not None:
                inputs.extend(video_inputs)
    inputs.sort(key=lambda item: (item.sha256, item.kind, item.input_id))
    issues.sort(key=lambda item: (item.sha256, item.code))
    return WorkspaceInput(workspace, workspace_id, version, tuple(inputs), tuple(issues))
