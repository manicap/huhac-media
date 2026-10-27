from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any

from normalizer.contract import ContractError
from normalizer.fingerprint import canonical_sha256
from normalizer.models import AssetInput, NormalizerConfig, WorkspaceInput


_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEYFRAME_ID = re.compile(r"keyframe-[0-9]{4}")
_FACE_ID = re.compile(r"face-[0-9]{4}")
_VISION_FIELDS = {
    "scene", "people", "activities", "objects", "environment",
    "visual_attributes", "tags", "description",
}
_FACET_FIELDS = ("activities", "objects", "environment", "visual_attributes", "tags")


def _relative(workspace: Path, value: object) -> tuple[Path, str] | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    target = workspace.joinpath(*pure.parts).resolve(strict=False)
    root = workspace.resolve(strict=True)
    if root not in target.parents:
        return None
    return target, pure.as_posix()


def _document(path: Path, workspace: Path) -> dict[str, Any]:
    location = path.relative_to(workspace).as_posix()
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        return {"status": "input_unavailable", "location": location, "payload": None,
                "semantic": {"location": location, "sentinel": "missing"}}
    except OSError as exc:
        return {"status": "input_unavailable", "location": location, "payload": None,
                "issue": str(exc), "semantic": {"location": location, "sentinel": "unreadable"}}
    digest = hashlib.sha256(content).hexdigest()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "location": location, "payload": None,
                "issue": f"invalid JSON: {exc}",
                "semantic": {"location": location, "content_sha256": digest, "sentinel": "invalid_json"}}
    if not isinstance(payload, dict):
        return {"status": "invalid", "location": location, "payload": None,
                "issue": "expected a JSON object",
                "semantic": {"location": location, "content_sha256": digest, "sentinel": "invalid_object"}}
    return {"status": "loaded", "location": location, "payload": payload,
            "semantic": {"location": location, "content_sha256": digest}}


def _configuration_valid(payload: dict[str, Any], fingerprint: str) -> bool:
    configuration = payload.get("configuration")
    return isinstance(configuration, dict) and canonical_sha256(configuration) == fingerprint


def _envelope_valid(
    payload: dict[str, Any], workspace: WorkspaceInput, *, name: str, version: str,
    fingerprint: str, asset: AssetInput | None = None,
) -> bool:
    valid = (
        payload.get("result_schema_version") == 1
        and payload.get("workspace_contract_version") == workspace.contract_version
        and payload.get("workspace_id") == workspace.workspace_id
        and payload.get("processor") == {"name": name, "version": version}
        and payload.get("configuration_fingerprint") == fingerprint
        and _configuration_valid(payload, fingerprint)
        and payload.get("status") in {"success", "failed"}
    )
    if asset is not None:
        valid = valid and payload.get("asset_id") == asset.asset_id and payload.get("sha256") == asset.sha256
    return bool(valid)


def _invalidate(record: dict[str, Any], issue: str) -> dict[str, Any]:
    record["status"] = "invalid"
    record["issue"] = issue
    record["payload"] = None
    record["semantic"]["sentinel"] = "invalid_contract"
    return record


def _session(workspace: WorkspaceInput, config: NormalizerConfig) -> dict[str, Any]:
    fingerprint = config.session_configuration_fingerprint
    logical = config.session_logical_input_fingerprint
    if fingerprint is None:
        return {"status": "not_analyzed", "records": [], "semantic": {"sentinel": "disabled"}}
    root = workspace.workspace / "analysis" / "session-grouper" / "session-grouper-v1" / fingerprint
    paths = [root / f"{logical}.json"] if logical else (
        sorted(path for path in root.glob("*.json") if path.is_file() and not path.is_symlink())
        if root.is_dir() else []
    )
    if not paths:
        missing = root / f"{logical}.json" if logical else root / "<logical-input>.json"
        rec = _document(missing, workspace.workspace)
        return {"status": "input_unavailable", "records": [rec], "semantic": rec["semantic"]}
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for path in paths:
        rec = _document(path, workspace.workspace)
        payload = rec.get("payload")
        expected_logical = path.stem
        if payload is None:
            (invalid if rec["status"] == "invalid" else valid).append(rec)
        elif not _envelope_valid(
            payload, workspace, name="session-grouper", version="session-grouper-v1", fingerprint=fingerprint
        ) or not isinstance(payload.get("input"), dict) or payload["input"].get("logical_fingerprint") != expected_logical:
            invalid.append(_invalidate(rec, "Session Grouper envelope/provenance mismatch"))
        elif payload.get("status") == "failed":
            rec["status"] = "failed"
            valid.append(rec)
        elif not isinstance(payload.get("result"), dict) or not isinstance(payload["result"].get("sessions"), list) or not isinstance(payload["result"].get("unassigned"), list):
            invalid.append(_invalidate(rec, "Invalid Session Grouper result schema"))
        else:
            rec["status"] = "success_nonempty" if payload["result"]["sessions"] else "success_empty"
            valid.append(rec)
    if logical:
        chosen = valid[0] if valid else invalid[0]
        return {"status": chosen["status"], "records": [chosen], "selected": chosen,
                "semantic": chosen["semantic"]}
    if len(valid) > 1:
        semantic = [item["semantic"] for item in valid + invalid]
        return {"status": "ambiguous", "records": valid + invalid,
                "issue": "Multiple Session Grouper logical inputs match the selected configuration",
                "semantic": {"candidates": semantic, "sentinel": "ambiguous"}}
    chosen = valid[0] if valid else invalid[0]
    return {"status": chosen["status"], "records": valid + invalid, "selected": chosen,
            "semantic": chosen["semantic"]}


