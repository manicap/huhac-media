from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest


TEST_WORKSPACE_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    (path / "workspace.json").write_text(
        json.dumps(
            {
                "workspace_contract_version": 1,
                "schema_version": 1,
                "workspace_id": str(TEST_WORKSPACE_ID),
                "asset_catalog": "metadata/catalog.json",
            }
        ),
        encoding="utf-8",
    )
    return path
