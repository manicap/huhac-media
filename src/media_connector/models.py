from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    content_read: bool = False
    content_checksum: bool = False
    consistent_snapshot: bool = False
    pagination: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {
            "content_read": self.content_read,
            "content_checksum": self.content_checksum,
            "consistent_snapshot": self.consistent_snapshot,
            "pagination": self.pagination,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryWarning:
    code: str
    logical_path: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "logical_path": self.logical_path}


@dataclass(frozen=True, slots=True)
class SourceObject:
    adapter_kind: str
    source_id: str
    object_id: str
    version_token: str
    logical_path: str
    size_bytes: int
    mtime_ns: int
    modified_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_kind": self.adapter_kind,
            "source_id": self.source_id,
            "object_id": self.object_id,
            "version_token": self.version_token,
            "logical_path": self.logical_path,
            "object_kind": "file",
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "modified_at": self.modified_at,
            "media_type_hint": None,
            "source_checksum": None,
        }


@dataclass(frozen=True, slots=True)
class ObjectPage:
    items: tuple[SourceObject, ...]
    next_cursor: str | None
    warnings: tuple[DiscoveryWarning, ...]

    def page_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "returned_count": len(self.items),
            "next_cursor": self.next_cursor,
        }
