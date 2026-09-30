from __future__ import annotations

import json
from pathlib import Path

from huhac_media.domain.errors import MediaError
from huhac_media.tools.runner import CommandRunner


class FFprobe:
    def __init__(self, executable: str = "ffprobe", runner: CommandRunner | None = None):
        self.executable = executable
        self.runner = runner or CommandRunner()

    def available(self) -> bool:
        return self.runner.available(self.executable)

    def version(self) -> str:
        first = self.runner.run([self.executable, "-version"], timeout=10).stdout.splitlines()
        return first[0] if first else "unknown"

    def probe(self, path: Path) -> dict:
        result = self.runner.run(
            [
                self.executable,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            timeout=120,
        )
        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaError("INVALID_TOOL_OUTPUT", "ffprobe returned invalid JSON", phase="metadata") from exc
        if isinstance(raw.get("format"), dict):
            raw["format"].pop("filename", None)
        return raw

