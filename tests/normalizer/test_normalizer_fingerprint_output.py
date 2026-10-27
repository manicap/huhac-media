from __future__ import annotations

import json
from pathlib import Path

import pytest

from normalizer.contract import load_workspace
from normalizer.fingerprint import configuration_fingerprint, input_set_fingerprint
from normalizer.models import NormalizerConfig
from normalizer.output import OutputError, validate_snapshot
from normalizer.service import analyze_prepared, prepare_workspace


def test_fingerprints_ignore_absolute_source_root_and_runtime_order(workspace_factory):
    first = load_workspace(workspace_factory(reverse=False, source_root="D:\\One"))
    second = load_workspace(workspace_factory(reverse=False, source_root="/mnt/two"))
    assert input_set_fingerprint(first) == input_set_fingerprint(second)
    assert configuration_fingerprint(NormalizerConfig()) == configuration_fingerprint(NormalizerConfig())


def test_catalog_array_order_changes_input_identity_because_json_pointers_change(workspace_factory):
    first = load_workspace(workspace_factory(reverse=False))
    second = load_workspace(workspace_factory(reverse=True))
    assert input_set_fingerprint(first) != input_set_fingerprint(second)


def test_one_metadata_change_changes_input_fingerprint(workspace_factory):
    root = workspace_factory()
    before = input_set_fingerprint(load_workspace(root))
    metadata = next((root / "metadata/assets").rglob("*.json"))
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["technical"]["width"] += 1
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    after = input_set_fingerprint(load_workspace(root))
    assert before != after


def test_corrupt_metadata_bytes_are_part_of_input_fingerprint(workspace_factory):
    root = workspace_factory([{"name": "broken", "corrupt_metadata": True}])
    before = input_set_fingerprint(load_workspace(root))
    metadata = next((root / "metadata/assets").rglob("*.json"))
    metadata.write_text("{different-invalid-json", encoding="utf-8")
    after = input_set_fingerprint(load_workspace(root))
    assert before != after


def test_publish_valid_snapshot_and_repeat_reuses_without_rewrite(workspace_factory):
    root = workspace_factory()
    first = analyze_prepared(prepare_workspace(root))
    target = first.prepared.output_path
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in target.rglob("*") if path.is_file()}
    second = analyze_prepared(prepare_workspace(root))
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in target.rglob("*") if path.is_file()}
    assert first.reused is False
    assert second.reused is True
    assert before == after
    assert validate_snapshot(target)["summary"]["asset_count"] == 2


@pytest.mark.parametrize("failure_stage", ["assets_written", "manifest_written", "before_publish"])
def test_fault_injection_never_publishes_incomplete_snapshot(workspace_factory, failure_stage):
    prepared = prepare_workspace(workspace_factory())

    def fail(stage: str, path: Path) -> None:
        if stage == failure_stage:
            raise OSError("injected failure")

    with pytest.raises(OSError, match="injected"):
        analyze_prepared(prepared, stage_hook=fail)
    assert not prepared.output_path.exists()
    assert not list(prepared.output_path.parent.glob(f".{prepared.input_set_fingerprint}.*.tmp"))
    recovered = analyze_prepared(prepare_workspace(prepared.workspace.workspace))
    assert recovered.reused is False
    assert validate_snapshot(recovered.prepared.output_path)


def test_tampered_snapshot_is_fingerprint_conflict_and_is_not_overwritten(workspace_factory):
    result = analyze_prepared(prepare_workspace(workspace_factory()))
    asset_path = next((result.prepared.output_path / "assets").rglob("*.json"))
    original = asset_path.read_bytes()
    asset_path.write_text("{}", encoding="utf-8")
    with pytest.raises(OutputError, match="conflicts"):
        prepare_workspace(result.prepared.workspace.workspace)
    assert asset_path.read_text(encoding="utf-8") == "{}"
    assert original != asset_path.read_bytes()


def test_manifest_configuration_fingerprint_conflict_is_rejected(workspace_factory):
    result = analyze_prepared(prepare_workspace(workspace_factory()))
    manifest_path = result.prepared.output_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["configuration"]["safe_conversion_policy"] = "tampered-policy"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OutputError, match="conflicts"):
        prepare_workspace(result.prepared.workspace.workspace)
