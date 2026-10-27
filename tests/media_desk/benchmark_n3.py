"""Reproducible Normalizer N3 off/on benchmark; not collected by pytest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc

from fastapi.testclient import TestClient

from benchmark_m1_1 import build_workspace
from media_desk.config import Settings
from media_desk.web import create_app
from normalizer.service import analyze_workspace


def _measure(settings: Settings, requests: int, facet: bool) -> dict:
    tracemalloc.start()
    started = time.perf_counter()
    app = create_app(settings=settings)
    startup_ms = (time.perf_counter() - started) * 1000
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    client = TestClient(app)
    params: dict[str, object] = {"limit": 50}
    if facet:
        params["tags"] = "benchmark-missing-exact-value"
    samples = []
    for index in range(requests):
        params["start"] = index * 50
        tick = time.perf_counter()
        response = client.get("/api/assets", params=params)
        response.raise_for_status()
        samples.append((time.perf_counter() - tick) * 1000)
    return {
        "startup_ms": round(startup_ms, 3),
        "peak_python_mib": round(peak / 1024 / 1024, 3),
        "batch_p50_ms": round(statistics.median(samples), 3),
        "batch_p95_ms": round(sorted(samples)[min(len(samples) - 1, int(len(samples) * .95))], 3),
    }


def run(count: int, requests: int, keep: Path | None) -> dict:
    temporary = None
    if keep is None:
        temporary = tempfile.TemporaryDirectory(prefix="media-desk-n3-")
        root = Path(temporary.name)
    else:
        root = keep
        root.mkdir(parents=True, exist_ok=True)
    workspace = root / "workspace"
    if not (workspace / "workspace.json").is_file():
        workspace = build_workspace(root, count)
    analysis = analyze_workspace(workspace)
    off = _measure(Settings(workspace=workspace), requests, False)
    on_settings = Settings(
        workspace=workspace,
        normalizer_configuration_fingerprint=analysis.prepared.configuration_fingerprint,
        normalizer_input_set_fingerprint=analysis.prepared.input_set_fingerprint,
    )
    on = _measure(on_settings, requests, False)
    facet = _measure(on_settings, requests, True)
    result = {"asset_count": count, "requests": requests, "off": off, "on": on,
              "exact_facet_no_match": facet,
              "startup_delta_ms": round(on["startup_ms"] - off["startup_ms"], 3),
              "peak_delta_mib": round(on["peak_python_mib"] - off["peak_python_mib"], 3),
              "workspace": str(workspace) if keep else None}
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=int, default=5000)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.assets, args.requests, args.keep), indent=2))
