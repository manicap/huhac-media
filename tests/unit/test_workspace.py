from pathlib import Path
import json

import pytest

from huhac_media.domain.errors import FatalError
from huhac_media.storage.workspace import initialize_workspace, validate_paths


def test_work_must_not_contain_input(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    with pytest.raises(ValueError, match="contain INPUT"):
        validate_paths(input_path, tmp_path)


def test_nonempty_unknown_workspace_is_rejected(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "unrelated.txt").write_text("data", encoding="utf-8")
    with pytest.raises(FatalError, match="unrecognized"):
        initialize_workspace(work)


def test_legacy_workspace_manifest_is_upgraded_additively(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    manifest = work / "workspace.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "workspace_id": "existing-id"}),
        encoding="utf-8",
    )

    payload = initialize_workspace(work)

    assert payload == {
        "schema_version": 1,
        "workspace_contract_version": 1,
        "workspace_id": "existing-id",
        "asset_catalog": "metadata/catalog.json",
    }
    assert json.loads(manifest.read_text(encoding="utf-8")) == payload


def test_incompatible_workspace_contract_is_rejected(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "workspace.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workspace_contract_version": 2,
                "workspace_id": "future-id",
                "asset_catalog": "metadata/catalog.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FatalError, match="contract version"):
        initialize_workspace(work)
