from __future__ import annotations

import json

from fastapi.testclient import TestClient

from media_desk.web import create_app


def test_overview_and_calendar_follow_active_asset(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    workspace_builder.add_asset(2, "video")
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    overview = client.get("/")
    calendar = client.get("/calendar", params={"active_asset_id": image["asset_id"]})

    assert overview.status_code == 200
    assert "Přehled" in overview.text
    assert "Otevřít knihovnu" in overview.text
    assert calendar.status_code == 200
    assert "1. 10. 2026" in calendar.text
    assert "media-1.jpg" in calendar.text
    assert "is-active" in calendar.text


def test_calendar_keeps_fallback_and_missing_dates_unassigned(workspace_builder) -> None:
    fallback = workspace_builder.add_asset(1)
    missing = workspace_builder.add_asset(2)
    for entry, value, fallback_flag in ((fallback, "2026-10-01T20:00:00", True), (missing, None, False)):
        path = workspace_builder.root / entry["metadata_location"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["capture"]["datetime"] = value
        payload["capture"]["filesystem_fallback"] = fallback_flag
        path.write_text(json.dumps(payload), encoding="utf-8")
    root = workspace_builder.publish()

    response = TestClient(create_app(root)).get(
        "/calendar", params={"active_asset_id": fallback["asset_id"]}
    )

    assert response.status_code == 200
    assert "Datum pořízení aktivního média není důvěryhodně známé" in response.text
    assert "2 médií má neznámé datum" in response.text


def test_relations_use_operational_day_and_expand_active_asset(workspace_builder) -> None:
    assigned = workspace_builder.add_asset(1)
    unassigned = workspace_builder.add_asset(2)
    fingerprint = "a" * 64
    workspace_builder.add_analysis(assigned, fingerprint)
    session_path = next((workspace_builder.root / "analysis/session-grouper").rglob("*.json"))
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    payload["result"]["sessions"][0]["operational_day"] = "2026-09-30"
    payload["result"]["unassigned"] = [
        {"asset_id": unassigned["asset_id"], "reason": "filesystem_fallback_disabled"}
    ]
    session_path.write_text(json.dumps(payload), encoding="utf-8")
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    assigned_page = client.get("/relations", params={"active_asset_id": assigned["asset_id"]})
    unassigned_page = client.get("/relations", params={"active_asset_id": unassigned["asset_id"]})

    assert assigned_page.status_code == 200
    assert "2026" in assigned_page.text
    assert "Automatická časová skupina" in assigned_page.text
    assert "<details class=\"session-card\" open>" in assigned_page.text
    assert unassigned_page.status_code == 200
    assert "filesystem_fallback_disabled" in unassigned_page.text


def test_multiple_session_results_are_not_merged(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    workspace_builder.add_analysis(image, "a" * 64)
    workspace_builder.add_analysis(image, "b" * 64)
    root = workspace_builder.publish()

    response = TestClient(create_app(root)).get("/relations")

    assert response.status_code == 200
    assert "Výsledek není jednoznačný" in response.text
