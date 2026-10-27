from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Callable

from normalizer import (
    MANIFEST_SCHEMA_VERSION,
    PROCESSOR_NAME,
    PROCESSOR_VERSION,
    RESULT_SCHEMA_VERSION,
)
from normalizer.fingerprint import configuration_fingerprint as compute_configuration_fingerprint
from normalizer.models import NormalizerConfig, WorkspaceInput
from normalizer.schema import validate_normalized_asset


class OutputError(RuntimeError):
    pass


_SHA256 = re.compile(r"[0-9a-f]{64}")


def snapshot_path(
    workspace: WorkspaceInput, configuration_fingerprint: str, input_fingerprint: str
) -> Path:
    target = (
        workspace.workspace
        / "analysis"
        / PROCESSOR_NAME
        / PROCESSOR_VERSION
        / configuration_fingerprint
        / input_fingerprint
    ).resolve(strict=False)
    root = workspace.workspace.resolve(strict=True)
    if root not in target.parents:
        raise OutputError("Normalizer output path escapes the workspace")
    return target


def _render_json(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _safe_snapshot_file(snapshot: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise OutputError(f"Invalid {label}: expected relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise OutputError(f"Invalid {label}: path escapes snapshot")
    target = snapshot.joinpath(*pure.parts)
    try:
        resolved_snapshot = snapshot.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
    except OSError as exc:
        raise OutputError(f"Missing {label}: {target}") from exc
    if resolved_snapshot not in resolved_target.parents or not resolved_target.is_file():
        raise OutputError(f"Invalid {label}: path escapes snapshot")
    return resolved_target


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputError(f"Invalid {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OutputError(f"Invalid {label}: expected object")
    return payload


def validate_snapshot(
    target: Path,
    *,
    workspace_id: str | None = None,
    configuration_fingerprint: str | None = None,
    input_set_fingerprint: str | None = None,
) -> dict[str, Any]:
    if not target.is_dir():
        raise OutputError(f"Snapshot does not exist: {target}")
    manifest_path = _safe_snapshot_file(target, "manifest.json", "Normalizer manifest")
    manifest = _read_object(manifest_path, "Normalizer manifest")
    expected_processor = {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
    valid = (
        manifest.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION
        and manifest.get("workspace_contract_version") == 1
        and manifest.get("processor") == expected_processor
        and manifest.get("model") is None
        and manifest.get("status") == "success"
        and manifest.get("error") is None
        and isinstance(manifest.get("configuration"), dict)
        and isinstance(manifest.get("configuration_fingerprint"), str)
        and isinstance(manifest.get("input_set_fingerprint"), str)
        and isinstance(manifest.get("assets"), list)
        and isinstance(manifest.get("summary"), dict)
    )
    if not valid:
        raise OutputError(f"Invalid Normalizer manifest: {target / 'manifest.json'}")
    try:
        stored_config = NormalizerConfig(**manifest["configuration"])
        stored_config.validate()
    except (TypeError, ValueError) as exc:
        raise OutputError("Invalid Normalizer manifest configuration") from exc
    if compute_configuration_fingerprint(stored_config) != manifest["configuration_fingerprint"]:
        raise OutputError("Normalizer manifest configuration fingerprint is inconsistent")
    if workspace_id is not None and manifest.get("workspace_id") != workspace_id:
        raise OutputError("Normalizer manifest workspace_id mismatch")
    if (
        configuration_fingerprint is not None
        and manifest.get("configuration_fingerprint") != configuration_fingerprint
    ):
        raise OutputError("Normalizer manifest configuration fingerprint mismatch")
    if (
        input_set_fingerprint is not None
        and manifest.get("input_set_fingerprint") != input_set_fingerprint
    ):
        raise OutputError("Normalizer manifest input fingerprint mismatch")
    if manifest["summary"].get("asset_count") != len(manifest["assets"]):
        raise OutputError("Normalizer manifest asset count mismatch")

    seen: set[str] = set()
    computed_summary = {
        "asset_count": 0,
        "input_issue_count": 0,
        "warning_count": 0,
        "invalid_value_count": 0,
        "missing_field_count": 0,
        "unavailable_asset_count": 0,
    }
    extended_summary = "analysis_status_counts" in manifest["summary"]
    if extended_summary:
        computed_summary.update(
            conflict_count=0,
            analyzed_asset_count=0,
            unprocessed_asset_count=0,
            analysis_status_counts={},
        )
    input_issue_codes = {
        "MISSING_METADATA_DOCUMENT",
        "INVALID_METADATA_DOCUMENT",
        "INVALID_METADATA_SCHEMA",
        "METADATA_IDENTITY_MISMATCH",
    }
    for record in manifest["assets"]:
        if not isinstance(record, dict):
            raise OutputError("Invalid Normalizer manifest asset record")
        asset_id = record.get("asset_id")
        sha256 = record.get("sha256")
        digest = record.get("content_sha256")
        if (
            not isinstance(asset_id, str)
            or not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
            or asset_id != f"sha256:{sha256}"
            or asset_id in seen
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise OutputError("Invalid Normalizer manifest asset identity/hash")
        path = _safe_snapshot_file(target, record.get("location"), "asset result")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise OutputError(f"Normalizer asset hash mismatch: {path}")
        payload = _read_object(path, "NormalizedAsset result")
        result = payload.get("result")
        if not (
            payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
            and payload.get("workspace_contract_version") == 1
            and payload.get("workspace_id") == manifest.get("workspace_id")
            and payload.get("asset_id") == asset_id
            and payload.get("sha256") == sha256
            and payload.get("processor") == expected_processor
            and payload.get("model") is None
            and payload.get("configuration_fingerprint")
            == manifest.get("configuration_fingerprint")
            and payload.get("input_set_fingerprint")
            == manifest.get("input_set_fingerprint")
            and payload.get("status") == "success"
            and payload.get("error") is None
            and isinstance(result, dict)
            and isinstance(result.get("identity"), dict)
            and result["identity"].get("asset_id") == asset_id
            and result["identity"].get("sha256") == sha256
            and not validate_normalized_asset(result)
        ):
            raise OutputError(f"Invalid NormalizedAsset envelope: {path}")
        completeness = result["completeness"]
        computed_summary["asset_count"] += 1
        computed_summary["warning_count"] += len(completeness["warnings"])
        computed_summary["invalid_value_count"] += len(completeness["invalid_values"])
        computed_summary["missing_field_count"] += len(completeness["missing_fields"])
        computed_summary["unavailable_asset_count"] += not completeness["source_available"]
        computed_summary["input_issue_count"] += sum(
            item.get("code") in input_issue_codes
            for item in completeness["warnings"]
            if isinstance(item, dict)
        )
        if extended_summary:
            computed_summary["conflict_count"] += len(completeness["conflicts"])
            asset_has_analysis = False
            for name, analysis in completeness["analyses"].items():
                statuses = computed_summary["analysis_status_counts"].setdefault(name, {})
                status = analysis["status"]
                statuses[status] = statuses.get(status, 0) + 1
                asset_has_analysis = asset_has_analysis or status in {
                    "success_nonempty", "success_empty", "failed", "invalid", "ambiguous"
                }
            computed_summary["analyzed_asset_count"] += asset_has_analysis
        seen.add(asset_id)
    if extended_summary:
        computed_summary["unprocessed_asset_count"] = (
            computed_summary["asset_count"] - computed_summary["analyzed_asset_count"]
        )
    if manifest["summary"] != computed_summary:
        raise OutputError("Normalizer manifest summary does not match asset results")
    return manifest


def reusable_manifest(
    target: Path,
    workspace: WorkspaceInput,
    config_fingerprint: str,
    input_fingerprint: str,
) -> dict[str, Any] | None:
    if not target.exists():
        return None
    try:
        return validate_snapshot(
            target,
            workspace_id=workspace.workspace_id,
            configuration_fingerprint=config_fingerprint,
            input_set_fingerprint=input_fingerprint,
        )
    except OutputError as exc:
        raise OutputError(
            "Existing Normalizer snapshot conflicts with its immutable fingerprint: "
            f"{target}: {exc}"
        ) from exc


def _default_stage_hook(stage: str, path: Path) -> None:
    return None


def publish_snapshot(
    target: Path,
    asset_payloads: list[dict[str, Any]],
    manifest_base: dict[str, Any],
    *,
    stage_hook: Callable[[str, Path], None] = _default_stage_hook,
) -> dict[str, Any]:
    if target.exists():
        raise OutputError(f"Refusing to overwrite immutable snapshot: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    )
    records: list[dict[str, str]] = []
    try:
        for payload in sorted(asset_payloads, key=lambda item: item["sha256"]):
            sha256 = payload["sha256"]
            location = PurePosixPath("assets") / sha256[:2] / f"{sha256}.json"
            path = staging.joinpath(*location.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            content = _render_json(payload)
            with path.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            records.append(
                {
                    "asset_id": payload["asset_id"],
                    "sha256": sha256,
                    "location": location.as_posix(),
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        stage_hook("assets_written", staging)
        manifest = {**manifest_base, "assets": records}
        manifest_path = staging / "manifest.json"
        content = _render_json(manifest)
        with manifest_path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        stage_hook("manifest_written", staging)
        if target.exists():
            raise OutputError(f"Snapshot appeared concurrently: {target}")
        stage_hook("before_publish", staging)
        os.replace(staging, target)
        return validate_snapshot(
            target,
            workspace_id=manifest["workspace_id"],
            configuration_fingerprint=manifest["configuration_fingerprint"],
            input_set_fingerprint=manifest["input_set_fingerprint"],
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def created_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def namespace_size(root: Path) -> int:
    if not root.is_dir():
        return 0
    resolved_root = root.resolve(strict=True)
    total = 0
    for directory, names, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        names[:] = [
            name for name in names if not (directory_path / name).is_symlink()
        ]
        for name in files:
            path = directory_path / name
            try:
                resolved = path.resolve(strict=True)
                if resolved_root in resolved.parents and resolved.is_file():
                    total += resolved.stat().st_size
            except OSError:
                continue
    return total
