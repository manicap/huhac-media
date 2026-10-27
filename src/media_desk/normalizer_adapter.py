from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from media_desk.models import NormalizerSnapshotStatus, WorkspaceSnapshot


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROCESSOR = {"name": "normalizer", "version": "normalizer-v1"}
_FACETS = ("activities", "objects", "environment", "visual_attributes", "tags")
_RESULT_SECTIONS = {
    "identity", "technical", "temporal", "semantic", "people", "event",
    "quality", "provenance", "completeness",
}
_ANALYSIS_STATUSES = {
    "success_nonempty", "success_empty", "not_analyzed", "failed",
    "not_applicable", "input_unavailable", "ambiguous", "invalid", "unknown",
}
_INPUT_ISSUE_CODES = {
    "MISSING_METADATA_DOCUMENT", "INVALID_METADATA_DOCUMENT",
    "INVALID_METADATA_SCHEMA", "METADATA_IDENTITY_MISMATCH",
}


class _StaleSnapshot(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _configuration_fingerprint(configuration: object) -> str:
    if not isinstance(configuration, dict):
        raise ValueError("invalid Normalizer configuration")
    expected = {
        "normalization_rules", "safe_conversion_policy", "include_unavailable_assets",
        "result_schema_version", "session_configuration_fingerprint",
        "session_logical_input_fingerprint", "keyframes_configuration_fingerprint",
        "vision_configuration_fingerprint", "faces_configuration_fingerprint",
        "faces_clustering_configuration_fingerprint",
        "faces_clustering_logical_input_fingerprint",
    }
    if set(configuration) != expected:
        raise ValueError("unsupported Normalizer configuration shape")
    rules = configuration.get("normalization_rules")
    if rules not in {"normalized-asset-n1", "normalized-asset-n2"}:
        raise ValueError("unsupported normalization rules")
    if configuration.get("safe_conversion_policy") != "safe-scalars-v1" or configuration.get("result_schema_version") != 1:
        raise ValueError("unsupported Normalizer policy or schema")
    fingerprint_fields = sorted(key for key in expected if key.endswith("_fingerprint"))
    if any(value is not None and not _SHA256.fullmatch(value) for key in fingerprint_fields
           for value in [configuration.get(key)]):
        raise ValueError("invalid upstream fingerprint")
    processor = {"name": "normalizer", "version": "normalizer-v1"}
    if rules == "normalized-asset-n1":
        selected = {key: value for key, value in configuration.items() if not key.endswith("_fingerprint")}
        value = {"processor": processor, "workspace_contract_version": 1,
                 "configuration": selected,
                 "future_upstream_selection": {"session_grouper": None, "video_keyframes": None,
                                                "vision": None, "faces": None}}
    else:
        value = {"processor": processor, "workspace_contract_version": 1,
                 "configuration": configuration,
                 "upstream_selection": {
                     "session_grouper": {"configuration_fingerprint": configuration["session_configuration_fingerprint"],
                                         "logical_input_fingerprint": configuration["session_logical_input_fingerprint"]},
                     "video_keyframes": {"configuration_fingerprint": configuration["keyframes_configuration_fingerprint"]},
                     "vision": {"configuration_fingerprint": configuration["vision_configuration_fingerprint"]},
                     "faces": {"configuration_fingerprint": configuration["faces_configuration_fingerprint"]},
                     "faces_clustering": {"configuration_fingerprint": configuration["faces_clustering_configuration_fingerprint"],
                                          "logical_input_fingerprint": configuration["faces_clustering_logical_input_fingerprint"]},
                 }}
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _validate_result(result: object, asset_id: str, sha256: str) -> dict[str, Any]:
    if not isinstance(result, dict) or set(result) != _RESULT_SECTIONS:
        raise ValueError("invalid NormalizedAsset result sections")
    identity = result.get("identity")
    if not isinstance(identity, dict) or identity.get("asset_id") != asset_id or identity.get("sha256") != sha256:
        raise ValueError("NormalizedAsset result identity mismatch")
    if identity.get("media_type") not in {"image", "video"} or identity.get("availability") not in {"available", "unavailable"}:
        raise ValueError("invalid NormalizedAsset identity values")
    technical = result.get("technical")
    if not isinstance(technical, dict) or set(technical) != {"common", "image", "video"}:
        raise ValueError("invalid NormalizedAsset technical section")
    temporal = result.get("temporal")
    if not isinstance(temporal, dict) or not isinstance(temporal.get("session_candidates"), list):
        raise ValueError("invalid NormalizedAsset temporal section")
    semantic = result.get("semantic")
    if not isinstance(semantic, dict) or semantic.get("status") not in _ANALYSIS_STATUSES:
        raise ValueError("invalid NormalizedAsset semantic status")
    if not isinstance(semantic.get("observations"), list) or not isinstance(semantic.get("facets"), dict):
        raise ValueError("invalid NormalizedAsset semantic section")
    for facet in _FACETS:
        values = semantic["facets"].get(facet)
        if not isinstance(values, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("value"), str)
            for item in values
        ):
            raise ValueError(f"invalid semantic facet: {facet}")
    people = result.get("people")
    if not isinstance(people, dict) or people.get("status") not in _ANALYSIS_STATUSES:
        raise ValueError("invalid NormalizedAsset people status")
    for field in ("face_observations", "anonymous_cluster_refs", "vision_people_observations"):
        if not isinstance(people.get(field), list):
            raise ValueError(f"invalid NormalizedAsset people field: {field}")
    provenance = result.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("field_sources"), dict):
        raise ValueError("invalid NormalizedAsset provenance")
    completeness = result.get("completeness")
    if not isinstance(completeness, dict) or not isinstance(completeness.get("source_available"), bool):
        raise ValueError("invalid NormalizedAsset completeness")
    analyses = completeness.get("analyses")
    if not isinstance(analyses, dict) or any(
        not isinstance(value, dict) or value.get("status") not in _ANALYSIS_STATUSES
        for value in analyses.values()
    ):
        raise ValueError("invalid NormalizedAsset analysis completeness")
    for field in ("missing_fields", "invalid_values", "conflicts", "warnings"):
        if not isinstance(completeness.get(field), list):
            raise ValueError(f"invalid NormalizedAsset completeness field: {field}")
    return result


