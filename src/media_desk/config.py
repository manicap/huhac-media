from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    workspace: Path
    host: str = "127.0.0.1"
    port: int = 8000
    keyframe_fingerprint: str | None = None


def load_settings(
    *,
    workspace: str | None,
    host: str | None,
    port: int | None,
    keyframe_fingerprint: str | None,
    config_path: Path | None,
) -> Settings:
    config: dict = {}
    if config_path is not None:
        try:
            payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(f"Cannot read config: {exc}") from exc
        section = payload.get("media_desk", {})
        if not isinstance(section, dict):
            raise ConfigurationError("Config section [media_desk] must be a table")
        config = section
    workspace_value = workspace or os.getenv("MEDIA_DESK_WORKSPACE") or config.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value:
        raise ConfigurationError(
            "Workspace is required: use --workspace, MEDIA_DESK_WORKSPACE, or [media_desk] workspace"
        )
    host_value = host or os.getenv("MEDIA_DESK_HOST") or config.get("host") or "127.0.0.1"
    port_value: object = (
        port
        if port is not None
        else os.getenv("MEDIA_DESK_PORT") or config.get("port") or 8000
    )
    fingerprint = (
        keyframe_fingerprint
        or os.getenv("MEDIA_DESK_KEYFRAME_FINGERPRINT")
        or config.get("keyframe_fingerprint")
    )
    try:
        parsed_port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Port must be an integer") from exc
    if not 1 <= parsed_port <= 65535:
        raise ConfigurationError("Port must be between 1 and 65535")
    if not isinstance(host_value, str) or not host_value:
        raise ConfigurationError("Host must be a non-empty string")
    if fingerprint is not None and not isinstance(fingerprint, str):
        raise ConfigurationError("Keyframe fingerprint must be a string")
    return Settings(Path(workspace_value), host_value, parsed_port, fingerprint)
