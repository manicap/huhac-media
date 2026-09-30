from __future__ import annotations

import argparse
from pathlib import Path

from huhac_media import __version__
from huhac_media.config import ConfigError, load_config
from huhac_media.exit_codes import ExitCode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huhac-media")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="scan and ingest a media tree")
    ingest.add_argument("--config", type=Path)
    ingest.add_argument("--input", type=Path)
    work_group = ingest.add_mutually_exclusive_group()
    work_group.add_argument("--work", type=Path)
    work_group.add_argument("--new-workspace", action="store_true")
    ingest.add_argument("--dry-run", action="store_true")
    ingest.add_argument("--yes", "--non-interactive", dest="non_interactive", action="store_true")
    ingest.add_argument("--no-warn-existing-workdir", action="store_true")
    ingest.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ingest":
        overrides = {
            "input": str(args.input) if args.input else None,
            "work": str(args.work) if args.work else None,
            "interactive": False if args.non_interactive else None,
            "warn_existing_workdir": False if args.no_warn_existing_workdir else None,
        }
        try:
            config = load_config(args.config, overrides)
        except (ConfigError, TypeError) as exc:
            print(f"Configuration error: {exc}")
            return ExitCode.USAGE_OR_CONFIG
        if config.input is None:
            print("Configuration error: INPUT is required")
            return ExitCode.USAGE_OR_CONFIG
        print("Ingest services are not implemented yet.")
        return ExitCode.FATAL
    return ExitCode.USAGE_OR_CONFIG

