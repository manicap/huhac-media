from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from huhac_media.domain.enums import MediaType, PlanKind
from huhac_media.domain.models import ExistingSource, IngestPlan, PlanItem, ScannedFile


@dataclass(frozen=True)
class CatalogSnapshot:
    sources_by_path: dict[str, ExistingSource] = field(default_factory=dict)
    asset_source_counts: dict[str, int] = field(default_factory=dict)
    failed_assets: frozenset[str] = frozenset()


class Planner:
    def plan(self, scanned: Iterable[ScannedFile], catalog: CatalogSnapshot) -> IngestPlan:
        plan = IngestPlan()
        seen_in_scan: dict[str, int] = {}
        for item in scanned:
            if item.media_type == MediaType.UNSUPPORTED or item.asset_id is None:
                plan.unsupported.append(item)
                continue
            path_key = item.relative_path.as_posix()
            existing = catalog.sources_by_path.get(path_key)
            if existing is None:
                kind = PlanKind.NEW
            elif existing.asset_id == item.asset_id and not existing.change_blocked:
                kind = PlanKind.KNOWN
            else:
                kind = PlanKind.CHANGED
            scanned_before = seen_in_scan.get(item.asset_id, 0)
            existing_references = catalog.asset_source_counts.get(item.asset_id, 0)
            duplicate = (
                existing_references > (1 if kind == PlanKind.KNOWN else 0)
                or scanned_before > 0
            )
            seen_in_scan[item.asset_id] = scanned_before + 1
            plan.items.append(
                PlanItem(
                    scanned=item,
                    kind=kind,
                    exact_duplicate=duplicate,
                    previous_failure=item.asset_id in catalog.failed_assets,
                    existing=existing,
                )
            )
        return plan
