from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Mapping
import tomllib


class ConfigurationError(ValueError):
    pass


def user_config_path(
    *,
    config_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the single per-user Media Desk config without creating it."""
    if config_dir is not None:
        return Path(config_dir) / "config.toml"
    env = os.environ if environ is None else environ
    if env.get("MEDIA_DESK_CONFIG_DIR"):
        return Path(env["MEDIA_DESK_CONFIG_DIR"]) / "config.toml"
    platform_value = sys.platform if platform_name is None else platform_name
    home_value = Path.home() if home is None else Path(home)
    if platform_value.startswith("win"):
        root = Path(env.get("APPDATA") or home_value / "AppData" / "Roaming")
        return root / "HUHAC" / "MediaDesk" / "config.toml"
    root = Path(env.get("XDG_CONFIG_HOME") or home_value / ".config")
    return root / "huhac" / "media-desk" / "config.toml"


def _read_config(path: Path, *, required: bool) -> dict[str, object]:
    if not path.exists() and not required:
        return {}
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"Cannot read config {path}: {exc}") from exc
    section = payload.get("media_desk", {})
    if not isinstance(section, dict):
        raise ConfigurationError("Config section [media_desk] must be a table")
    return section


def _selected(
    cli_value: object,
    env_value: object,
    explicit_value: object,
    profile_value: object,
    default: object,
) -> tuple[object, str]:
    for value, source in (
        (cli_value, "cli"),
        (env_value, "env"),
        (explicit_value, "explicit_config"),
        (profile_value, "profile"),
    ):
        if value is not None and value != "":
            return value, source
    return default, "default"


@dataclass(frozen=True)
class Settings:
    workspace: Path | None
    host: str = "127.0.0.1"
    port: int = 8000
    keyframe_fingerprint: str | None = None
    profile_config_path: Path | None = None
    workspace_source: str = "default"
    host_source: str = "default"
    port_source: str = "default"
    keyframe_fingerprint_source: str = "default"

    @property
    def workspace_editable(self) -> bool:
        return self.workspace_source in {"default", "profile"}


def load_settings(
    *,
    workspace: str | None,
    host: str | None,
    port: int | None,
    keyframe_fingerprint: str | None,
    config_path: Path | None,
    config_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Settings:
    env = os.environ if environ is None else environ
    profile_path = user_config_path(
        config_dir=config_dir,
        environ=env,
        platform_name=platform_name,
        home=home,
    )
    profile = _read_config(profile_path, required=False)
    explicit = _read_config(Path(config_path), required=True) if config_path is not None else {}

    workspace_value, workspace_source = _selected(
        workspace,
        env.get("MEDIA_DESK_WORKSPACE"),
        explicit.get("workspace"),
        profile.get("workspace"),
        None,
    )
    host_value, host_source = _selected(
        host,
        env.get("MEDIA_DESK_HOST"),
        explicit.get("host"),
        profile.get("host"),
        "127.0.0.1",
    )
    port_value, port_source = _selected(
        port,
        env.get("MEDIA_DESK_PORT"),
        explicit.get("port"),
        profile.get("port"),
        8000,
    )
    fingerprint, fingerprint_source = _selected(
        keyframe_fingerprint,
        env.get("MEDIA_DESK_KEYFRAME_FINGERPRINT"),
        explicit.get("keyframe_fingerprint"),
        profile.get("keyframe_fingerprint"),
        None,
    )

    if workspace_value is not None and not isinstance(workspace_value, str):
        raise ConfigurationError("Workspace must be a path string")
    if not isinstance(host_value, str) or not host_value:
        raise ConfigurationError("Host must be a non-empty string")
    try:
        parsed_port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Port must be an integer") from exc
    if not 1 <= parsed_port <= 65535:
        raise ConfigurationError("Port must be between 1 and 65535")
    if fingerprint is not None and not isinstance(fingerprint, str):
        raise ConfigurationError("Keyframe fingerprint must be a string")

    return Settings(
        Path(workspace_value).expanduser() if workspace_value else None,
        host_value,
        parsed_port,
        fingerprint,
        profile_path,
        workspace_source,
        host_source,
        port_source,
        fingerprint_source,
    )


def save_profile_workspace(config_path: Path, workspace: Path) -> None:
    """Atomically persist the validated workspace while preserving supported preferences."""
    path = Path(config_path)
    existing = _read_config(path, required=False)
    values: dict[str, object] = {"workspace": str(workspace)}
    for key in ("host", "port", "keyframe_fingerprint"):
        if key in existing:
            values[key] = existing[key]
    lines = ["[media_desk]"]
    for key in ("workspace", "host", "port", "keyframe_fingerprint"):
        if key not in values:
            continue
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ConfigurationError(f"Unsupported profile value for {key}")
        rendered = str(value) if isinstance(value, int) else json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} = {rendered}")
    content = "\n".join(lines) + "\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(f"Cannot create config directory: {exc}") from exc
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise ConfigurationError(f"Cannot save config: {exc}") from exc
