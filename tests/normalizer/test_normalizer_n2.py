from __future__ import annotations

import json
from pathlib import Path

import pytest

from normalizer.fingerprint import canonical_sha256
from normalizer.models import NormalizerConfig
from normalizer.service import analyze_prepared, plan_report, prepare_workspace


def _write(path: Path, payload: object, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding="utf-8")


def _catalog(workspace: Path) -> dict:
    return json.loads((workspace / "metadata" / "catalog.json").read_text(encoding="utf-8"))


def _enable_preview(workspace: Path, asset: dict) -> dict:
    catalog = _catalog(workspace)
    entry = next(item for item in catalog["assets"] if item["asset_id"] == asset["asset_id"])
    location = f"previews/images/{asset['sha256'][:2]}/{asset['sha256']}.jpg"
    (workspace / location).parent.mkdir(parents=True, exist_ok=True)
    (workspace / location).write_bytes(b"public-preview")
    entry["preview_location"] = location
    _write(workspace / "metadata" / "catalog.json", catalog)
    return {"kind": "image_preview", "asset_id": asset["asset_id"],
            "sha256": asset["sha256"], "location": location}


def _keyframes(workspace: Path, asset: dict, count: int = 2, *, failed: bool = False) -> tuple[str, list[dict]]:
    configuration = {"recipe": "keyframes-test-v1"}
    fingerprint = canonical_sha256(configuration)
    path = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1" / fingerprint / asset["sha256"][:2] / f"{asset['sha256']}.json"
    frames = []
    for index in range(count):
        keyframe_id = f"keyframe-{index:04d}"
        location = path.with_suffix("") / "keyframes" / f"{keyframe_id}.jpg"
        location.parent.mkdir(parents=True, exist_ok=True)
        location.write_bytes(f"keyframe-{index}".encode())
        timestamp = float(index + 1)
        provenance = {
            "kind": "video_keyframe", "asset_id": asset["asset_id"], "sha256": asset["sha256"],
            "keyframe_id": keyframe_id, "location": location.relative_to(workspace).as_posix(),
            "timestamp_s": timestamp,
            "video_keyframe_processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
            "video_keyframe_configuration_fingerprint": fingerprint,
        }
        frames.append({
            "keyframe_id": keyframe_id, "location": provenance["location"], "timestamp_s": timestamp,
            "source_video_asset_id": asset["asset_id"], "source_video_sha256": asset["sha256"],
            "processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
            "model": {"framework": "OpenCLIP", "name": "fixture"},
            "configuration_fingerprint": fingerprint,
            "provenance": provenance,
        })
    _write(path, {
        "result_schema_version": 1, "workspace_contract_version": 1,
        "workspace_id": "normalizer-workspace", "asset_id": asset["asset_id"], "sha256": asset["sha256"],
        "processor": {"name": "video-keyframes", "version": "video-keyframes-v1"},
        "model": {"framework": "OpenCLIP", "name": "fixture"},
        "configuration": configuration, "configuration_fingerprint": fingerprint,
        "status": "failed" if failed else "success",
        "error": {"code": "DECODE_FAILED", "message": "fixture"} if failed else None,
        "result": None if failed else {"keyframes": frames},
    })
    return fingerprint, frames


def _analysis(workspace: Path, processor: str, asset: dict, visual_input: dict,
              result: dict | None, *, failed: bool = False, configuration: dict | None = None) -> str:
    configuration = configuration or {"recipe": f"{processor}-test-v1"}
    fingerprint = canonical_sha256(configuration)
    base = workspace / "analysis" / processor / f"{processor}-v1" / fingerprint / asset["sha256"][:2] / asset["sha256"]
    path = base / "image-preview.json" if visual_input["kind"] == "image_preview" else (
        base / "video-keyframes" / visual_input["video_keyframe_configuration_fingerprint"] / f"{visual_input['keyframe_id']}.json"
    )
    input_id = "image-preview" if visual_input["kind"] == "image_preview" else visual_input["keyframe_id"]
    payload_result = None if failed else (
        {"vision": result, "attempts": [{"attempt": 0, "kind": "initial", "raw_model_response": "{}", "validation_errors": []}]}
        if processor == "vision" else {"image": {"width": 100, "height": 100, "color_order": "BGR"}, "faces": result}
    )
    _write(path, {
        "result_schema_version": 1, "workspace_contract_version": 1, "workspace_id": "normalizer-workspace",
        "asset_id": asset["asset_id"], "sha256": asset["sha256"],
        "processor": {"name": processor, "version": f"{processor}-v1"},
        "model": {"framework": "fixture", "name": processor},
        "configuration": configuration, "configuration_fingerprint": fingerprint,
        "input_kind": visual_input["kind"], "input": visual_input,
        "status": "failed" if failed else "success",
        "error": {"code": "FIXTURE_FAILED", "message": "fixture"} if failed else None,
        "result": payload_result,
    })
    return fingerprint


