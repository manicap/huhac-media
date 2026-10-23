from __future__ import annotations

import base64
import bisect
import errno
import hashlib
import json
import os
import stat
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from media_connector.errors import ConnectorError, configuration_error, source_error
from media_connector.models import (
    AdapterCapabilities,
    DiscoveryWarning,
    ObjectPage,
    SourceObject,
)


CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 16_384
WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
OFFLINE_ERRNOS = {
    value
    for value in (
        getattr(errno, "ENODEV", None),
        getattr(errno, "ENXIO", None),
        getattr(errno, "ENETDOWN", None),
        getattr(errno, "ENETUNREACH", None),
        getattr(errno, "ESTALE", None),
    )
    if value is not None
}


def _is_link_like(file_stat: os.stat_result) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(file_stat.st_mode) or bool(attributes & reparse_flag)


def _map_os_error(exc: OSError, *, subject: str) -> ConnectorError:
    if isinstance(exc, PermissionError) or exc.errno in {errno.EACCES, errno.EPERM}:
        return source_error(
            "SOURCE_PERMISSION_DENIED", f"permission denied while inspecting {subject}"
        )
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return source_error("SOURCE_NOT_FOUND", f"{subject} was not found")
    if exc.errno in OFFLINE_ERRNOS:
        return source_error("SOURCE_OFFLINE", f"{subject} is offline or unavailable")
    return source_error("SOURCE_IO_ERROR", f"cannot inspect {subject}: {exc}")


def _validate_component(component: str) -> str:
    normalized = unicodedata.normalize("NFC", component)
    if (
        not normalized
        or normalized in {".", ".."}
        or "\x00" in normalized
        or "/" in normalized
        or "\\" in normalized
        or ":" in normalized
        or normalized.endswith((" ", "."))
        or any(ord(character) < 32 for character in normalized)
    ):
        raise source_error(
            "UNSAFE_PATH", "source contains a path that is unsafe for portable discovery", retryable=False
        )
    device_base = normalized.split(".", 1)[0].upper()
    if device_base in WINDOWS_DEVICE_NAMES:
        raise source_error(
            "UNSAFE_PATH", "source contains a reserved device path", retryable=False
        )
    return normalized


def _logical_path(parts: tuple[str, ...]) -> str:
    return "/".join(_validate_component(part) for part in parts)


def _object_id(logical_path: str) -> str:
    encoded = base64.urlsafe_b64encode(logical_path.encode("utf-8")).decode("ascii")
    return f"local-path-v1:{encoded.rstrip('=')}"


