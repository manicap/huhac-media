from pathlib import Path
import json

import pytest
from PIL import Image

from huhac_media.config import AppConfig, ImageConfig
from huhac_media.cli import main
from huhac_media.domain.enums import PlanKind
from huhac_media.domain.models import IngestPlan, MetadataResult
from huhac_media.exit_codes import ExitCode
from huhac_media.media.metadata import MetadataExtractor
from huhac_media.media.preview import PREVIEW_PROCESSOR_VERSION, PreviewGenerator, preview_fingerprint, preview_path
from huhac_media.services.ingest import IngestService, METADATA_VERSION
from huhac_media.services.planner import CatalogSnapshot, Planner
from huhac_media.services.preflight import render_preflight
from huhac_media.services.scanner import Scanner
from huhac_media.storage.catalog import read_catalog
from huhac_media.storage.database import Database
from huhac_media.storage.workspace import initialize_workspace


pytestmark = pytest.mark.integration


class FakeProbe:
    def probe(self, path: Path) -> dict:
        return {"EXIF:Make": "Synthetic"}


def execute(
    input_path: Path, work: Path, database: Database, plan: IngestPlan | None = None
):
    if plan is None:
        plan = Planner().plan(Scanner().scan(input_path, work), read_catalog(database))
    config = AppConfig(input=input_path, work=work, interactive=False, image=ImageConfig(max_dimension=16))
    service = IngestService(
        database,
        MetadataExtractor(FakeProbe()),
        PreviewGenerator(config.image),
    )
    return service.execute(input_path, work, plan, config)


def test_second_ingest_preflight_reuses_successful_asset_stages(
    tmp_path: Path, capsys
) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    Image.new("RGB", (32, 16), "green").save(input_path / "photo.jpg")
    (input_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")

    first = execute(input_path, work, database)
    with database.transaction() as connection:
        stages_before = [
            tuple(row)
            for row in connection.execute(
                "SELECT stage, status, attempts, output_path FROM asset_stages ORDER BY stage"
            )
        ]

    second_plan = Planner().plan(Scanner().scan(input_path, work), read_catalog(database))
    preflight = render_preflight(input_path, work, second_plan, exists=True)

    assert first.status == "success"
    assert second_plan.count(PlanKind.KNOWN) == 1
    assert second_plan.count(PlanKind.NEW) == 0
    assert len(second_plan.unsupported) == 1
    assert "Already known .......... 1" in preflight
    assert "Unsupported ............ 1" in preflight

    dry_run_result = main(["ingest", "--input", str(input_path), "--dry-run"])
    dry_run_output = capsys.readouterr().out
    assert dry_run_result == ExitCode.SUCCESS
    assert "WORKSPACE: existing (will be reused)" in dry_run_output
    assert "Already known .......... 1" in dry_run_output

    second = execute(input_path, work, database, second_plan)
    with database.transaction() as connection:
        stages_after = [
            tuple(row)
            for row in connection.execute(
                "SELECT stage, status, attempts, output_path FROM asset_stages ORDER BY stage"
            )
        ]

    assert second.status == "success"
    assert second.processed_assets == 0
    assert second.skipped_assets == 1
    assert stages_after == stages_before


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
    reports = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (work / "runs").rglob("report.json")
    ]
    assert len(reports) == 2
    assert all(report["status"] == "success" for report in reports)
    assert {report["plan"]["new"] for report in reports} == {0, 1}
    assert {report["plan"]["known"] for report in reports} == {0, 1}
    assert list((work / "logs").glob("*.log"))
    with database.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM workspace").fetchone()[0] == 1


def test_metadata_version_change_reruns_only_metadata_stage(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    Image.new("RGB", (32, 16), "green").save(input_path / "photo.jpg")
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")

    execute(input_path, work, database)
    preview = next((work / "previews").rglob("*.jpg"))
    preview_time = preview.stat().st_mtime_ns
    with database.transaction() as connection:
        connection.execute(
            "UPDATE asset_stages SET processor_version = 'metadata-v1' WHERE stage = 'metadata'"
        )

    result = execute(input_path, work, database)

    with database.transaction() as connection:
        metadata = dict(
            connection.execute(
                "SELECT stage, processor_version, attempts FROM asset_stages "
                "WHERE stage = 'metadata' AND processor_version = ?",
                (METADATA_VERSION,),
            ).fetchone()
        )
        preview_attempts = connection.execute(
            "SELECT attempts FROM asset_stages WHERE stage = 'preview'"
        ).fetchone()[0]
    assert result.processed_assets == 1
    assert metadata == {
        "stage": "metadata",
        "processor_version": METADATA_VERSION,
        "attempts": 1,
    }
    assert preview_attempts == 1
    assert preview.stat().st_mtime_ns == preview_time


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


def test_previous_running_report_is_recovered(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")
    from huhac_media.config import config_as_dict
    from huhac_media.services.reporting import RunReporter
    from huhac_media.storage.catalog import CatalogStore
    config = AppConfig(input=input_path, work=work, interactive=False)
    old_id = CatalogStore(database).start_run(input_path, work, config_as_dict(config))
    old_reporter = RunReporter(work, old_id, input_path, Planner().plan([], CatalogSnapshot()), config)
    old_path = old_reporter.report_path
    old_reporter.close()

    execute(input_path, work, database)

    assert json.loads(old_path.read_text(encoding="utf-8"))["status"] == "interrupted"


def test_video_metadata_is_ingested_without_preview(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    video = input_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"synthetic")
    work = input_path / "_processing"
    initialize_workspace(work)
    database = Database(work / "state" / "catalog.sqlite3")
    plan = Planner().plan(Scanner().scan(input_path, work), read_catalog(database))
    config = AppConfig(input=input_path, work=work, interactive=False)
    ffprobe = FakeProbe()
    service = IngestService(database, MetadataExtractor(FakeProbe(), ffprobe), PreviewGenerator(config.image))
    result = service.execute(input_path, work, plan, config)
    assert result.status == "success"
    with database.transaction() as connection:
        stages = [row[0] for row in connection.execute("SELECT stage FROM asset_stages")]
    assert stages == ["metadata"]


def test_zero_length_candidate_is_isolated_as_preview_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "input"
    input_path.mkdir()
    (input_path / "zero.jpg").write_bytes(b"")
    work = input_path / "_processing"
    initialize_workspace(work)
    result = execute(input_path, work, Database(work / "state" / "catalog.sqlite3"))
    assert result.status == "partial"