def _keyframe_record(workspace: WorkspaceInput, asset: AssetInput, fingerprint: str) -> dict[str, Any]:
    path = workspace.workspace / "analysis" / "video-keyframes" / "video-keyframes-v1" / fingerprint / asset.sha256[:2] / f"{asset.sha256}.json"
    rec = _document(path, workspace.workspace)
    payload = rec.get("payload")
    if payload is None:
        return rec
    if not _envelope_valid(payload, workspace, name="video-keyframes", version="video-keyframes-v1", fingerprint=fingerprint, asset=asset) or not isinstance(payload.get("model"), dict):
        return _invalidate(rec, "Video Keyframes envelope/model provenance mismatch")
    if payload.get("status") == "failed":
        rec["status"] = "failed"
        return rec
    result = payload.get("result")
    frames = result.get("keyframes") if isinstance(result, dict) else None
    if not isinstance(frames, list) or not frames:
        return _invalidate(rec, "Successful Video Keyframes result requires keyframes")
    expected_dir = path.with_suffix("") / "keyframes"
    seen: set[str] = set()
    inputs: list[dict[str, Any]] = []
    for frame in frames:
        keyframe_id = frame.get("keyframe_id") if isinstance(frame, dict) else None
        timestamp = frame.get("timestamp_s") if isinstance(frame, dict) else None
        location = _relative(workspace.workspace, frame.get("location") if isinstance(frame, dict) else None)
        if (
            not isinstance(frame, dict) or not isinstance(keyframe_id, str)
            or not _KEYFRAME_ID.fullmatch(keyframe_id) or keyframe_id in seen
            or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
            or not math.isfinite(float(timestamp)) or timestamp < 0
            or frame.get("source_video_asset_id") != asset.asset_id
            or frame.get("source_video_sha256") != asset.sha256
            or frame.get("processor") != {"name": "video-keyframes", "version": "video-keyframes-v1"}
            or frame.get("configuration_fingerprint") != fingerprint
            or not isinstance(frame.get("model"), dict) or location is None
            or expected_dir.resolve(strict=False) not in location[0].parents or not location[0].is_file()
        ):
            return _invalidate(rec, "Invalid keyframe identity, timestamp, provenance, or reference")
        seen.add(keyframe_id)
        provenance = {
            "kind": "video_keyframe", "asset_id": asset.asset_id, "sha256": asset.sha256,
            "keyframe_id": keyframe_id, "location": location[1], "timestamp_s": timestamp,
            "video_keyframe_processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
            "video_keyframe_configuration_fingerprint": fingerprint,
        }
        inputs.append({"kind": "video_keyframe", "input_id": keyframe_id,
                       "timestamp_s": timestamp, "provenance": provenance})
    rec["status"] = "success_nonempty"
    rec["inputs"] = sorted(inputs, key=lambda item: item["input_id"])
    return rec


def _image_input(workspace: WorkspaceInput, asset: AssetInput) -> dict[str, Any] | None:
    location = _relative(workspace.workspace, asset.catalog.get("preview_location"))
    if location is None or not location[0].is_file():
        return None
    return {"kind": "image_preview", "input_id": "image-preview", "timestamp_s": None,
            "provenance": {"kind": "image_preview", "asset_id": asset.asset_id,
                           "sha256": asset.sha256, "location": location[1]}}


