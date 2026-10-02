from __future__ import annotations

import argparse
import json
from pathlib import Path

from faces.clustering import execute_clustering, prepare_clustering
from faces.contract import ContractError
from faces.inference import OpenVINOEmbedder, YuNetDetector
from faces.models import ClusterConfig, FacesConfig
from faces.service import execute_prepared, prepare_workspace


SUCCESS = 0
PARTIAL = 1
USAGE_OR_CONTRACT = 2
FATAL = 3
INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="faces")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze", help="detect and embed faces in public previews and video keyframes"
    )
    analyze.add_argument("--workspace", required=True, type=Path)
    analyze.add_argument(
        "--yunet-model", type=Path, default=Path("models/face_detection_yunet_2023mar.onnx")
    )
    analyze.add_argument(
        "--reid-model",
        type=Path,
        default=Path(
            "models/intel/face-reidentification-retail-0095/FP32/"
            "face-reidentification-retail-0095.xml"
        ),
    )
    analyze.add_argument("--score-threshold", type=float, default=0.70)
    analyze.add_argument("--nms-threshold", type=float, default=0.30)
    analyze.add_argument("--top-k", type=int, default=5000)
    analyze.add_argument("--reid-precision", choices=("FP16", "FP32"), default="FP32")
    analyze.add_argument("--keyframe-fingerprint")
    analyze.add_argument("--dry-run", action="store_true")
    analyze.add_argument("--force", action="store_true")
    analyze.add_argument("--json", action="store_true", dest="json_output")

    cluster = subparsers.add_parser(
        "cluster", help="cluster reusable Faces v1 embeddings without model inference"
    )
    cluster.add_argument("--workspace", required=True, type=Path)
    cluster.add_argument("--faces-fingerprint", required=True)
    cluster.add_argument("--similarity-threshold", type=float, default=0.70)
    cluster.add_argument("--keyframe-fingerprint")
    cluster.add_argument("--dry-run", action="store_true")
    cluster.add_argument("--force", action="store_true")
    cluster.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _analysis_report(result) -> dict:
    return {
        "workspace": str(result.prepared.workspace.workspace),
        "configuration_fingerprint": result.prepared.configuration_fingerprint,
        "visual_input_count": len(result.prepared.plans),
        "would_process": sum(plan.action == "process" for plan in result.prepared.plans),
        "would_reuse": sum(plan.action == "reuse" for plan in result.prepared.plans),
        "processed": result.processed,
        "reused": result.reused,
        "failed": result.failed,
        "skipped": result.skipped,
        "detected_faces": result.detected_faces,
        "dry_run": result.dry_run,
        "issues": [
            {
                "asset_id": issue.asset_id,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in result.prepared.workspace.issues
        ],
    }


def _print_analysis(report: dict) -> None:
    print("FACES PROCESSOR V1")
    print(f"Workspace:      {report['workspace']}")
    print(f"Fingerprint:    {report['configuration_fingerprint']}")
    print(f"Visual inputs:  {report['visual_input_count']}")
    print(f"Would process:  {report['would_process']}")
    print(f"Would reuse:    {report['would_reuse']}")
    print(f"Processed:      {report['processed']}")
    print(f"Reused:         {report['reused']}")
    print(f"Failed:         {report['failed']}")
    print(f"Skipped:        {report['skipped']}")
    print(f"Detected faces: {report['detected_faces']}")
    for issue in report["issues"]:
        print(f"  {issue['code']:<28} {issue['asset_id']} {issue['message']}")


def _analyze(args) -> int:
    config = FacesConfig(
        score_threshold=args.score_threshold,
        nms_threshold=args.nms_threshold,
        top_k=args.top_k,
        embedding_model_precision=args.reid_precision,
    )
    try:
        prepared = prepare_workspace(
            args.workspace,
            config,
            keyframe_fingerprint=args.keyframe_fingerprint,
            force=args.force,
        )
        if args.dry_run:
            result = execute_prepared(prepared, dry_run=True)
        else:
            needs_processing = any(plan.action == "process" for plan in prepared.plans)
            detector = YuNetDetector(args.yunet_model, config) if needs_processing else None
            embedder = OpenVINOEmbedder(args.reid_model, config) if needs_processing else None
            progress = None if args.json_output else _print_progress
            result = execute_prepared(
                prepared,
                dry_run=False,
                detector=detector,
                embedder=embedder,
                progress=progress,
            )
    except (ContractError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT
    except KeyboardInterrupt:
        print("Interrupted.")
        return INTERRUPTED
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"Fatal error: {exc}")
        return FATAL
    report = _analysis_report(result)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        _print_analysis(report)
    return PARTIAL if not result.dry_run and (result.failed or result.skipped) else SUCCESS


def _print_progress(index, total, plan, outcome, face_count) -> None:
    identity = f"{plan.visual_input.sha256[:12]}/{plan.visual_input.input_id}"
    print(f"[{index}/{total}] {identity} {outcome} faces={face_count}")


def _cluster(args) -> int:
    config = ClusterConfig(similarity_threshold=args.similarity_threshold)
    try:
        prepared = prepare_clustering(
            args.workspace,
            args.faces_fingerprint,
            config,
            keyframe_fingerprint=args.keyframe_fingerprint,
            force=args.force,
        )
        result = execute_clustering(prepared, dry_run=args.dry_run)
    except (ContractError, OSError, ValueError) as exc:
        print(f"Contract/configuration error: {exc}")
        return USAGE_OR_CONTRACT
    report = {
        "workspace": str(prepared.workspace.workspace),
        "faces_configuration_fingerprint": prepared.faces_configuration_fingerprint,
        "configuration_fingerprint": prepared.configuration_fingerprint,
        "logical_input_fingerprint": prepared.logical_input_fingerprint,
        "face_count": len(prepared.records),
        "cluster_count": result.cluster_count,
        "uncertain_count": result.uncertain_count,
        "action": prepared.action,
        "reused": result.reused,
        "dry_run": result.dry_run,
        "output": str(prepared.output_path),
    }
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("FACES CLUSTERING V1")
        for key, value in report.items():
            print(f"{key}: {value}")
    return SUCCESS


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _analyze(args) if args.command == "analyze" else _cluster(args)
