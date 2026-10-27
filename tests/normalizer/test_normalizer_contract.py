from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

import pytest

from normalizer.contract import ContractError, load_workspace


def test_loads_only_public_contract_and_preserves_missing_invalid_metadata(
    workspace_factory, monkeypatch
):
    root = workspace_factory(
        [
            {"name": "missing", "metadata": None},
            {"name": "corrupt", "corrupt_metadata": True},
        ]
    )
    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQLite read")),
    )
    loaded = load_workspace(root)
    assert sorted(issue.code for asset in loaded.assets for issue in asset.issues) == [
        "INVALID_METADATA_DOCUMENT",
        "MISSING_METADATA_DOCUMENT",
    ]
    assert (root / "state" / "catalog.sqlite3").read_bytes() == b"must-not-be-read"


def test_rejects_missing_workspace_invalid_id_and_asset_identity(workspace_factory, tmp_path):
    with pytest.raises(ContractError, match="does not exist"):
        load_workspace(tmp_path / "absent")
    with pytest.raises(ContractError, match="workspace_id"):
        load_workspace(workspace_factory([], workspace_id=""))
    with pytest.raises(ContractError, match="asset identity"):
        load_workspace(workspace_factory([{"name": "bad", "asset_id": "sha256:no"}]))


def test_rejects_catalog_and_metadata_path_traversal(workspace_factory):
    catalog_escape = workspace_factory([])
    manifest_path = catalog_escape / "workspace.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["asset_catalog"] = "../catalog.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ContractError, match="stay inside"):
        load_workspace(catalog_escape)

    metadata_escape = workspace_factory([{"name": "bad"}])
    catalog_path = metadata_escape / "metadata" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["assets"][0]["metadata_location"] = "metadata/assets/../../outside.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ContractError, match="stay inside"):
        load_workspace(metadata_escape)


def test_rejects_metadata_symlink_escape(workspace_factory, tmp_path):
    root = workspace_factory([{"name": "linked", "skip_metadata_file": True}])
    catalog = json.loads((root / "metadata/catalog.json").read_text(encoding="utf-8"))
    relative = catalog["assets"][0]["metadata_location"]
    target = root / Path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        os.symlink(outside, target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(ContractError, match="escapes"):
        load_workspace(root)


def test_rejects_metadata_identity_mismatch_as_asset_issue(workspace_factory):
    root = workspace_factory(
        [{"name": "mismatch", "metadata_payload": {"schema_version": 1, "asset": {"asset_id": "sha256:" + "f" * 64}}}]
    )
    loaded = load_workspace(root)
    assert loaded.assets[0].issues[0].code == "METADATA_IDENTITY_MISMATCH"
