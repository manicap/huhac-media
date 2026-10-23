from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConnectorError(Exception):
    code: str
    message: str
    exit_code: int
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.message = " ".join(str(self.message).split())[:500]
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


def configuration_error(code: str, message: str) -> ConnectorError:
    return ConnectorError(code=code, message=message, exit_code=2)


def source_error(
    code: str, message: str, *, retryable: bool = True
) -> ConnectorError:
    return ConnectorError(
        code=code,
        message=message,
        exit_code=3,
        retryable=retryable,
    )
