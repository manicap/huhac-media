from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from media_connector.errors import ConnectorError, configuration_error
from media_connector.service import CONTRACT, CONTRACT_VERSION, OPERATION, discover_local
from media_connector.transfer_service import transfer_error_envelope, transfer_preflight


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
    transfer = subparsers.add_parser("transfer", help="copy verified media into Media Storage")
    transfer_commands = transfer.add_subparsers(dest="transfer_command", required=True)
    preflight = transfer_commands.add_parser("preflight", help="validate a transfer without writes")
    _add_transfer_arguments(preflight)
    return parser


def _add_transfer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--media-storage", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--transfer-work-root", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)


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
    operation = "transfer-preflight" if argv and argv[:2] == ["transfer", "preflight"] else OPERATION
    try:
        args = build_parser().parse_args(argv)
        if args.command == "local-discovery":
            payload = discover_local(
                workspace=args.workspace,
                source_root=args.source_root,
                page_size=args.page_size,
                cursor=args.cursor,
            )
        else:
            payload = transfer_preflight(
                workspace=args.workspace,
                media_storage=args.media_storage,
                state_root=args.state_root,
                work_root=args.transfer_work_root,
                selection_path=args.selection,
            )
    except ConnectorError as exc:
        envelope = transfer_error_envelope(operation, exc.to_dict()) if operation.startswith("transfer-") else _error_envelope(exc)
        _emit(envelope)
        return exc.exit_code
    except Exception:
        error = ConnectorError(
            code="INTERNAL_ERROR",
            message="unexpected internal error",
            exit_code=3,
            retryable=False,
        )
        envelope = transfer_error_envelope(operation, error.to_dict()) if operation.startswith("transfer-") else _error_envelope(error)
        _emit(envelope)
        return error.exit_code
    _emit(payload)
    return 0