def _empty_summary(extended: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "asset_count": 0, "input_issue_count": 0, "warning_count": 0,
        "invalid_value_count": 0, "missing_field_count": 0,
        "unavailable_asset_count": 0,
    }
    if extended:
        summary.update(
            conflict_count=0, analyzed_asset_count=0, unprocessed_asset_count=0,
            analysis_status_counts={},
        )
    return summary


def _add_summary(summary: dict[str, Any], result: dict[str, Any], extended: bool) -> None:
    completeness = result["completeness"]
    summary["asset_count"] += 1
    summary["warning_count"] += len(completeness["warnings"])
    summary["invalid_value_count"] += len(completeness["invalid_values"])
    summary["missing_field_count"] += len(completeness["missing_fields"])
    summary["unavailable_asset_count"] += not completeness["source_available"]
    summary["input_issue_count"] += sum(
        isinstance(item, dict) and item.get("code") in _INPUT_ISSUE_CODES
        for item in completeness["warnings"]
    )
    if not extended:
        return
    has_analysis = False
    for name, analysis in completeness["analyses"].items():
        statuses = summary["analysis_status_counts"].setdefault(name, {})
        status = analysis["status"]
        statuses[status] = statuses.get(status, 0) + 1
        has_analysis = has_analysis or status in {
            "success_nonempty", "success_empty", "failed", "invalid", "ambiguous",
        }
    summary["analyzed_asset_count"] += has_analysis
    summary["conflict_count"] += len(completeness["conflicts"])


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    completeness = result["completeness"]
    return {
        "identity": result["identity"],
        "semantic": {
            "status": result["semantic"]["status"],
            "facets": result["semantic"]["facets"],
        },
        "people": {
            "status": result["people"]["status"],
            "detected_face_count": result["people"].get("detected_face_count"),
        },
        "event": result["event"],
        "completeness": {
            "source_available": completeness["source_available"],
            "analyses": completeness["analyses"],
            "warning_count": len(completeness["warnings"]),
        },
    }


