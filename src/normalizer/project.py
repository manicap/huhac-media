from __future__ import annotations

from collections import defaultdict
from typing import Any

from normalizer.models import AssetInput, NormalizerConfig


_FACETS = ("activities", "objects", "environment", "visual_attributes", "tags")
_FAILURE_PRIORITY = ("invalid", "ambiguous", "failed", "input_unavailable", "unknown")


def _aggregate(records: list[dict[str, Any]]) -> str:
    if not records:
        return "input_unavailable"
    statuses = {record.get("status", "unknown") for record in records}
    for status in _FAILURE_PRIORITY:
        if status in statuses:
            return status
    return "success_nonempty" if "success_nonempty" in statuses else "success_empty"


def _analysis(status: str, records: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"status": status}
    if records is not None:
        value["expected_input_count"] = len(records)
        value["input_statuses"] = [
            {
                "input_kind": item.get("input", {}).get("kind"),
                "input_id": item.get("input", {}).get("input_id"),
                "status": item.get("status", "unknown"),
                "source_document": item.get("location"),
                "issue": item.get("issue"),
            }
            for item in records
        ]
    value.update(extra)
    return value


def _session_projection(result: dict[str, Any], asset: AssetInput, upstream: dict[str, Any], config: NormalizerConfig) -> None:
    source = upstream["session_grouper"]
    status = source["status"]
    analysis = _analysis(status, source.get("records"),
                         configuration_fingerprint=config.session_configuration_fingerprint,
                         logical_input_fingerprint=config.session_logical_input_fingerprint)
    selected = source.get("selected")
    payload = selected.get("payload") if isinstance(selected, dict) else None
    if status in {"success_empty", "success_nonempty"} and isinstance(payload, dict):
        logical = payload.get("input", {}).get("logical_fingerprint")
        analysis["logical_input_fingerprint"] = logical
        projected: list[dict[str, Any]] = []
        for session in payload["result"]["sessions"]:
            if not isinstance(session, dict) or not isinstance(session.get("assets"), list):
                status = "invalid"
                break
            for member in session["assets"]:
                if isinstance(member, dict) and member.get("asset_id") == asset.asset_id:
                    projected.append({
                        "session_id": session.get("session_id"),
                        "start": session.get("start"), "end": session.get("end"),
                        "operational_day": session.get("operational_day"),
                        "boundary_reason": session.get("boundary_reason"),
                        "confidence": session.get("confidence"),
                        "assignment_confidence": member.get("assignment_confidence"),
                        "assignment_reason": member.get("assignment_reason"),
                        "timestamp": member.get("timestamp"),
                        "provenance": {
                            "source_document": selected["location"],
                            "processor": {"name": "session-grouper", "version": "session-grouper-v1"},
                            "configuration_fingerprint": config.session_configuration_fingerprint,
                            "logical_input_fingerprint": logical,
                        },
                    })
        unassigned = next((item for item in payload["result"]["unassigned"]
                           if isinstance(item, dict) and item.get("asset_id") == asset.asset_id), None)
        if status == "invalid":
            analysis["status"] = "invalid"
        elif projected:
            result["temporal"]["session_candidates"] = projected
            analysis["status"] = "success_nonempty"
        elif unassigned is not None:
            analysis.update(status="success_empty", unassigned_reason=unassigned.get("reason"),
                            timestamp=unassigned.get("timestamp"))
        else:
            analysis["status"] = "invalid"
            analysis["issue"] = "asset missing from both sessions and unassigned"
    result["completeness"]["analyses"]["session_grouper"] = analysis


def _keyframe_projection(result: dict[str, Any], asset: AssetInput, upstream: dict[str, Any], config: NormalizerConfig) -> None:
    if asset.catalog["media_type"] != "video":
        analysis = _analysis("not_applicable")
    elif config.keyframes_configuration_fingerprint is None:
        analysis = _analysis("not_analyzed")
    else:
        record = upstream["video_keyframes"].get(asset.asset_id)
        analysis = _analysis(record.get("status", "unknown") if record else "input_unavailable",
                             [record] if record else [],
                             configuration_fingerprint=config.keyframes_configuration_fingerprint,
                             keyframe_count=len(record.get("inputs", [])) if record else 0)
    result["completeness"]["analyses"]["video_keyframes"] = analysis


