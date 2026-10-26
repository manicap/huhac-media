from __future__ import annotations

import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Iterable

from media_desk.models import Asset, EventRecord, WorkspaceSnapshot


class CursorError(ValueError):
    pass


@dataclass(frozen=True)
class QuerySpec:
    media_type: str = "all"
    query: str = ""
    sort: str = "captured_desc"
    date_from: str | None = None
    date_to: str | None = None
    event_id: str | None = None

    def normalized(self) -> "QuerySpec":
        media_type = self.media_type if self.media_type in {"all", "image", "video"} else "all"
        sort = self.sort if self.sort in {"captured_desc", "captured_asc"} else "captured_desc"
        event_id = self.event_id.strip() if isinstance(self.event_id, str) and self.event_id.strip() else None
        return QuerySpec(media_type, self.query.strip().casefold(), sort, self.date_from, self.date_to, event_id)

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
    def __init__(
        self,
        snapshot: WorkspaceSnapshot,
        cache_size: int = 24,
        events: Iterable[EventRecord] = (),
        manual_assignments: dict[str, str | None] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self._events: tuple[EventRecord, ...] = ()
        self._event_assets: dict[str, frozenset[str]] = {}
        self._asset_event_names: dict[str, tuple[str, ...]] = {}
        self._asset_assignment: dict[str, tuple[str, str, str]] = {}
        self._manual_assignments = dict(manual_assignments or {})
        self._cache_size = cache_size
        self._query_cache: OrderedDict[str, tuple[Asset, ...]] = OrderedDict()
        self._by_id = {asset.asset_id: asset for asset in snapshot.assets}
        self.update_events(events)

    def _snapshot_identity(self) -> str:
        identity = {
            "workspace_id": self.snapshot.workspace_id,
            "generated_at": self.snapshot.generated_at,
            "assets": [
                [asset.asset_id, asset.media_type, asset.capture_time, asset.capture_filesystem_fallback]
                for asset in self.snapshot.assets
            ],
            "events": [
                [event.event_id, event.name, list(event.session_ids), [interval.__dict__ for interval in event.intervals]] for event in self._events
            ],
            "manual_assignments": self._manual_assignments,
        }
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def update_events(self, events: Iterable[EventRecord], manual_assignments: dict[str, str | None] | None = None) -> None:
        self._events = tuple(sorted(events, key=lambda item: item.event_id))
        if manual_assignments is not None:
            self._manual_assignments = dict(manual_assignments)
        sessions = {session.session_id: session for session in self.snapshot.sessions}
        automatic: dict[str, list[tuple[str, str]]] = {}
        for event in self._events:
            intervals_by_session = {interval.session_id: interval for interval in event.intervals}
            for session_id in event.session_ids:
                session = sessions.get(session_id)
                if session is None:
                    continue
                interval = intervals_by_session.get(session_id)
                for asset_id in session.asset_ids:
                    asset = self._by_id.get(asset_id)
                    if asset is None or (interval and not self._in_interval(asset, interval.start, interval.end)):
                        continue
                    automatic.setdefault(asset_id, []).append((event.event_id, event.name))
        self._asset_assignment = {}
        for asset in self.snapshot.assets:
            if asset.asset_id in self._manual_assignments:
                event_id = self._manual_assignments[asset.asset_id]
                event = next((item for item in self._events if item.event_id == event_id), None)
                if event:
                    self._asset_assignment[asset.asset_id] = (event.event_id, event.name, "manual")
            else:
                candidates = automatic.get(asset.asset_id, [])
                if len(candidates) == 1:
                    self._asset_assignment[asset.asset_id] = (*candidates[0], "interval")
        self._event_assets = {event.event_id: frozenset(asset_id for asset_id, value in self._asset_assignment.items() if value[0] == event.event_id) for event in self._events}
        self._asset_event_names = {asset_id: (value[1],) for asset_id, value in self._asset_assignment.items()}
        self._query_cache.clear()
        self.snapshot_id = self._snapshot_identity()

    def event_names_for(self, asset_id: str) -> tuple[str, ...]:
        return self._asset_event_names.get(asset_id, ())

    def assignment_for(self, asset_id: str) -> dict | None:
        value = self._asset_assignment.get(asset_id)
        return {"event_id": value[0], "name": value[1], "source": value[2]} if value else None

    @staticmethod
    def _in_interval(asset: Asset, start: str | None, end: str | None) -> bool:
        if not asset.capture_time or asset.capture_filesystem_fallback:
            return False
        try:
            value = datetime.fromisoformat(asset.capture_time.replace("Z", "+00:00"))
            if value.tzinfo is None or value.utcoffset() is None:
                return False
            return (start is None or value >= datetime.fromisoformat(start)) and (end is None or value < datetime.fromisoformat(end))
        except ValueError:
            return False

    def query(self, spec: QuerySpec) -> tuple[Asset, ...]:
        spec = spec.normalized()
        key = spec.fingerprint
        cached = self._query_cache.get(key)
        if cached is not None:
            self._query_cache.move_to_end(key)
            return cached
        assets: Iterable[Asset] = self.snapshot.assets
        if spec.event_id:
            allowed = (frozenset(asset.asset_id for asset in self.snapshot.assets if asset.asset_id not in self._asset_assignment)
                       if spec.event_id == "unassigned" else self._event_assets.get(spec.event_id, frozenset()))
            assets = (asset for asset in assets if asset.asset_id in allowed)
        if spec.media_type != "all":
            assets = (asset for asset in assets if asset.media_type == spec.media_type)
        if spec.query:
            assets = (
                asset
                for asset in assets
                if spec.query in asset.display_name.casefold()
                or spec.query in asset.catalog_name.casefold()
                or spec.query in asset.source_name.casefold()
                or spec.query in asset.asset_id.casefold()
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
        chronological = known + unknown
        groups: OrderedDict[str, list[Asset]] = OrderedDict()
        for asset in chronological:
            assignment = self._asset_assignment.get(asset.asset_id)
            groups.setdefault(assignment[0] if assignment else "unassigned", []).append(asset)
        result = tuple(asset for group in groups.values() for asset in group)
        self._query_cache[key] = result
        self._query_cache.move_to_end(key)
        while len(self._query_cache) > self._cache_size:
            self._query_cache.popitem(last=False)
        return result

    def sections(self, spec: QuerySpec) -> list[dict]:
        sections: list[dict] = []
        previous: str | None = None
        for index, asset in enumerate(self.query(spec)):
            assignment = self._asset_assignment.get(asset.asset_id)
            key = assignment[0] if assignment else "unassigned"
            if key != previous:
                sections.append({"event_id": key, "name": assignment[1] if assignment else "Bez přiřazené akce", "start_index": index, "count": 0, "date": None})
                previous = key
            section = sections[-1]
            section["count"] += 1
            date = capture_date(asset)
            if date and section["date"] is None:
                section["date"] = date.isoformat()
        return sections

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
        first_unknown: int | None = None
        for index, asset in enumerate(self.query(spec)):
            date = capture_date(asset)
            if date is None:
                unknown += 1
                if first_unknown is None:
                    first_unknown = index
                continue
            key = (date.year, date.month)
            segment = segments.setdefault(
                key, {"year": date.year, "month": date.month, "count": 0, "index": index}
            )
            segment["count"] += 1
        result = list(segments.values())
        if unknown:
            result.append({"year": None, "month": None, "count": unknown, "index": first_unknown})
        return result
