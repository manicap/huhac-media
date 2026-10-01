from __future__ import annotations

import argparse
import json
from pathlib import Path

from vision.contract import ContractError
from vision.models import VisionConfig
from vision.ollama import OllamaClient, OllamaError
from vision.service import execute_prepared, prepare_workspace


SUCCESS = 0
PARTIAL = 1
USAGE_OR_CONTRACT = 2
FATAL = 3
INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vision")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser(
        "analyze", help="analyze public image previews and Video Keyframe v1 outputs"
    )
    analyze.add_argument("--workspace", required=True, type=Path)
    analyze.add_argument("--dry-run", action="store_true")
    analyze.add_argument("--json", action="store_true", dest="json_output")
    analyze.add_argument("--model", default="minicpm-v4.6:latest")
    analyze.add_argument("--endpoint", default="http://localhost:11434")
    analyze.add_argument("--temperature", type=float, default=0.0)
    analyze.add_argument("--num-ctx", type=int, default=8192)
    analyze.add_argument("--num-predict", type=int, default=1024)
    analyze.add_argument("--max-repair-attempts", type=int, default=1)
    analyze.add_argument("--keyframe-fingerprint")
    analyze.add_argument("--force", action="store_true")
    return parser


def _timing_summary(result) -> dict:
    totals = [timing.total_seconds for timing in result.timings]
    return {
        "total_seconds": round(sum(totals), 6),
        "model_seconds": round(sum(timing.model_seconds for timing in result.timings), 6),
        "attempts": sum(timing.attempts for timing in result.timings),
        "timed_input_count": len(totals),
        "average_processed_seconds": round(sum(totals) / len(totals), 6) if totals else None,
        "min_processed_seconds": min(totals) if totals else None,
        "max_processed_seconds": max(totals) if totals else None,
    }


def _report(result) -> dict:
    plans = [
        {
            "asset_id": plan.visual_input.asset_id,
            "input_id": plan.visual_input.input_id,
            "input_kind": plan.visual_input.kind,
            "action": plan.action,
            "input": plan.visual_input.provenance,
            "output": str(plan.output_path),
        }
        for plan in result.prepared.plans
    ]
    issues = [
        {
            "asset_id": issue.asset_id,
            "media_type": issue.media_type,
            "code": issue.code,
            "message": issue.message,
        }
        for issue in result.prepared.workspace.issues
    ]
    return {
        "workspace": str(result.prepared.workspace.workspace),
        "configuration_fingerprint": result.prepared.configuration_fingerprint,
        "force": result.prepared.force,
        "visual_input_count": len(plans),
        "image_preview_count": sum(plan["input_kind"] == "image_preview" for plan in plans),
        "video_keyframe_count": sum(plan["input_kind"] == "video_keyframe" for plan in plans),
        "would_process": sum(plan["action"] == "process" for plan in plans),
        "would_reuse": sum(plan["action"] == "reuse" for plan in plans),
        "processed": result.processed,
        "reused": result.reused,
        "failed": result.failed,
        "skipped": result.skipped,
        "dry_run": result.dry_run,
        "timing": _timing_summary(result),
        "inputs": plans,
        "issues": issues,
    }


def _print_report(report: dict) -> None:
    print("VISION PROCESSOR V1")
    print(f"Workspace:       {report['workspace']}")
    print(f"Image previews:  {report['image_preview_count']}")
    print(f"Video keyframes: {report['video_keyframe_count']}")
    print(f"Would process:   {report['would_process']}")
    print(f"Would reuse:     {report['would_reuse']}")
    print(f"Processed:       {report['processed']}")
    print(f"Reused:          {report['reused']}")
    print(f"Failed:          {report['failed']}")
    print(f"Skipped:         {report['skipped']}")
    if not report["dry_run"]:
        timing = report["timing"]
        average = timing["average_processed_seconds"]
        minimum = timing["min_processed_seconds"]
        maximum = timing["max_processed_seconds"]
        print("Timing:")
        print(f"  Total:          {timing['total_seconds']:.2f} s")
        print(f"  Model:          {timing['model_seconds']:.2f} s")
        print(f"  Avg processed:  {average:.2f} s" if average is not None else "  Avg processed:  n/a")
        print(f"  Min:            {minimum:.2f} s" if minimum is not None else "  Min:            n/a")
        print(f"  Max:            {maximum:.2f} s" if maximum is not None else "  Max:            n/a")
    for issue in report["issues"]:
        print(f"  {issue['code']:<28} {issue['asset_id']} {issue['message']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = VisionConfig(
        model=args.model,
        temperature=args.temperature,
        num_ctx=args.num_ctx,
        num_predict=args.num_predict,
        max_repair_attempts=args.max_repair_attempts,
    )
    try:
        prepared = prepare_workspace(
            args.workspace,
            config,
            keyframe_fingerprint=args.keyframe_fingerprint,
            force=args.force,
        )
        client = OllamaClient(args.endpoint, config)
    except (ContractError, OSError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT

    if args.dry_run:
        result = execute_prepared(prepared, dry_run=True)
    else:
        needs_processing = any(plan.action == "process" for plan in prepared.plans)
        if needs_processing:
            try:
                client.require_model()
            except OllamaError as exc:
                print(f"Fatal error [{exc.code}]: {exc}")
                return FATAL
        try:
            progress = None if args.json_output else _print_progress
            result = execute_prepared(
                prepared, dry_run=False, model=client, progress=progress
            )
        except KeyboardInterrupt:
            print("Interrupted.")
            return INTERRUPTED
        except OSError as exc:
            print(f"Fatal error: {exc}")
            return FATAL

    report = _report(result)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        _print_report(report)
    if result.dry_run:
        return SUCCESS
    return PARTIAL if result.failed or result.skipped else SUCCESS


def _print_progress(index, total, plan, outcome, timing) -> None:
    visual_input = plan.visual_input
    identity = f"{visual_input.sha256[:12]}/{visual_input.input_id}"
    suffix = "" if outcome == "processed" else f" {outcome}"
    print(
        f"[{index}/{total}] {visual_input.kind} {identity}{suffix} ... "
        f"{timing.total_seconds:.1f} s"
    )
