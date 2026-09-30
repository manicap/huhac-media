from pathlib import Path

import pytest
from PIL import Image

from huhac_media.config import AppConfig, ImageConfig
from huhac_media.domain.models import MetadataResult
from huhac_media.media.metadata import MetadataExtractor
from huhac_media.media.preview import PREVIEW_PROCESSOR_VERSION, PreviewGenerator, preview_fingerprint, preview_path
from huhac_media.services.ingest import IngestService
from huhac_media.services.planner import CatalogSnapshot, Planner
from huhac_media.services.scanner import Scanner
from huhac_media.storage.catalog import read_catalog
from huhac_media.storage.database import Database
from huhac_media.storage.workspace import initialize_workspace


pytestmark = pytest.mark.integration


class FakeProbe:
    def probe(self, path: Path) -> dict:
        return {"EXIF:Make": "Synthetic"}


def execute(input_path: Path, work: Path, database: Database):
    plan = Planner().plan(Scanner().scan(input_path, work), read_catalog(database))
    config = AppConfig(input=input_path, work=work, interactive=False, image=ImageConfig(max_dimension=16))
    service = IngestService(
        database,
        MetadataExtractor(FakeProbe()),
        PreviewGenerator(config.image),
    )
    return service.execute(input_path, work, plan, config)


def test_ingest_writes_sidecars_preview_and_reuses_success(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    source = input_path / "Huháč.jpg"
    Image.new("RGB", (32, 16), "green").save(source)
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")

    first = execute(input_path, work, database)
    preview = next((work / "previews").rglob("*.jpg"))
    preview_time = preview.stat().st_mtime_ns
    second = execute(input_path, work, database)

    assert first.status == "success"
    assert second.processed_assets == 0
    assert second.skipped_assets == 1
    assert preview.stat().st_mtime_ns == preview_time
    assert len(list((work / "metadata" / "sources").glob("*.json"))) == 1
    assert len(list((work / "metadata" / "assets").rglob("*.json"))) == 1
    assert len(list((work / "metadata" / "raw").rglob("*.exiftool.json"))) == 1


def test_preview_failure_does_not_discard_metadata_or_stop_batch(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    (input_path / "broken.jpg").write_bytes(b"not an image")
    Image.new("RGB", (8, 8), "blue").save(input_path / "good.jpg")
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")

    result = execute(input_path, work, database)

    assert result.status == "partial"
    with database.transaction() as connection:
        statuses = connection.execute(
            "SELECT stage, status FROM asset_stages ORDER BY stage, status"
        ).fetchall()
        assert sum(row["stage"] == "metadata" and row["status"] == "success" for row in statuses) == 2
        assert sum(row["stage"] == "preview" and row["status"] == "failed" for row in statuses) == 1
        assert sum(row["stage"] == "preview" and row["status"] == "success" for row in statuses) == 1


def test_processing_stage_is_retried_after_interruption(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    source = input_path / "photo.jpg"
    Image.new("RGB", (8, 8), "red").save(source)
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")
    execute(input_path, work, database)
    snapshot = read_catalog(database)
    asset_id = snapshot.sources_by_path["photo.jpg"].asset_id
    sha = asset_id.removeprefix("sha256:")
    output = preview_path(work, sha)
    output.unlink()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE asset_stages SET status = 'processing' WHERE asset_id = ? AND stage = 'preview'",
            (asset_id,),
        )

    execute(input_path, work, database)

    with database.transaction() as connection:
        row = connection.execute(
            "SELECT status, attempts FROM asset_stages WHERE asset_id = ? AND stage = 'preview'",
            (asset_id,),
        ).fetchone()
        assert row["status"] == "success"
        assert row["attempts"] == 2
    assert output.is_file()
