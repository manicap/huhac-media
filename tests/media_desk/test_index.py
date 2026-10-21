from __future__ import annotations

import json

from fastapi.testclient import TestClient

from media_desk.contract import load_workspace
from media_desk.index import LibraryIndex, QuerySpec, capture_date
from media_desk.web import create_app


def _set_capture(builder, entry, value, *, fallback=False, timezone="+02:00"):
    path = builder.root / entry["metadata_location"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["capture"] = {
        "datetime": value,
        "source": "filesystem:mtime" if fallback else "ExifIFD:DateTimeOriginal",
        "timezone_offset": timezone,
        "filesystem_fallback": fallback,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_index_is_deterministic_and_cursor_is_bound_to_filters(workspace_builder) -> None:
    first = workspace_builder.add_asset(1)
    second = workspace_builder.add_asset(2)
    third = workspace_builder.add_asset(3, "video")
    for number in range(4, 14):
        workspace_builder.add_asset(number)
    for entry in (first, second):
        _set_capture(workspace_builder, entry, "2026-10-01T20:00:00+02:00")
    root = workspace_builder.publish()
    index = LibraryIndex(load_workspace(root))

    ordered = index.query(QuerySpec(media_type="image"))
    ids = [item.asset_id for item in ordered]
    first_position = ids.index(first["asset_id"])
    assert ids[first_position : first_position + 2] == sorted([first["asset_id"], second["asset_id"]])
    batch = index.batch(QuerySpec(), limit=10)
    assert batch["total_count"] == 13
    assert len({item.asset_id for item in batch["items"]}) == 10

    client = TestClient(create_app(root))
    response = client.get("/api/assets", params={"limit": 10, "media_type": "image"})
    assert response.status_code == 200
    foreign = client.get(
        "/api/assets",
        params={"limit": 10, "media_type": "video", "cursor": response.json()["next_cursor"]},
    )
    assert foreign.status_code == 409


def test_locator_calendar_and_date_policy(workspace_builder) -> None:
    aware = workspace_builder.add_asset(1)
    naive = workspace_builder.add_asset(2)
    fallback = workspace_builder.add_asset(3)
    missing = workspace_builder.add_asset(4)
    _set_capture(workspace_builder, aware, "2025-12-31T23:30:00-08:00", timezone="-08:00")
    _set_capture(workspace_builder, naive, "2026-01-02T01:00:00", timezone=None)
    _set_capture(workspace_builder, fallback, "2026-01-03T01:00:00", fallback=True)
    _set_capture(workspace_builder, missing, None, timezone=None)
    root = workspace_builder.publish()
    snapshot = load_workspace(root)
    index = LibraryIndex(snapshot)

    assert capture_date(next(item for item in snapshot.assets if item.asset_id == aware["asset_id"])).isoformat() == "2025-12-31"
    assert index.locate(QuerySpec(), year=2025, month=12)["asset_id"] == aware["asset_id"]
    calendar = index.calendar(QuerySpec())
    assert calendar["years"][2025]["months"][12]["count"] == 1
    assert calendar["years"][2026]["months"][1]["count"] == 1
    assert calendar["unassigned_count"] == 2


def test_range_api_locates_without_prior_batches(workspace_builder) -> None:
    for number in range(1, 121):
        entry = workspace_builder.add_asset(number)
        _set_capture(workspace_builder, entry, f"2025-{((number - 1) % 12) + 1:02d}-01T12:00:00+01:00")
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    located = client.get("/api/locate", params={"year": 2025, "month": 3}).json()
    batch = client.get("/api/assets", params={"limit": 20, "start": located["index"]}).json()

    assert batch["start_index"] == located["index"]
    assert batch["items"][0]["asset_id"] == located["asset_id"]
    assert batch["total_count"] == 120
