import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from video_keyframes.cli import main
from video_keyframes.models import KeyframeConfig
from video_keyframes.service import execute_prepared, prepare_workspace
from video_keyframes.tools import ToolError


pytestmark = pytest.mark.integration


class FakeProbe:
    def __init__(self, duration: float = 3.0):
        self.value = duration
        self.calls = 0

    def duration(self, source: Path) -> float:
        self.calls += 1
        return self.value


class FakeFFmpeg:
    def __init__(self, *, fail_name: str | None = None):
        self.fail_name = fail_name
        self.calls = 0

    def extract_png(self, source: Path, timestamp_s: float, target: Path, max_dimension: int):
        self.calls += 1
        if self.fail_name and source.name == self.fail_name:
            raise ToolError("BROKEN_VIDEO", "synthetic decode failure")
        color = (round(timestamp_s * 50) % 255, 20, 30)
        Image.new("RGB", (320, 180), color).save(target)


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, paths: tuple[Path, ...]):
        self.calls += 1
        return np.array([[1.0, index * 0.01] for index in range(len(paths))])


class InterruptingEmbedder:
    def embed(self, paths: tuple[Path, ...]):
        raise KeyboardInterrupt


def test_process_reuse_and_temporary_cleanup(keyframe_workspace_factory) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    config = KeyframeConfig(coverage_similarity=0.8)
    prepared = prepare_workspace(workspace_path, config)
    probe = FakeProbe()
    ffmpeg = FakeFFmpeg()
    embedder = FakeEmbedder()

    result = execute_prepared(
        prepared, dry_run=False, ffprobe=probe, ffmpeg=ffmpeg, embedder=embedder
    )

    assert (result.processed, result.reused, result.failed) == (1, 0, 0)
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["result"]["sampling"]["sample_count"] == 3
    assert len(payload["result"]["keyframes"]) == 1
    keyframe = workspace_path / payload["result"]["keyframes"][0]["location"]
    assert keyframe.is_file()
    assert not list((workspace_path / "analysis").rglob("sample-*.jpg"))
    assert not list((workspace_path / "analysis").rglob("decoded-*.png"))
    assert not list((workspace_path / "analysis").rglob("*.tmp"))

    repeated = prepare_workspace(workspace_path, config)
    assert repeated.plans[0].action == "reuse"
    second = execute_prepared(repeated, dry_run=False)
    assert (second.processed, second.reused, second.failed) == (0, 1, 0)
    assert probe.calls == 1
    assert embedder.calls == 1


def test_one_failed_asset_does_not_stop_other_video(keyframe_workspace_factory) -> None:
    workspace_path, _ = keyframe_workspace_factory(
        [
            {"relative_path": "broken.mp4"},
            {"relative_path": "good.mp4"},
        ]
    )
    prepared = prepare_workspace(workspace_path, KeyframeConfig())

    result = execute_prepared(
        prepared,
        dry_run=False,
        ffprobe=FakeProbe(1.0),
        ffmpeg=FakeFFmpeg(fail_name="broken.mp4"),
        embedder=FakeEmbedder(),
    )

    assert result.processed == 1
    assert result.failed == 1
    payloads = [json.loads(plan.output_path.read_text(encoding="utf-8")) for plan in prepared.plans]
    assert {payload["status"] for payload in payloads} == {"success", "failed"}
    failed = next(payload for payload in payloads if payload["status"] == "failed")
    assert failed["error"]["code"] == "BROKEN_VIDEO"
    assert failed["result"] is None


def test_dry_run_never_invokes_tools_or_creates_analysis(
    keyframe_workspace_factory, capsys
) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])

    exit_code = main(
        [
            "analyze",
            "--workspace",
            str(workspace_path),
            "--dry-run",
            "--json",
            "--ffmpeg",
            "definitely-missing-ffmpeg",
            "--ffprobe",
            "definitely-missing-ffprobe",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["would_process"] == 1
    assert report["assets"][0]["action"] == "process"
    assert not (workspace_path / "analysis").exists()


def test_unavailable_source_is_reported_without_tool_work(
    keyframe_workspace_factory,
) -> None:
    workspace_path, _ = keyframe_workspace_factory([{"create_source": False}])
    prepared = prepare_workspace(workspace_path, KeyframeConfig())

    result = execute_prepared(prepared, dry_run=False)

    assert result.failed == 1
    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert payload["error"]["code"] == "SOURCE_UNAVAILABLE"


def test_changed_source_bytes_fail_before_decode(keyframe_workspace_factory) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    prepared = prepare_workspace(workspace_path, KeyframeConfig())
    assert prepared.plans[0].asset.source is not None
    prepared.plans[0].asset.source.absolute_path.write_bytes(b"changed after ingest")
    ffmpeg = FakeFFmpeg()

    result = execute_prepared(
        prepared,
        dry_run=False,
        ffprobe=FakeProbe(),
        ffmpeg=ffmpeg,
        embedder=FakeEmbedder(),
    )

    payload = json.loads(prepared.plans[0].output_path.read_text(encoding="utf-8"))
    assert result.failed == 1
    assert payload["error"]["code"] == "SOURCE_IDENTITY_MISMATCH"
    assert ffmpeg.calls == 0


def test_interrupted_processing_is_not_published_as_complete(
    keyframe_workspace_factory,
) -> None:
    workspace_path, _ = keyframe_workspace_factory([{}])
    prepared = prepare_workspace(workspace_path, KeyframeConfig())

    with pytest.raises(KeyboardInterrupt):
        execute_prepared(
            prepared,
            dry_run=False,
            ffprobe=FakeProbe(1.0),
            ffmpeg=FakeFFmpeg(),
            embedder=InterruptingEmbedder(),
        )

    assert not prepared.plans[0].output_path.exists()
    assert not list((workspace_path / "analysis").rglob("sample-*.jpg"))
    assert not list((workspace_path / "analysis").rglob("decoded-*.png"))
