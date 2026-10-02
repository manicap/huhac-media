from __future__ import annotations

import json

import pytest

from vision.models import VisionConfig
from vision.service import execute_prepared, prepare_workspace

from conftest import canonical_result


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def analyze(self, image_path, prompt):
        self.calls.append((image_path, prompt))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def encoded(value):
    return json.dumps(value)


def test_valid_response_is_published_with_raw_and_canonical(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    raw = encoded(canonical_result())
    model = FakeModel([raw])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert (result.processed, result.failed, result.skipped) == (1, 0, 1)
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["input_kind"] == "image_preview"
    assert payload["result"]["attempts"][0]["raw_model_response"] == raw
    assert payload["result"]["vision"] == canonical_result()


def test_safe_normalization_does_not_require_repair(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    value = canonical_result(people={"approx_count": "8", "crowd": "true"})
    model = FakeModel([encoded(value)])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert result.processed == 1
    assert len(model.calls) == 1
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["result"]["vision"]["people"] == {"approx_count": 8, "crowd": True}


def test_schema_error_triggers_limited_repair(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    invalid = canonical_result(people={"approx_count": "several", "crowd": False})
    model = FakeModel([encoded(invalid), encoded(canonical_result())])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert result.processed == 1
    assert len(model.calls) == 2
    assert "Only correct structure and data types" in model.calls[1][1]
    assert "several" in model.calls[1][1]


def test_malformed_json_is_repaired(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    model = FakeModel(["not json", encoded(canonical_result())])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert result.processed == 1
    assert len(model.calls) == 2


def test_repair_failure_writes_explicit_failure_and_raw_attempts(workspace_factory):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    model = FakeModel(["bad", "still bad"])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert result.failed == 1
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "INVALID_MODEL_RESULT"
    assert payload["result"]["vision"] is None
    assert [item["raw_model_response"] for item in payload["result"]["attempts"]] == ["bad", "still bad"]


def test_per_input_error_isolation(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig(max_repair_attempts=0))
    model = FakeModel([RuntimeError("first failed"), encoded(canonical_result())])
    result = execute_prepared(prepared, dry_run=False, model=model)
    assert (result.processed, result.failed) == (1, 1)
    statuses = [json.loads(plan.output_path.read_text(encoding="utf-8"))["status"] for plan in prepared.plans]
    assert statuses == ["failed", "success"]


def test_dry_run_never_calls_model_or_writes(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    model = FakeModel([])
    result = execute_prepared(prepared, dry_run=True, model=model)
    assert result.processed == 0
    assert result.reused == 0
    assert model.calls == []
    assert all(not plan.output_path.exists() for plan in prepared.plans)


@pytest.mark.integration
def test_second_run_reuses_results_without_model_calls(workspace_factory):
    workspace = workspace_factory()
    prepared = prepare_workspace(workspace, VisionConfig())
    model = FakeModel([encoded(canonical_result()), encoded(canonical_result())])
    first = execute_prepared(prepared, dry_run=False, model=model)
    assert first.processed == 2
    second_prepared = prepare_workspace(workspace, VisionConfig())
    second_model = FakeModel([])
    second = execute_prepared(second_prepared, dry_run=False, model=second_model)
    assert second.reused == 2
    assert second_model.calls == []


def test_video_result_preserves_keyframe_identity_and_timestamp(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    video_plan = next(plan for plan in prepared.plans if plan.visual_input.kind == "video_keyframe")
    image_plan = next(plan for plan in prepared.plans if plan.visual_input.kind == "image_preview")
    model = FakeModel([encoded(canonical_result()), encoded(canonical_result())])
    execute_prepared(prepared, dry_run=False, model=model)
    payload = json.loads(video_plan.output_path.read_text(encoding="utf-8"))
    assert payload["input"]["keyframe_id"] == "keyframe-0000"
    assert payload["input"]["timestamp_s"] == 1.0
    assert payload["input"]["asset_id"] == video_plan.visual_input.asset_id
    assert image_plan.output_path.exists()


def test_per_input_timing_is_persisted(workspace_factory, monkeypatch):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    clock = iter([0.0, 1.0, 4.0, 5.0])
    monkeypatch.setattr("vision.service.perf_counter", lambda: next(clock))
    model = FakeModel([encoded(canonical_result())])
    result = execute_prepared(prepared, dry_run=False, model=model)
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["timing"] == {
        "total_seconds": 5.0,
        "model_seconds": 3.0,
        "attempts": 1,
    }
    assert result.timings[0].as_dict() == payload["timing"]


def test_repair_timing_counts_all_model_requests(workspace_factory, monkeypatch):
    prepared = prepare_workspace(workspace_factory(keyframes=False), VisionConfig())
    clock = iter([0.0, 1.0, 3.0, 4.0, 7.0, 8.0])
    monkeypatch.setattr("vision.service.perf_counter", lambda: next(clock))
    invalid = canonical_result(people={"approx_count": "several", "crowd": False})
    model = FakeModel([encoded(invalid), encoded(canonical_result())])
    result = execute_prepared(prepared, dry_run=False, model=model)
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["timing"] == {
        "total_seconds": 8.0,
        "model_seconds": 5.0,
        "attempts": 2,
    }
    assert result.timings[0].attempts == 2


def test_force_bypasses_reuse_and_replaces_only_current_result(workspace_factory):
    workspace = workspace_factory()
    first = prepare_workspace(workspace, VisionConfig())
    model = FakeModel([encoded(canonical_result()), encoded(canonical_result())])
    execute_prepared(first, dry_run=False, model=model)
    target = first.plans[0].output_path
    old_payload = json.loads(target.read_text(encoding="utf-8"))
    unrelated = workspace / "analysis" / "vision" / "vision-v1" / ("f" * 64) / "keep.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep", encoding="utf-8")
    upstream = next(
        (workspace / "analysis" / "video-keyframes").rglob("keyframe-0000.jpg")
    )
    upstream_bytes = upstream.read_bytes()

    normal = prepare_workspace(workspace, VisionConfig())
    assert all(plan.action == "reuse" for plan in normal.plans)
    forced = prepare_workspace(workspace, VisionConfig(), force=True)
    assert all(plan.action == "process" for plan in forced.plans)
    replacement = canonical_result(scene="outdoor setting")
    forced_model = FakeModel([encoded(replacement), encoded(replacement)])
    execute_prepared(forced, dry_run=False, model=forced_model)

    new_payload = json.loads(target.read_text(encoding="utf-8"))
    assert new_payload["result"]["vision"]["scene"] == "outdoor setting"
    assert new_payload["created_at"] != old_payload["created_at"]
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert upstream.read_bytes() == upstream_bytes
    assert list(target.parent.glob("*.tmp")) == []


def test_dry_run_force_reports_process_without_model_or_writes(workspace_factory):
    workspace = workspace_factory()
    first = prepare_workspace(workspace, VisionConfig())
    execute_prepared(
        first,
        dry_run=False,
        model=FakeModel([encoded(canonical_result()), encoded(canonical_result())]),
    )
    snapshots = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    forced = prepare_workspace(workspace, VisionConfig(), force=True)
    dry_model = FakeModel([])
    result = execute_prepared(forced, dry_run=True, model=dry_model)
    assert sum(plan.action == "process" for plan in forced.plans) == 2
    assert result.processed == 0
    assert dry_model.calls == []
    assert snapshots == {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
