from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from huhac_media.domain.enums import MediaType, PlanKind


@dataclass(frozen=True)
class ScannedFile:
    absolute_path: Path
    relative_path: PurePosixPath
    filename: str
    size_bytes: int
    filesystem_mtime_ns: int
    media_type: MediaType
    format: str | None
    mime_type: str | None
    sha256: str | None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def asset_id(self) -> str | None:
        return f"sha256:{self.sha256}" if self.sha256 else None


@dataclass(frozen=True)
class ExistingSource:
    source_path_id: str
    source_version_id: str
    relative_path: str
    asset_id: str
    stage_failures: int = 0
    change_blocked: bool = False


@dataclass(frozen=True)
class PlanItem:
    scanned: ScannedFile
    kind: PlanKind
    exact_duplicate: bool = False
    previous_failure: bool = False
    existing: ExistingSource | None = None


@dataclass
class IngestPlan:
    items: list[PlanItem] = field(default_factory=list)
    unsupported: list[ScannedFile] = field(default_factory=list)

    @property
    def supported(self) -> list[PlanItem]:
        return self.items

    def count(self, kind: PlanKind) -> int:
        return sum(item.kind == kind for item in self.items)

    @property
    def duplicate_count(self) -> int:
        return sum(item.exact_duplicate for item in self.items)

    @property
    def previous_failure_count(self) -> int:
        return sum(item.previous_failure for item in self.items)


@dataclass(frozen=True)
class ToolResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class MetadataResult:
    normalized: dict[str, Any]
    raw_exiftool: dict[str, Any] | None = None
    raw_ffprobe: dict[str, Any] | None = None
