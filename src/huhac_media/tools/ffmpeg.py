from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from huhac_media.tools.runner import CommandRunner


class FFmpeg:
    def __init__(self, executable: str = "ffmpeg", runner: CommandRunner | None = None):
        self.executable = executable
        self.runner = runner or CommandRunner()

    def available(self) -> bool:
        return self.runner.available(self.executable)

    def version(self) -> str:
        first = self.runner.run([self.executable, "-version"], timeout=10).stdout.splitlines()
        return first[0] if first else "unknown"

    def render_preview(self, source: Path, target: Path, max_dimension: int, quality: int) -> None:
        if source.suffix.casefold() in {".heic", ".heif"}:
            with TemporaryDirectory(prefix=".heic-decode-", dir=target.parent) as temporary:
                decoded = Path(temporary) / "decoded.png"
                self.runner.run(
                    [
                        self.executable,
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        str(source),
                        "-frames:v",
                        "1",
                        "-vcodec",
                        "png",
                        "-f",
                        "image2",
                        str(decoded),
                    ],
                    timeout=180,
                )
                self._render_scaled(decoded, target, max_dimension, quality)
            return
        self._render_scaled(source, target, max_dimension, quality)

    def _render_scaled(
        self, source: Path, target: Path, max_dimension: int, quality: int
    ) -> None:
        qscale = max(2, min(31, round(31 - (quality / 100 * 29))))
        scale = (
            f"scale={max_dimension}:{max_dimension}:"
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
                "-vf",
                scale,
                "-frames:v",
                "1",
                "-q:v",
                str(qscale),
                "-vcodec",
                "mjpeg",
                "-f",
                "image2",
                str(target),
            ],
            timeout=180,
        )
