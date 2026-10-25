from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4

from media_desk.models import EventRecord, WorkspaceSnapshot


SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CATALOG_NAME = re.compile(r"(VID|IMG)-([0-9]{4,})")
_EVENT_ID = re.compile(r"event-[0-9a-f]{32}")


class UserDataError(ValueError):
    pass


@dataclass
class UserLibraryData:
    workspace_id: str
    catalog_names: dict[str, str]
    display_names: dict[str, str]
    events: list[EventRecord]
    provenance_projection: dict[str, Any] | None = None


def library_data_path(profile_config_path: Path | None, workspace_id: str) -> Path | None:
    if profile_config_path is None:
        return None
    return Path(profile_config_path).parent / "library-data" / f"{workspace_id}.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise UserDataError(f"Nelze uložit uživatelská data Media Desku: {exc}") from exc


def _clean_name(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise UserDataError(f"{label} musí být text")
    name = value.strip()
    if not name or len(name) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise UserDataError(f"{label} je prázdný nebo obsahuje nepovolené znaky")
    return name


def _parse(payload: object, workspace_id: str) -> UserLibraryData:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise UserDataError("Nepodporovaná verze uživatelských dat Media Desku")
    if payload.get("workspace_id") != workspace_id:
        raise UserDataError("Uživatelská data patří jinému workspace")
    raw_catalog = payload.get("catalog_names")
    raw_display = payload.get("display_names")
    raw_events = payload.get("events")
    if not isinstance(raw_catalog, dict) or not isinstance(raw_display, dict) or not isinstance(raw_events, list):
        raise UserDataError("Neplatná struktura uživatelských dat Media Desku")
    catalog_names: dict[str, str] = {}
    display_names: dict[str, str] = {}
    for asset_id, value in raw_catalog.items():
        if not isinstance(asset_id, str) or not asset_id.startswith("sha256:"):
            raise UserDataError("Neplatný asset ID v katalogizačních názvech")
        catalog_names[asset_id] = _clean_name(value, "Katalogizační název")
    for asset_id, value in raw_display.items():
        if not isinstance(asset_id, str) or not asset_id.startswith("sha256:"):
            raise UserDataError("Neplatný asset ID v zobrazovacích názvech")
        display_names[asset_id] = _clean_name(value, "Zobrazovací název")
    events: list[EventRecord] = []
    seen_events: set[str] = set()
    for item in raw_events:
        if not isinstance(item, dict) or set(item) != {"event_id", "name", "session_ids"}:
            raise UserDataError("Neplatný záznam akce")
        event_id = item["event_id"]
        session_ids = item["session_ids"]
        if not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id) or event_id in seen_events:
            raise UserDataError("Neplatný nebo duplicitní identifikátor akce")
        if not isinstance(session_ids, list) or not session_ids or any(
            not isinstance(value, str) or not value for value in session_ids
        ):
            raise UserDataError("Akce musí obsahovat alespoň jednu platnou časovou relaci")
        seen_events.add(event_id)
        events.append(EventRecord(event_id, _clean_name(item["name"], "Název akce"), tuple(sorted(set(session_ids)))))
    projection = payload.get("provenance_projection")
    if projection is not None and not isinstance(projection, dict):
        raise UserDataError("Neplatná provenance zobrazovacích názvů")
    return UserLibraryData(workspace_id, catalog_names, display_names, events, projection)


def _serialize(data: UserLibraryData) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": data.workspace_id,
        "catalog_names": data.catalog_names,
        "display_names": data.display_names,
        "events": [
            {"event_id": event.event_id, "name": event.name, "session_ids": list(event.session_ids)}
            for event in sorted(data.events, key=lambda value: (value.name.casefold(), value.event_id))
        ],
        "provenance_projection": data.provenance_projection,
    }


def _connector_manifest(workspace_id: str, environ: Mapping[str, str]) -> Path | None:
    local = environ.get("LOCALAPPDATA")
    if not local:
        return None
    root = Path(local) / "HUHAC" / "MediaConnector" / "libraries" / workspace_id / "manifests"
    try:
        candidates = [path for path in root.glob("*.json") if path.is_file()]
        return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None
    except OSError:
        return None


