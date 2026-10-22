"""Reproducible S2a.1 startup/access profiler; not collected by pytest."""

from __future__ import annotations

import argparse
from collections import Counter
import cProfile
import io
import json
import math
import os
from pathlib import Path
import pstats
import statistics
import time
import tracemalloc

from fastapi.testclient import TestClient

from media_desk import originals
from media_desk.config import ORIGINALS_MAPPING_VERIFICATION, OriginalsMapping, Settings
from media_desk.web import create_app


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * quantile) - 1))]


class OriginalIoCounter:
    def __init__(self, root: Path) -> None:
        self.root = os.path.normcase(str(root.absolute()))
        self.counts: Counter[str] = Counter()
        self._originals: dict[str, object] = {}

    def _inside(self, path: Path) -> bool:
        value = os.path.normcase(str(path.absolute()))
        return value == self.root or value.startswith(self.root + os.sep)

    def __enter__(self) -> OriginalIoCounter:
        for name in ("resolve", "stat", "exists", "is_file", "open"):
            original = getattr(Path, name)
            self._originals[name] = original

            def counted(path, *args, _name=name, _original=original, **kwargs):
                if self._inside(path):
                    self.counts[_name] += 1
                    if os.path.normcase(str(path.absolute())) != self.root:
                        self.counts[f"per_file_{_name}"] += 1
                return _original(path, *args, **kwargs)

            setattr(Path, name, counted)
        self._originals["sha256"] = originals._sha256_file

        def counted_hash(path: Path) -> str:
            if self._inside(path):
                self.counts["sha256"] += 1
            return self._originals["sha256"](path)

        originals._sha256_file = counted_hash
        return self

    def __exit__(self, *_exc) -> None:
        for name in ("resolve", "stat", "exists", "is_file", "open"):
            setattr(Path, name, self._originals[name])
        originals._sha256_file = self._originals["sha256"]


def _settings(workspace: Path, local_root: Path, count: int) -> Settings:
    return Settings(
        workspace=workspace,
        workspace_source="profile",
        originals_mapping=OriginalsMapping(
            "s2a-benchmark",
            r"D:\Archive\Huhac",
            local_root,
            ORIGINALS_MAPPING_VERIFICATION,
            min(16, count),
            count,
        ),
    )


def run(root: Path, count: int, repeats: int, profile: bool) -> dict:
    workspace = root / "workspace"
    local_root = root / "local-originals"
    if not (workspace / "workspace.json").is_file():
        raise RuntimeError("Build the dataset first with benchmark_s2a.py --keep ROOT")
    settings = _settings(workspace, local_root, count)
    startup_samples: list[float] = []
    aggregate: Counter[str] = Counter()
    apps = []
    for _index in range(repeats):
        with OriginalIoCounter(local_root) as counter:
            tick = time.perf_counter()
            app = create_app(settings=settings)
            startup_samples.append((time.perf_counter() - tick) * 1000)
        aggregate.update(counter.counts)
        apps.append(app)
    tracemalloc.start()
    create_app(settings=settings)
    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    app = apps[-1]
    client = TestClient(app)
    handler_ms = {}
    for url in ("/", "/library", "/api/index"):
        samples = []
        for _index in range(5):
            tick = time.perf_counter()
            response = client.get(url)
            response.raise_for_status()
            samples.append((time.perf_counter() - tick) * 1000)
        handler_ms[url] = {
            "samples": [round(value, 3) for value in samples],
            "p50": round(statistics.median(samples), 3),
            "p95": round(_percentile(samples, 0.95), 3),
        }

    access_ms = {}
    access_io: Counter[str] = Counter()
    for label, media_type, headers in (
        ("image_get", "image", {}),
        ("video_range", "video", {"Range": "bytes=2-5"}),
    ):
        asset = next(item for item in app.state.snapshot.assets if item.media_type == media_type)
        if asset.original is None:
            continue
        samples = []
        for _index in range(5):
            with OriginalIoCounter(local_root) as counter:
                tick = time.perf_counter()
                response = client.get(f"/artifacts/{asset.original.token}", headers=headers)
                response.raise_for_status()
                samples.append((time.perf_counter() - tick) * 1000)
            access_io.update(counter.counts)
        access_ms[label] = {
            "samples": [round(value, 3) for value in samples],
            "p50": round(statistics.median(samples), 3),
            "p95": round(_percentile(samples, 0.95), 3),
        }

    failure_ms = {}
    image = next(item for item in app.state.snapshot.assets if item.media_type == "image")
    if image.original is not None:
        url = f"/artifacts/{image.original.token}"

        def measure_failure(label: str) -> None:
            samples = []
            statuses = []
            for _index in range(5):
                tick = time.perf_counter()
                response = client.get(url)
                samples.append((time.perf_counter() - tick) * 1000)
                statuses.append(response.status_code)
            failure_ms[label] = {
                "statuses": statuses,
                "p50": round(statistics.median(samples), 3),
                "p95": round(_percentile(samples, 0.95), 3),
            }

        target = local_root.joinpath(*image.original.relative_paths[0].split("/"))
        missing = target.with_name(target.name + ".missing")
        target.rename(missing)
        try:
            measure_failure("missing_file")
        finally:
            missing.rename(target)

        offline = local_root.with_name(local_root.name + ".offline")
        local_root.rename(offline)
        try:
            measure_failure("offline_root")
        finally:
            offline.rename(local_root)

        outside = root / "outside-symlink-target.bin"
        content = target.read_bytes()
        outside.write_bytes(b"outside")
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            failure_ms["symlink_escape"] = {"status": "not available on this host"}
            target.write_bytes(content)
        else:
            try:
                measure_failure("symlink_escape")
            finally:
                target.unlink()
                target.write_bytes(content)
        finally:
            outside.unlink(missing_ok=True)

    profile_top = None
    if profile:
        profiler = cProfile.Profile()
        profiler.enable()
        create_app(settings=settings)
        profiler.disable()
        output = io.StringIO()
        pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("cumulative").print_stats(25)
        profile_top = output.getvalue()

    per_start = {name: total // repeats for name, total in aggregate.items()}
    return {
        "asset_count": count,
        "repeats": repeats,
        "cache": "first run after dataset build, then warm OS cache; no forced cache flush",
        "startup_ms": {
            "samples": [round(value, 3) for value in startup_samples],
            "p50": round(statistics.median(startup_samples), 3),
            "p95": round(_percentile(startup_samples, 0.95), 3),
        },
        "original_io_per_start": per_start,
        "first_response_ms": handler_ms,
        "original_access_ms": access_ms,
        "original_access_io_total": dict(access_io),
        "failure_access_ms": failure_ms,
        "python_peak_tracemalloc_mib": round(peak_bytes / 1024 / 1024, 3),
        "profile_top": profile_top,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--assets", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.assets, args.repeats, args.profile), indent=2))
