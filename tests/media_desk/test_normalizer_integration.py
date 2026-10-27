from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import pytest

from fastapi.testclient import TestClient

from media_desk.config import Settings, load_settings
from media_desk.effective_view import effective_asset_view
from media_desk.index import CursorError, LibraryIndex, QuerySpec
from media_desk.normalizer_adapter import attach_normalizer_snapshot
from media_desk.contract import load_workspace
from media_desk.web import create_app
from normalizer.service import analyze_workspace
from normalizer.models import NormalizerConfig


def _normalizer_snapshot(builder, *, facets=None):
    entry = builder.add_asset(1)
    workspace = builder.publish()
    analysis = analyze_workspace(workspace)
    config = analysis.prepared.configuration_fingerprint
    input_set = analysis.prepared.input_set_fingerprint
    if facets:
        manifest_path = analysis.prepared.output_path / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        record = manifest["assets"][0]
        result_path = analysis.prepared.output_path / record["location"]
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["result"]["semantic"]["status"] = "success_nonempty"
        payload["result"]["semantic"]["facets"].update(facets)
        content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        result_path.write_bytes(content)
        record["content_sha256"] = hashlib.sha256(content).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return workspace, entry, config, input_set, analysis.prepared.output_path


def _rewrite_first(output: Path, transform) -> None:
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["assets"][0]
    path = output / record["location"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    transform(payload["result"])
    content = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(content)
    record["content_sha256"] = hashlib.sha256(content).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_explicit_snapshot_links_by_exact_asset_id(workspace_builder):
    workspace, entry, config, input_set, _ = _normalizer_snapshot(workspace_builder)
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == "available"
    assert snapshot.assets[0].normalized["identity"]["asset_id"] == entry["asset_id"]


def test_missing_and_invalid_selection_are_nonfatal(workspace_builder):
    workspace_builder.add_asset(1)
    snapshot = load_workspace(workspace_builder.publish())
    missing = attach_normalizer_snapshot(snapshot, "a" * 64, "b" * 64)
    invalid = attach_normalizer_snapshot(snapshot, "BAD", None)
    assert missing.normalizer.state == "missing" and missing.assets[0].normalized is None
    assert invalid.normalizer.state == "invalid_selection"


def test_config_only_selection_detects_ambiguity(workspace_builder):
    workspace, _, config, input_set, output = _normalizer_snapshot(workspace_builder)
    duplicate = output.parent / ("f" * 64)
    shutil.copytree(output, duplicate)
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, None)
    assert snapshot.normalizer.state == "ambiguous"


def test_changed_catalog_marks_snapshot_stale(workspace_builder):
    workspace, _, config, input_set, _ = _normalizer_snapshot(workspace_builder)
    workspace_builder.add_asset(2)
    workspace_builder.publish()
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == "stale"


def test_tampered_result_is_invalid_not_a_crash(workspace_builder):
    workspace, _, config, input_set, output = _normalizer_snapshot(workspace_builder)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    (output / manifest["assets"][0]["location"]).write_text("{}", encoding="utf-8")
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == "invalid"


@pytest.mark.parametrize("target", ["result", "summary"])
def test_invalid_result_schema_and_manifest_summary_are_rejected(workspace_builder, target):
    workspace, _, config, input_set, output = _normalizer_snapshot(workspace_builder)
    if target == "result":
        _rewrite_first(output, lambda result: result.pop("quality"))
    else:
        path = output / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["summary"]["warning_count"] += 1
        path.write_text(json.dumps(manifest), encoding="utf-8")
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == "invalid"


