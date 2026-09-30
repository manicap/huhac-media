from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from huhac_media.config import AppConfig, config_as_dict
from huhac_media.domain.enums import MediaType, PlanKind
from huhac_media.domain.errors import MediaError
from huhac_media.domain.models import IngestPlan
from huhac_media.media.metadata import MetadataExtractor
from huhac_media.media.preview import PREVIEW_PROCESSOR_VERSION, PreviewGenerator, preview_fingerprint, preview_path
from huhac_media.storage.catalog import CatalogStore
from huhac_media.storage.database import Database
from huhac_media.storage.sidecars import asset_path, export_asset, export_sources, write_raw_sidecars


METADATA_VERSION = "metadata-v1"
METADATA_FINGERPRINT = "normalized-v1"


@dataclass(frozen=True)
class IngestResult:
    run_id: str
    status: str
    processed_assets: int
    skipped_assets: int
    failed_stages: int


class IngestService:
    def __init__(
        self,
        database: Database,
        metadata: MetadataExtractor,
        preview: PreviewGenerator,
    ):
        self.database = database
        self.store = CatalogStore(database)
        self.metadata = metadata
        self.preview = preview

    def execute(self, input_path: Path, work_path: Path, plan: IngestPlan, config: AppConfig) -> IngestResult:
        self.store.recover_interrupted()
        run_id = self.store.start_run(input_path, work_path, config_as_dict(config))
        self.store.record_discovery(
            run_id, plan, changed_source_policy=config.changed_source_policy, scan_complete=True
        )
        export_sources(
            self.database,
            work_path,
            {item.scanned.relative_path.as_posix() for item in plan.items},
        )
        eligible: dict[str, object] = {}
        for item in plan.items:
            if item.kind == PlanKind.CHANGED and config.changed_source_policy == "error":
                continue
            assert item.scanned.asset_id is not None
            eligible.setdefault(item.scanned.asset_id, item.scanned)

        processed = skipped = 0
        for scanned in eligible.values():
            ran = self._metadata(run_id, work_path, scanned)
            if scanned.media_type == MediaType.IMAGE:
                ran = self._preview(run_id, work_path, scanned, config) or ran
            if ran:
                processed += 1
            else:
                skipped += 1
            export_asset(self.database, work_path, scanned.asset_id)

        failed = self.store.error_count(run_id)
        status = "partial" if failed else "success"
        self.store.finish_run(
            run_id,
            status,
            {"processed_assets": processed, "skipped_assets": skipped, "failed_stages": failed},
        )
        return IngestResult(run_id, status, processed, skipped, failed)

    def _metadata(self, run_id: str, work: Path, scanned) -> bool:
        output = asset_path(work, scanned.sha256)
        if not self.store.stage_needs_run(
            scanned.asset_id, "metadata", METADATA_VERSION, METADATA_FINGERPRINT, output
        ):
            return False
        self.store.start_stage(scanned.asset_id, "metadata", METADATA_VERSION, METADATA_FINGERPRINT)
        try:
            result = self.metadata.extract(scanned)
            raw_refs = write_raw_sidecars(
                work, scanned.sha256, result.raw_exiftool, result.raw_ffprobe
            )
            payload = dict(result.normalized)
            payload["raw_metadata"] = raw_refs
            self.store.update_asset_metadata(scanned.asset_id, payload)
            self.store.complete_stage(
                scanned.asset_id, "metadata", METADATA_VERSION, METADATA_FINGERPRINT, output
            )
        except Exception as exc:
            self._fail(run_id, scanned, "metadata", METADATA_VERSION, METADATA_FINGERPRINT, exc)
        return True

    def _preview(self, run_id: str, work: Path, scanned, config: AppConfig) -> bool:
        fingerprint = preview_fingerprint(config.image)
        output = preview_path(work, scanned.sha256)
        if not self.store.stage_needs_run(
            scanned.asset_id, "preview", PREVIEW_PROCESSOR_VERSION, fingerprint, output
        ):
            return False
        self.store.start_stage(
            scanned.asset_id, "preview", PREVIEW_PROCESSOR_VERSION, fingerprint
        )
        try:
            self.preview.create(scanned, output)
            self.store.complete_stage(
                scanned.asset_id, "preview", PREVIEW_PROCESSOR_VERSION, fingerprint, output
            )
        except Exception as exc:
            self._fail(
                run_id, scanned, "preview", PREVIEW_PROCESSOR_VERSION, fingerprint, exc
            )
        return True

    def _fail(self, run_id: str, scanned, stage: str, version: str, fingerprint: str, exc: Exception) -> None:
        code = exc.code if isinstance(exc, MediaError) else type(exc).__name__.upper()
        diagnostics = exc.diagnostics if isinstance(exc, MediaError) else {}
        self.store.fail_stage(
            run_id,
            scanned.relative_path.as_posix(),
            scanned.asset_id,
            stage,
            version,
            fingerprint,
            code,
            str(exc),
            diagnostics,
        )
