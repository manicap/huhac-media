from __future__ import annotations

import json
from pathlib import Path

import pytest

from media_connector.errors import ConnectorError
from media_connector.workspace import read_workspace_id

TEST_WORKSPACE_ID = "12345678-1234-5678-1234-567812345678"


def test_reads_workspace_identity_without_catalog(workspace: Path) -> None:
    assert read_workspace_id(workspace) == TEST_WORKSPACE_ID
    assert not (workspace / "metadata").exists()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("not-json", "WORKSPACE_INVALID"),
        (json.dumps([]), "WORKSPACE_INVALID"),
        (json.dumps({"workspace_contract_version": 2, "workspace_id": TEST_WORKSPACE_ID}), "UNSUPPORTED_WORKSPACE_CONTRACT"),
        (json.dumps({"workspace_contract_version": 1, "workspace_id": "invalid"}), "WORKSPACE_INVALID"),
    ],
)
def test_rejects_invalid_workspace(tmp_path: Path, payload: str, code: str) -> None:
    (tmp_path / "workspace.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ConnectorError) as caught:
        read_workspace_id(tmp_path)
    assert caught.value.code == code
    assert caught.value.exit_code == 2


def test_reports_missing_workspace(tmp_path: Path) -> None:
    with pytest.raises(ConnectorError) as caught:
        read_workspace_id(tmp_path)
    assert caught.value.code == "WORKSPACE_NOT_FOUND"
