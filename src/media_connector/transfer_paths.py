from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from media_connector.adapters.local import _is_link_like
from media_connector.errors import configuration_error


@dataclass(frozen=True, slots=True)
class TransferRoots:
    workspace: Path
    media_storage: Path
    state_root: Path
    work_root: Path


def _existing_directory(path: Path, label: str) -> Path:
    try:
        info = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise configuration_error("ROOT_UNAVAILABLE", f"{label} is unavailable: {exc}") from exc
    if _is_link_like(info) or not stat.S_ISDIR(info.st_mode):
        raise configuration_error("UNSAFE_ROOT", f"{label} must be a regular directory, not a link")
    return resolved


def _overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def validate_roots(
    *, workspace: Path, media_storage: Path, state_root: Path, work_root: Path, source_root: Path
) -> TransferRoots:
    roots = TransferRoots(
        _existing_directory(workspace, "workspace"),
        _existing_directory(media_storage, "media storage"),
        _existing_directory(state_root, "state root"),
        _existing_directory(work_root, "transfer work root"),
    )
    source = _existing_directory(source_root, "source root")
    named = {
        "workspace": roots.workspace,
        "media storage": roots.media_storage,
        "state root": roots.state_root,
        "transfer work root": roots.work_root,
        "source root": source,
    }
    entries = list(named.items())
    for index, (first_name, first_path) in enumerate(entries):
        for second_name, second_path in entries[index + 1 :]:
            if _overlap(first_path, second_path):
                raise configuration_error(
                    "ROOT_OVERLAP", f"{first_name} and {second_name} must not overlap"
                )
    try:
        if os.stat(roots.media_storage).st_dev != os.stat(roots.work_root).st_dev:
            raise configuration_error(
                "STAGING_FILESYSTEM_MISMATCH",
                "transfer work root must be on the same filesystem as media storage",
            )
    except OSError as exc:
        raise configuration_error("ROOT_UNAVAILABLE", f"root filesystem cannot be inspected: {exc}") from exc
    _require_local_filesystem(roots.media_storage)
    _require_local_filesystem(roots.state_root)
    return roots


def validate_recovery_roots(
    *, workspace: Path, media_storage: Path, state_root: Path, work_root: Path
) -> TransferRoots:
    roots = TransferRoots(
        _existing_directory(workspace, "workspace"),
        _existing_directory(media_storage, "media storage"),
        _existing_directory(state_root, "state root"),
        _existing_directory(work_root, "transfer work root"),
    )
    named = {
        "workspace": roots.workspace,
        "media storage": roots.media_storage,
        "state root": roots.state_root,
        "transfer work root": roots.work_root,
    }
    entries = list(named.items())
    for index, (first_name, first_path) in enumerate(entries):
        for second_name, second_path in entries[index + 1 :]:
            if _overlap(first_path, second_path):
                raise configuration_error(
                    "ROOT_OVERLAP", f"{first_name} and {second_name} must not overlap"
                )
    if os.stat(roots.media_storage).st_dev != os.stat(roots.work_root).st_dev:
        raise configuration_error(
            "STAGING_FILESYSTEM_MISMATCH",
            "transfer work root must be on the same filesystem as media storage",
        )
    _require_local_filesystem(roots.media_storage)
    _require_local_filesystem(roots.state_root)
    return roots


def _require_local_filesystem(path: Path) -> None:
    if os.name == "nt":
        import ctypes

        drive = Path(path.anchor)
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(drive))
        if drive_type != 3:  # DRIVE_FIXED
            raise configuration_error(
                "UNSUPPORTED_FILESYSTEM", "media storage must use a qualified local fixed drive"
            )
        return
    if os.name == "posix" and Path("/proc/self/mountinfo").exists():
        resolved = str(path)
        best: tuple[int, str] | None = None
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            left, separator, right = line.partition(" - ")
            if not separator:
                continue
            fields = left.split()
            details = right.split()
            if len(fields) < 5 or not details:
                continue
            mountpoint = fields[4].replace("\\040", " ")
            if resolved == mountpoint or resolved.startswith(mountpoint.rstrip("/") + "/"):
                if best is None or len(mountpoint) > best[0]:
                    best = (len(mountpoint), details[0])
        local_types = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "tmpfs", "overlay"}
        if best is None or best[1] not in local_types:
            raise configuration_error(
                "UNSUPPORTED_FILESYSTEM", "media storage filesystem is not qualified as local"
            )
        return
    raise configuration_error(
        "UNSUPPORTED_FILESYSTEM", "media storage filesystem cannot be safely classified"
    )
