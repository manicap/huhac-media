from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any, Callable

from normalizer import (
    MANIFEST_SCHEMA_VERSION,
    PROCESSOR_NAME,
    PROCESSOR_VERSION,
    RESULT_SCHEMA_VERSION,
)
from normalizer.contract import load_workspace, load_workspace_header
from normalizer.fingerprint import configuration_fingerprint, input_set_fingerprint
from normalizer.models import AnalysisResult, NormalizerConfig, PreparedRun
from normalizer.normalize import normalize_asset
from normalizer.project import project_upstream
from normalizer.upstream import blocking_ambiguities, load_upstream
from normalizer.output import (
    OutputError,
    created_at_utc,
    namespace_size,
    publish_snapshot,
    reusable_manifest,
    snapshot_path,
    validate_snapshot,
)
from normalizer.schema import validate_normalized_asset


_SHA256 = re.compile(r"[0-9a-f]{64}")


def prepare_workspace(
    workspace_path: Path, config: NormalizerConfig | None = None
) -> PreparedRun:
    config = config or NormalizerConfig()
    config.validate()
    workspace = load_workspace(workspace_path)
    selected_assets = tuple(
        asset
        for asset in workspace.assets
        if config.include_unavailable_assets
        or asset.catalog["availability"] == "available"
    )
    if selected_assets != workspace.assets:
        workspace = type(workspace)(
            workspace=workspace.workspace,
            workspace_id=workspace.workspace_id,
            contract_version=workspace.contract_version,
            manifest_location=workspace.manifest_location,
            manifest_semantic=workspace.manifest_semantic,
            catalog_location=workspace.catalog_location,
            catalog_semantic={
                **workspace.catalog_semantic,
                "assets": [
                    entry for entry in workspace.catalog_semantic["assets"]
                    if entry["asset_id"] in {asset.asset_id for asset in selected_assets}
                ],
            },
            catalog_generated_at=workspace.catalog_generated_at,
            catalog_run_id=workspace.catalog_run_id,
            assets=selected_assets,
        )
    upstream, upstream_semantic = load_upstream(workspace, config)
    workspace = type(workspace)(
        workspace=workspace.workspace,
        workspace_id=workspace.workspace_id,
        contract_version=workspace.contract_version,
        manifest_location=workspace.manifest_location,
        manifest_semantic=workspace.manifest_semantic,
        catalog_location=workspace.catalog_location,
        catalog_semantic=workspace.catalog_semantic,
        catalog_generated_at=workspace.catalog_generated_at,
        catalog_run_id=workspace.catalog_run_id,
        assets=workspace.assets,
        upstream=upstream,
        upstream_semantic=upstream_semantic,
    )
    config_hash = configuration_fingerprint(config)
    input_hash = input_set_fingerprint(workspace)
    target = snapshot_path(workspace, config_hash, input_hash)
    existing = reusable_manifest(target, workspace, config_hash, input_hash)
    return PreparedRun(workspace, config, config_hash, input_hash, target, existing is not None)


