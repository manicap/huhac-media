from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

from huhac_media import __version__
from huhac_media.config import AppConfig, config_as_dict
from huhac_media.domain.enums import MediaType, PlanKind
from huhac_media.domain.models import IngestPlan
from huhac_media.storage.atomic import write_json_atomic


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunReporter:
    def __init__(
        self,
        work_path: Path,
        run_id: str,
        input_path: Path,
        plan: IngestPlan,
        config: AppConfig,
        tool_versions: dict[str, str] | None = None,
        log_level: str = "INFO",
    ):
        self.work_path = work_path
        self.run_id = run_id
        self.started_at = utc_now()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.directory = work_path / "runs" / f"{stamp}_{run_id}"
        self.report_path = self.directory / "report.json"
        self.log_path = work_path / "logs" / f"{stamp}_{run_id}.log"
        formats = Counter(item.scanned.format or "UNKNOWN" for item in plan.items)
        images = sum(item.scanned.media_type == MediaType.IMAGE for item in plan.items)
        videos = sum(item.scanned.media_type == MediaType.VIDEO for item in plan.items)
        self.payload: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "running",
            "app_version": __version__,
            "started_at": self.started_at,
            "finished_at": None,
            "input": str(input_path),
            "work": str(work_path),
            "tools": tool_versions or {},
            "scan": {
                "files_total": len(plan.items) + len(plan.unsupported),
                "images": images,
                "videos": videos,
                "unsupported": len(plan.unsupported),
                "bytes_total": sum(
                    item.scanned.size_bytes for item in plan.items
                ) + sum(item.size_bytes for item in plan.unsupported),
                "formats": dict(sorted(formats.items())),
            },
            "plan": {
                "known": plan.count(PlanKind.KNOWN),
                "new": plan.count(PlanKind.NEW),
                "changed": plan.count(PlanKind.CHANGED),
                "exact_duplicates": plan.duplicate_count,
                "previous_failures": plan.previous_failure_count,
            },
            "result": None,
            "errors": [],
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.directory / "effective-config.json", config_as_dict(config))
        write_json_atomic(self.report_path, self.payload)
        self.logger = logging.getLogger(f"huhac_media.run.{run_id}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = logging.FileHandler(self.log_path, encoding="utf-8")
        self.handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(self.handler)
        self.logger.info("Effective configuration: %s", config_as_dict(config))
        self.logger.info("Scan: %s Plan: %s", self.payload["scan"], self.payload["plan"])

    def finish(self, status: str, result: dict, errors: list[dict]) -> None:
        self.payload.update(
            status=status,
            finished_at=utc_now(),
            result=result,
            errors=errors,
        )
        write_json_atomic(self.report_path, self.payload)
        self.logger.info("Run finished status=%s result=%s", status, result)

    def close(self) -> None:
        self.logger.removeHandler(self.handler)
        self.handler.close()


def mark_report_interrupted(work_path: Path, run_id: str) -> None:
    matches = list((work_path / "runs").glob(f"*_{run_id}/report.json"))
    for report_path in matches:
        import json

        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") == "running":
            payload["status"] = "interrupted"
            payload["finished_at"] = utc_now()
            write_json_atomic(report_path, payload)