def _vision_schema(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != _VISION_FIELDS:
        return False
    if not isinstance(value["scene"], str) or not isinstance(value["description"], str):
        return False
    people = value["people"]
    if not isinstance(people, dict) or set(people) != {"approx_count", "crowd"}:
        return False
    count = people["approx_count"]
    if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
        return False
    if not isinstance(people["crowd"], bool):
        return False
    return all(isinstance(value[field], list) and all(isinstance(item, str) for item in value[field]) for field in _FACET_FIELDS)


def _analysis_record(
    workspace: WorkspaceInput, asset: AssetInput, fingerprint: str, processor: str,
    visual_input: dict[str, Any],
) -> dict[str, Any]:
    base = workspace.workspace / "analysis" / processor / f"{processor}-v1" / fingerprint / asset.sha256[:2] / asset.sha256
    if visual_input["kind"] == "image_preview":
        path = base / "image-preview.json"
    else:
        kf = visual_input["provenance"]["video_keyframe_configuration_fingerprint"]
        path = base / "video-keyframes" / kf / f"{visual_input['input_id']}.json"
    rec = _document(path, workspace.workspace)
    rec.update(input=visual_input)
    payload = rec.get("payload")
    if payload is None:
        return rec
    if not _envelope_valid(payload, workspace, name=processor, version=f"{processor}-v1", fingerprint=fingerprint, asset=asset) or not isinstance(payload.get("model"), dict) or payload.get("input_kind") != visual_input["kind"] or payload.get("input") != visual_input["provenance"]:
        return _invalidate(rec, f"{processor.title()} envelope/input provenance mismatch")
    if payload.get("status") == "failed":
        rec["status"] = "failed"
        return rec
    result = payload.get("result")
    if processor == "vision":
        vision = result.get("vision") if isinstance(result, dict) else None
        if not _vision_schema(vision):
            return _invalidate(rec, "Invalid Vision result schema")
        rec["status"] = "success_nonempty"
    else:
        faces = result.get("faces") if isinstance(result, dict) else None
        if not isinstance(faces, list):
            return _invalidate(rec, "Invalid Faces result schema")
        for index, face in enumerate(faces):
            confidence = face.get("confidence") if isinstance(face, dict) else None
            if (
                not isinstance(face, dict) or face.get("face_id") != f"face-{index:04d}"
                or face.get("provenance") != visual_input["provenance"]
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence)) or not 0 <= confidence <= 1
                or not isinstance(face.get("bbox"), dict) or not isinstance(face.get("landmarks"), list)
                or not isinstance(face.get("embedding"), list)
            ):
                return _invalidate(rec, "Invalid Faces detection schema/provenance")
        rec["status"] = "success_nonempty" if faces else "success_empty"
    return rec


