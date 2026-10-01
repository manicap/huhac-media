from __future__ import annotations

import json

from vision.cli import _print_report, _report, main
from vision.models import VisionConfig
from vision.ollama import OllamaClient, OllamaError
from vision.prompt import initial_prompt
from vision.service import execute_prepared, prepare_workspace

from conftest import canonical_result


def test_cli_dry_run_does_not_require_ollama(workspace_factory, monkeypatch, capsys):
    workspace = workspace_factory()
    monkeypatch.setattr(
        OllamaClient,
        "require_model",
        lambda self: (_ for _ in ()).throw(AssertionError("Ollama contacted")),
    )
    code = main(["analyze", "--workspace", str(workspace), "--dry-run", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["would_process"] == 2


def test_missing_model_produces_clear_fatal_error(workspace_factory, monkeypatch, capsys):
    workspace = workspace_factory(keyframes=False)
    monkeypatch.setattr(
        OllamaClient,
        "require_model",
        lambda self: (_ for _ in ()).throw(OllamaError("MODEL_UNAVAILABLE", "model absent; no download")),
    )
    code = main(["analyze", "--workspace", str(workspace)])
    assert code == 3
    output = capsys.readouterr().out
    assert "MODEL_UNAVAILABLE" in output
    assert "no download" in output


def test_ollama_payload_uses_image_and_deterministic_options(tmp_path, monkeypatch):
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"image")
    client = OllamaClient("http://localhost:11434", VisionConfig())
    captured = {}

    def fake_request(path, *, method="GET", payload=None):
        captured.update(path=path, method=method, payload=payload)
        return {"message": {"content": "{}"}}

    monkeypatch.setattr(client, "_json_request", fake_request)
    assert client.analyze(image, "prompt") == "{}"
    assert captured["path"] == "/api/chat"
    assert captured["payload"]["options"]["temperature"] == 0.0
    assert captured["payload"]["messages"][0]["images"]
    assert "ffmpeg" not in json.dumps(captured).casefold()


def test_prompt_v2_forbids_text_content_and_activity_inference():
    prompt = " ".join(initial_prompt().split())
    assert "Do not read, transcribe, quote, interpret, or use visible text" in prompt
    assert "brand names, logos, signs, posters, labels, screens" in prompt
    assert "Do not include the contents or inferred meaning of visible text" in prompt
    assert "including scene, activities, objects, environment" in prompt
    assert "Activities must describe actions visibly being performed" in prompt
    assert "Do not infer an activity merely from objects, equipment, furniture" in prompt


def test_human_progress_is_printed_for_actual_processing(workspace_factory, monkeypatch, capsys):
    workspace = workspace_factory(keyframes=False)
    monkeypatch.setattr(OllamaClient, "require_model", lambda self: {})
    monkeypatch.setattr(
        OllamaClient, "analyze", lambda self, path, prompt: json.dumps(canonical_result())
    )
    code = main(["analyze", "--workspace", str(workspace)])
    output = capsys.readouterr().out
    assert code == 1  # the fixture deliberately has no video keyframe result
    assert "[1/1] image_preview" in output
    assert "Timing:" in output


def test_json_mode_is_not_contaminated_by_progress(workspace_factory, monkeypatch, capsys):
    workspace = workspace_factory(keyframes=False)
    monkeypatch.setattr(OllamaClient, "require_model", lambda self: {})
    monkeypatch.setattr(
        OllamaClient, "analyze", lambda self, path, prompt: json.dumps(canonical_result())
    )
    main(["analyze", "--workspace", str(workspace), "--json"])
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["processed"] == 1
    assert "[1/" not in output


def test_reuse_only_summary_has_zero_totals_and_no_division_by_zero(
    workspace_factory, capsys
):
    workspace = workspace_factory(keyframes=False)

    class Model:
        def analyze(self, path, prompt):
            return json.dumps(canonical_result())

    first = prepare_workspace(workspace, VisionConfig())
    execute_prepared(first, dry_run=False, model=Model())
    reused = execute_prepared(
        prepare_workspace(workspace, VisionConfig()), dry_run=False, model=Model()
    )
    report = _report(reused)
    assert report["timing"] == {
        "total_seconds": 0,
        "model_seconds": 0,
        "attempts": 0,
        "timed_input_count": 0,
        "average_processed_seconds": None,
        "min_processed_seconds": None,
        "max_processed_seconds": None,
    }
    _print_report(report)
    assert "Avg processed:  n/a" in capsys.readouterr().out


def test_cli_dry_run_force_reports_reusable_inputs_as_process(
    workspace_factory, monkeypatch, capsys
):
    workspace = workspace_factory()

    class Model:
        def analyze(self, path, prompt):
            return json.dumps(canonical_result())

    execute_prepared(
        prepare_workspace(workspace, VisionConfig()), dry_run=False, model=Model()
    )
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    monkeypatch.setattr(
        OllamaClient,
        "require_model",
        lambda self: (_ for _ in ()).throw(AssertionError("Ollama contacted")),
    )
    code = main(
        [
            "analyze",
            "--workspace",
            str(workspace),
            "--dry-run",
            "--force",
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["force"] is True
    assert report["would_process"] == 2
    assert report["would_reuse"] == 0
    assert before == {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
