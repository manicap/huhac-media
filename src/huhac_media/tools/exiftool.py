from __future__ import annotations

import json
from pathlib import Path

from huhac_media.domain.errors import MediaError
from huhac_media.tools.runner import CommandRunner


class ExifTool:
    def __init__(self, executable: str = "exiftool", runner: CommandRunner | None = None):
        self.executable = executable
        self.runner = runner or CommandRunner()

    def available(self) -> bool:
        return self.runner.available(self.executable)

    def version(self) -> str:
        return self.runner.run([self.executable, "-ver"], timeout=10).stdout.strip()

    def probe(self, path: Path) -> dict:
        result = self.runner.run(
            [self.executable, "-j", "-G1", "-a", "-s", "-n", str(path)], timeout=120
        )
        try:
            payload = json.loads(result.stdout)
            raw = payload[0]
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            raise MediaError("INVALID_TOOL_OUTPUT", "ExifTool returned invalid JSON", phase="metadata") from exc
        raw.pop("SourceFile", None)
        raw.pop("File:Directory", None)
        return raw

