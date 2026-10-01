from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Sequence


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or {}


class CommandRunner:
    def available(self, executable: str) -> bool:
        return shutil.which(executable) is not None

    def run(self, arguments: Sequence[str], timeout: float) -> str:
        command = tuple(str(argument) for argument in arguments)
        try:
            completed = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ToolError("TOOL_UNAVAILABLE", f"Executable not found: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolError("TOOL_TIMEOUT", f"Tool timed out: {command[0]}") from exc
        if completed.returncode != 0:
            raise ToolError(
                "TOOL_FAILED",
                f"{command[0]} exited with code {completed.returncode}",
                {"returncode": completed.returncode, "stderr": completed.stderr[-16384:]},
            )
        return completed.stdout


class FFprobe:
    def __init__(self, executable: str = "ffprobe", runner: CommandRunner | None = None):
        self.executable = executable
        self.runner = runner or CommandRunner()

    def available(self) -> bool:
        return self.runner.available(self.executable)

    def duration(self, source: Path) -> float:
        stdout = self.runner.run(
            [
                self.executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(source),
            ],
            timeout=120,
        )
        try:
            value = float(json.loads(stdout)["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ToolError("INVALID_DURATION", "ffprobe did not return a valid duration") from exc
        if not 0 < value < float("inf"):
            raise ToolError("INVALID_DURATION", f"Invalid video duration: {value!r}")
        return value


class FFmpeg:
    def __init__(self, executable: str = "ffmpeg", runner: CommandRunner | None = None):
        self.executable = executable
        self.runner = runner or CommandRunner()

    def available(self) -> bool:
        return self.runner.available(self.executable)

    def extract_png(
        self, source: Path, timestamp_s: float, target: Path, max_dimension: int
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        scale = (
            f"scale=w='min({max_dimension},iw)':h='min({max_dimension},ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2"
        )
        self.runner.run(
            [
                self.executable,
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-ss",
                f"{timestamp_s:.6f}",
                "-frames:v",
                "1",
                "-vf",
                scale,
                "-an",
                "-sn",
                "-dn",
                "-vcodec",
                "png",
                "-f",
                "image2",
                str(target),
            ],
            timeout=180,
        )
        if not target.is_file():
            raise ToolError("FRAME_NOT_CREATED", f"FFmpeg did not create frame at {timestamp_s:.6f}s")
