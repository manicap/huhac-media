import json
from pathlib import Path

import pytest
from PIL import Image

from huhac_media.config import AppConfig, ImageConfig
from huhac_media.media.metadata import MetadataExtractor
from huhac_media.media.preview import PreviewGenerator
from huhac_media.services.ingest import IngestService
from huhac_media.services.planner import Planner
from huhac_media.services.scanner import Scanner
from huhac_media.storage.catalog import read_catalog
from huhac_media.storage.database import Database
from huhac_media.storage.workspace import initialize_workspace


pytestmark = pytest.mark.integration


class FakeProbe:
    def probe(self, path: Path) -> dict:
        return {"EXIF:Make": "Synthetic"}


def ingest(input_path: Path, work_path: Path, database: Database) -> str:
    plan = Planner().plan(
        Scanner().scan(input_path, work_path), read_catalog(database)
    )
    config = AppConfig(
        input=input_path,
        work=work_path,
        interactive=False,
        image=ImageConfig(max_dimension=16),
    )
    result = IngestService(
        database,
        MetadataExtractor(FakeProbe()),
        PreviewGenerator(config.image),
    ).execute(input_path, work_path, plan, config)
    assert result.status == "success"
    return result.run_id


def read_contract(work_path: Path) -> dict:
    manifest = json.loads((work_path / "workspace.json").read_text(encoding="utf-8"))
    return json.loads(
        (work_path / manifest["asset_catalog"]).read_text(encoding="utf-8")
    )


def test_public_contract_tracks_assets_provenance_and_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    first_source = input_path / "a.jpg"
    duplicate_source = input_path / "b.jpg"
    Image.new("RGB", (32, 16), "green").save(first_source)
    duplicate_source.write_bytes(first_source.read_bytes())
    (input_path / "clip.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypisom" + b"synthetic"
    )
    (input_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    work_path = input_path / "_processing"
    manifest = initialize_workspace(work_path)
    database = Database(work_path / "state" / "catalog.sqlite3")

    first_run_id = ingest(input_path, work_path, database)
    first_contract = read_contract(work_path)

    assert first_contract["workspace_contract_version"] == 1
    assert first_contract["workspace_id"] == manifest["workspace_id"]
    assert first_contract["generated_by_run_id"] == first_run_id
    assert first_contract["source_root"] == str(input_path.resolve())
    assert len(first_contract["assets"]) == 2
    assert all(
        asset["asset_id"] == f"sha256:{asset['sha256']}"
        for asset in first_contract["assets"]
    )
    assert all(
        asset["availability"] == "available"
        for asset in first_contract["assets"]
    )
    assert all(asset["metadata_location"] for asset in first_contract["assets"])
    assert all(
        (work_path / asset["metadata_location"]).is_file()
        for asset in first_contract["assets"]
    )
    image_asset = next(
        asset for asset in first_contract["assets"] if asset["media_type"] == "image"
    )
    video_asset = next(
        asset for asset in first_contract["assets"] if asset["media_type"] == "video"
    )
    assert {source["relative_path"] for source in image_asset["sources"]} == {
        "a.jpg",
        "b.jpg",
    }
    assert (work_path / image_asset["preview_location"]).is_file()
    assert video_asset["preview_location"] is None
    assert all(
        source["relative_path"] != "notes.txt"
        for asset in first_contract["assets"]
        for source in asset["sources"]
    )
    assert not list((work_path / "metadata").glob(".catalog.json.*.tmp"))

    old_image_asset_id = image_asset["asset_id"]
    duplicate_source.rename(input_path / "renamed.jpg")
    renamed_run_id = ingest(input_path, work_path, database)
    renamed_contract = read_contract(work_path)
    renamed_image = next(
        asset
        for asset in renamed_contract["assets"]
        if asset["asset_id"] == old_image_asset_id
    )

    assert len(renamed_contract["assets"]) == 2
    assert renamed_contract["generated_by_run_id"] == renamed_run_id
    assert renamed_run_id != first_run_id
    assert not list((work_path / "metadata").glob(".catalog.json.*.tmp"))
    assert {
        (source["relative_path"], source["status"])
        for source in renamed_image["sources"]
    } == {("a.jpg", "active"), ("b.jpg", "absent"), ("renamed.jpg", "active")}

    Image.new("RGB", (32, 16), "blue").save(first_source)
    changed_run_id = ingest(input_path, work_path, database)
    changed_contract = read_contract(work_path)
    changed_image = next(
        asset
        for asset in changed_contract["assets"]
        if asset["media_type"] == "image" and asset["asset_id"] != old_image_asset_id
    )
    old_image = next(
        asset
        for asset in changed_contract["assets"]
        if asset["asset_id"] == old_image_asset_id
    )

    assert len(changed_contract["assets"]) == 3
    assert changed_contract["generated_by_run_id"] == changed_run_id
    assert not list((work_path / "metadata").glob(".catalog.json.*.tmp"))
    assert changed_image["availability"] == "available"
    assert any(
        source["relative_path"] == "a.jpg" and source["status"] == "active"
        for source in changed_image["sources"]
    )
    assert any(
        source["relative_path"] == "a.jpg" and source["status"] == "superseded"
        for source in old_image["sources"]
    )
    assert old_image["availability"] == "available"
