from __future__ import annotations

import argparse
import json
from pathlib import Path

from normalizer.contract import ContractError
from normalizer.models import NormalizerConfig
from normalizer.output import OutputError
from normalizer.service import (
    analyze_prepared,
    inspect_status,
    plan_report,
    prepare_workspace,
)


SUCCESS = 0
PARTIAL = 1
USAGE_OR_CONTRACT = 2
FATAL = 3
INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="normalizer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("plan", "validate and plan a read-only Normalizer N2 snapshot"),
        ("analyze", "publish or reuse a Normalizer N2 snapshot"),
        ("status", "inspect Normalizer snapshots without modifying them"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--workspace", required=True, type=Path)
        command.add_argument("--json", action="store_true", dest="json_output")
        command.add_argument("--session-fingerprint", dest="session_configuration_fingerprint")
        command.add_argument("--session-input", dest="session_logical_input_fingerprint")
        command.add_argument("--keyframes-fingerprint", dest="keyframes_configuration_fingerprint")
        command.add_argument("--vision-fingerprint", dest="vision_configuration_fingerprint")
        command.add_argument("--faces-fingerprint", dest="faces_configuration_fingerprint")
        command.add_argument("--faces-clustering-fingerprint", dest="faces_clustering_configuration_fingerprint")
        command.add_argument("--faces-clustering-input", dest="faces_clustering_logical_input_fingerprint")
    return parser


def _print_plan(report: dict) -> None:
    print("NORMALIZER N2 PLAN")
    print(f"Workspace:     {report['workspace']}")
    print(f"Assets:        {report['asset_count']} ({report['image_count']} image, {report['video_count']} video)")
    print(f"Input issues:  {report['input_issue_count']}")
    print("Upstream:")
    for name, status in report["upstream_statuses"].items():
        print(f"  {name:<20} expected={report['upstream_expected_inputs'][name]} status={status}")
    if report["blocking_ambiguities"]:
        print(f"Blocking:      {', '.join(report['blocking_ambiguities'])}")
    print(f"Config:        {report['configuration_fingerprint']}")
    print(f"Inputs:        {report['input_set_fingerprint']}")
    print(f"Result:        {'REUSE' if report['reusable'] else 'CREATE'} {report['output']}")
    for issue in report["issues"]:
        print(f"  {issue['code']:<28} {issue['asset_id']} {issue['message']}")


def _print_analysis(report: dict) -> None:
    summary = report["summary"]
    print("NORMALIZER N2")
    print(f"Workspace:     {report['workspace']}")
    print(f"Assets:        {summary['asset_count']}")
    print(f"Input issues:  {summary['input_issue_count']}")
    print(f"Warnings:      {summary['warning_count']}")
    print(f"Invalid:       {summary['invalid_value_count']}")
    print(f"Result:        {'REUSED' if report['reused'] else 'WRITTEN'} {report['output']}")


def _print_status(report: dict) -> None:
    print("NORMALIZER N2 STATUS")
    print(f"Workspace:       {report['workspace']}")
    print(f"Snapshots:       {report['snapshot_count']}")
    print(f"Valid:           {report['valid_snapshot_count']}")
    print(f"Invalid:         {report['invalid_snapshot_count']}")
    print(f"Analyzed media:  {report['analyzed_asset_count']}")
    print(f"Unprocessed:     {report['unprocessed_asset_count']}")
    print(f"Conflicts:       {report['conflict_count']}")
    print(f"Namespace bytes: {report['size_bytes']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            report = inspect_status(args.workspace)
            if args.json_output:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            else:
                _print_status(report)
            return SUCCESS if report["invalid_snapshot_count"] == 0 else PARTIAL

        config = NormalizerConfig(
            session_configuration_fingerprint=args.session_configuration_fingerprint,
            session_logical_input_fingerprint=args.session_logical_input_fingerprint,
            keyframes_configuration_fingerprint=args.keyframes_configuration_fingerprint,
            vision_configuration_fingerprint=args.vision_configuration_fingerprint,
            faces_configuration_fingerprint=args.faces_configuration_fingerprint,
            faces_clustering_configuration_fingerprint=args.faces_clustering_configuration_fingerprint,
            faces_clustering_logical_input_fingerprint=args.faces_clustering_logical_input_fingerprint,
        )
        prepared = prepare_workspace(args.workspace, config)
        planned = plan_report(prepared)
        if args.command == "plan":
            if args.json_output:
                print(json.dumps(planned, ensure_ascii=False, sort_keys=True))
            else:
                _print_plan(planned)
            return PARTIAL if planned["blocking_ambiguities"] else SUCCESS

        analysis = analyze_prepared(prepared)
        report = {
            "workspace": str(prepared.workspace.workspace),
            "configuration_fingerprint": prepared.configuration_fingerprint,
            "input_set_fingerprint": prepared.input_set_fingerprint,
            "output": str(prepared.output_path),
            "reused": analysis.reused,
            "summary": analysis.manifest["summary"],
        }
        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            _print_analysis(report)
        return PARTIAL if (
            report["summary"]["input_issue_count"] or report["summary"]["warning_count"]
        ) else SUCCESS
    except (ContractError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT
    except KeyboardInterrupt:
        print("Interrupted.")
        return INTERRUPTED
    except (OSError, OutputError) as exc:
        print(f"Fatal error: {exc}")
        return FATAL