def _modified_at(mtime_ns: int) -> str:
    value = datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class LocalFilesystemAdapter:
    adapter_kind = "local"
    capabilities = AdapterCapabilities()

    def __init__(self, source_root: Path):
        self._requested_root = source_root
        try:
            root_stat = os.lstat(source_root)
        except OSError as exc:
            raise _map_os_error(exc, subject="source root") from exc
        if _is_link_like(root_stat):
            raise configuration_error(
                "UNSAFE_SOURCE_ROOT", "source root must not be a symlink or reparse point"
            )
        if not stat.S_ISDIR(root_stat.st_mode):
            raise configuration_error("SOURCE_NOT_DIRECTORY", "source root is not a directory")
        try:
            self.root = source_root.resolve(strict=True)
        except OSError as exc:
            raise _map_os_error(exc, subject="source root") from exc

        identity_path = os.path.normcase(str(self.root))
        digest = hashlib.sha256(os.fsencode(identity_path)).hexdigest()
        self.source_id = f"local-sha256:{digest}"

    def list_page(self, *, page_size: int, cursor: str | None) -> ObjectPage:
        if not 1 <= page_size <= 10_000:
            raise configuration_error("INVALID_ARGUMENT", "page_size must be from 1 to 10000")
        after = self._decode_cursor(cursor) if cursor is not None else None
        items, warnings = self._enumerate()
        paths = [item.logical_path for item in items]
        start = bisect.bisect_right(paths, after) if after is not None else 0
        selected = tuple(items[start : start + page_size])
        end = start + len(selected)
        next_cursor = None
        if selected and end < len(items):
            next_cursor = self._encode_cursor(selected[-1].logical_path)
        return ObjectPage(
            items=selected,
            next_cursor=next_cursor,
            warnings=tuple(warnings),
        )

    def _enumerate(self) -> tuple[list[SourceObject], list[DiscoveryWarning]]:
        items: list[SourceObject] = []
        warnings: list[DiscoveryWarning] = []
        collision_keys: dict[str, str] = {}

        def walk(directory: Path, relative_parts: tuple[str, ...]) -> None:
            try:
                directory_stat = os.lstat(directory)
                if _is_link_like(directory_stat) or not stat.S_ISDIR(directory_stat.st_mode):
                    raise source_error(
                        "UNSAFE_PATH",
                        "source directory changed during discovery",
                        retryable=False,
                    )
                resolved_directory = directory.resolve(strict=True)
                if resolved_directory != self.root and self.root not in resolved_directory.parents:
                    raise source_error(
                        "UNSAFE_PATH", "source directory escaped the configured root", retryable=False
                    )
                with os.scandir(directory) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
                resolved_after_scan = directory.resolve(strict=True)
                if resolved_after_scan != resolved_directory:
                    raise source_error(
                        "UNSAFE_PATH",
                        "source directory changed during discovery",
                        retryable=False,
                    )
            except ConnectorError:
                raise
            except OSError as exc:
                raise _map_os_error(exc, subject="source directory") from exc

            for entry in entries:
                raw_parts = (*relative_parts, entry.name)
                logical = _logical_path(raw_parts)
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise _map_os_error(exc, subject=f"source entry {logical}") from exc
                if _is_link_like(entry_stat):
                    warnings.append(DiscoveryWarning("LINK_SKIPPED", logical))
                    continue
                if stat.S_ISDIR(entry_stat.st_mode):
                    walk(Path(entry.path), raw_parts)
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    warnings.append(DiscoveryWarning("SPECIAL_FILE_SKIPPED", logical))
                    continue

                collision_key = logical.casefold()
                previous = collision_keys.get(collision_key)
                if previous is not None and previous != logical:
                    raise source_error(
                        "PATH_COLLISION",
                        "source contains paths that collide after normalization",
                        retryable=False,
                    )
                collision_keys[collision_key] = logical
                items.append(
                    SourceObject(
                        adapter_kind=self.adapter_kind,
                        source_id=self.source_id,
                        object_id=_object_id(logical),
                        version_token=f"local-stat-v1:{entry_stat.st_size}:{entry_stat.st_mtime_ns}",
                        logical_path=logical,
                        size_bytes=entry_stat.st_size,
                        mtime_ns=entry_stat.st_mtime_ns,
                        modified_at=_modified_at(entry_stat.st_mtime_ns),
                    )
                )

        walk(self.root, ())
        items.sort(key=lambda item: item.logical_path)
        warnings.sort(key=lambda warning: (warning.logical_path, warning.code))
        return items, warnings

    def _encode_cursor(self, after: str) -> str:
        payload = json.dumps(
            {"v": CURSOR_VERSION, "source_id": self.source_id, "after": after},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    def _decode_cursor(self, cursor: str) -> str:
        if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
            raise configuration_error("INVALID_CURSOR", "cursor is empty or too long")
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise configuration_error("INVALID_CURSOR", "cursor is malformed") from exc
        if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
            raise configuration_error("INVALID_CURSOR", "cursor version is unsupported")
        if payload.get("source_id") != self.source_id:
            raise configuration_error(
                "CURSOR_SOURCE_MISMATCH", "cursor belongs to a different source root"
            )
        after = payload.get("after")
        if not isinstance(after, str) or not after:
            raise configuration_error("INVALID_CURSOR", "cursor position is invalid")
        return after
