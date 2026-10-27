from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from media_desk.models import Asset


@dataclass(frozen=True)
class EffectiveAssetView:
    display_name: str
    catalog_name: str
    event: dict[str, Any] | None
    event_candidates: tuple[dict[str, Any], ...]
    sources: dict[str, str]


def effective_asset_view(asset: Asset, event_assignment: dict[str, Any] | None) -> EffectiveAssetView:
    normalized_event = asset.normalized.get("event", {}) if asset.normalized else {}
    candidates = normalized_event.get("machine_candidates", [])
    candidates = tuple(item for item in candidates if isinstance(item, dict))
    return EffectiveAssetView(
        display_name=asset.display_name,
        catalog_name=asset.catalog_name,
        event=event_assignment,
        event_candidates=candidates,
        sources={
            "display_name": "user" if asset.display_name != asset.catalog_name else "catalog",
            "catalog_name": "user" if asset.catalog_name != asset.source_name else "catalog",
            "event": event_assignment.get("source", "none") if event_assignment else "none",
            "semantic": "normalizer" if asset.normalized else "none",
        },
    )