def _vision_projection(result: dict[str, Any], asset: AssetInput, upstream: dict[str, Any], config: NormalizerConfig) -> None:
    if config.vision_configuration_fingerprint is None:
        result["semantic"].update(status="not_analyzed", observations=[])
        result["completeness"]["analyses"]["vision"] = _analysis("not_analyzed")
        return
    records = upstream["vision"].get(asset.asset_id, [])
    status = _aggregate(records)
    observations: list[dict[str, Any]] = []
    facet_sources: dict[str, dict[str, list[dict[str, Any]]]] = {
        field: defaultdict(list) for field in _FACETS
    }
    people: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") != "success_nonempty":
            continue
        payload = record["payload"]
        vision = payload["result"]["vision"]
        input_value = record["input"]
        observation_id = f"vision:{input_value['kind']}:{input_value['input_id']}"
        provenance = {
            "source_document": record["location"],
            "processor": {"name": "vision", "version": "vision-v1"},
            "model": payload.get("model"),
            "configuration_fingerprint": config.vision_configuration_fingerprint,
        }
        observation = {
            "observation_id": observation_id,
            "input_kind": input_value["kind"], "input_id": input_value["input_id"],
            "keyframe_timestamp_s": input_value.get("timestamp_s"),
            "vision_configuration_fingerprint": config.vision_configuration_fingerprint,
            "keyframes_configuration_fingerprint": input_value.get("provenance", {}).get("video_keyframe_configuration_fingerprint"),
            **vision, "provenance": provenance,
        }
        observations.append(observation)
        people.append({
            "input_kind": input_value["kind"], "input_id": input_value["input_id"],
            "keyframe_timestamp_s": input_value.get("timestamp_s"),
            "approx_count": vision["people"]["approx_count"], "crowd": vision["people"]["crowd"],
            "provenance": provenance,
        })
        for field in _FACETS:
            for value in vision[field]:
                display = value.strip()
                if display:
                    source = {
                        "observation_id": observation_id,
                        "source_document": record["location"],
                        "source_pointer": f"/result/vision/{field}",
                    }
                    if source not in facet_sources[field][display.casefold()]:
                        facet_sources[field][display.casefold()].append(source)
    facets: dict[str, list[dict[str, Any]]] = {}
    for field in _FACETS:
        values = []
        for key, sources in facet_sources[field].items():
            displays = sorted(
                {value.strip() for observation in observations for value in observation[field]
                 if value.strip().casefold() == key}, key=lambda item: (item.casefold(), item)
            )
            values.append({"key": key, "value": displays[0],
                           "provenance": sorted(sources, key=lambda item: (item["observation_id"], item["source_document"]))})
        facets[field] = sorted(values, key=lambda item: (item["key"], item["value"]))
    observations.sort(key=lambda item: (item["input_kind"], item["input_id"]))
    people.sort(key=lambda item: (item["input_kind"], item["input_id"]))
    result["semantic"].update(status=status, observations=observations, facets=facets)
    result["people"]["vision_people_observations"] = people
    result["completeness"]["analyses"]["vision"] = _analysis(
        status, records, configuration_fingerprint=config.vision_configuration_fingerprint
    )