def plan_report(prepared: PreparedRun) -> dict[str, Any]:
    issues = [
        {
            "asset_id": issue.asset_id,
            "code": issue.code,
            "message": issue.message,
            "location": issue.location,
        }
        for asset in prepared.workspace.assets
        for issue in asset.issues
    ]
    types = Counter(asset.catalog["media_type"] for asset in prepared.workspace.assets)
    upstream_statuses: dict[str, Any] = {
        "session_grouper": prepared.workspace.upstream["session_grouper"]["status"],
        "video_keyframes": Counter(
            item["status"] for item in prepared.workspace.upstream["video_keyframes"].values()
        ),
        "vision": Counter(item["status"] for records in prepared.workspace.upstream["vision"].values() for item in records),
        "faces": Counter(item["status"] for records in prepared.workspace.upstream["faces"].values() for item in records),
        "faces_clustering": prepared.workspace.upstream["faces_clustering"]["status"],
    }
    return {
        "workspace": str(prepared.workspace.workspace),
        "workspace_id": prepared.workspace.workspace_id,
        "workspace_contract_version": prepared.workspace.contract_version,
        "source_contracts": [
            prepared.workspace.manifest_location,
            prepared.workspace.catalog_location,
            "metadata/assets/<sha-prefix>/<sha256>.json",
        ],
        "configuration": prepared.config.as_dict(),
        "configuration_fingerprint": prepared.configuration_fingerprint,
        "input_set_fingerprint": prepared.input_set_fingerprint,
        "output": str(prepared.output_path),
        "asset_count": len(prepared.workspace.assets),
        "image_count": types["image"],
        "video_count": types["video"],
        "input_issue_count": len(issues),
        "issues": issues,
        "upstream_selection": prepared.config.upstream_selection(),
        "upstream_statuses": {
            key: dict(value) if isinstance(value, Counter) else value
            for key, value in upstream_statuses.items()
        },
        "upstream_expected_inputs": {
            "session_grouper": 1 if prepared.config.session_configuration_fingerprint else 0,
            "video_keyframes": len(prepared.workspace.upstream["video_keyframes"]),
            "vision": sum(len(value) for value in prepared.workspace.upstream["vision"].values()),
            "faces": sum(len(value) for value in prepared.workspace.upstream["faces"].values()),
            "faces_clustering": 1 if prepared.config.faces_clustering_configuration_fingerprint else 0,
        },
        "blocking_ambiguities": blocking_ambiguities(prepared.workspace.upstream),
        "reusable": prepared.reusable,
        "read_only": True,
    }


def analyze_prepared(
    prepared: PreparedRun,
    *,
    stage_hook: Callable[[str, Path], None] | None = None,
) -> AnalysisResult:
    ambiguities = blocking_ambiguities(prepared.workspace.upstream)
    if ambiguities:
        raise ValueError(
            "Ambiguous upstream selection; provide an explicit logical input fingerprint for: "
            + ", ".join(ambiguities)
        )
    if prepared.reusable:
        manifest = validate_snapshot(
            prepared.output_path,
            workspace_id=prepared.workspace.workspace_id,
            configuration_fingerprint=prepared.configuration_fingerprint,
            input_set_fingerprint=prepared.input_set_fingerprint,
        )
        return AnalysisResult(prepared, manifest, reused=True)

    created_at = created_at_utc()
    payloads: list[dict[str, Any]] = []
    warning_count = invalid_count = missing_count = unavailable_count = 0
    input_issue_count = 0
    conflict_count = 0
    analysis_status_counts: dict[str, Counter[str]] = {}
    analyzed_asset_count = 0
    for asset in prepared.workspace.assets:
        result = project_upstream(
            normalize_asset(asset), asset, prepared.workspace.upstream, prepared.config
        )
        errors = validate_normalized_asset(result)
        if errors:
            raise OutputError(
                f"Internal NormalizedAsset validation failed for {asset.asset_id}: "
                + "; ".join(errors)
            )
        completeness = result["completeness"]
        warning_count += len(completeness["warnings"])
        invalid_count += len(completeness["invalid_values"])
        missing_count += len(completeness["missing_fields"])
        unavailable_count += not completeness["source_available"]
        conflict_count += len(completeness["conflicts"])
        asset_has_analysis = False
        for name, analysis in completeness["analyses"].items():
            analysis_status_counts.setdefault(name, Counter())[analysis["status"]] += 1
            asset_has_analysis = asset_has_analysis or analysis["status"] in {
                "success_nonempty", "success_empty", "failed", "invalid", "ambiguous"
            }
        analyzed_asset_count += asset_has_analysis
        input_issue_count += len(asset.issues)
        payloads.append(
            {
                "result_schema_version": RESULT_SCHEMA_VERSION,
                "workspace_contract_version": prepared.workspace.contract_version,
                "workspace_id": prepared.workspace.workspace_id,
                "asset_id": asset.asset_id,
                "sha256": asset.sha256,
                "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
                "model": None,
                "configuration_fingerprint": prepared.configuration_fingerprint,
                "input_set_fingerprint": prepared.input_set_fingerprint,
                "created_at": created_at,
                "status": "success",
                "error": None,
                "result": result,
            }
        )
    summary = {
        "asset_count": len(payloads),
        "input_issue_count": input_issue_count,
        "warning_count": warning_count,
        "invalid_value_count": invalid_count,
        "missing_field_count": missing_count,
        "unavailable_asset_count": unavailable_count,
        "conflict_count": conflict_count,
        "analyzed_asset_count": analyzed_asset_count,
        "unprocessed_asset_count": len(payloads) - analyzed_asset_count,
        "analysis_status_counts": {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(analysis_status_counts.items())
        },
    }
    manifest_base = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "workspace_contract_version": prepared.workspace.contract_version,
        "workspace_id": prepared.workspace.workspace_id,
        "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
        "model": None,
        "configuration": prepared.config.as_dict(),
        "configuration_fingerprint": prepared.configuration_fingerprint,
        "input_set_fingerprint": prepared.input_set_fingerprint,
        "input": {
            "workspace_manifest": prepared.workspace.manifest_location,
            "asset_catalog": prepared.workspace.catalog_location,
            "catalog_generated_at": prepared.workspace.catalog_generated_at,
            "catalog_run_id": prepared.workspace.catalog_run_id,
        },
        "created_at": created_at,
        "status": "success",
        "error": None,
        "summary": summary,
    }
    kwargs = {} if stage_hook is None else {"stage_hook": stage_hook}
    manifest = publish_snapshot(
        prepared.output_path, payloads, manifest_base, **kwargs
    )
    return AnalysisResult(prepared, manifest, reused=False)