def _vision_value(tag: str) -> dict:
    return {
        "scene": "concert", "people": {"approx_count": 3, "crowd": False},
        "activities": [" Playing ", "playing"], "objects": ["Guitar", " guitar "],
        "environment": ["Stage"], "visual_attributes": ["Straße", " STRASSE "],
        "tags": [tag], "description": f"Observation {tag}",
    }


def _face(visual_input: dict, index: int, confidence: float) -> dict:
    return {"face_id": f"face-{index:04d}", "provenance": visual_input,
            "bbox": {"x": 1, "y": 1, "width": 10, "height": 10},
            "confidence": confidence, "landmarks": [], "embedding": []}


def _session(workspace: Path, image: dict, video: dict, *, logical: str = "1" * 64) -> str:
    configuration = {"rollover_hour": 6}
    fingerprint = canonical_sha256(configuration)
    path = workspace / "analysis" / "session-grouper" / "session-grouper-v1" / fingerprint / f"{logical}.json"
    timestamp = {"datetime": "2026-10-26T12:30:00+01:00", "source": "EXIF",
                 "timezone_offset": "+01:00", "filesystem_fallback": False, "confidence": "strong"}
    _write(path, {
        "result_schema_version": 1, "workspace_contract_version": 1, "workspace_id": "normalizer-workspace",
        "processor": {"name": "session-grouper", "version": "session-grouper-v1"}, "model": None,
        "configuration": configuration, "configuration_fingerprint": fingerprint,
        "input": {"logical_fingerprint": logical}, "status": "success", "error": None,
        "result": {
            "sessions": [{"session_id": "session-1", "start": "2026-10-26T12:30:00+01:00",
                          "end": "2026-10-26T12:30:00+01:00", "operational_day": "2026-10-26",
                          "boundary_reason": "first_asset", "confidence": "strong",
                          "assets": [{"asset_id": image["asset_id"], "assignment_confidence": "strong",
                                      "assignment_reason": "trusted_timestamp_sequence", "timestamp": timestamp}]}],
            "unassigned": [{"asset_id": video["asset_id"], "reason": "missing_timestamp", "timestamp": None}],
        },
    })
    return fingerprint


def _cluster(workspace: Path, asset: dict, visual_input: dict, faces_fp: str,
             *, face_id: str = "face-0000", logical: str = "3" * 64) -> str:
    configuration = {"similarity_threshold": 0.6}
    fingerprint = canonical_sha256(configuration)
    path = workspace / "analysis" / "faces" / "faces-clustering-v1" / fingerprint / f"{logical}.json"
    _write(path, {
        "result_schema_version": 1, "workspace_contract_version": 1, "workspace_id": "normalizer-workspace",
        "processor": {"name": "faces-clustering", "version": "faces-clustering-v1"}, "model": None,
        "configuration": configuration, "configuration_fingerprint": fingerprint,
        "logical_input_fingerprint": logical, "faces_configuration_fingerprint": faces_fp,
        "status": "success", "error": None,
        "result": {"face_count": 1, "clusters": [{
            "cluster_id": "face-cluster-0000", "status": "core", "member_count": 1,
            "members": [{"asset_id": asset["asset_id"], "sha256": asset["sha256"],
                         "input_kind": visual_input["kind"], "input_id": "image-preview",
                         "face_id": face_id, "faces_result_location": "fixture", "provenance": visual_input}],
        }]},
    })
    return fingerprint


