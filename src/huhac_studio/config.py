from __future__ import annotations

import os
from pathlib import Path


def default_studio_data_root() -> Path:
    """Return a host-local profile root, never a checkout or media workspace."""

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "HUHAC" / "Studio"
        return Path.home() / "AppData" / "Local" / "HUHAC" / "Studio"
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "huhac" / "studio"
    return Path.home() / ".local" / "share" / "huhac" / "studio"


def default_project_database_path() -> Path:
    return default_studio_data_root() / "projects.sqlite3"
