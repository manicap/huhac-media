from __future__ import annotations

import argparse
import json
from pathlib import Path

from session_grouper.contract import ContractError
from session_grouper.models import GroupingConfig
from session_grouper.output import OutputError
from session_grouper.service import analyze_workspace


SUCCESS = 0
USAGE_OR_CONTRACT = 2
FATAL = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="session-grouper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="group workspace assets by time")
    analyze.add_argument("--workspace", required=True, type=Path)
    analyze.add_argument("--dry-run", action="store_true")
    analyze.add_argument("--json", action="store_true", dest="json_output")
    analyze.add_argument("--rollover-hour", type=int, default=6)
    analyze.add_argument("--max-gap-hours", type=float, default=8.0)
    analyze.add_argument("--assign-filesystem-fallback", action="store_true")
    analyze.add_argument("--fallback-attach-minutes", type=float, default=30.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = GroupingConfig(
        rollover_hour=args.rollover_hour,
        max_gap_hours=args.max_gap_hours,
        assign_filesystem_fallback=args.assign_filesystem_fallback,
        fallback_attach_minutes=args.fallback_attach_minutes,
    )
    try:
        config.validate()
        analysis = analyze_workspace(args.workspace, config, dry_run=args.dry_run)
    except (ContractError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT
    except (OSError, OutputError) as exc:
        print(f"Fatal error: {exc}")
        return FATAL

    summary = analysis.payload["result"]["summary"]
    report = {
        **summary,
        "dry_run": analysis.dry_run,
        "reused": analysis.reused,
        "output": str(analysis.output_path),
        "configuration_fingerprint": analysis.payload["configuration_fingerprint"],
        "input_fingerprint": analysis.payload["input"]["logical_fingerprint"],
    }
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        mode = "DRY RUN" if analysis.dry_run else "REUSED" if analysis.reused else "WRITTEN"
        print("SESSION GROUPER")
        print(f"Workspace:  {analysis.workspace.workspace}")
        print(f"Sessions:   {summary['session_count']}")
        print(f"Assigned:   {summary['assigned_asset_count']}")
        print(f"Unassigned: {summary['unassigned_asset_count']}")
        print(f"Result:     {mode} {analysis.output_path}")
    return SUCCESS
