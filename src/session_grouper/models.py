from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum


class TimestampConfidence(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    LOW = "low"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class GroupingConfig:
    rollover_hour: int = 6
    max_gap_hours: float = 8.0
    assign_filesystem_fallback: bool = False
    fallback_attach_minutes: float = 30.0
    min_year: int = 1990
    max_year: int = 2100

    def validate(self) -> None:
        if not 0 <= self.rollover_hour <= 23:
            raise ValueError("rollover_hour must be between 0 and 23")
        if self.max_gap_hours <= 0:
            raise ValueError("max_gap_hours must be positive")
        if self.fallback_attach_minutes < 0:
            raise ValueError("fallback_attach_minutes must not be negative")
        if self.min_year > self.max_year:
            raise ValueError("min_year must not exceed max_year")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TimestampEvidence:
    value: str
    wall_time: datetime
    source: str | None
    timezone_offset: str | None
    filesystem_fallback: bool
    confidence: TimestampConfidence


@dataclass(frozen=True)
class AssetObservation:
    asset_id: str
    sha256: str
    media_type: str
    availability: str
    metadata_location: str | None
    timestamp: TimestampEvidence | None
    timestamp_issue: str | None = None


@dataclass
class Session:
    operational_day: str
    boundary_reason: str
    anchor_start: datetime
    anchor_end: datetime
    assets: list[AssetObservation] = field(default_factory=list)


@dataclass(frozen=True)
class UnassignedAsset:
    asset: AssetObservation
    reason: str


@dataclass(frozen=True)
class GroupingResult:
    sessions: tuple[Session, ...]
    unassigned: tuple[UnassignedAsset, ...]
