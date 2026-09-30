from enum import StrEnum


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    UNSUPPORTED = "unsupported"


class StageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FATAL = "fatal"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class SourceVersionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ABSENT = "absent"


class PlanKind(StrEnum):
    KNOWN = "known"
    NEW = "new"
    CHANGED = "changed"
    RETRY = "retry"

