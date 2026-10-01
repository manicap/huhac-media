from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_keyframes.contract import ContractError
from video_keyframes.embedding import OpenClipEmbedder
from video_keyframes.models import KeyframeConfig
from video_keyframes.service import execute_prepared, prepare_workspace
from video_keyframes.tools import FFmpeg, FFprobe


SUCCESS = 0
PARTIAL = 1
USAGE_OR_CONTRACT = 2
FATAL = 3
INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-keyframes")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser(
        "analyze", help="extract representative keyframes from workspace videos"
    )
    analyze.add_argument("--workspace", required=True, type=Path)
    analyze.add_argument("--dry-run", action="store_true")
    analyze.add_argument("--json", action="store_true", dest="json_output")
    analyze.add_argument("--sampling-interval-s", type=float, default=1.0)
    analyze.add_argument("--coverage-similarity", type=float, default=0.85)
    analyze.add_argument("--max-dimension", type=int, default=768)
    analyze.add_argument("--jpeg-quality", type=int, default=90)
    analyze.add_argument("--ffmpeg", default="ffmpeg")
    analyze.add_argument("--ffprobe", default="ffprobe")
    return parser


def _report(result) -> dict:
    plans = [
        {
            "asset_id": plan.asset.asset_id,
            "action": plan.action,
            "output": str(plan.output_path),
            "source": (
                plan.asset.source.relative_path if plan.asset.source is not None else None
            ),
        }
        for plan in result.prepared.plans
    ]
    return {
        "workspace": str(result.prepared.workspace.workspace),
        "configuration_fingerprint": result.prepared.configuration_fingerprint,
        "video_asset_count": len(plans),
        "would_process": sum(plan["action"] == "process" for plan in plans),
        "processed": result.processed,
        "reused": result.reused,
        "failed": result.failed,
        "skipped": result.skipped,
        "dry_run": result.dry_run,
        "assets": plans,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = KeyframeConfig(
        sampling_interval_s=args.sampling_interval_s,
        coverage_similarity=args.coverage_similarity,
        max_dimension=args.max_dimension,
        jpeg_quality=args.jpeg_quality,
    )
    try:
        prepared = prepare_workspace(args.workspace, config)
    except (ContractError, OSError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT

    if args.dry_run:
        result = execute_prepared(prepared, dry_run=True)
    else:
        needs_processing = any(plan.action == "process" for plan in prepared.plans)
        ffprobe = FFprobe(args.ffprobe)
        ffmpeg = FFmpeg(args.ffmpeg)
        embedder = OpenClipEmbedder(config)
        if needs_processing and not ffprobe.available():
            print(f"Fatal error: required ffprobe executable not found: {args.ffprobe}")
            return FATAL
        if needs_processing and not ffmpeg.available():
            print(f"Fatal error: required FFmpeg executable not found: {args.ffmpeg}")
            return FATAL
        if needs_processing and not embedder.available():
            print("Fatal error: OpenCLIP/PyTorch/NumPy dependencies are unavailable")
            return FATAL
        try:
            result = execute_prepared(
                prepared,
                dry_run=False,
                ffprobe=ffprobe,
                ffmpeg=ffmpeg,
                embedder=embedder,
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
        print("VIDEO KEYFRAME EXTRACTOR")
        print(f"Workspace:     {report['workspace']}")
        print(f"Video assets:  {report['video_asset_count']}")
        print(f"Would process: {report['would_process']}")
        print(f"Processed:     {report['processed']}")
        print(f"Reused:        {report['reused']}")
        print(f"Failed:        {report['failed']}")
        print(f"Skipped:       {report['skipped']}")
        for asset in report["assets"]:
            print(f"  {asset['action']:<18} {asset['asset_id']} {asset['source'] or '-'}")
    return PARTIAL if result.failed else SUCCESS
