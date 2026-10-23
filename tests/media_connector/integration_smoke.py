from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from media_desk.config import Settings
from media_desk.web import create_app


def _run(arguments: list[str], root: Path) -> tuple[float, str]:
    started = time.perf_counter()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[2] / "src")
    completed = subprocess.run(
        [sys.executable, *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {arguments}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return elapsed, completed.stdout.strip()


def _source_snapshot(root: Path) -> dict[str, tuple[str, int, int]]:
    return {
        path.relative_to(root).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _make_media(source: Path) -> None:
    image = Image.new("RGB", (96, 64), (190, 30, 60))
    image.save(source / "photo-original.jpg", quality=92)
    (source / "renamed-duplicate.jpeg").write_bytes((source / "photo-original.jpg").read_bytes())
    Image.new("RGB", (80, 50), (20, 120, 210)).save(source / "graphic.png")
    Image.new("RGB", (72, 54), (40, 180, 80)).save(source / "web-image.webp")
    Image.new("RGB", (64, 48), (230, 180, 20)).save(source / "scan.tiff")

    frames = []
    for index in range(10):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:, :, 0] = index * 20
        frame[:, :, 1] = 180 - index * 10
        frame[:, :, 2] = 40 + index * 15
        frames.append(frame)
    for filename, fourcc in (
        ("clip.avi", "MJPG"),
        ("clip.mp4", "mp4v"),
        ("clip.mov", "mp4v"),
        ("clip.mkv", "MJPG"),
    ):
        writer = cv2.VideoWriter(str(source / filename), cv2.VideoWriter_fourcc(*fourcc), 5.0, (64, 48))
        if not writer.isOpened():
            raise RuntimeError(f"OpenCV cannot create {filename}")
        for frame in frames:
            writer.write(frame)
        writer.release()


def _fake_ffprobe(path: Path) -> None:
    path.write_text(
        "@echo off\r\n"
        "if \"%~1\"==\"-version\" (echo ffprobe synthetic-smoke 1.0& exit /b 0)\r\n"
        "echo {\"format\":{\"format_name\":\"synthetic\",\"duration\":\"2.0\",\"bit_rate\":\"1000\"},"
        "\"streams\":[{\"codec_type\":\"video\",\"codec_name\":\"synthetic\",\"width\":64,\"height\":48,"
        "\"avg_frame_rate\":\"5/1\"}]}\r\n",
        encoding="ascii",
    )


def run(exiftool: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="huhac-connector-smoke-") as temporary:
        root = Path(temporary)
        source = root / "external-source"
        storage = root / "media-storage"
        workspace = root / "workspace"
        state = root / "connector-state"
        work = root / "transfer-work"
        source.mkdir()
        _make_media(source)
        source_before = _source_snapshot(source)
        timings: dict[str, float] = {}

        timings["init_preflight_seconds"], init_preflight_output = _run(
            ["-m", "huhac_media", "init", "--storage", str(storage), "--workspace", str(workspace), "--preflight", "--json"],
            root,
        )
        init_preflight = json.loads(init_preflight_output)
        timings["init_seconds"], init_output = _run(
            ["-m", "huhac_media", "init", "--storage", str(storage), "--workspace", str(workspace),
             "--operation-id", init_preflight["operation_id"], "--yes", "--json"],
            root,
        )
        init_result = json.loads(init_output)
        if init_result["state"] != "ready":
            raise AssertionError(init_result)

        timings["discovery_seconds"], discovery_output = _run(
            ["-m", "media_connector", "local-discovery", "--workspace", str(workspace),
             "--source-root", str(source), "--page-size", "100"],
            root,
        )
        discovery = json.loads(discovery_output)
        if discovery["page"]["returned_count"] != len(source_before):
            raise AssertionError(discovery)

        state.mkdir()
        work.mkdir()
        selection_path = root / "selection.json"
        selection_path.write_text(
            json.dumps(
                {
                    "contract": "huhac.media-connector.transfer-selection",
                    "contract_version": 1,
                    "workspace_id": discovery["library"]["workspace_id"],
                    "source": discovery["source"],
                    "items": [
                        {
                            "object_id": item["object_id"],
                            "version_token": item["version_token"],
                            "logical_path": item["logical_path"],
                        }
                        for item in discovery["page"]["items"]
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        common = [
            "--workspace", str(workspace), "--media-storage", str(storage),
            "--state-root", str(state), "--transfer-work-root", str(work),
            "--selection", str(selection_path),
        ]
        timings["transfer_preflight_seconds"], transfer_preflight_output = _run(
            ["-m", "media_connector", "transfer", "preflight", *common], root
        )
        transfer_preflight = json.loads(transfer_preflight_output)
        if transfer_preflight["preflight"]["writes_performed"] is not False:
            raise AssertionError(transfer_preflight)
        timings["transfer_seconds"], transfer_output = _run(
            ["-m", "media_connector", "transfer", "run", *common,
             "--operation-id", str(uuid4()), "--yes"],
            root,
        )
        transfer = json.loads(transfer_output)
        transfer_items = transfer["run"]["items"]
        hashes = [item["content_sha256"] for item in transfer_items]
        payloads = list((storage / "objects" / "sha256").rglob("payload.*"))
        if len(hashes) - len(set(hashes)) != 1:
            raise AssertionError("the synthetic duplicate was not identified by content")
        if len(payloads) != len(set(hashes)):
            raise AssertionError("physical content deduplication failed")
        if sum(item["status"] == "deduplicated_existing" for item in transfer_items) != 1:
            raise AssertionError(transfer_items)

        fake_ffprobe = root / "ffprobe-smoke.cmd"
        _fake_ffprobe(fake_ffprobe)
        config = root / "ingest.toml"
        config.write_text(
            f"input = '{storage}'\nwork = '{workspace}'\ninteractive = false\nwarn_existing_workdir = false\n"
            f"[tools]\nexiftool = '{exiftool}'\nffprobe = '{fake_ffprobe}'\nffmpeg = 'missing-ffmpeg-smoke'\n",
            encoding="utf-8",
        )
        timings["ingest_seconds"], ingest_output = _run(
            ["-m", "huhac_media", "ingest", "--config", str(config), "--yes", "--no-warn-existing-workdir"],
            root,
        )

        catalog = json.loads((workspace / "metadata" / "catalog.json").read_text(encoding="utf-8"))
        assets = catalog["assets"]
        if len(assets) != len(set(hashes)):
            raise AssertionError("catalog does not contain one asset per unique content hash")
        image_assets = [asset for asset in assets if asset["media_type"] == "image"]
        video_assets = [asset for asset in assets if asset["media_type"] == "video"]
        for asset in image_assets:
            preview = workspace / asset["preview_location"]
            if not preview.is_file():
                raise AssertionError(f"missing preview: {preview}")
            with Image.open(preview) as opened:
                opened.verify()
        if any(asset["preview_location"] is not None for asset in video_assets):
            raise AssertionError("video unexpectedly has an image preview")
        if any(
            not source_item["relative_path"].startswith("objects/sha256/")
            for asset in assets
            for source_item in asset["sources"]
            if source_item["status"] == "active"
        ):
            raise AssertionError("catalog contains a non-CAS source path")

        desk_started = time.perf_counter()
        app = create_app(settings=Settings(workspace=workspace, workspace_source="cli"))
        with TestClient(app) as client:
            health = client.get("/health")
            overview = client.get("/")
            library = client.get("/library")
            api = client.get("/api/assets?limit=50")
            if (health.status_code, overview.status_code, library.status_code, api.status_code) != (200, 200, 200, 200):
                raise AssertionError("Media Desk did not open the generated workspace")
            api_items = api.json()["items"]
            if len(api_items) != len(assets):
                raise AssertionError("Media Desk asset count differs from the catalog")
            image_item = next(item for item in api_items if item["media_type"] == "image")
            video_item = next(item for item in api_items if item["media_type"] == "video")
            if client.get(image_item["preview_url"]).status_code != 200:
                raise AssertionError("Media Desk preview is unavailable")
            range_response = client.get(video_item["original_url"], headers={"Range": "bytes=0-99"})
            if range_response.status_code != 206 or len(range_response.content) != 100:
                raise AssertionError("Media Desk video range access failed")
        timings["media_desk_seconds"] = time.perf_counter() - desk_started

        source_after = _source_snapshot(source)
        if source_after != source_before:
            raise AssertionError("external source changed during workflow")

        suffixes = sorted(path.suffix for path in payloads)
        expected_suffixes = [".avi", ".jpg", ".mkv", ".mov", ".mp4", ".png", ".tif", ".webp"]
        if suffixes != expected_suffixes:
            raise AssertionError(f"unexpected canonical suffixes: {suffixes}")
        return {
            "status": "success",
            "workspace_contract_version": json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))["workspace_contract_version"],
            "source_files": len(source_before),
            "source_unchanged": True,
            "transfer_items": len(transfer_items),
            "unique_content_objects": len(payloads),
            "deduplicated_items": sum(item["status"] == "deduplicated_existing" for item in transfer_items),
            "canonical_suffixes": suffixes,
            "catalog_assets": len(assets),
            "image_assets": len(image_assets),
            "video_assets": len(video_assets),
            "validated_previews": len(image_assets),
            "media_desk": {"health": 200, "overview": 200, "library": 200, "api_assets": len(assets), "video_range": 206},
            "timings_seconds": {key: round(value, 6) for key, value in timings.items()},
            "tooling": {"exiftool": str(exiftool), "ffprobe": "synthetic stub", "video_generator": f"OpenCV {cv2.__version__}"},
            "ingest_stdout_tail": ingest_output.splitlines()[-1],
        }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: integration_smoke.py <path-to-exiftool>")
    print(json.dumps(run(Path(sys.argv[1]).resolve(strict=True)), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