def analyze_workspace(
    workspace_path: Path, config: NormalizerConfig | None = None
) -> AnalysisResult:
    return analyze_prepared(prepare_workspace(workspace_path, config))


def inspect_status(workspace_path: Path) -> dict[str, Any]:
    workspace, manifest = load_workspace_header(workspace_path)
    workspace_id = manifest["workspace_id"]
    root = workspace / "analysis" / PROCESSOR_NAME / PROCESSOR_VERSION
    snapshots: list[dict[str, Any]] = []
    if root.is_dir():
        resolved_root = root.resolve(strict=True)
        resolved_workspace = workspace.resolve(strict=True)
        if resolved_workspace not in resolved_root.parents:
            raise OutputError("Normalizer namespace escapes the workspace")
        for config_dir in sorted(root.iterdir(), key=lambda path: path.name):
            if (
                config_dir.is_symlink()
                or not config_dir.is_dir()
                or not _SHA256.fullmatch(config_dir.name)
            ):
                continue
            for input_dir in sorted(config_dir.iterdir(), key=lambda path: path.name):
                if (
                    input_dir.is_symlink()
                    or not input_dir.is_dir()
                    or not _SHA256.fullmatch(input_dir.name)
                ):
                    continue
                record: dict[str, Any] = {
                    "configuration_fingerprint": config_dir.name,
                    "input_set_fingerprint": input_dir.name,
                    "path": str(input_dir),
                }
                try:
                    valid = validate_snapshot(
                        input_dir,
                        workspace_id=workspace_id,
                        configuration_fingerprint=config_dir.name,
                        input_set_fingerprint=input_dir.name,
                    )
                    record.update(
                        valid=True,
                        asset_count=valid["summary"]["asset_count"],
                        analyzed_asset_count=valid["summary"].get("analyzed_asset_count", 0),
                        unprocessed_asset_count=valid["summary"].get(
                            "unprocessed_asset_count", valid["summary"]["asset_count"]
                        ),
                        conflict_count=valid["summary"].get("conflict_count", 0),
                        analysis_status_counts=valid["summary"].get("analysis_status_counts", {}),
                        created_at=valid.get("created_at"),
                    )
                except OutputError as exc:
                    record.update(valid=False, error=str(exc))
                snapshots.append(record)
    return {
        "workspace": str(workspace),
        "workspace_id": workspace_id,
        "namespace": str(root),
        "snapshot_count": len(snapshots),
        "valid_snapshot_count": sum(item["valid"] for item in snapshots),
        "invalid_snapshot_count": sum(not item["valid"] for item in snapshots),
        "historical_result_count": len(snapshots),
        "analyzed_asset_count": sum(item.get("analyzed_asset_count", 0) for item in snapshots if item["valid"]),
        "unprocessed_asset_count": sum(item.get("unprocessed_asset_count", 0) for item in snapshots if item["valid"]),
        "conflict_count": sum(item.get("conflict_count", 0) for item in snapshots if item["valid"]),
        "size_bytes": namespace_size(root),
        "snapshots": snapshots,
        "read_only": True,
    }
