from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path

from huhac_studio.catalog import InMemoryWorkspaceCatalog
from huhac_studio.config import default_project_database_path
from huhac_studio.web import create_app
from media_desk.contract import load_workspace


def _loopback(value: str) -> str:
    if value.casefold() == "localhost":
        return value
    try:
        if ipaddress.ip_address(value).is_loopback:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Studio Project Core must bind to a loopback address")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the HUHÁČ Studio Project Core writer")
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Optional public workspace to attach; omit for offline project access",
    )
    parser.add_argument("--database", type=Path, default=default_project_database_path())
    parser.add_argument("--host", type=_loopback, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8878)
    parser.add_argument(
        "--frontend",
        type=Path,
        help="Built Studio frontend directory; defaults to studio/dist when present",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    database = arguments.database.expanduser().resolve()
    if arguments.workspace is None:
        catalog = InMemoryWorkspaceCatalog({})
    else:
        workspace = arguments.workspace.expanduser().resolve()
        if database == workspace or workspace in database.parents:
            raise SystemExit("Studio database must not be stored inside the media workspace")
        snapshot = load_workspace(workspace)
        catalog = InMemoryWorkspaceCatalog.from_snapshots({snapshot.workspace_id: snapshot})
    import uvicorn

    frontend = arguments.frontend
    if frontend is None:
        candidate = Path.cwd() / "studio" / "dist"
        frontend = candidate if (candidate / "index.html").is_file() else None

    uvicorn.run(
        create_app(
            database_path=database,
            catalog=catalog,
            bind_host=arguments.host,
            frontend_dir=frontend,
        ),
        host=arguments.host,
        port=arguments.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