def _cluster(workspace: WorkspaceInput, config: NormalizerConfig, faces_records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    fingerprint = config.faces_clustering_configuration_fingerprint
    logical = config.faces_clustering_logical_input_fingerprint
    if fingerprint is None:
        return {"status": "not_analyzed", "records": [], "semantic": {"sentinel": "disabled"}}
    root = workspace.workspace / "analysis" / "faces" / "faces-clustering-v1" / fingerprint
    paths = [root / f"{logical}.json"] if logical else (
        sorted(path for path in root.glob("*.json") if path.is_file() and not path.is_symlink()) if root.is_dir() else []
    )
    if not paths:
        missing = root / f"{logical}.json" if logical else root / "<logical-input>.json"
        rec = _document(missing, workspace.workspace)
        return {"status": "input_unavailable", "records": [rec], "semantic": rec["semantic"]}
    known = {
        (asset_id, record["input"]["kind"], record["input"]["input_id"], face.get("face_id"))
        for asset_id, records in faces_records.items() for record in records
        if record.get("status") in {"success_empty", "success_nonempty"}
        for face in record["payload"]["result"]["faces"]
    }
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for path in paths:
        rec = _document(path, workspace.workspace)
        payload = rec.get("payload")
        expected_logical = path.stem
        if payload is None:
            (invalid if rec["status"] == "invalid" else valid).append(rec)
            continue
        ok = (
            isinstance(payload, dict)
            and _envelope_valid(payload, workspace, name="faces-clustering", version="faces-clustering-v1", fingerprint=fingerprint)
            and payload.get("logical_input_fingerprint") == expected_logical
            and payload.get("faces_configuration_fingerprint") == config.faces_configuration_fingerprint
            and payload.get("model") is None and isinstance(payload.get("result"), dict)
            and isinstance(payload["result"].get("clusters"), list)
        )
        if ok:
            for cluster in payload["result"]["clusters"]:
                if not isinstance(cluster, dict) or not isinstance(cluster.get("cluster_id"), str) or cluster.get("status") not in {"core", "uncertain"} or not isinstance(cluster.get("members"), list):
                    ok = False
                    break
                for member in cluster["members"]:
                    key = (member.get("asset_id"), member.get("input_kind"), member.get("input_id"), member.get("face_id")) if isinstance(member, dict) else None
                    if key not in known:
                        ok = False
                        break
        if not ok:
            invalid.append(_invalidate(rec, "Faces clustering envelope/member provenance mismatch"))
        else:
            rec["status"] = "success_nonempty" if payload["result"]["clusters"] else "success_empty"
            valid.append(rec)
    if logical:
        chosen = valid[0] if valid else invalid[0]
        return {"status": chosen["status"], "records": [chosen], "selected": chosen, "semantic": chosen["semantic"]}
    if len(valid) > 1:
        return {"status": "ambiguous", "records": valid + invalid,
                "issue": "Multiple Faces Clustering logical inputs match the selected configuration",
                "semantic": {"candidates": [item["semantic"] for item in valid + invalid], "sentinel": "ambiguous"}}
    chosen = valid[0] if valid else invalid[0]
    return {"status": chosen["status"], "records": valid + invalid, "selected": chosen, "semantic": chosen["semantic"]}


def load_upstream(workspace: WorkspaceInput, config: NormalizerConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    session = _session(workspace, config)
    keyframes: dict[str, dict[str, Any]] = {}
    visual_inputs: dict[str, list[dict[str, Any]]] = {}
    for asset in workspace.assets:
        inputs: list[dict[str, Any]] = []
        if asset.catalog["media_type"] == "image":
            image_input = _image_input(workspace, asset)
            if image_input is not None:
                inputs.append(image_input)
        elif config.keyframes_configuration_fingerprint:
            record = _keyframe_record(workspace, asset, config.keyframes_configuration_fingerprint)
            keyframes[asset.asset_id] = record
            inputs.extend(record.get("inputs", []))
        elif config.vision_configuration_fingerprint or config.faces_configuration_fingerprint:
            root = workspace.workspace / "analysis" / "video-keyframes" / "video-keyframes-v1"
            candidates: list[dict[str, Any]] = []
            if root.is_dir():
                for path in sorted(root.glob(f"*/{asset.sha256[:2]}/{asset.sha256}.json")):
                    fingerprint = path.parents[1].name
                    if _SHA256.fullmatch(fingerprint):
                        candidate = _keyframe_record(workspace, asset, fingerprint)
                        if candidate.get("status") in {"success_empty", "success_nonempty"}:
                            candidates.append(candidate)
            if len(candidates) > 1:
                keyframes[asset.asset_id] = {
                    "status": "ambiguous", "payload": None,
                    "issue": "Multiple compatible keyframe configurations exist; select one explicitly",
                    "records": candidates,
                    "semantic": {"sentinel": "ambiguous", "candidates": [item["semantic"] for item in candidates]},
                }
        visual_inputs[asset.asset_id] = inputs

    analyses: dict[str, dict[str, list[dict[str, Any]]]] = {"vision": {}, "faces": {}}
    for processor, fingerprint in (("vision", config.vision_configuration_fingerprint), ("faces", config.faces_configuration_fingerprint)):
        if fingerprint is None:
            continue
        for asset in workspace.assets:
            records = [
                _analysis_record(workspace, asset, fingerprint, processor, item)
                for item in visual_inputs[asset.asset_id]
            ]
            if not records:
                kind = "image_preview" if asset.catalog["media_type"] == "image" else "video_keyframe"
                records = [{
                    "status": "input_unavailable",
                    "location": None,
                    "payload": None,
                    "input": {"kind": kind, "input_id": None, "timestamp_s": None},
                    "issue": "Required public preview/keyframe input is unavailable",
                    "semantic": {"asset_id": asset.asset_id, "input_kind": kind,
                                 "sentinel": "upstream_input_unavailable"},
                }]
            analyses[processor][asset.asset_id] = records
    clustering = _cluster(workspace, config, analyses["faces"])
    runtime = {"session_grouper": session, "video_keyframes": keyframes,
               "vision": analyses["vision"], "faces": analyses["faces"],
               "faces_clustering": clustering, "visual_inputs": visual_inputs}
    semantic = {
        "selection": config.upstream_selection(),
        "session_grouper": session["semantic"],
        "video_keyframes": {key: value["semantic"] for key, value in sorted(keyframes.items())},
        "vision": {key: [item["semantic"] for item in value] for key, value in sorted(analyses["vision"].items())},
        "faces": {key: [item["semantic"] for item in value] for key, value in sorted(analyses["faces"].items())},
        "faces_clustering": clustering["semantic"],
    }
    return runtime, semantic


def blocking_ambiguities(upstream: dict[str, Any]) -> list[str]:
    values = [name for name in ("session_grouper", "faces_clustering") if upstream[name]["status"] == "ambiguous"]
    if any(item.get("status") == "ambiguous" for item in upstream["video_keyframes"].values()):
        values.append("video_keyframes")
    return values
