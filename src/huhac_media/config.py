from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from typing import Any, Mapping


class ConfigError(ValueError):
    """Raised when effective configuration is invalid."""


@dataclass(frozen=True)
class ImageConfig:
    max_dimension: int = 768
    format: str = "jpeg"
    quality: int = 90
    allow_upscale: bool = False
    transparent_background: str = "black"


@dataclass(frozen=True)
class ToolConfig:
    exiftool: str = "exiftool"
    ffprobe: str = "ffprobe"
    ffmpeg: str = "ffmpeg"


@dataclass(frozen=True)
class AppConfig:
    input: Path | None = None
    work: Path | None = None
    interactive: bool = True
    warn_existing_workdir: bool = True
    changed_source_policy: str = "reprocess"
    image: ImageConfig = field(default_factory=ImageConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)


def _resolve_path(value: object, base: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("Paths must be non-empty strings")
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def load_config(path: Path | None = None, overrides: Mapping[str, Any] | None = None) -> AppConfig:
    data: dict[str, Any] = {}
    base = Path.cwd()
    if path is not None:
        config_path = path.expanduser().resolve()
        try:
            with config_path.open("rb") as stream:
                data = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"Cannot read config {config_path}: {exc}") from exc
        base = config_path.parent

    merged = dict(data)
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value

    image_data = merged.get("image", {})
    tools_data = merged.get("tools", {})
    if not isinstance(image_data, dict) or not isinstance(tools_data, dict):
        raise ConfigError("Sections [image] and [tools] must be tables")

    image = ImageConfig(**image_data)
    tools = ToolConfig(**tools_data)
    config = AppConfig(
        input=_resolve_path(merged.get("input"), base),
        work=_resolve_path(merged.get("work"), base),
        interactive=merged.get("interactive", True),
        warn_existing_workdir=merged.get("warn_existing_workdir", True),
        changed_source_policy=merged.get("changed_source_policy", "reprocess"),
        image=image,
        tools=tools,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.changed_source_policy not in {"reprocess", "error"}:
        raise ConfigError("changed_source_policy must be 'reprocess' or 'error'")
    if config.image.max_dimension < 1:
        raise ConfigError("image.max_dimension must be positive")
    if not 1 <= config.image.quality <= 100:
        raise ConfigError("image.quality must be between 1 and 100")
    if config.image.format.lower() != "jpeg":
        raise ConfigError("M1 supports only JPEG previews")
    if config.image.transparent_background not in {"black", "white"}:
        raise ConfigError("image.transparent_background must be black or white")


def config_as_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "input": str(config.input) if config.input else None,
        "work": str(config.work) if config.work else None,
        "interactive": config.interactive,
        "warn_existing_workdir": config.warn_existing_workdir,
        "changed_source_policy": config.changed_source_policy,
        "image": {
            "max_dimension": config.image.max_dimension,
            "format": config.image.format,
            "quality": config.image.quality,
            "allow_upscale": config.image.allow_upscale,
            "transparent_background": config.image.transparent_background,
        },
        "tools": {
            "exiftool": config.tools.exiftool,
            "ffprobe": config.tools.ffprobe,
            "ffmpeg": config.tools.ffmpeg,
        },
    }
