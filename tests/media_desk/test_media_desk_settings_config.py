from __future__ import annotations

import os
from pathlib import Path

import pytest

from media_desk.cli import main
from media_desk.config import (
    ConfigurationError,
    ORIGINALS_MAPPING_VERIFICATION,
    OriginalsMapping,
    load_settings,
    save_profile,
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


def test_config_directory_can_be_isolated_by_environment(tmp_path: Path) -> None:
    resolved = user_config_path(environ={"MEDIA_DESK_CONFIG_DIR": str(tmp_path / "isolated")})

    assert resolved == tmp_path / "isolated/config.toml"


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


def test_profile_mapping_round_trip_is_host_local(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    workspace = tmp_path / "workspace"
    originals = tmp_path / "originals"
    mapping = OriginalsMapping(
        workspace_id="workspace-test",
        source_root=r"D:\Huhac\Media",
        local_root=originals.resolve(),
        verification=ORIGINALS_MAPPING_VERIFICATION,
        verified_assets=16,
        eligible_assets=120,
    )

    save_profile(profile / "config.toml", workspace=workspace, originals_mapping=mapping)
    settings = _load(profile)

    assert settings.originals_mapping == mapping
    assert "[media_desk.originals_mapping]" in (profile / "config.toml").read_text(
        encoding="utf-8"
    )


def test_mapping_is_not_loaded_from_explicit_config(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.toml"
    explicit.write_text(
        """[media_desk]
workspace = "explicit"
[media_desk.originals_mapping]
workspace_id = "workspace-test"
source_root = "D:\\\\Media"
local_root = "/mnt/media"
verification = "sha256-sample-v1"
verified_assets = 1
eligible_assets = 1
""",
        encoding="utf-8",
    )

    settings = _load(tmp_path / "profile", config_path=explicit)

    assert settings.workspace == Path("explicit")
    assert settings.originals_mapping is None


@pytest.mark.parametrize(
    "mapping_line,match",
    [
        ('verification = "unknown"', "Unsupported originals mapping verification"),
        ('local_root = "relative"', "absolute host path"),
        ("verified_assets = 0", "positive integer"),
        ("eligible_assets = 0", "include every verified asset"),
    ],
)
def test_invalid_profile_mapping_is_rejected(
    tmp_path: Path, mapping_line: str, match: str
) -> None:
    values = {
        "verification": 'verification = "sha256-sample-v1"',
        "local_root": f'local_root = {str(tmp_path.resolve())!r}',
        "verified_assets": "verified_assets = 1",
        "eligible_assets": "eligible_assets = 1",
    }
    key = mapping_line.split(" =", 1)[0]
    values[key] = mapping_line
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "config.toml").write_text(
        "\n".join(
            (
                '[media_desk]',
                'workspace = "workspace"',
                '[media_desk.originals_mapping]',
                'workspace_id = "workspace-test"',
                'source_root = "D:\\\\Media"',
                values["local_root"],
                values["verification"],
                values["verified_assets"],
                values["eligible_assets"],
                "",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match=match):
        _load(profile)


def test_workspace_change_clears_mapping_but_same_workspace_preserves_it(tmp_path: Path) -> None:
    profile = tmp_path / "profile/config.toml"
    first = tmp_path / "workspace-one"
    mapping = OriginalsMapping(
        "workspace-test",
        r"D:\Media",
        tmp_path.resolve(),
        ORIGINALS_MAPPING_VERIFICATION,
        1,
        1,
    )
    save_profile(profile, workspace=first, originals_mapping=mapping)

    save_profile_workspace(profile, first)
    assert _load(profile.parent).originals_mapping == mapping

    save_profile_workspace(profile, tmp_path / "workspace-two")
    assert _load(profile.parent).originals_mapping is None


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


def test_cli_without_workspace_starts_web_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}
    monkeypatch.setenv("MEDIA_DESK_CONFIG_DIR", str(tmp_path / "clean-profile"))
    for name in (
        "MEDIA_DESK_WORKSPACE",
        "MEDIA_DESK_HOST",
        "MEDIA_DESK_PORT",
        "MEDIA_DESK_KEYFRAME_FINGERPRINT",
    ):
        monkeypatch.delenv(name, raising=False)

    def fake_run(app, *, host, port):
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr("uvicorn.run", fake_run)

    assert main([]) == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
    assert captured["app"].state.snapshot is None
    assert captured["app"].state.workspace_validation.state == "unset"
