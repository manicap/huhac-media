from __future__ import annotations

import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Iterable

from media_desk.models import Asset, WorkspaceSnapshot


class CursorError(ValueError):
    pass


@dataclass(frozen=True)
class QuerySpec:
    media_type: str = "all"
    query: str = ""
    sort: str = "captured_desc"
    date_from: str | None = None
    date_to: str | None = None

    def normalized(self) -> "QuerySpec":
        media_type = self.media_type if self.media_type in {"all", "image", "video"} else "all"
        sort = self.sort if self.sort in {"captured_desc", "captured_asc"} else "captured_desc"
        return QuerySpec(media_type, self.query.strip().casefold(), sort, self.date_from, self.date_to)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.normalized().__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def capture_date(asset: Asset):
    """Return the source wall-clock date, never converted to the host timezone."""
    if not asset.capture_time or asset.capture_filesystem_fallback:
        return None
    try:
        value = asset.capture_time.replace("Z", "+00:00")
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def capture_label(asset: Asset) -> str:
    if not asset.capture_time:
        return "Datum pořízení neznámé"
    if asset.capture_filesystem_fallback:
        return f"{asset.capture_time} · čas souboru (nízká důvěra)"
    if asset.capture_timezone or asset.capture_time.endswith("Z") or "+" in asset.capture_time[10:]:
        return asset.capture_time
    return f"{asset.capture_time} · bez časové zóny"


class LibraryIndex:
    def __init__(self, snapshot: WorkspaceSnapshot, cache_size: int = 24) -> None:
        self.snapshot = snapshot
        identity = {
            "workspace_id": snapshot.workspace_id,
            "generated_at": snapshot.generated_at,
            "assets": [
                [asset.asset_id, asset.media_type, asset.capture_time, asset.capture_filesystem_fallback]
                for asset in snapshot.assets
            ],
        }
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.snapshot_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self._by_id = {asset.asset_id: asset for asset in snapshot.assets}
        self._cache_size = cache_size
        self._query_cache: OrderedDict[str, tuple[Asset, ...]] = OrderedDict()

    def query(self, spec: QuerySpec) -> tuple[Asset, ...]:
        spec = spec.normalized()
        key = spec.fingerprint
        cached = self._query_cache.get(key)
        if cached is not None:
            self._query_cache.move_to_end(key)
            return cached
        assets: Iterable[Asset] = self.snapshot.assets
        if spec.media_type != "all":
            assets = (asset for asset in assets if asset.media_type == spec.media_type)
        if spec.query:
            assets = (
                asset
                for asset in assets
                if spec.query in asset.source_name.casefold() or spec.query in asset.asset_id.casefold()
            )
        filtered = []
        for asset in assets:
            date = capture_date(asset)
            if spec.date_from and (date is None or date.isoformat() < spec.date_from):
                continue
            if spec.date_to and (date is None or date.isoformat() > spec.date_to):
                continue
            filtered.append(asset)
        known = [asset for asset in filtered if capture_date(asset) is not None]
        unknown = [asset for asset in filtered if capture_date(asset) is None]
        reverse = spec.sort == "captured_desc"
        # Stable two-pass sort keeps asset_id ascending as the deterministic tie-break.
        known.sort(key=lambda asset: asset.asset_id)
        known.sort(key=lambda asset: asset.capture_time or "", reverse=reverse)
        unknown.sort(key=lambda asset: asset.asset_id)
        result = tuple(known + unknown)
        self._query_cache[key] = result
        self._query_cache.move_to_end(key)
        while len(self._query_cache) > self._cache_size:
            self._query_cache.popitem(last=False)
        return result

    def _cursor(self, spec: QuerySpec, start: int) -> str:
        value = {"v": 1, "s": self.snapshot_id, "q": spec.fingerprint, "i": start}
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(self, spec: QuerySpec, cursor: str) -> int:
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CursorError("Neplatný cursor") from exc
        if not isinstance(value, dict) or value.get("v") != 1:
            raise CursorError("Neplatná verze cursoru")
        if value.get("s") != self.snapshot_id or value.get("q") != spec.fingerprint:
            raise CursorError("Data nebo filtry byly aktualizovány")
        start = value.get("i")
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise CursorError("Neplatná pozice cursoru")
        return start

    def batch(
        self,
        spec: QuerySpec,
        limit: int = 50,
        cursor: str | None = None,
        start: int | None = None,
        requested_snapshot: str | None = None,
    ) -> dict:
        spec = spec.normalized()
        if requested_snapshot and requested_snapshot != self.snapshot_id:
            raise CursorError("Data byla aktualizována")
        assets = self.query(spec)
        if cursor:
            start = self._decode_cursor(spec, cursor)
        start = max(0, min(start or 0, len(assets)))
        end = min(start + limit, len(assets))
        return {
            "snapshot_id": self.snapshot_id,
            "start_index": start,
            "total_count": len(assets),
            "items": assets[start:end],
            "next_cursor": self._cursor(spec, end) if end < len(assets) else None,
            "prev_cursor": self._cursor(spec, max(0, start - limit)) if start > 0 else None,
        }

    def locate(
        self,
        spec: QuerySpec,
        *,
        asset_id: str | None = None,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
    ) -> dict | None:
        for index, asset in enumerate(self.query(spec)):
            date = capture_date(asset)
            matches_date = date is not None and (year is None or date.year == year)
            matches_date = matches_date and (month is None or date.month == month)
            matches_date = matches_date and (day is None or date.day == day)
            if (asset_id and asset.asset_id == asset_id) or (not asset_id and year is not None and matches_date):
                return {"index": index, "asset_id": asset.asset_id, "capture_date": date.isoformat() if date else None}
        return None

    def calendar(self, spec: QuerySpec) -> dict:
        years: dict[int, dict] = {}
        unassigned = 0
        for asset in self.query(spec):
            date = capture_date(asset)
            if date is None:
                unassigned += 1
                continue
            year = years.setdefault(date.year, {"count": 0, "months": {}})
            year["count"] += 1
            month = year["months"].setdefault(date.month, {"count": 0, "days": {}, "covers": []})
            month["count"] += 1
            month["days"][date.day] = month["days"].get(date.day, 0) + 1
            if asset.preview and len(month["covers"]) < 4:
                month["covers"].append(asset.preview.token)
        return {"snapshot_id": self.snapshot_id, "years": years, "unassigned_count": unassigned}

    def time_segments(self, spec: QuerySpec) -> list[dict]:
        segments: OrderedDict[tuple[int, int], dict] = OrderedDict()
        unknown = 0
        for index, asset in enumerate(self.query(spec)):
            date = capture_date(asset)
            if date is None:
                unknown += 1
                continue
            key = (date.year, date.month)
            segment = segments.setdefault(
                key, {"year": date.year, "month": date.month, "count": 0, "index": index}
            )
            segment["count"] += 1
        result = list(segments.values())
        if unknown:
            result.append({"year": None, "month": None, "count": unknown, "index": len(self.query(spec)) - unknown})
        return result