def _snapshot_asset(result, asset: dict) -> dict:
    record = next(item for item in result.manifest["assets"] if item["asset_id"] == asset["asset_id"])
    return json.loads((result.prepared.output_path / record["location"]).read_text(encoding="utf-8"))["result"]


def test_n2_projects_sessions_keyframes_vision_faces_and_exact_facets(workspace_factory):
    workspace = workspace_factory()
    catalog = _catalog(workspace)
    image, video = sorted(catalog["assets"], key=lambda item: item["media_type"])
    image_input = _enable_preview(workspace, image)
    keyframe_fp, frames = _keyframes(workspace, video, count=2)
    video_inputs = [frame["provenance"] for frame in frames]

    vision_fp = _analysis(workspace, "vision", image, image_input, _vision_value("image"))
    for index, visual_input in enumerate(video_inputs):
        assert _analysis(workspace, "vision", video, visual_input, _vision_value(f"video-{index}")) == vision_fp
    faces_fp = _analysis(workspace, "faces", image, image_input, [])
    for index, visual_input in enumerate(video_inputs):
        assert _analysis(workspace, "faces", video, visual_input,
                         [_face(visual_input, face_index, 0.9 - face_index * 0.05)
                          for face_index in range(index + 1)]) == faces_fp
    session_fp = _session(workspace, image, video)

    config = NormalizerConfig(
        session_configuration_fingerprint=session_fp,
        session_logical_input_fingerprint="1" * 64,
        keyframes_configuration_fingerprint=keyframe_fp,
        vision_configuration_fingerprint=vision_fp,
        faces_configuration_fingerprint=faces_fp,
    )
    analyzed = analyze_prepared(prepare_workspace(workspace, config))
    image_result = _snapshot_asset(analyzed, image)
    video_result = _snapshot_asset(analyzed, video)

    assert image_result["temporal"]["session_candidates"][0]["session_id"] == "session-1"
    assert video_result["completeness"]["analyses"]["session_grouper"]["unassigned_reason"] == "missing_timestamp"
    assert len(video_result["semantic"]["observations"]) == 2
    assert {item["keyframe_timestamp_s"] for item in video_result["semantic"]["observations"]} == {1.0, 2.0}
    assert image_result["semantic"]["facets"]["objects"] == [{
        "key": "guitar", "value": "Guitar",
        "provenance": [{"observation_id": "vision:image_preview:image-preview",
                        "source_document": image_result["semantic"]["observations"][0]["provenance"]["source_document"],
                        "source_pointer": "/result/vision/objects"}]
    }]
    assert image_result["semantic"]["facets"]["visual_attributes"][0]["key"] == "strasse"
    assert image_result["people"]["detected_face_count"] == 0
    assert image_result["completeness"]["analyses"]["faces"]["status"] == "success_empty"
    assert video_result["people"]["detected_face_count"] is None
    assert [item["detected_face_count"] for item in video_result["people"]["face_observations"]] == [1, 2]
    assert video_result["people"]["vision_people_observations"][0]["approx_count"] == 3


def test_selected_failed_missing_and_invalid_results_have_distinct_states(workspace_factory):
    workspace = workspace_factory([{"name": "video", "media_type": "video"}])
    video = _catalog(workspace)["assets"][0]
    keyframe_fp, _ = _keyframes(workspace, video, failed=True)
    vision_fp = canonical_sha256({"recipe": "vision-test-v1"})
    faces_fp = canonical_sha256({"recipe": "faces-test-v1"})
    config = NormalizerConfig(keyframes_configuration_fingerprint=keyframe_fp,
                              vision_configuration_fingerprint=vision_fp,
                              faces_configuration_fingerprint=faces_fp)
    result = analyze_prepared(prepare_workspace(workspace, config))
    asset = _snapshot_asset(result, video)
    assert asset["completeness"]["analyses"]["video_keyframes"]["status"] == "failed"
    assert asset["completeness"]["analyses"]["vision"]["status"] == "input_unavailable"
    assert asset["completeness"]["analyses"]["faces"]["status"] == "input_unavailable"