def _faces_projection(result: dict[str, Any], asset: AssetInput, upstream: dict[str, Any], config: NormalizerConfig) -> None:
    if config.faces_configuration_fingerprint is None:
        result["people"]["status"] = "not_analyzed"
        result["completeness"]["analyses"]["faces"] = _analysis("not_analyzed")
        result["completeness"]["analyses"]["faces_clustering"] = _analysis("not_analyzed")
        return
    records = upstream["faces"].get(asset.asset_id, [])
    status = _aggregate(records)
    observations: list[dict[str, Any]] = []
    for record in records:
        if record.get("status") not in {"success_empty", "success_nonempty"}:
            continue
        payload = record["payload"]
        input_value = record["input"]
        faces = payload["result"]["faces"]
        observations.append({
            "input_kind": input_value["kind"], "input_id": input_value["input_id"],
            "keyframe_timestamp_s": input_value.get("timestamp_s"),
            "detected_face_count": len(faces),
            "detector_confidences": [face["confidence"] for face in faces],
            "faces_configuration_fingerprint": config.faces_configuration_fingerprint,
            "keyframes_configuration_fingerprint": input_value.get("provenance", {}).get("video_keyframe_configuration_fingerprint"),
            "face_refs": [face["face_id"] for face in faces],
            "provenance": {"source_document": record["location"],
                           "processor": {"name": "faces", "version": "faces-v1"},
                           "model": payload.get("model"),
                           "configuration_fingerprint": config.faces_configuration_fingerprint},
        })
    observations.sort(key=lambda item: (item["input_kind"], item["input_id"]))
    result["people"]["status"] = status
    result["people"]["face_observations"] = observations
    result["people"]["detected_face_count"] = (
        observations[0]["detected_face_count"]
        if asset.catalog["media_type"] == "image" and len(observations) == 1 else None
    )
    result["completeness"]["analyses"]["faces"] = _analysis(
        status, records, configuration_fingerprint=config.faces_configuration_fingerprint
    )

    cluster = upstream["faces_clustering"]
    cluster_status = cluster["status"]
    refs: list[dict[str, Any]] = []
    selected = cluster.get("selected")
    payload = selected.get("payload") if isinstance(selected, dict) else None
    if cluster_status in {"success_empty", "success_nonempty"} and isinstance(payload, dict):
        for item in payload["result"]["clusters"]:
            for member in item["members"]:
                if member.get("asset_id") == asset.asset_id:
                    refs.append({
                        "cluster_id": item["cluster_id"], "cluster_status": item["status"],
                        "input_kind": member.get("input_kind"), "input_id": member.get("input_id"),
                        "face_id": member.get("face_id"),
                        "provenance": {"source_document": selected["location"],
                                       "processor": {"name": "faces-clustering", "version": "faces-clustering-v1"},
                                       "configuration_fingerprint": config.faces_clustering_configuration_fingerprint,
                                       "logical_input_fingerprint": payload.get("logical_input_fingerprint")},
                    })
    result["people"]["anonymous_cluster_refs"] = sorted(
        refs, key=lambda item: (item["cluster_id"], item["input_kind"], item["input_id"], item["face_id"])
    )
    result["completeness"]["analyses"]["faces_clustering"] = _analysis(
        cluster_status, cluster.get("records"),
        configuration_fingerprint=config.faces_clustering_configuration_fingerprint,
        logical_input_fingerprint=(payload or {}).get("logical_input_fingerprint") if isinstance(payload, dict) else config.faces_clustering_logical_input_fingerprint,
    )


def _warnings(result: dict[str, Any]) -> None:
    for name, analysis in result["completeness"]["analyses"].items():
        if analysis["status"] in {"failed", "input_unavailable", "ambiguous", "invalid", "unknown"}:
            result["completeness"]["warnings"].append({
                "code": f"{name.upper()}_{analysis['status'].upper()}",
                "target": f"/completeness/analyses/{name}",
                "reason": analysis.get("issue") or f"{name} status is {analysis['status']}",
            })
    result["completeness"]["warnings"].sort(key=lambda item: (item["code"], item.get("target", "")))


def project_upstream(result: dict[str, Any], asset: AssetInput, upstream: dict[str, Any], config: NormalizerConfig) -> dict[str, Any]:
    _session_projection(result, asset, upstream, config)
    _keyframe_projection(result, asset, upstream, config)
    _vision_projection(result, asset, upstream, config)
    _faces_projection(result, asset, upstream, config)
    _warnings(result)
    return result