@pytest.mark.parametrize("mutation, expected", [
    (lambda manifest: manifest.update(workspace_id="other-workspace"), "stale"),
    (lambda manifest: manifest.update(configuration_fingerprint="d" * 64), "invalid"),
    (lambda manifest: manifest["assets"][0].update(location="../escape.json"), "invalid"),
])
def test_manifest_mismatch_and_traversal_are_diagnostic(workspace_builder, mutation, expected):
    workspace, _, config, input_set, output = _normalizer_snapshot(workspace_builder)
    path = output / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutation(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == expected


def test_symlinked_result_is_rejected_when_supported(workspace_builder):
    workspace, _, config, input_set, output = _normalizer_snapshot(workspace_builder)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    result = output / manifest["assets"][0]["location"]
    outside = output.parent / "outside.json"
    outside.write_bytes(result.read_bytes())
    result.unlink()
    try:
        result.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    assert snapshot.normalizer.state == "invalid"


def test_exact_facets_combine_and_report_counts(workspace_builder):
    facets = {
        "activities": [{"key": "running", "value": "Running", "provenance": []}],
        "objects": [{"key": "dog", "value": "Dog", "provenance": []}],
    }
    workspace, entry, config, input_set, _ = _normalizer_snapshot(workspace_builder, facets=facets)
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    index = LibraryIndex(snapshot)
    assert [item.asset_id for item in index.query(QuerySpec(activities=("Running",), objects=("Dog",)))] == [entry["asset_id"]]
    assert index.query(QuerySpec(activities=("running",))) == ()
    assert index.facet_counts(QuerySpec())["activities"] == [{"value": "Running", "count": 1}]


def test_facets_combine_with_search_and_bind_cursors(workspace_builder):
    first = workspace_builder.add_asset(1)
    workspace_builder.add_asset(2)
    workspace = workspace_builder.publish()
    analysis = analyze_workspace(workspace)
    _rewrite_first(analysis.prepared.output_path, lambda result: result["semantic"]["facets"].update(
        tags=[{"key": "selected", "value": "Selected", "provenance": []}]))
    snapshot = attach_normalizer_snapshot(load_workspace(workspace),
        analysis.prepared.configuration_fingerprint, analysis.prepared.input_set_fingerprint)
    index = LibraryIndex(snapshot)
    spec = QuerySpec(media_type="image", query="media-1", tags=("Selected",))
    assert [item.asset_id for item in index.query(spec)] == [first["asset_id"]]
    cursor = index.batch(QuerySpec(), limit=1)["next_cursor"]
    assert cursor is not None
    with pytest.raises(CursorError):
        index.batch(QuerySpec(tags=("Selected",)), limit=1, cursor=cursor)


def test_list_is_compact_and_detail_has_full_normalized_payload(workspace_builder, tmp_path):
    facets = {"tags": [{"key": "night", "value": "Night", "provenance": []}]}
    workspace, entry, config, input_set, _ = _normalizer_snapshot(workspace_builder, facets=facets)
    app = create_app(settings=Settings(workspace=workspace,
        normalizer_configuration_fingerprint=config, normalizer_input_set_fingerprint=input_set),
        user_data_path=tmp_path / "user.json")
    client = TestClient(app)
    item = client.get("/api/assets", params={"limit": 50}).json()["items"][0]
    detail = client.get(f"/api/assets/{entry['sha256']}").json()
    assert item["semantic_facets"]["tags"] == ["Night"] and "normalized" not in item
    assert detail["normalized"]["identity"]["asset_id"] == entry["asset_id"]


def test_library_and_detail_render_normalizer_state(workspace_builder, tmp_path):
    workspace, entry, config, input_set, _ = _normalizer_snapshot(workspace_builder)
    client = TestClient(create_app(settings=Settings(workspace=workspace,
        normalizer_configuration_fingerprint=config, normalizer_input_set_fingerprint=input_set),
        user_data_path=tmp_path / "user.json"))
    assert "Sjednocené informace" in client.get(f"/assets/{entry['sha256']}").text
    assert client.get("/library").status_code == 200


def test_effective_view_keeps_machine_candidates_but_user_event_wins(workspace_builder):
    workspace, _, config, input_set, _ = _normalizer_snapshot(workspace_builder)
    snapshot = attach_normalizer_snapshot(load_workspace(workspace), config, input_set)
    asset = snapshot.assets[0]
    asset.normalized["event"]["machine_candidates"] = [{"name": "Machine"}]
    effective = effective_asset_view(asset, {"event_id": "user", "name": "User", "source": "manual"})
    assert effective.event["name"] == "User"
    assert effective.event_candidates == ({"name": "Machine"},)


def test_video_observations_and_people_sources_remain_separate(workspace_builder, tmp_path):
    entry = workspace_builder.add_asset(1, media_type="video")
    workspace = workspace_builder.publish()
    analysis = analyze_workspace(workspace)
    def enrich(result):
        provenance = {"processor": {"name": "vision", "version": "vision-v1"}}
        result["semantic"].update(status="success_nonempty", observations=[
            {"input_kind": "video_keyframe", "input_id": "keyframe-0001", "keyframe_timestamp_s": 1.0,
             "description": "first", "provenance": provenance},
            {"input_kind": "video_keyframe", "input_id": "keyframe-0002", "keyframe_timestamp_s": 2.0,
             "description": "second", "provenance": provenance},
        ])
        result["people"].update(
            status="success_nonempty", detected_face_count=None,
            vision_people_observations=[{"approx_count": 3}],
            face_observations=[{"detected_face_count": 1}],
            anonymous_cluster_refs=[{"cluster_id": "anonymous-1"}],
        )
    _rewrite_first(analysis.prepared.output_path, enrich)
    client = TestClient(create_app(settings=Settings(
        workspace=workspace,
        normalizer_configuration_fingerprint=analysis.prepared.configuration_fingerprint,
        normalizer_input_set_fingerprint=analysis.prepared.input_set_fingerprint),
        user_data_path=tmp_path / "user.json"))
    payload = client.get(f"/api/assets/{entry['sha256']}").json()["normalized"]
    assert [item["input_id"] for item in payload["semantic"]["observations"]] == ["keyframe-0001", "keyframe-0002"]
    assert payload["people"]["detected_face_count"] is None
    assert payload["people"]["vision_people_observations"][0]["approx_count"] == 3
    assert payload["people"]["face_observations"][0]["detected_face_count"] == 1
    assert payload["people"]["anonymous_cluster_refs"][0]["cluster_id"] == "anonymous-1"


def test_requests_do_not_reread_normalizer_files(workspace_builder, tmp_path, monkeypatch):
    workspace, entry, config, input_set, output = _normalizer_snapshot(workspace_builder)
    app = create_app(settings=Settings(workspace=workspace,
        normalizer_configuration_fingerprint=config, normalizer_input_set_fingerprint=input_set),
        user_data_path=tmp_path / "user.json")
    original = Path.read_bytes
    def guarded(path):
        if output in path.parents:
            raise AssertionError("Normalizer disk read after app creation")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    client = TestClient(app)
    assert client.get("/api/assets", params={"limit": 50}).status_code == 200
    assert client.get(f"/api/assets/{entry['sha256']}").status_code == 200


def test_normalizer_rebuild_does_not_rewrite_user_store(workspace_builder, tmp_path):
    workspace, _, config, input_set, _ = _normalizer_snapshot(workspace_builder)
    user_path = tmp_path / "user.json"
    create_app(settings=Settings(workspace=workspace,
        normalizer_configuration_fingerprint=config, normalizer_input_set_fingerprint=input_set),
        user_data_path=user_path)
    before = user_path.read_bytes()
    rebuilt = analyze_workspace(workspace, NormalizerConfig(normalization_rules="normalized-asset-n2"))
    create_app(settings=Settings(workspace=workspace,
        normalizer_configuration_fingerprint=rebuilt.prepared.configuration_fingerprint,
        normalizer_input_set_fingerprint=rebuilt.prepared.input_set_fingerprint),
        user_data_path=user_path)
    assert user_path.read_bytes() == before


def test_normalizer_fingerprints_follow_settings_precedence(tmp_path):
    settings = load_settings(
        workspace=None, host=None, port=None, keyframe_fingerprint=None,
        config_path=None, config_dir=tmp_path,
        normalizer_configuration_fingerprint="a" * 64,
        normalizer_input_set_fingerprint=None,
        environ={"MEDIA_DESK_NORMALIZER_CONFIGURATION_FINGERPRINT": "b" * 64,
                 "MEDIA_DESK_NORMALIZER_INPUT_SET_FINGERPRINT": "c" * 64},
    )
    assert settings.normalizer_configuration_fingerprint == "a" * 64
    assert settings.normalizer_input_set_fingerprint == "c" * 64
