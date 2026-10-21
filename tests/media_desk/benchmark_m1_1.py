"""Reproducible M1.1 API benchmark; not collected by pytest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time

from fastapi.testclient import TestClient

from conftest import WorkspaceBuilder
from media_desk.web import create_app


def build_workspace(root: Path, count: int) -> Path:
    builder = WorkspaceBuilder(root / "workspace", root / "originals")
    for index in range(1, count + 1):
        entry = builder.add_asset(
            index,
            "video" if index % 7 == 0 else "image",
            preview=index <= 20,
            original=False,
        )
        metadata = builder.root / entry["metadata_location"]
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        year, month, day = 2012 + index % 15, 1 + index % 12, 1 + index % 28
        payload["capture"]["datetime"] = f"{year:04d}-{month:02d}-{day:02d}T20:00:00+02:00"
        metadata.write_text(json.dumps(payload), encoding="utf-8")
    return builder.publish()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * quantile))]


def run(count: int, requests: int, keep: Path | None) -> dict:
    temporary = None
    if keep is None:
        temporary = tempfile.TemporaryDirectory(prefix="media-desk-m1-1-")
        root = Path(temporary.name)
    else:
        root = keep
        root.mkdir(parents=True, exist_ok=True)
    workspace = root / "workspace"
    if not (workspace / "workspace.json").is_file():
        workspace = build_workspace(root, count)
    started = time.perf_counter()
    app = create_app(workspace)
    startup_ms = (time.perf_counter() - started) * 1000
    client = TestClient(app)
    client.get("/api/assets", params={"limit": 50})
    samples = []
    for index in range(requests):
        tick = time.perf_counter()
        response = client.get(
            "/api/assets", params={"limit": 50, "start": index * 50 % count}
        )
        response.raise_for_status()
        samples.append((time.perf_counter() - tick) * 1000)
    tick = time.perf_counter()
    located = client.get("/api/locate", params={"year": 2012, "month": 4})
    located.raise_for_status()
    locate_ms = (time.perf_counter() - tick) * 1000
    result = {
        "asset_count": count,
        "requests": requests,
        "startup_ms": round(startup_ms, 3),
        "batch_p50_ms": round(statistics.median(samples), 3),
        "batch_p95_ms": round(percentile(samples, 0.95), 3),
        "batch_max_ms": round(max(samples), 3),
        "remote_month_locator_ms": round(locate_ms, 3),
        "workspace": str(workspace) if keep else None,
    }
    if temporary:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=int, default=5000)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.assets, args.requests, args.keep), indent=2))
