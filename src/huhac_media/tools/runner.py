from __future__ import annotations

import shutil
import subprocess
from typing import Sequence

from huhac_media.domain.errors import MediaError
from huhac_media.domain.models import ToolResult


MAX_DIAGNOSTIC_CHARS = 16_384


class CommandRunner:
    def available(self, executable: str) -> bool:
        return shutil.which(executable) is not None

    def run(self, arguments: Sequence[str], *, timeout: float = 60.0) -> ToolResult:
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
            raise MediaError(
                "TOOL_UNAVAILABLE", f"Executable not found: {command[0]}", phase="tool"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise MediaError(
                "TOOL_TIMEOUT",
                f"External tool timed out after {timeout:g}s: {command[0]}",
                phase="tool",
            ) from exc
        result = ToolResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout[-MAX_DIAGNOSTIC_CHARS:],
            stderr=completed.stderr[-MAX_DIAGNOSTIC_CHARS:],
        )
        if result.returncode != 0:
            raise MediaError(
                "TOOL_FAILED",
                f"{command[0]} exited with code {result.returncode}",
                phase="tool",
                diagnostics={"returncode": result.returncode, "stderr": result.stderr},
            )
        return result

