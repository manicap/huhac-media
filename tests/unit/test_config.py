from pathlib import Path

import pytest

from huhac_media.config import ConfigError, load_config


def test_defaults_and_relative_paths_use_config_directory(tmp_path: Path) -> None:
    config_file = tmp_path / "huhac.toml"
    config_file.write_text("input = 'media'\n", encoding="utf-8")

    config = load_config(config_file)

    assert config.input == tmp_path / "media"
    assert config.work is None
    assert config.image.max_dimension == 768


def test_cli_overrides_config(tmp_path: Path) -> None:
    config_file = tmp_path / "huhac.toml"
    config_file.write_text("input = 'old'\ninteractive = true\n", encoding="utf-8")

    config = load_config(config_file, {"input": str(tmp_path / "new"), "interactive": False})

    assert config.input == tmp_path / "new"
    assert config.interactive is False


def test_invalid_policy_is_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "huhac.toml"
    config_file.write_text("changed_source_policy = 'ignore'\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(config_file)

