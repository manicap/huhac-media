from __future__ import annotations

import json

import pytest

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
        return {
            "message": {"role": "assistant", "content": "{}"},
            "done": True,
            "done_reason": "stop",
        }

    monkeypatch.setattr(client, "_json_request", fake_request)
    assert client.analyze(image, "prompt") == "{}"
    assert captured["path"] == "/api/chat"
    assert captured["payload"]["think"] is False
    assert "keep_alive" not in captured["payload"]
    assert captured["payload"]["options"]["temperature"] == 0.0
    assert captured["payload"]["messages"][0]["images"]
    assert "ffmpeg" not in json.dumps(captured).casefold()


def _analyze_response(tmp_path, monkeypatch, response):
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"private-image-bytes")
    client = OllamaClient("http://localhost:11434", VisionConfig())
    monkeypatch.setattr(client, "_json_request", lambda *args, **kwargs: response)
    return client.analyze(image, "prompt containing private details")


def test_done_response_with_content_succeeds(tmp_path, monkeypatch):
    content = _analyze_response(
        tmp_path,
        monkeypatch,
        {
            "message": {"role": "assistant", "content": '{"scene":"room"}'},
            "done": True,
            "done_reason": "stop",
        },
    )
    assert content == '{"scene":"room"}'


def test_empty_content_fails(tmp_path, monkeypatch):
    with pytest.raises(OllamaError, match="no message content") as captured:
        _analyze_response(
            tmp_path,
            monkeypatch,
            {"message": {"role": "assistant", "content": "  "}, "done": True},
        )
    assert captured.value.code == "OLLAMA_INVALID_RESPONSE"


def test_thinking_is_not_used_as_content_and_only_length_is_diagnostic(
    tmp_path, monkeypatch
):
    secret_thinking = "private chain of thought"
    with pytest.raises(OllamaError) as captured:
        _analyze_response(
            tmp_path,
            monkeypatch,
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": secret_thinking,
                },
                "done": True,
                "done_reason": "length",
            },
        )
    assert captured.value.diagnostics == {
        "done": True,
        "done_reason": "length",
        "thinking_length": len(secret_thinking),
    }
    assert secret_thinking not in json.dumps(captured.value.diagnostics)


def test_done_false_is_captured(tmp_path, monkeypatch):
    with pytest.raises(OllamaError) as captured:
        _analyze_response(
            tmp_path,
            monkeypatch,
            {"message": {"content": "ignored"}, "done": False},
        )
    assert captured.value.code == "OLLAMA_INCOMPLETE_RESPONSE"
    assert captured.value.diagnostics["done"] is False


def test_top_level_error_in_http_200_is_captured_without_error_text(
    tmp_path, monkeypatch
):
    with pytest.raises(OllamaError) as captured:
        _analyze_response(
            tmp_path,
            monkeypatch,
            {"error": "sensitive server detail", "done": False},
        )
    assert captured.value.code == "OLLAMA_RESPONSE_ERROR"
    assert captured.value.diagnostics == {"done": False}
    assert "sensitive server detail" not in str(captured.value)


def test_ollama_timing_and_token_metadata_use_safe_diagnostic_names(
    tmp_path, monkeypatch
):
    response = {
        "message": {
            "content": "",
            "thinking": "do not persist this thinking text",
            "images": ["base64-secret"],
        },
        "done": True,
        "done_reason": "length",
        "total_duration": 9_000_000_000,
        "load_duration": 2_000_000_000,
        "prompt_eval_count": 100,
        "prompt_eval_duration": 3_000_000_000,
        "eval_count": 50,
        "eval_duration": 4_000_000_000,
    }
    with pytest.raises(OllamaError) as captured:
        _analyze_response(tmp_path, monkeypatch, response)
    assert captured.value.diagnostics == {
        "done": True,
        "done_reason": "length",
        "thinking_length": 33,
        "total_duration_ns": 9_000_000_000,
        "load_duration_ns": 2_000_000_000,
        "prompt_eval_duration_ns": 3_000_000_000,
        "eval_duration_ns": 4_000_000_000,
        "prompt_eval_count": 100,
        "eval_count": 50,
    }
    serialized = json.dumps(captured.value.diagnostics)
    assert "base64-secret" not in serialized
    assert "do not persist" not in serialized
    assert "private-image-bytes" not in serialized


def test_safe_ollama_diagnostics_are_persisted_on_input_failure(
    workspace_factory, monkeypatch
):
    workspace = workspace_factory(keyframes=False)
    prepared = prepare_workspace(workspace, VisionConfig())
    client = OllamaClient("http://localhost:11434", VisionConfig())
    monkeypatch.setattr(
        client,
        "_json_request",
        lambda *args, **kwargs: {
            "message": {"content": "", "thinking": "secret thinking"},
            "done": False,
            "total_duration": 123,
            "eval_count": 7,
        },
    )
    result = execute_prepared(prepared, dry_run=False, model=client)
    assert result.failed == 1
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["error"]["code"] == "OLLAMA_INCOMPLETE_RESPONSE"
    assert payload["error"]["diagnostics"] == {
        "done": False,
        "thinking_length": 15,
        "total_duration_ns": 123,
        "eval_count": 7,
    }
    assert "secret thinking" not in json.dumps(payload["error"]["diagnostics"])


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
