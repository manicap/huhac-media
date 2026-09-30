from __future__ import annotations

import hashlib
from pathlib import Path


class UnstableSourceError(OSError):
    """The source changed while its identity was being calculated."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise UnstableSourceError(f"Source changed while hashing: {path}")
    return digest.hexdigest()

