from __future__ import annotations

import argparse

import pytest

from huhac_studio.cli import _loopback, build_parser


def test_cli_defaults_to_loopback_and_host_local_database(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    arguments = build_parser().parse_args([])

    assert arguments.host == "127.0.0.1"
    assert arguments.port == 8878
    assert arguments.database == tmp_path / "local" / "HUHAC" / "Studio" / "projects.sqlite3"
    assert arguments.workspace is None


def test_cli_rejects_non_loopback_bind():
    with pytest.raises(argparse.ArgumentTypeError):
        _loopback("0.0.0.0")
