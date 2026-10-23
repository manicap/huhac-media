from __future__ import annotations

import ctypes
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from media_connector.adapters.local import _is_link_like
from media_connector.errors import ConnectorError


CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ExistingObject:
    payload: Path
    relative_path: str
    suffix: str


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ConnectorError("CONTENT_READ_FAILED", "content cannot be read for verification", 4, True) from exc
    return digest.hexdigest(), size


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_rename_no_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        move = ctypes.windll.kernel32.MoveFileExW
        move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
        move.restype = ctypes.c_int
        if not move(str(source), str(target), 0x8):  # MOVEFILE_WRITE_THROUGH, no replace
            error = ctypes.get_last_error()
            if error in {80, 183}:
                raise FileExistsError(str(target))
            raise OSError(error, "atomic MoveFileExW failed")
        return
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise ConnectorError("ATOMIC_PUBLISH_UNSUPPORTED", "renameat2 is unavailable", 4)
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:  # RENAME_NOREPLACE
        error = ctypes.get_errno()
        if error == getattr(os, "EEXIST", 17) or error == 17:
            raise FileExistsError(str(target))
        raise OSError(error, "atomic renameat2 failed")


class ContentStore:
    def __init__(self, root: Path):
        self.root = root

    def object_directory(self, content_hash: str) -> Path:
        if len(content_hash) != 64 or any(character not in "0123456789abcdef" for character in content_hash):
            raise ConnectorError("INVALID_CONTENT_ID", "content SHA-256 is invalid", 4)
        return self.root / "objects" / "sha256" / content_hash[:2] / content_hash

    def inspect_existing(self, content_hash: str, expected_size: int) -> ExistingObject | None:
        directory = self.object_directory(content_hash)
        if not directory.exists():
            return None
        try:
            directory_info = os.lstat(directory)
            if _is_link_like(directory_info) or not stat.S_ISDIR(directory_info.st_mode):
                raise ConnectorError("CONTENT_OBJECT_CORRUPT_OR_COLLISION", "content object path is unsafe", 4)
            entries = list(directory.iterdir())
            if len(entries) != 1 or not entries[0].name.startswith("payload."):
                raise ConnectorError("CONTENT_OBJECT_CORRUPT_OR_COLLISION", "content object layout is invalid", 4)
            payload = entries[0]
            payload_info = os.lstat(payload)
            if _is_link_like(payload_info) or not stat.S_ISREG(payload_info.st_mode):
                raise ConnectorError("CONTENT_OBJECT_CORRUPT_OR_COLLISION", "content payload is unsafe", 4)
        except ConnectorError:
            raise
        except OSError as exc:
            raise ConnectorError("CONTENT_OBJECT_INSPECTION_FAILED", "content object cannot be inspected", 4, True) from exc
        actual_hash, actual_size = hash_file(payload)
        if actual_hash != content_hash or actual_size != expected_size:
            raise ConnectorError(
                "CONTENT_OBJECT_CORRUPT_OR_COLLISION",
                "existing content object does not match its SHA-256 identity",
                4,
            )
        return ExistingObject(payload, payload.relative_to(self.root).as_posix(), payload.suffix[1:])

    def ensure_parent(self, content_hash: str) -> Path:
        current = self.root
        for component in ("objects", "sha256", content_hash[:2]):
            current = current / component
            current.mkdir(exist_ok=True)
            info = os.lstat(current)
            if _is_link_like(info) or not stat.S_ISDIR(info.st_mode):
                raise ConnectorError("UNSAFE_STORAGE_PATH", "content store parent is unsafe", 4)
            if self.root not in current.resolve(strict=True).parents:
                raise ConnectorError("UNSAFE_STORAGE_PATH", "content store escaped its root", 4)
        return current

    def publish(self, staging_directory: Path, content_hash: str) -> None:
        target = self.object_directory(content_hash)
        parent = self.ensure_parent(content_hash)
        try:
            atomic_rename_no_replace(staging_directory, target)
            _fsync_directory(parent)
        except FileExistsError:
            raise
        except ConnectorError:
            raise
        except OSError as exc:
            raise ConnectorError("ATOMIC_PUBLISH_FAILED", "atomic content publication failed", 4, True) from exc
