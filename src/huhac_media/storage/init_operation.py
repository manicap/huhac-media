from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from typing import Iterator

from huhac_media.storage.atomic import write_json_atomic


MARKER_NAME = ".huhac-init-v1.json"
LOCK_NAME = ".huhac-init.lock"


class InitializationBusyError(RuntimeError):
    pass


@contextmanager
def init_lock(workspace: Path) -> Iterator[None]:
    path = workspace / LOCK_NAME
    try:
        stream = path.open("a+b")
    except PermissionError as exc:
        # Windows can deny opening a byte-range locked file before locking() is reached.
        raise InitializationBusyError("archive initialization is already running") from exc
    try:
        try:
            stream.seek(0)
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InitializationBusyError("archive initialization is already running") from exc
        yield
    finally:
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        stream.close()


def read_marker(workspace: Path) -> dict | None:
    path = workspace / MARKER_NAME
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported initialization marker")
    return payload


def write_marker(workspace: Path, payload: dict) -> None:
    write_json_atomic(workspace / MARKER_NAME, payload)
