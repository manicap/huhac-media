from __future__ import annotations

import json

from vision.cli import main
from vision.models import VisionConfig
from vision.ollama import OllamaClient, OllamaError


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
