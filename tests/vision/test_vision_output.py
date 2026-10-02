from __future__ import annotations

import json

from vision.models import VisionConfig
from vision.output import (
    configuration_fingerprint,
    read_reusable_result,
    result_path,
    success_payload,
    write_json_atomic,
)
from vision.service import prepare_workspace

from conftest import KEYFRAME_FP, canonical_result


def test_configuration_fingerprint_covers_semantic_recipe():
    base = configuration_fingerprint(VisionConfig())
    assert base == configuration_fingerprint(VisionConfig())
    assert base != configuration_fingerprint(VisionConfig(model="another-model"))
    assert base != configuration_fingerprint(VisionConfig(num_predict=512))
    assert base != configuration_fingerprint(VisionConfig(max_repair_attempts=2))
    assert base != configuration_fingerprint(VisionConfig(prompt_recipe="objective-v2"))


def test_prompt_recipe_v2_changes_fingerprint_from_v1():
    current = VisionConfig()
    previous = VisionConfig(prompt_recipe="objective-visual-description-v1")
    assert current.prompt_recipe == "objective-visual-description-v2"
    assert configuration_fingerprint(current) != configuration_fingerprint(previous)


def test_think_setting_changes_configuration_fingerprint():
    assert VisionConfig().think is False
    assert configuration_fingerprint(VisionConfig()) != configuration_fingerprint(
        VisionConfig(think=True)
    )


def test_result_layout_distinguishes_image_and_upstream_keyframe(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    image = next(plan for plan in prepared.plans if plan.visual_input.kind == "image_preview")
    video = next(plan for plan in prepared.plans if plan.visual_input.kind == "video_keyframe")
    assert image.output_path.name == "image-preview.json"
    assert "analysis\\vision\\vision-v1" in str(image.output_path)
    assert video.output_path.name == "keyframe-0000.json"
    assert video.output_path.parent.name == KEYFRAME_FP


def test_atomic_output_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "nested" / "result.json"
    write_json_atomic(target, {"ok": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert list(target.parent.glob("*.tmp")) == []


def test_only_complete_valid_success_result_is_reused(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    plan = prepared.plans[0]
    payload = success_payload(
        prepared.workspace,
        prepared.config,
        prepared.configuration_fingerprint,
        plan.visual_input,
        [{"attempt": 0, "kind": "initial", "raw_model_response": "{}", "validation_errors": []}],
        canonical_result(),
        {"total_seconds": 1.0, "model_seconds": 0.9, "attempts": 1},
    )
    write_json_atomic(plan.output_path, payload)
    assert read_reusable_result(
        prepared.workspace,
        plan.output_path,
        prepared.config,
        prepared.configuration_fingerprint,
        plan.visual_input,
    ) is not None
    payload["result"]["vision"]["people"]["crowd"] = "false"
    write_json_atomic(plan.output_path, payload)
    assert read_reusable_result(
        prepared.workspace,
        plan.output_path,
        prepared.config,
        prepared.configuration_fingerprint,
        plan.visual_input,
    ) is None


def test_malformed_or_failed_result_is_not_reused(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    plan = prepared.plans[0]
    plan.output_path.parent.mkdir(parents=True)
    plan.output_path.write_text("not-json", encoding="utf-8")
    again = prepare_workspace(prepared.workspace.workspace, VisionConfig())
    assert again.plans[0].action == "process"


def test_success_with_incomplete_attempt_audit_is_not_reused(workspace_factory):
    prepared = prepare_workspace(workspace_factory(), VisionConfig())
    plan = prepared.plans[0]
    payload = success_payload(
        prepared.workspace,
        prepared.config,
        prepared.configuration_fingerprint,
        plan.visual_input,
        [{"attempt": 0, "kind": "initial", "raw_model_response": "{}", "validation_errors": []}],
        canonical_result(),
        {"total_seconds": 1.0, "model_seconds": 0.9, "attempts": 1},
    )
    payload["result"]["attempts"] = [{"attempt": 0}]
    write_json_atomic(plan.output_path, payload)
    again = prepare_workspace(prepared.workspace.workspace, VisionConfig())
    assert again.plans[0].action == "process"
    plan.output_path.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    again = prepare_workspace(prepared.workspace.workspace, VisionConfig())
    assert again.plans[0].action == "process"
