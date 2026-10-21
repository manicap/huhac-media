from __future__ import annotations

import os
from pathlib import Path

import pytest

from media_desk.config import (
    ConfigurationError,
    load_settings,
    save_profile_workspace,
    user_config_path,
)


def _load(config_dir: Path, **overrides):
    values = {
        "workspace": None,
        "host": None,
        "port": None,
        "keyframe_fingerprint": None,
        "config_path": None,
        "config_dir": config_dir,
        "environ": {},
    }
    values.update(overrides)
    return load_settings(**values)


def test_per_user_config_paths_are_os_specific(tmp_path: Path) -> None:
    windows = user_config_path(
        environ={"APPDATA": str(tmp_path / "roaming")}, platform_name="win32", home=tmp_path
    )
    linux = user_config_path(
        environ={"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, platform_name="linux", home=tmp_path
    )

    assert windows == tmp_path / "roaming/HUHAC/MediaDesk/config.toml"
    assert linux == tmp_path / "xdg/huhac/media-desk/config.toml"


def test_clean_profile_starts_without_workspace(tmp_path: Path) -> None:
    settings = _load(tmp_path / "profile")

    assert settings.workspace is None
    assert settings.workspace_source == "default"
    assert settings.workspace_editable is True
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_precedence_is_resolved_per_parameter(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "config.toml").write_text(
        '[media_desk]\nworkspace = "profile"\nhost = "profile-host"\nport = 7001\n',
        encoding="utf-8",
    )
    explicit = tmp_path / "explicit.toml"
    explicit.write_text(
        '[media_desk]\nworkspace = "explicit"\nhost = "explicit-host"\nport = 7002\n',
        encoding="utf-8",
    )

    settings = _load(
        profile,
        workspace="cli",
        config_path=explicit,
        environ={"MEDIA_DESK_HOST": "env-host"},
    )

    assert settings.workspace == Path("cli")
    assert settings.workspace_source == "cli"
    assert settings.host == "env-host"
    assert settings.host_source == "env"
    assert settings.port == 7002
    assert settings.port_source == "explicit_config"
    assert settings.workspace_editable is False


def test_profile_workspace_round_trip_is_atomic(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    target = tmp_path / "workspace"

    save_profile_workspace(profile / "config.toml", target)
    settings = _load(profile)

    assert settings.workspace == target
    assert settings.workspace_source == "profile"
    assert list(profile.glob("*.tmp")) == []


def test_failed_replace_keeps_original_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    config = profile / "config.toml"
    original = '[media_desk]\nworkspace = "original"\n'
    config.write_text(original, encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ConfigurationError, match="Cannot save config"):
        save_profile_workspace(config, tmp_path / "new")

    assert config.read_text(encoding="utf-8") == original
    assert list(profile.glob("*.tmp")) == []
