from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    PARTIAL_FAILURE = 1
    USAGE_OR_CONFIG = 2
    FATAL = 3
    CANCELLED = 4
    INTERRUPTED = 130

