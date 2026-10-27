from __future__ import annotations

from typing import Any


RESULT_SECTIONS = {
    "identity",
    "technical",
    "temporal",
    "semantic",
    "people",
    "event",
    "quality",
    "provenance",
    "completeness",
}

ANALYSIS_STATUSES = {
    "success_nonempty", "success_empty", "not_analyzed", "failed",
    "not_applicable", "input_unavailable", "ambiguous", "invalid", "unknown",
}


def validate_normalized_asset(result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["$: expected object"]
    missing = RESULT_SECTIONS - result.keys()
    extra = result.keys() - RESULT_SECTIONS
    errors.extend(f"$.{key}: missing required field" for key in sorted(missing))
    errors.extend(f"$.{key}: unexpected field" for key in sorted(extra))
    identity = result.get("identity")
    required_identity = {
        "asset_id", "sha256", "media_type", "size_bytes", "format", "mime_type",
        "availability", "sources",
    }
    if not isinstance(identity, dict):
        errors.append("$.identity: expected object")
    else:
        for key in sorted(required_identity - identity.keys()):
            errors.append(f"$.identity.{key}: missing required field")
        if identity.get("media_type") not in {"image", "video"}:
            errors.append("$.identity.media_type: expected image or video")
        if identity.get("availability") not in {"available", "unavailable"}:
            errors.append("$.identity.availability: expected available or unavailable")
        if not isinstance(identity.get("sources"), list):
            errors.append("$.identity.sources: expected array")
    technical = result.get("technical")
    if not isinstance(technical, dict) or set(technical) != {"common", "image", "video"}:
        errors.append("$.technical: expected common, image and video")
    temporal = result.get("temporal")
    capture = temporal.get("capture") if isinstance(temporal, dict) else None
    if not isinstance(capture, dict) or set(capture) != {
        "datetime", "source", "timezone_offset", "filesystem_fallback", "quality"
    }:
        errors.append("$.temporal.capture: invalid capture object")
    elif capture.get("quality") not in {
        "source_timestamp", "filesystem_fallback", "missing"
    }:
        errors.append("$.temporal.capture.quality: invalid value")
    if not isinstance(temporal, dict) or not isinstance(temporal.get("session_candidates"), list):
        errors.append("$.temporal.session_candidates: expected array")
    semantic = result.get("semantic")
    if not isinstance(semantic, dict) or semantic.get("status") not in ANALYSIS_STATUSES:
        errors.append("$.semantic.status: invalid analysis status")
    elif not isinstance(semantic.get("observations"), list) or not isinstance(semantic.get("facets"), dict):
        errors.append("$.semantic: observations/facets have invalid shape")
    people = result.get("people")
    if not isinstance(people, dict) or people.get("status") not in ANALYSIS_STATUSES:
        errors.append("$.people.status: invalid analysis status")
    elif any(not isinstance(people.get(key), list) for key in (
        "face_observations", "anonymous_cluster_refs", "vision_people_observations"
    )):
        errors.append("$.people: observation fields must be arrays")
    completeness = result.get("completeness")
    required_completeness = {
        "source_available", "analyses", "missing_fields", "invalid_values",
        "conflicts", "warnings",
    }
    if not isinstance(completeness, dict):
        errors.append("$.completeness: expected object")
    else:
        for key in sorted(required_completeness - completeness.keys()):
            errors.append(f"$.completeness.{key}: missing required field")
        for key in ("missing_fields", "invalid_values", "conflicts", "warnings"):
            if key in completeness and not isinstance(completeness[key], list):
                errors.append(f"$.completeness.{key}: expected array")
        analyses = completeness.get("analyses")
        if not isinstance(analyses, dict):
            errors.append("$.completeness.analyses: expected object")
        else:
            for name, analysis in analyses.items():
                if not isinstance(analysis, dict) or analysis.get("status") not in ANALYSIS_STATUSES:
                    errors.append(f"$.completeness.analyses.{name}.status: invalid value")
    provenance = result.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(
        provenance.get("field_sources"), dict
    ):
        errors.append("$.provenance.field_sources: expected object")
    return errors