def _project_original_names(path: Path, workspace_id: str, asset_hashes: set[str]) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserDataError(f"Nelze načíst transfer manifest: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("contract") != "huhac.media-connector.provenance":
        raise UserDataError("Transfer manifest nemá očekávaný veřejný provenance kontrakt")
    if payload.get("contract_version") != 1 or payload.get("workspace_id") != workspace_id:
        raise UserDataError("Transfer manifest patří jiné verzi nebo workspace")
    items = payload.get("items")
    if not isinstance(items, list):
        raise UserDataError("Transfer manifest neobsahuje pole items")
    paths_by_hash: dict[str, set[str]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("status") not in {"published", "deduplicated_existing"}:
            continue
        sha256 = item.get("content_sha256")
        logical = item.get("logical_path")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256) or sha256 not in asset_hashes:
            continue
        if not isinstance(logical, str) or not logical or "\\" in logical:
            continue
        pure = PurePosixPath(logical)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            continue
        paths_by_hash.setdefault(sha256, set()).add(pure.as_posix())
    candidates = {
        sha256: PurePosixPath(next(iter(paths))).name
        for sha256, paths in paths_by_hash.items() if len(paths) == 1
    }
    counts: dict[str, int] = {}
    for name in candidates.values():
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    names = {sha256: name for sha256, name in candidates.items() if counts[name.casefold()] == 1}
    return names, {
        "contract": payload["contract"], "contract_version": 1,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "projected_names": len(names), "source": str(path),
    }


class UserDataStore:
    def __init__(
        self, snapshot: WorkspaceSnapshot, path: Path | None, *,
        environ: Mapping[str, str] | None = None, connector_manifest: Path | None = None,
    ) -> None:
        self.path = path
        self._lock = RLock()
        self.error: str | None = None
        if path is not None and path.exists():
            try:
                self.data = _parse(json.loads(path.read_text(encoding="utf-8")), snapshot.workspace_id)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, UserDataError) as exc:
                self.error = str(exc)
                self.data = UserLibraryData(snapshot.workspace_id, {}, {}, [])
        else:
            self.data = UserLibraryData(snapshot.workspace_id, {}, {}, [])
        changed = self._ensure_names(snapshot, environ or os.environ, connector_manifest)
        self.apply(snapshot)
        if changed and path is not None and self.error is None:
            self.save()

    def _ensure_names(
        self, snapshot: WorkspaceSnapshot, environ: Mapping[str, str], connector_manifest: Path | None,
    ) -> bool:
        changed = False
        used: dict[str, set[int]] = {"VID": set(), "IMG": set()}
        for value in self.data.catalog_names.values():
            match = _CATALOG_NAME.fullmatch(value)
            if match:
                used[match.group(1)].add(int(match.group(2)))
        for media_type, prefix in (("video", "VID"), ("image", "IMG")):
            next_number = 1
            for asset in sorted((item for item in snapshot.assets if item.media_type == media_type), key=lambda item: item.asset_id):
                if asset.asset_id in self.data.catalog_names:
                    continue
                while next_number in used[prefix]:
                    next_number += 1
                self.data.catalog_names[asset.asset_id] = f"{prefix}-{next_number:04d}"
                used[prefix].add(next_number)
                changed = True
        missing = [asset for asset in snapshot.assets if asset.asset_id not in self.data.display_names]
        projected: dict[str, str] = {}
        if missing and self.data.provenance_projection is None:
            manifest = connector_manifest or _connector_manifest(snapshot.workspace_id, environ)
            if manifest is not None:
                try:
                    projected, projection = _project_original_names(
                        manifest, snapshot.workspace_id, {asset.sha256 for asset in snapshot.assets}
                    )
                    self.data.provenance_projection = projection
                except UserDataError as exc:
                    self.data.provenance_projection = {"error": str(exc)}
                changed = True
        for asset in missing:
            self.data.display_names[asset.asset_id] = projected.get(asset.sha256, self.data.catalog_names[asset.asset_id])
            changed = True
        return changed

    def apply(self, snapshot: WorkspaceSnapshot) -> None:
        for asset in snapshot.assets:
            asset.catalog_name = self.data.catalog_names.get(asset.asset_id, asset.asset_id)
            asset.display_name = self.data.display_names.get(asset.asset_id, asset.catalog_name)

    @property
    def events(self) -> tuple[EventRecord, ...]:
        return tuple(sorted(self.data.events, key=lambda value: (value.name.casefold(), value.event_id)))

    def save(self) -> None:
        if self.path is not None:
            _atomic_write(self.path, _serialize(self.data))

    def upsert_event(
        self, *, event_id: str | None, name: str, session_ids: tuple[str, ...], valid_session_ids: set[str],
    ) -> EventRecord:
        clean_name = _clean_name(name, "Název akce")
        selected = tuple(sorted(set(session_ids)))
        if not selected or any(value not in valid_session_ids for value in selected):
            raise UserDataError("Vyberte alespoň jednu existující časovou relaci")
        if event_id:
            if not _EVENT_ID.fullmatch(event_id) or not any(item.event_id == event_id for item in self.data.events):
                raise UserDataError("Akce neexistuje")
        else:
            event_id = f"event-{uuid4().hex}"
        record = EventRecord(event_id, clean_name, selected)
        with self._lock:
            self.data.events = [item for item in self.data.events if item.event_id != event_id]
            self.data.events.append(record)
            self.save()
        return record

    def delete_event(self, event_id: str) -> None:
        if not _EVENT_ID.fullmatch(event_id):
            raise UserDataError("Neplatný identifikátor akce")
        with self._lock:
            retained = [item for item in self.data.events if item.event_id != event_id]
            if len(retained) == len(self.data.events):
                raise UserDataError("Akce neexistuje")
            self.data.events = retained
            self.save()
