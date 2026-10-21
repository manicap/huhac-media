from __future__ import annotations

import argparse
from pathlib import Path
import sys

from media_desk.config import ConfigurationError, load_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="media-desk",
        description="Read-only gallery for an existing Huhac media workspace",
    )
    parser.add_argument("--workspace", help="existing workspace directory")
    parser.add_argument("--config", type=Path, help="TOML config with [media_desk]")
    parser.add_argument("--host", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (default: 8000)")
    parser.add_argument(
        "--keyframe-fingerprint",
        help="explicit Video Keyframe v1 configuration fingerprint",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings(
            workspace=args.workspace,
            host=args.host,
            port=args.port,
            keyframe_fingerprint=args.keyframe_fingerprint,
            config_path=args.config,
        )
    except ConfigurationError as exc:
        print(f"media-desk: {exc}", file=sys.stderr)
        return 2
    try:
        import uvicorn
    except ImportError:
        print('media-desk: install dependencies with pip install -e ".[media-desk]"', file=sys.stderr)
        return 3
    from media_desk.web import create_app

    app = create_app(settings=settings)
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0
