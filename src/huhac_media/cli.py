from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from huhac_media import __version__
from huhac_media.config import ConfigError, load_config
from huhac_media.domain.enums import MediaType
from huhac_media.domain.errors import FatalError
from huhac_media.exit_codes import ExitCode
from huhac_media.media.metadata import MetadataExtractor
from huhac_media.media.preview import PreviewGenerator
from huhac_media.services.ingest import IngestService
from huhac_media.services.planner import CatalogSnapshot, Planner
from huhac_media.services.preflight import render_preflight
from huhac_media.services.scanner import Scanner
from huhac_media.storage.catalog import read_catalog
from huhac_media.storage.database import Database
from huhac_media.storage.workspace import initialize_workspace, select_work_path, validate_paths, workspace_lock
from huhac_media.tools.exiftool import ExifTool
from huhac_media.tools.ffmpeg import FFmpeg
from huhac_media.tools.ffprobe import FFprobe


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
        try:
            input_path = config.input.resolve(strict=True)
            work_path = select_work_path(input_path, config.work, args.new_workspace)
            validate_paths(input_path, work_path)
            catalog_path = work_path / "state" / "catalog.sqlite3"
            catalog = (
                read_catalog(Database(catalog_path, read_only=True))
                if catalog_path.is_file()
                else CatalogSnapshot()
            )
            scanned = Scanner().scan(input_path, work_path)
            plan = Planner().plan(scanned, catalog)
        except (OSError, ValueError) as exc:
            print(f"Fatal error: {exc}")
            return ExitCode.FATAL
        print(
            render_preflight(
                input_path,
                work_path,
                plan,
                exists=work_path.exists(),
                show_workspace_status=config.warn_existing_workdir or not work_path.exists(),
            )
        )
        if args.dry_run:
            print("\nDRY RUN: no files or state were changed.")
            return (
                ExitCode.PARTIAL_FAILURE
                if any(item.error_code for item in plan.unsupported)
                else ExitCode.SUCCESS
            )
        exiftool = ExifTool(config.tools.exiftool)
        ffprobe = FFprobe(config.tools.ffprobe)
        ffmpeg = FFmpeg(config.tools.ffmpeg)
        if plan.items and not exiftool.available():
            print(f"\nFatal error: required ExifTool executable not found: {config.tools.exiftool}")
            return ExitCode.FATAL
        if any(item.scanned.media_type == MediaType.VIDEO for item in plan.items) and not ffprobe.available():
            print(f"\nFatal error: video requires ffprobe: {config.tools.ffprobe}")
            return ExitCode.FATAL
        fallback_formats = {"HEIC", "HEIF", "CR2", "CR3", "NEF", "ARW", "DNG"}
        if any(item.scanned.format in fallback_formats for item in plan.items) and not ffmpeg.available():
            print("\nWarning: FFmpeg is unavailable; some HEIC/RAW previews may fail.")
        if config.interactive:
            try:
                answer = input("\nContinue? [Y/n] ").strip().casefold()
            except EOFError:
                print("Cancelled: confirmation input is unavailable.")
                return ExitCode.CANCELLED
            if answer not in {"", "y", "yes", "a", "ano"}:
                print("Cancelled.")
                return ExitCode.CANCELLED
        effective = replace(config, input=input_path, work=work_path)
        try:
            initialize_workspace(work_path)
            with workspace_lock(work_path):
                database = Database(work_path / "state" / "catalog.sqlite3")
                extractor = MetadataExtractor(
                    exiftool,
                    ffprobe if any(item.scanned.media_type == MediaType.VIDEO for item in plan.items) else None,
                )
                preview = PreviewGenerator(effective.image, ffmpeg if ffmpeg.available() else None)
                result = IngestService(database, extractor, preview).execute(
                    input_path, work_path, plan, effective
                )
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return ExitCode.INTERRUPTED
        except (OSError, FatalError, ValueError) as exc:
            print(f"\nFatal error: {exc}")
            return ExitCode.FATAL
        print(
            f"\nRun {result.run_id}: {result.status}; processed={result.processed_assets}, "
            f"skipped={result.skipped_assets}, failures={result.failed_stages}"
        )
        return ExitCode.PARTIAL_FAILURE if result.failed_stages else ExitCode.SUCCESS
    return ExitCode.USAGE_OR_CONFIG
