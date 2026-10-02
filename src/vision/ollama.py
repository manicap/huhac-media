from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from vision.models import VisionConfig
from vision.schema import VISION_JSON_SCHEMA


class OllamaError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or {}


class OllamaClient:
    def __init__(self, endpoint: str, config: VisionConfig, timeout_s: float = 180.0):
        endpoint = endpoint.rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Ollama endpoint must be an absolute HTTP(S) URL")
        self.endpoint = endpoint
        self.config = config
        self.timeout_s = timeout_s

    def _json_request(
        self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.endpoint + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            diagnostics = {"status": exc.code}
            try:
                diagnostics["body"] = exc.read().decode("utf-8", errors="replace")[-4096:]
            except OSError:
                pass
            raise OllamaError("OLLAMA_HTTP_ERROR", f"Ollama returned HTTP {exc.code}", diagnostics) from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise OllamaError("OLLAMA_UNAVAILABLE", f"Cannot reach Ollama at {self.endpoint}: {exc}") from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OllamaError("OLLAMA_INVALID_RESPONSE", "Ollama returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise OllamaError("OLLAMA_INVALID_RESPONSE", "Ollama response is not an object")
        return decoded

    def require_model(self) -> dict[str, Any]:
        response = self._json_request("/api/tags")
        models = response.get("models")
        if not isinstance(models, list):
            raise OllamaError("OLLAMA_INVALID_RESPONSE", "Ollama model list is invalid")
        for item in models:
            if not isinstance(item, dict):
                continue
            names = {item.get("name"), item.get("model")}
            if self.config.model in names:
                return item
        raise OllamaError(
            "MODEL_UNAVAILABLE",
            f"Ollama model is not installed: {self.config.model}. The processor will not download it.",
        )

    def analyze(self, image_path: Path, prompt: str) -> str:
        try:
            image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise OllamaError("INPUT_UNREADABLE", f"Cannot read visual input: {image_path}: {exc}") from exc
        response = self._json_request(
            "/api/chat",
            method="POST",
            payload={
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt, "images": [image]}],
                "stream": False,
                "think": self.config.think,
                "format": VISION_JSON_SCHEMA,
                "options": {
                    "temperature": self.config.temperature,
                    "num_ctx": self.config.num_ctx,
                    "num_predict": self.config.num_predict,
                },
            },
        )
        diagnostics = _response_diagnostics(response)
        if "error" in response:
            raise OllamaError(
                "OLLAMA_RESPONSE_ERROR",
                "Ollama returned an error in an HTTP 200 response",
                diagnostics,
            )
        if response.get("done") is not True:
            raise OllamaError(
                "OLLAMA_INCOMPLETE_RESPONSE",
                "Ollama response did not complete",
                diagnostics,
            )
        done_reason = response.get("done_reason")
        if done_reason is not None and not isinstance(done_reason, str):
            raise OllamaError(
                "OLLAMA_INVALID_RESPONSE",
                "Ollama response has an invalid done_reason",
                diagnostics,
            )
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaError(
                "OLLAMA_INVALID_RESPONSE",
                "Ollama response has no message content",
                diagnostics,
            )
        return content


def _response_diagnostics(response: dict[str, Any]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    done = response.get("done")
    if isinstance(done, bool):
        diagnostics["done"] = done
    done_reason = response.get("done_reason")
    if isinstance(done_reason, str):
        diagnostics["done_reason"] = done_reason
    message = response.get("message")
    thinking = message.get("thinking") if isinstance(message, dict) else None
    if isinstance(thinking, str):
        diagnostics["thinking_length"] = len(thinking)
    for source, target in (
        ("total_duration", "total_duration_ns"),
        ("load_duration", "load_duration_ns"),
        ("prompt_eval_duration", "prompt_eval_duration_ns"),
        ("eval_duration", "eval_duration_ns"),
        ("prompt_eval_count", "prompt_eval_count"),
        ("eval_count", "eval_count"),
    ):
        value = response.get(source)
        if not isinstance(value, bool) and isinstance(value, int) and value >= 0:
            diagnostics[target] = value
    return diagnostics