def _safe_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("invalid result location")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("result location escapes snapshot")
    target = root.joinpath(relative)
    if target.is_symlink():
        raise ValueError("symlinked result is not allowed")
    resolved = target.resolve(strict=True)
    if not _inside(root.resolve(strict=True), resolved) or not resolved.is_file():
        raise ValueError("result is outside snapshot")
    return resolved


def _status(state: str, message: str, config: str | None, input_set: str | None,
            *, summary: dict[str, Any] | None = None, diagnostics: list[str] | None = None):
    return NormalizerSnapshotStatus(
        state, message, config, input_set, summary or {}, tuple(diagnostics or ())
    )


def attach_normalizer_snapshot(
    snapshot: WorkspaceSnapshot,
    configuration_fingerprint: str | None,
    input_set_fingerprint: str | None,
) -> WorkspaceSnapshot:
    """Attach one explicitly selected public Normalizer snapshot, read-only."""
    if configuration_fingerprint is None and input_set_fingerprint is None:
        state = _status("not_configured", "Normalizer snapshot is not configured.", None, None)
        return replace(snapshot, normalizer=state)
    if not _SHA256.fullmatch(configuration_fingerprint or ""):
        state = _status("invalid_selection", "A Normalizer configuration fingerprint must be 64 lowercase hex characters.",
                        configuration_fingerprint, input_set_fingerprint)
        return replace(snapshot, normalizer=state)
    root = snapshot.root / "analysis" / "normalizer" / "normalizer-v1"
    if input_set_fingerprint is None:
        config_root = root / configuration_fingerprint
        try:
            candidates = sorted(
                item.name for item in config_root.iterdir()
                if item.is_dir() and not item.is_symlink() and _SHA256.fullmatch(item.name)
            )
        except (FileNotFoundError, OSError):
            candidates = []
        if len(candidates) != 1:
            state_name = "ambiguous" if len(candidates) > 1 else "missing"
            state = _status(state_name, "Normalizer input-set selection is ambiguous." if candidates else "No Normalizer input-set snapshot exists for the selected configuration.",
                            configuration_fingerprint, None,
                            diagnostics=[f"candidate_count={len(candidates)}"])
            return replace(snapshot, normalizer=state)
        input_set_fingerprint = candidates[0]
    if not _SHA256.fullmatch(input_set_fingerprint):
        state = _status("invalid_selection", "Normalizer input-set fingerprint must be 64 lowercase hex characters.",
                        configuration_fingerprint, input_set_fingerprint)
        return replace(snapshot, normalizer=state)
    selected = root / configuration_fingerprint / input_set_fingerprint
    try:
        if root.is_symlink() or selected.is_symlink():
            raise ValueError("symlinked Normalizer namespace is not allowed")
        root_resolved = root.resolve(strict=True)
        selected_resolved = selected.resolve(strict=True)
        if not selected_resolved.is_dir() or not _inside(root_resolved, selected_resolved):
            raise ValueError("selected snapshot escapes Normalizer namespace")
    except FileNotFoundError:
        state = _status("missing", "The selected Normalizer snapshot does not exist.",
                        configuration_fingerprint, input_set_fingerprint)
        return replace(snapshot, normalizer=state)
    except (OSError, ValueError) as exc:
        state = _status("invalid", "The selected Normalizer snapshot is unsafe or unreadable.",
                        configuration_fingerprint, input_set_fingerprint, diagnostics=[str(exc)])
        return replace(snapshot, normalizer=state)

    try:
        manifest_path = _safe_file(selected_resolved, "manifest.json")
        manifest = _read_json(manifest_path)
        if not (
            manifest.get("manifest_schema_version") == 1
            and manifest.get("workspace_contract_version") == snapshot.contract_version
            and manifest.get("workspace_id") == snapshot.workspace_id
            and manifest.get("processor") == _PROCESSOR
            and manifest.get("model") is None
            and manifest.get("status") == "success"
            and manifest.get("error") is None
            and manifest.get("configuration_fingerprint") == configuration_fingerprint
            and manifest.get("input_set_fingerprint") == input_set_fingerprint
            and isinstance(manifest.get("assets"), list)
            and isinstance(manifest.get("summary"), dict)
        ):
            if (manifest.get("workspace_id") != snapshot.workspace_id or
                    manifest.get("workspace_contract_version") != snapshot.contract_version):
                raise _StaleSnapshot("manifest workspace identity is stale")
            raise ValueError("manifest identity or envelope mismatch")
        if _configuration_fingerprint(manifest.get("configuration")) != configuration_fingerprint:
            raise ValueError("manifest configuration fingerprint is inconsistent")
        assets_by_id = {asset.asset_id: asset for asset in snapshot.assets}
        if len(manifest["assets"]) != len(assets_by_id) or manifest["summary"].get("asset_count") != len(assets_by_id):
            raise _StaleSnapshot("manifest asset count does not match Media Desk catalog")
        seen: set[str] = set()
        loaded: dict[str, tuple[dict[str, Any], bytes]] = {}
        extended_summary = "analysis_status_counts" in manifest["summary"]
        computed_summary = _empty_summary(extended_summary)
        for record in manifest["assets"]:
            if not isinstance(record, dict):
                raise ValueError("invalid manifest asset record")
            asset_id, sha256 = record.get("asset_id"), record.get("sha256")
            asset = assets_by_id.get(asset_id)
            if asset is None or asset.sha256 != sha256 or asset_id in seen:
                raise _StaleSnapshot("asset identity/hash does not match Media Desk catalog")
            path = _safe_file(selected_resolved, record.get("location"))
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != record.get("content_sha256"):
                raise ValueError("asset result content hash mismatch")
            payload = json.loads(content)
            result = payload.get("result") if isinstance(payload, dict) else None
            if not (
                payload.get("result_schema_version") == 1
                and payload.get("workspace_contract_version") == snapshot.contract_version
                and payload.get("workspace_id") == snapshot.workspace_id
                and payload.get("asset_id") == asset_id
                and payload.get("sha256") == sha256
                and payload.get("processor") == _PROCESSOR
                and payload.get("model") is None
                and payload.get("configuration_fingerprint") == configuration_fingerprint
                and payload.get("input_set_fingerprint") == input_set_fingerprint
                and payload.get("status") == "success"
                and payload.get("error") is None
            ):
                raise ValueError("invalid NormalizedAsset envelope")
            result = _validate_result(result, asset_id, sha256)
            _add_summary(computed_summary, result, extended_summary)
            loaded[asset_id] = (_compact_result(result), content)
            seen.add(asset_id)
        if seen != set(assets_by_id):
            raise _StaleSnapshot("Normalizer snapshot does not cover the exact catalog")
        if extended_summary:
            computed_summary["unprocessed_asset_count"] = (
                computed_summary["asset_count"] - computed_summary["analyzed_asset_count"]
            )
            computed_summary["analysis_status_counts"] = {
                name: dict(sorted(counts.items()))
                for name, counts in sorted(computed_summary["analysis_status_counts"].items())
            }
        if manifest["summary"] != computed_summary:
            raise ValueError("Normalizer manifest summary does not match asset results")
    except _StaleSnapshot as exc:
        state = _status("stale", "The selected Normalizer snapshot does not match the active workspace catalog.",
                        configuration_fingerprint, input_set_fingerprint, diagnostics=[str(exc)])
        return replace(snapshot, normalizer=state)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        state = _status("invalid", "The selected Normalizer snapshot failed validation.",
                        configuration_fingerprint, input_set_fingerprint, diagnostics=[str(exc)])
        return replace(snapshot, normalizer=state)

    for asset in snapshot.assets:
        compact, content = loaded[asset.asset_id]
        asset.normalized = compact
        asset.normalized_payload = content
    state = _status("available", "Selected Normalizer snapshot is loaded.",
                    configuration_fingerprint, input_set_fingerprint, summary=manifest["summary"])
    return replace(snapshot, normalizer=state)
