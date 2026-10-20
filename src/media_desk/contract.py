from __future__ import annotations

import json
import mimetypes
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable

from media_desk import SUPPORTED_WORKSPACE_CONTRACT_VERSION
from media_desk.models import (
    Artifact,
    Asset,
    FaceClusterReference,
    ProcessorResult,
    SessionReference,
    WorkspaceSnapshot,
)


class ContractError(ValueError):
    """A safe, user-facing public-contract validation error."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEYFRAME_ID = re.compile(r"keyframe-[0-9]{4}")
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing {label}: {path.name}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Invalid {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"Invalid {label}: expected a JSON object")
    return payload


def _safe_relative(root: Path, value: object, label: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractError(f"Invalid {label}: expected a workspace-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ContractError(f"Invalid {label}: path must stay inside the workspace")
    target = root.joinpath(*pure.parts).resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if target != resolved_root and resolved_root not in target.parents:
        raise ContractError(f"Invalid {label}: path escapes the workspace")
    return target, pure.as_posix()


def _inside(root: Path, candidate: Path) -> bool:
    resolved_root = root.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=True)
    return resolved_candidate != resolved_root and resolved_root in resolved_candidate.parents


def _existing_public_file(
    workspace: Path,
    value: object,
    label: str,
    allowed_prefixes: Iterable[str],
) -> tuple[Path, str] | None:
    if value is None:
        return None
    target, location = _safe_relative(workspace, value, label)
    if not any(location.startswith(prefix) for prefix in allowed_prefixes):
        raise ContractError(f"Invalid {label}: location is not a public artifact")
    try:
        resolved = target.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None
    root = workspace.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        return None
    return resolved, location


def _asset_identity(entry: dict[str, Any]) -> tuple[str, str]:
    asset_id = entry.get("asset_id")
    sha256 = entry.get("sha256")
    if not isinstance(asset_id, str) or not isinstance(sha256, str):
        raise ContractError("Invalid asset catalog: asset identity is missing")
    if not _SHA256.fullmatch(sha256) or asset_id != f"sha256:{sha256}":
        raise ContractError(f"Invalid asset identity: {asset_id}")
    return asset_id, sha256


def _metadata(workspace: Path, entry: dict[str, Any], asset_id: str) -> dict[str, Any]:
    location = entry.get("metadata_location")
    if location is None:
        return {}
    try:
        target, _ = _safe_relative(workspace, location, f"metadata_location for {asset_id}")
        if not str(PurePosixPath(location)).startswith("metadata/assets/"):
            return {}
        return _read_json(target, f"asset metadata for {asset_id}")
    except ContractError:
        return {}


def _source_name(entry: dict[str, Any]) -> str:
    sources = entry.get("sources")
    if not isinstance(sources, list):
        return "Unknown source"
    active = sorted(
        source.get("relative_path")
        for source in sources
        if isinstance(source, dict)
        and source.get("status") == "active"
        and isinstance(source.get("relative_path"), str)
    )
    candidates = active or sorted(
        source.get("relative_path")
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("relative_path"), str)
    )
    return candidates[0] if candidates else "Unknown source"


def _original(
    source_root_value: object,
    entry: dict[str, Any],
    sha256: str,
) -> Artifact | None:
    if not isinstance(source_root_value, str) or not source_root_value:
        return None
    source_root = Path(source_root_value)
    if not source_root.is_absolute():
        return None
    root = source_root.resolve(strict=False)
    sources = entry.get("sources")
    if not isinstance(sources, list):
        return None
    active: list[tuple[str, str]] = []
    for source in sources:
        if not isinstance(source, dict) or source.get("status") != "active":
            continue
        relative = source.get("relative_path")
        version = source.get("source_version_id")
        if isinstance(relative, str) and isinstance(version, str):
            active.append((relative, version))
    for relative, _version in sorted(active):
        try:
            if "\\" in relative:
                continue
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts:
                continue
            candidate = root.joinpath(*pure.parts).resolve(strict=True)
            if root not in candidate.parents or not candidate.is_file():
                continue
        except (OSError, RuntimeError):
            continue
        return Artifact(
            token=f"original-{sha256}",
            path=candidate,
            authorization_root=root,
            media_type=str(entry.get("mime_type") or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"),
            kind="original",
        )
    return None


def _valid_keyframes(
    workspace: Path,
    workspace_id: str,
    contract_version: int,
    asset_id: str,
    sha256: str,
) -> list[tuple[str, list[dict[str, Any]]]]:
    root = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1"
    candidates = sorted(root.glob(f"*/{sha256[:2]}/{sha256}.json")) if root.is_dir() else []
    valid: list[tuple[str, list[dict[str, Any]]]] = []
    for candidate in candidates:
        fingerprint = candidate.parents[1].name
        if not _SHA256.fullmatch(fingerprint):
            continue
        try:
            resolved = candidate.resolve(strict=True)
            if root.resolve(strict=True) not in resolved.parents or not _inside(workspace, resolved):
                continue
            payload = _read_json(resolved, "video keyframe result")
        except (ContractError, OSError):
            continue
        result = payload.get("result")
        keyframes = result.get("keyframes") if isinstance(result, dict) else None
        if not (
            payload.get("result_schema_version") == 1
            and payload.get("workspace_contract_version") == contract_version
            and payload.get("workspace_id") == workspace_id
            and payload.get("asset_id") == asset_id
            and payload.get("sha256") == sha256
            and payload.get("processor") == {"name": "video-keyframes", "version": "video-keyframes-v1"}
            and payload.get("configuration_fingerprint") == fingerprint
            and payload.get("status") == "success"
            and isinstance(keyframes, list)
            and keyframes
        ):
            continue
        selected: list[dict[str, Any]] = []
        expected = candidate.with_suffix("") / "keyframes"
        for item in keyframes:
            if not isinstance(item, dict):
                selected = []
                break
            keyframe_id = item.get("keyframe_id")
            if (
                not isinstance(keyframe_id, str)
                or not _KEYFRAME_ID.fullmatch(keyframe_id)
                or item.get("source_video_asset_id") != asset_id
                or item.get("source_video_sha256") != sha256
                or item.get("configuration_fingerprint") != fingerprint
            ):
                selected = []
                break
            try:
                image, location = _safe_relative(workspace, item.get("location"), "keyframe location")
                image = image.resolve(strict=True)
                if (
                    expected.resolve(strict=True) not in image.parents
                    or not _inside(workspace, image)
                    or not image.is_file()
                ):
                    selected = []
                    break
            except (ContractError, OSError):
                selected = []
                break
            selected.append({"path": image, "location": location, "keyframe_id": keyframe_id})
        if selected:
            valid.append((fingerprint, selected))
    return valid


def _preview(
    workspace: Path,
    workspace_id: str,
    version: int,
    entry: dict[str, Any],
    asset_id: str,
    sha256: str,
    requested_fingerprint: str | None,
) -> tuple[Artifact | None, str]:
    if entry.get("media_type") == "image":
        try:
            found = _existing_public_file(
                workspace,
                entry.get("preview_location"),
                f"preview_location for {asset_id}",
                ("previews/images/",),
            )
        except ContractError:
            return None, "Invalid preview path"
        if found is None:
            return None, "Preview missing"
        path, _location = found
        return Artifact(f"preview-{sha256}", path, workspace, "image/jpeg", "preview"), "Preview available"
    valid = _valid_keyframes(workspace, workspace_id, version, asset_id, sha256)
    if requested_fingerprint:
        valid = [item for item in valid if item[0] == requested_fingerprint]
    if len(valid) > 1:
        return None, "Multiple keyframe configurations; select one explicitly"
    if not valid:
        return None, "No compatible completed keyframe result"
    fingerprint, keyframes = valid[0]
    first = keyframes[0]
    return (
        Artifact(
            f"keyframe-{sha256}-{fingerprint}-{first['keyframe_id']}",
            first["path"],
            workspace,
            "image/jpeg",
            "keyframe",
        ),
        f"Video keyframe · {fingerprint[:12]}",
    )


def _processor_results(
    workspace: Path,
    workspace_id: str,
    version: int,
    asset_id: str,
    sha256: str,
    name: str,
    processor_version: str,
) -> list[ProcessorResult]:
    root = workspace / "analysis" / name / processor_version
    if not root.is_dir():
        return []
    patterns = [
        f"*/{sha256[:2]}/{sha256}/image-preview.json",
        f"*/{sha256[:2]}/{sha256}/video-keyframes/*/keyframe-*.json",
    ]
    found: list[ProcessorResult] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            try:
                resolved = path.resolve(strict=True)
                if root.resolve(strict=True) not in resolved.parents or not _inside(workspace, resolved):
                    continue
                payload = _read_json(resolved, f"{name} result")
            except (ContractError, OSError):
                continue
            fingerprint = path.relative_to(root).parts[0]
            result = payload.get("result")
            if not (
                _SHA256.fullmatch(fingerprint)
                and payload.get("result_schema_version") == 1
                and payload.get("workspace_contract_version") == version
                and payload.get("workspace_id") == workspace_id
                and payload.get("asset_id") == asset_id
                and payload.get("sha256") == sha256
                and payload.get("processor") == {"name": name, "version": processor_version}
                and payload.get("configuration_fingerprint") == fingerprint
                and payload.get("status") == "success"
                and isinstance(result, dict)
            ):
                continue
            found.append(
                ProcessorResult(
                    processor=name,
                    version=processor_version,
                    configuration_fingerprint=fingerprint,
                    model=payload.get("model"),
                    created_at=payload.get("created_at") if isinstance(payload.get("created_at"), str) else None,
                    result=result,
                )
            )
    return found


def _apply_sessions(snapshot_assets: dict[str, Asset], workspace: Path, workspace_id: str) -> None:
    root = workspace / "analysis" / "session-grouper" / "session-grouper-v1"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*.json")):
        try:
            resolved = path.resolve(strict=True)
            if root.resolve(strict=True) not in resolved.parents or not _inside(workspace, resolved):
                continue
            payload = _read_json(resolved, "session result")
        except (ContractError, OSError):
            continue
        fingerprint = path.parent.name
        result = payload.get("result")
        sessions = result.get("sessions") if isinstance(result, dict) else None
        if not (
            _SHA256.fullmatch(fingerprint)
            and payload.get("result_schema_version") == 1
            and payload.get("workspace_contract_version") == 1
            and payload.get("workspace_id") == workspace_id
            and payload.get("processor") == {"name": "session-grouper", "version": "session-grouper-v1"}
            and payload.get("configuration_fingerprint") == fingerprint
            and payload.get("status") == "success"
            and isinstance(sessions, list)
        ):
            continue
        for session in sessions:
            if not isinstance(session, dict) or not isinstance(session.get("assets"), list):
                continue
            reference = SessionReference(
                session_id=str(session.get("session_id") or "session"),
                start=session.get("start") if isinstance(session.get("start"), str) else None,
                end=session.get("end") if isinstance(session.get("end"), str) else None,
                confidence=session.get("confidence") if isinstance(session.get("confidence"), str) else None,
                configuration_fingerprint=fingerprint,
            )
            for member in session["assets"]:
                asset = snapshot_assets.get(member.get("asset_id")) if isinstance(member, dict) else None
                if asset is not None:
                    asset.sessions.append(reference)


def _apply_face_clusters(snapshot_assets: dict[str, Asset], workspace: Path, workspace_id: str) -> None:
    root = workspace / "analysis" / "faces" / "faces-clustering-v1"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*.json")):
        try:
            resolved = path.resolve(strict=True)
            if root.resolve(strict=True) not in resolved.parents or not _inside(workspace, resolved):
                continue
            payload = _read_json(resolved, "face clustering result")
        except (ContractError, OSError):
            continue
        fingerprint = path.parent.name
        result = payload.get("result")
        clusters = result.get("clusters") if isinstance(result, dict) else None
        if not (
            _SHA256.fullmatch(fingerprint)
            and payload.get("result_schema_version") == 1
            and payload.get("workspace_contract_version") == 1
            and payload.get("workspace_id") == workspace_id
            and payload.get("processor") == {"name": "faces-clustering", "version": "faces-clustering-v1"}
            and payload.get("configuration_fingerprint") == fingerprint
            and payload.get("status") == "success"
            and isinstance(clusters, list)
        ):
            continue
        for cluster in clusters:
            if not isinstance(cluster, dict) or not isinstance(cluster.get("members"), list):
                continue
            member_count = cluster.get("member_count")
            if isinstance(member_count, bool) or not isinstance(member_count, int):
                member_count = len(cluster["members"])
            reference = FaceClusterReference(
                cluster_id=str(cluster.get("cluster_id") or "anonymous-cluster"),
                status=str(cluster.get("status") or "unknown"),
                member_count=member_count,
                configuration_fingerprint=fingerprint,
            )
            for member in cluster["members"]:
                asset = snapshot_assets.get(member.get("asset_id")) if isinstance(member, dict) else None
                if asset is not None and reference not in asset.face_clusters:
                    asset.face_clusters.append(reference)


def load_workspace(
    workspace_path: Path,
    keyframe_fingerprint: str | None = None,
) -> WorkspaceSnapshot:
    if keyframe_fingerprint is not None and not _SHA256.fullmatch(keyframe_fingerprint):
        raise ContractError("Keyframe fingerprint must be 64 lowercase hexadecimal characters")
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
    catalog_path, _ = _safe_relative(workspace, manifest.get("asset_catalog"), "asset_catalog")
    catalog = _read_json(catalog_path, "asset catalog")
    if catalog.get("workspace_contract_version") != version:
        raise ContractError("Asset catalog contract version does not match workspace.json")
    if catalog.get("workspace_id") != workspace_id:
        raise ContractError("Asset catalog workspace_id does not match workspace.json")
    entries = catalog.get("assets")
    if not isinstance(entries, list):
        raise ContractError("Invalid asset catalog: assets must be an array")
    source_root = catalog.get("source_root")
    if not isinstance(source_root, str) or not source_root or not (
        PurePosixPath(source_root).is_absolute() or PureWindowsPath(source_root).is_absolute()
    ):
        raise ContractError("Invalid asset catalog: source_root must be an absolute path")

    assets: list[Asset] = []
    artifacts: dict[str, Artifact] = {}
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractError("Invalid asset catalog: asset entry must be an object")
        missing = sorted(_REQUIRED_ASSET_FIELDS - entry.keys())
        if missing:
            raise ContractError(f"Invalid asset catalog: missing fields {', '.join(missing)}")
        asset_id, sha256 = _asset_identity(entry)
        if asset_id in seen:
            raise ContractError(f"Invalid asset catalog: duplicate asset_id {asset_id}")
        seen.add(asset_id)
        media_type = entry.get("media_type")
        availability = entry.get("availability")
        if media_type not in {"image", "video"} or availability not in {"available", "unavailable"}:
            raise ContractError(f"Invalid catalog values for {asset_id}")
        if (
            isinstance(entry.get("size_bytes"), bool)
            or not isinstance(entry.get("size_bytes"), int)
            or entry["size_bytes"] < 0
        ):
            raise ContractError(f"Invalid size_bytes for {asset_id}")
        if not isinstance(entry.get("format"), str) or not isinstance(entry.get("mime_type"), str):
            raise ContractError(f"Invalid media facts for {asset_id}")
        if not isinstance(entry.get("sources"), list):
            raise ContractError(f"Invalid sources for {asset_id}: expected an array")
        if entry.get("metadata_location") is not None and not isinstance(entry.get("metadata_location"), str):
            raise ContractError(f"Invalid metadata_location for {asset_id}")
        if entry.get("preview_location") is not None and not isinstance(entry.get("preview_location"), str):
            raise ContractError(f"Invalid preview_location for {asset_id}")
        metadata = _metadata(workspace, entry, asset_id)
        capture = metadata.get("capture") if isinstance(metadata.get("capture"), dict) else {}
        technical = metadata.get("technical") if isinstance(metadata.get("technical"), dict) else {}
        preview, preview_status = _preview(
            workspace, workspace_id, version, entry, asset_id, sha256, keyframe_fingerprint
        )
        original = _original(source_root, entry, sha256) if availability == "available" else None
        asset = Asset(
            asset_id=asset_id,
            sha256=sha256,
            media_type=media_type,
            format=str(entry.get("format") or "Unknown"),
            mime_type=str(entry.get("mime_type") or "application/octet-stream"),
            size_bytes=entry["size_bytes"],
            availability=availability,
            source_name=_source_name(entry),
            capture_time=capture.get("datetime") if isinstance(capture.get("datetime"), str) else None,
            capture_source=capture.get("source") if isinstance(capture.get("source"), str) else None,
            technical=technical,
            preview=preview,
            preview_status=preview_status,
            original=original,
        )
        asset.vision.extend(
            _processor_results(workspace, workspace_id, version, asset_id, sha256, "vision", "vision-v1")
        )
        asset.faces.extend(
            _processor_results(workspace, workspace_id, version, asset_id, sha256, "faces", "faces-v1")
        )
        for artifact in (preview, original):
            if artifact is not None:
                artifacts[artifact.token] = artifact
        assets.append(asset)

    by_id = {asset.asset_id: asset for asset in assets}
    _apply_sessions(by_id, workspace, workspace_id)
    _apply_face_clusters(by_id, workspace, workspace_id)
    assets.sort(key=lambda asset: ((asset.capture_time or ""), asset.asset_id), reverse=True)
    return WorkspaceSnapshot(
        root=workspace,
        workspace_id=workspace_id,
        contract_version=version,
        generated_at=catalog.get("generated_at") if isinstance(catalog.get("generated_at"), str) else None,
        assets=tuple(assets),
        artifacts=artifacts,
        keyframe_fingerprint=keyframe_fingerprint,
    )
