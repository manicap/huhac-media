from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Callable, Literal


FilesystemKind = Literal["local", "network", "unknown"]
Classifier = Callable[[Path], FilesystemKind]
_REPARSE_POINT = 0x400
_NETWORK_TYPES = {
    "9p", "ceph", "cifs", "davfs", "fuse.sshfs", "glusterfs", "nfs", "nfs4", "smb", "smbfs",
}
_LOCAL_TYPES = {
    "apfs", "btrfs", "ext2", "ext3", "ext4", "f2fs", "hfs", "hfsplus", "overlay",
    "tmpfs", "vfat", "xfs", "zfs",
}


@dataclass(frozen=True)
class PathIdentity:
    device: int
    inode: int


def nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise FileNotFoundError(path)
        candidate = parent
    return candidate


def canonical_target(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    anchor = nearest_existing(path)
    suffix = path.parts[len(anchor.parts) :]
    return anchor.resolve(strict=True).joinpath(*suffix)


def validate_path_text(path: Path) -> None:
    raw = str(path)
    if not raw or len(raw.encode("utf-8")) > 4096:
        raise ValueError("path is empty or exceeds 4096 UTF-8 bytes")
    if any(ord(character) < 32 for character in raw):
        raise ValueError("path contains a control character")
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("path must be absolute and normalized")


def contains_reparse_or_symlink(path: Path) -> bool:
    existing = nearest_existing(path)
    parts = existing.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            return True
        if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            return True
    return False


def identity(path: Path) -> PathIdentity:
    info = nearest_existing(path).stat()
    return PathIdentity(info.st_dev, info.st_ino)


def roots_overlap(left: Path, right: Path) -> bool:
    left_norm = os.path.normcase(str(left))
    right_norm = os.path.normcase(str(right))
    try:
        common = os.path.commonpath((left_norm, right_norm))
    except ValueError:
        return False
    return common in {left_norm, right_norm}


def classify_filesystem(path: Path) -> FilesystemKind:
    existing = nearest_existing(path)
    if os.name == "nt":
        import ctypes

        drive = Path(existing.anchor or existing).anchor
        kind = ctypes.windll.kernel32.GetDriveTypeW(str(drive))
        if kind in {2, 3, 6}:  # removable, fixed, RAM disk
            return "local"
        if kind == 4:
            return "network"
        return "unknown"

    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.is_file():
        return "unknown"
    resolved = existing.resolve(strict=True)
    selected: tuple[int, str] | None = None
    try:
        lines = mountinfo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "unknown"
    for line in lines:
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        post = after.split()
        if len(fields) < 5 or not post:
            continue
        mount = Path(fields[4].replace("\\040", " ").replace("\\134", "\\"))
        try:
            resolved.relative_to(mount)
        except ValueError:
            continue
        if selected is None or len(mount.parts) > selected[0]:
            selected = (len(mount.parts), post[0])
    if selected is None:
        return "unknown"
    fs_type = selected[1].casefold()
    if fs_type in _NETWORK_TYPES:
        return "network"
    if fs_type in _LOCAL_TYPES:
        return "local"
    return "unknown"