def test_upstream_byte_change_changes_input_fingerprint_and_reuse_is_exact(workspace_factory):
    workspace = workspace_factory([{"name": "image", "media_type": "image"}])
    image = _catalog(workspace)["assets"][0]
    image_input = _enable_preview(workspace, image)
    vision_fp = _analysis(workspace, "vision", image, image_input, _vision_value("one"))
    config = NormalizerConfig(vision_configuration_fingerprint=vision_fp)
    first = prepare_workspace(workspace, config)
    written = analyze_prepared(first)
    assert prepare_workspace(workspace, config).reusable is True
    path = next((workspace / "analysis" / "vision" / "vision-v1" / vision_fp).rglob("image-preview.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    _write(path, payload, indent=2)
    changed = prepare_workspace(workspace, config)
    assert changed.input_set_fingerprint != first.input_set_fingerprint
    assert changed.output_path != written.prepared.output_path


def test_aggregate_ambiguity_is_visible_in_plan_and_blocks_analyze(workspace_factory):
    workspace = workspace_factory()
    catalog = _catalog(workspace)
    image, video = sorted(catalog["assets"], key=lambda item: item["media_type"])
    fingerprint = _session(workspace, image, video, logical="1" * 64)
    _session(workspace, image, video, logical="2" * 64)
    prepared = prepare_workspace(workspace, NormalizerConfig(session_configuration_fingerprint=fingerprint))
    assert plan_report(prepared)["blocking_ambiguities"] == ["session_grouper"]
    with pytest.raises(ValueError, match="Ambiguous upstream selection"):
        analyze_prepared(prepared)


def test_configuration_selection_changes_configuration_fingerprint(workspace_factory):
    workspace = workspace_factory()
    first = prepare_workspace(workspace, NormalizerConfig(vision_configuration_fingerprint="a" * 64))
    second = prepare_workspace(workspace, NormalizerConfig(vision_configuration_fingerprint="b" * 64))
    assert first.configuration_fingerprint != second.configuration_fingerprint
    assert plan_report(first)["upstream_expected_inputs"]["vision"] == 2


def test_faces_cluster_refs_are_anonymous_and_bad_membership_is_invalid(workspace_factory):
    workspace = workspace_factory([{"name": "image", "media_type": "image"}])
    image = _catalog(workspace)["assets"][0]
    image_input = _enable_preview(workspace, image)
    faces_fp = _analysis(workspace, "faces", image, image_input, [_face(image_input, 0, 0.91)])
    cluster_fp = _cluster(workspace, image, image_input, faces_fp)
    config = NormalizerConfig(
        faces_configuration_fingerprint=faces_fp,
        faces_clustering_configuration_fingerprint=cluster_fp,
        faces_clustering_logical_input_fingerprint="3" * 64,
    )
    asset = _snapshot_asset(analyze_prepared(prepare_workspace(workspace, config)), image)
    assert asset["people"]["anonymous_cluster_refs"][0]["cluster_id"] == "face-cluster-0000"
    assert asset["people"]["anonymous_cluster_refs"][0]["cluster_status"] == "core"

    workspace_bad = workspace_factory([{"name": "image-bad", "media_type": "image"}])
    bad_image = _catalog(workspace_bad)["assets"][0]
    bad_input = _enable_preview(workspace_bad, bad_image)
    bad_faces_fp = _analysis(workspace_bad, "faces", bad_image, bad_input, [_face(bad_input, 0, 0.8)])
    bad_cluster_fp = _cluster(workspace_bad, bad_image, bad_input, bad_faces_fp, face_id="face-9999")
    bad_config = NormalizerConfig(
        faces_configuration_fingerprint=bad_faces_fp,
        faces_clustering_configuration_fingerprint=bad_cluster_fp,
        faces_clustering_logical_input_fingerprint="3" * 64,
    )
    bad_asset = _snapshot_asset(analyze_prepared(prepare_workspace(workspace_bad, bad_config)), bad_image)
    assert bad_asset["completeness"]["analyses"]["faces_clustering"]["status"] == "invalid"
    assert bad_asset["people"]["anonymous_cluster_refs"] == []


def test_multiple_unselected_keyframe_configurations_are_ambiguous(workspace_factory):
    workspace = workspace_factory([{"name": "video", "media_type": "video"}])
    video = _catalog(workspace)["assets"][0]
    first_fp, _ = _keyframes(workspace, video)
    second_configuration = {"recipe": "keyframes-test-v2"}
    second_fp = canonical_sha256(second_configuration)
    source = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1" / first_fp / video["sha256"][:2] / f"{video['sha256']}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["configuration"] = second_configuration
    payload["configuration_fingerprint"] = second_fp
    for frame in payload["result"]["keyframes"]:
        frame["configuration_fingerprint"] = second_fp
        old = workspace / frame["location"]
        new_base = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1" / second_fp / video["sha256"][:2] / video["sha256"] / "keyframes"
        new_base.mkdir(parents=True, exist_ok=True)
        new = new_base / old.name
        new.write_bytes(old.read_bytes())
        frame["location"] = new.relative_to(workspace).as_posix()
    second_path = workspace / "analysis" / "video-keyframes" / "video-keyframes-v1" / second_fp / video["sha256"][:2] / f"{video['sha256']}.json"
    _write(second_path, payload)
    prepared = prepare_workspace(workspace, NormalizerConfig(vision_configuration_fingerprint="a" * 64))
    assert "video_keyframes" in plan_report(prepared)["blocking_ambiguities"]
    with pytest.raises(ValueError, match="video_keyframes"):
        analyze_prepared(prepared)


def test_session_absent_and_vision_invalid_or_failed_are_not_success_empty(workspace_factory):
    workspace = workspace_factory([{"name": "image", "media_type": "image"}])
    image = _catalog(workspace)["assets"][0]
    image_input = _enable_preview(workspace, image)
    vision_fp = _analysis(workspace, "vision", image, image_input, {"scene": "missing fields"})
    config = NormalizerConfig(
        session_configuration_fingerprint="b" * 64,
        session_logical_input_fingerprint="c" * 64,
        vision_configuration_fingerprint=vision_fp,
    )
    asset = _snapshot_asset(analyze_prepared(prepare_workspace(workspace, config)), image)
    assert asset["completeness"]["analyses"]["session_grouper"]["status"] == "input_unavailable"
    assert asset["completeness"]["analyses"]["vision"]["status"] == "invalid"

    failed_workspace = workspace_factory([{"name": "failed-image", "media_type": "image"}])
    failed_image = _catalog(failed_workspace)["assets"][0]
    failed_input = _enable_preview(failed_workspace, failed_image)
    failed_fp = _analysis(failed_workspace, "vision", failed_image, failed_input, None, failed=True)
    failed_asset = _snapshot_asset(
        analyze_prepared(prepare_workspace(failed_workspace, NormalizerConfig(
            vision_configuration_fingerprint=failed_fp
        ))), failed_image
    )
    assert failed_asset["completeness"]["analyses"]["vision"]["status"] == "failed"


def test_n2_never_reads_sqlite_originals_raw_metadata_or_media_desk_user_data(
    workspace_factory, tmp_path, monkeypatch
):
    originals = tmp_path / "originals"
    originals.mkdir()
    (originals / "secret.jpg").write_bytes(b"original")
    workspace = workspace_factory(
        [{"name": "image", "media_type": "image"}], source_root=str(originals)
    )
    forbidden = [
        workspace / "state" / "catalog.sqlite3",
        workspace / "metadata" / "raw" / "do-not-read.json",
        workspace / "media-desk" / "user-data.json",
        originals / "secret.jpg",
    ]
    for path in forbidden[1:3]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"private")
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def guarded_bytes(path: Path):
        if any(path.resolve(strict=False) == item.resolve(strict=False) for item in forbidden):
            raise AssertionError(f"forbidden read: {path}")
        return original_read_bytes(path)

    def guarded_text(path: Path, *args, **kwargs):
        if any(path.resolve(strict=False) == item.resolve(strict=False) for item in forbidden):
            raise AssertionError(f"forbidden read: {path}")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_text)
    analyze_prepared(prepare_workspace(workspace, NormalizerConfig()))
