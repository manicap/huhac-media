from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from media_connector.errors import ConnectorError, configuration_error
from media_connector.service import CONTRACT, CONTRACT_VERSION, OPERATION, discover_local


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise configuration_error("INVALID_ARGUMENT", message)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="media-connector")
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover = subparsers.add_parser(
        "local-discovery", help="enumerate local files without opening their content"
    )
    discover.add_argument("--workspace", required=True, type=Path)
    discover.add_argument("--source-root", required=True, type=Path)
    discover.add_argument("--page-size", type=int, default=1000)
    discover.add_argument("--cursor")
    return parser


def _error_envelope(error: ConnectorError) -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "operation": OPERATION,
        "status": "error",
        "library": None,
        "source": None,
        "capabilities": None,
        "page": None,
        "warnings": [],
        "error": error.to_dict(),
    }


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        payload = discover_local(
            workspace=args.workspace,
            source_root=args.source_root,
            page_size=args.page_size,
            cursor=args.cursor,
        )
    except ConnectorError as exc:
        _emit(_error_envelope(exc))
        return exc.exit_code
    except Exception:
        error = ConnectorError(
            code="INTERNAL_ERROR",
            message="unexpected internal error",
            exit_code=3,
            retryable=False,
        )
        _emit(_error_envelope(error))
        return error.exit_code
    _emit(payload)
    return 0
