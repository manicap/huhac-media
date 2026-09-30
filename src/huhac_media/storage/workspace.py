from __future__ import annotations

from pathlib import Path


def select_work_path(input_path: Path, configured: Path | None, new_workspace: bool) -> Path:
    if configured is not None:
        return configured.resolve(strict=False)
    base = input_path / "_processing"
    if not new_workspace:
        return base.resolve(strict=False)
    index = 1
    while True:
        candidate = input_path / f"_processing_{index:03d}"
        if not candidate.exists():
            return candidate.resolve(strict=False)
        index += 1


def validate_paths(input_path: Path, work_path: Path) -> None:
    resolved_input = input_path.resolve(strict=True)
    if not resolved_input.is_dir():
        raise NotADirectoryError(resolved_input)
    resolved_work = work_path.resolve(strict=False)
    if resolved_work == resolved_input:
        raise ValueError("WORK must not be the same directory as INPUT")

