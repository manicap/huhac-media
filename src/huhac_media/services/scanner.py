from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from huhac_media.domain.enums import MediaType
from huhac_media.domain.models import ScannedFile
from huhac_media.media.detection import Detection, detect_media
from huhac_media.media.hashing import UnstableSourceError, sha256_file


Detector = Callable[[Path], Detection]
Hasher = Callable[[Path], str]


def _is_in_workspace(path: Path, workspace: Path | None) -> bool:
    if workspace is None:
        return False
    resolved = path.resolve(strict=False)
    return resolved == workspace or workspace in resolved.parents


class Scanner:
    def __init__(self, detector: Detector = detect_media, hasher: Hasher = sha256_file):
        self.detector = detector
        self.hasher = hasher

    def scan(self, input_path: Path, work_path: Path | None = None) -> list[ScannedFile]:
        root = input_path.resolve(strict=True)
        if not root.is_dir():
            raise NotADirectoryError(root)
        workspace = work_path.resolve(strict=False) if work_path else None
        results: list[ScannedFile] = []
        for directory, directories, filenames in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            directories[:] = sorted(
                name
                for name in directories
                if not (directory_path / name).is_symlink()
                and not _is_in_workspace(directory_path / name, workspace)
            )
            for filename in sorted(filenames):
                path = directory_path / filename
                if path.is_symlink() or _is_in_workspace(path, workspace):
                    continue
                results.append(self._scan_file(root, path))
        return results

    def _scan_file(self, root: Path, path: Path) -> ScannedFile:
        relative = PurePosixPath(path.relative_to(root).as_posix())
        try:
            stat = path.stat()
            detected = self.detector(path)
            digest = None
            if detected.media_type != MediaType.UNSUPPORTED:
                digest = self.hasher(path)
            return ScannedFile(
                absolute_path=path,
                relative_path=relative,
                filename=path.name,
                size_bytes=stat.st_size,
                filesystem_mtime_ns=stat.st_mtime_ns,
                media_type=detected.media_type,
                format=detected.format,
                mime_type=detected.mime_type,
                sha256=digest,
            )
        except UnstableSourceError as exc:
            return self._error_item(path, relative, "UNSTABLE_SOURCE", str(exc))
        except OSError as exc:
            return self._error_item(path, relative, "SOURCE_READ_FAILED", str(exc))

    @staticmethod
    def _error_item(path: Path, relative: PurePosixPath, code: str, message: str) -> ScannedFile:
        return ScannedFile(
            absolute_path=path,
            relative_path=relative,
            filename=path.name,
            size_bytes=0,
            filesystem_mtime_ns=0,
            media_type=MediaType.UNSUPPORTED,
            format=None,
            mime_type=None,
            sha256=None,
            error_code=code,
            error_message=message,
        )

