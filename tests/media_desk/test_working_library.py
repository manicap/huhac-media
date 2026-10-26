from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from fastapi.testclient import TestClient

from media_desk.config import Settings
from media_desk.models import EventInterval
from media_desk.web import create_app


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1")


def _csrf(client: TestClient, page: str = "/events") -> str:
    response = client.get(page)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    token = match.group(1) if match else client.cookies.get("media_desk_csrf")
    assert response.status_code == 200 and token
    return token


def _manifest(path: Path, workspace_id: str, items: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "contract": "huhac.media-connector.provenance",
                "contract_version": 1,
                "workspace_id": workspace_id,
                "run_id": "run-test",
                "items": items,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_names_are_projected_once_and_catalog_names_survive_restart(workspace_builder, tmp_path: Path) -> None:
    unique = workspace_builder.add_asset(1, source_name="objects/one/payload.jpg")
    ambiguous = workspace_builder.add_asset(2, "video", source_name="objects/two/payload.mp4")
    root = workspace_builder.publish()
    manifest = _manifest(
        tmp_path / "transfer.json",
        workspace_builder.workspace_id,
        [
            {"status": "published", "content_sha256": unique["sha256"], "logical_path": "Výběr/žluťoučký kůň.jpg"},
            {"status": "published", "content_sha256": ambiguous["sha256"], "logical_path": "clip.mp4"},
            {"status": "deduplicated_existing", "content_sha256": ambiguous["sha256"], "logical_path": "clip (1).mp4"},
        ],
    )
    data_path = tmp_path / "profile/library-data/test.json"

    first = _client(create_app(root, user_data_path=data_path, connector_manifest=manifest))
    payload = first.get("/api/assets", params={"page_size": 10}).json()["assets"]
    by_id = {item["asset_id"]: item for item in payload}
    assert by_id[unique["asset_id"]]["display_name"] == "žluťoučký kůň.jpg"
    assert by_id[unique["asset_id"]]["catalog_name"] == "IMG-0001"
    assert by_id[ambiguous["asset_id"]]["display_name"] == "VID-0001"
    assert data_path.exists()

    manifest.unlink()
    restarted = _client(create_app(root, user_data_path=data_path))
    restarted_payload = restarted.get(f"/api/assets/{unique['sha256']}").json()
    assert restarted_payload["display_name"] == "žluťoučký kůň.jpg"
    assert restarted_payload["catalog_name"] == "IMG-0001"


def test_events_persist_and_filter_cursor_api(workspace_builder, tmp_path: Path) -> None:
    assigned = workspace_builder.add_asset(1)
    workspace_builder.add_asset(2)
    workspace_builder.add_analysis(assigned, "a" * 64)
    root = workspace_builder.publish()
    data_path = tmp_path / "library-data.json"
    client = _client(create_app(root, user_data_path=data_path))
    token = _csrf(client)

    saved = client.post(
        "/events/save",
        data={
            "csrf_token": token,
            "event_id": "",
            "name": "Koncert Žluťoučký",
            "session_ids": "session-synthetic",
        },
        headers={"Origin": "http://127.0.0.1"},
    )
    assert saved.status_code == 200
    assert "Koncert Žluťoučký" in saved.text
    stored = json.loads(data_path.read_text(encoding="utf-8"))
    event_id = stored["events"][0]["event_id"]
    batch = client.get("/api/assets", params={"limit": 10, "event_id": event_id}).json()
    assert batch["total_count"] == 1
    assert batch["items"][0]["asset_id"] == assigned["asset_id"]
    assert batch["items"][0]["event_names"] == ["Koncert Žluťoučký"]

    restarted = _client(create_app(root, user_data_path=data_path))
    page = restarted.get("/library", params={"event_id": event_id})
    assert page.status_code == 200
    assert "Koncert Žluťoučký" in page.text
    assert restarted.get("/api/index", params={"event_id": event_id}).json()["total_count"] == 1


def test_video_card_contract_is_lazy_and_shared_audio_is_browser_local(workspace_builder) -> None:
    video = workspace_builder.add_asset(1, "video", preview=False)
    metadata = workspace_builder.root / video["metadata_location"]
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["technical"]["duration_seconds"] = 65.4
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    root = workspace_builder.publish()
    client = _client(create_app(root))

    item = client.get(f"/api/assets/{video['sha256']}").json()
    script = client.get("/static/library.js").text
    audio = client.get("/static/media-controls.js").text
    assert item["preview_url"] is None
    assert item["original_url"]
    assert item["display_name"] == "VID-0001"
    assert item["event_names"] == []
    assert "video.preload = \"metadata\"" in script
    assert "await video.play()" in script
    assert "Bez náhledu" in script
    assert "/static/huhac-placeholder.png" in script
    assert "ověří se při otevření" not in script
    assert 'localStorage.setItem(STORAGE_KEY' in audio
    assert "activeVideo.pause()" in audio
    assert "server" not in audio.casefold()


def test_card_polish_uses_portal_toolbar_and_capture_time_hierarchy(workspace_builder) -> None:
    workspace_builder.add_asset(1, "video", preview=False)
    root = workspace_builder.publish()
    client = _client(create_app(root))

    script = client.get("/static/library.js").text
    styles = client.get("/static/library.css").text
    logo = client.get("/static/huhac-placeholder.png")
    assert 'document.body.append(menuOverlay)' in script
    assert 'menuOverlay.className = "card-menu-overlay"' in script
    assert 'window.innerHeight' in script and 'window.innerWidth' in script
    assert 'scrollRoot.addEventListener("scroll", () => { closeMenu();' in script
    assert '<div class="tile-toolbar">' in script
    assert 'item.media_type === "video" ? "Video" : "Foto"' in script
    assert 'class="tile-media-badge"' in script
    assert 'class="tile-capture-overlay"' in script
    assert 'class="tile-time"' in script and 'class="tile-date"' in script
    assert 'time: `${match[4]}:${match[5]}`' in script
    assert 'class="tile-detail"' in script
    assert 'item.event_names?.length' in script
    assert 'tile-secondary' not in script
    assert 'brand-placeholder' in script and 'Bez náhledu' in script
    assert 'revealAction.hidden = window.matchMedia' in script
    assert 'tile.querySelector("video")?.pause()' in script
    assert '.card-menu-overlay { position: fixed;' in styles
    assert '.tile-media-strip' not in styles
    assert 'aspect-ratio: 9 / 16' in styles
    assert '--tile-min: 132px' in styles
    assert 'previewWidth * 16 / 9' in script
    assert 'app.style.setProperty("--tile-height"' in script
    assert '.tile-event' in styles
    assert '.tile-play { position: absolute;' not in styles
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert len(logo.content) > 100_000


def test_reveal_uses_only_validated_asset_path_and_existing_http_guards(
    workspace_builder, tmp_path: Path, monkeypatch
) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    profile = tmp_path / "profile/config.toml"
    app = create_app(
        settings=Settings(
            workspace=root,
            host="127.0.0.1",
            profile_config_path=profile,
            workspace_source="profile",
        ),
        user_data_path=tmp_path / "user-data.json",
    )
    client = _client(app)
    token = _csrf(client, "/library")
    calls = []
    monkeypatch.setattr("media_desk.web.sys.platform", "win32")
    monkeypatch.setattr("media_desk.web.subprocess.Popen", lambda command, **kwargs: calls.append((command, kwargs)))

    opened = client.post(
        f"/api/assets/{image['sha256']}/reveal",
        data={"csrf_token": token},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert opened.status_code == 200
    assert calls[0][0][0:2] == ["explorer.exe", "/select,"]
    assert Path(calls[0][0][2]) == workspace_builder.originals / "set/media-1.jpg"
    assert calls[0][1]["close_fds"] is True

    foreign = client.post(
        f"/api/assets/{image['sha256']}/reveal",
        data={"csrf_token": token},
        headers={"Origin": "http://evil.invalid"},
    )
    injected = client.post(
        f"/api/assets/{image['sha256']}/reveal",
        data={"csrf_token": token, "path": "C:\\Windows\\System32"},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert foreign.status_code == 403
    assert injected.status_code == 400
    assert len(calls) == 1


def test_event_split_is_half_open_atomic_and_manual_assignment_wins(
    workspace_builder, tmp_path: Path
) -> None:
    before = workspace_builder.add_asset(16)
    boundary = workspace_builder.add_asset(17)
    after = workspace_builder.add_asset(18)
    unknown = workspace_builder.add_asset(19)
    workspace_builder.add_analysis(before, "b" * 64)
    session_path = next((workspace_builder.root / "analysis/session-grouper").rglob("*.json"))
    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    session_payload["result"]["sessions"][0]["assets"] = [
        {"asset_id": item["asset_id"]} for item in (before, boundary, after, unknown)
    ]
    session_path.write_text(json.dumps(session_payload), encoding="utf-8")
    times = {
        before["asset_id"]: "2026-10-16T21:34:59+02:00",
        boundary["asset_id"]: "2026-10-16T21:35:00+02:00",
        after["asset_id"]: "2026-10-16T22:00:00+02:00",
    }
    for item in (before, boundary, after, unknown):
        path = workspace_builder.root / item["metadata_location"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if item is unknown:
            payload["capture"] = {"datetime": None, "source": None, "timezone_offset": None, "filesystem_fallback": False}
        else:
            payload["capture"]["datetime"] = times[item["asset_id"]]
        path.write_text(json.dumps(payload), encoding="utf-8")
    root = workspace_builder.publish()
    data_path = tmp_path / "events-v2.json"
    client = _client(create_app(root, user_data_path=data_path))
    token = _csrf(client)
    revision = json.loads(data_path.read_text(encoding="utf-8"))["revision"]
    client.post(
        "/events/save",
        data={"csrf_token": token, "event_id": "", "name": "Exploze", "session_ids": "session-synthetic", "revision": revision},
        headers={"Origin": "http://127.0.0.1"},
    )
    stored = json.loads(data_path.read_text(encoding="utf-8"))
    event_id, revision = stored["events"][0]["event_id"], stored["revision"]
    assigned = client.post(
        "/events/assign",
        data={"csrf_token": token, "asset_id": after["asset_id"], "event_id": event_id, "revision": revision},
        headers={"Origin": "http://127.0.0.1"},
    )
    revision = assigned.json()["revision"]
    form = {
        "csrf_token": token, "event_id": event_id, "session_id": "session-synthetic",
        "boundary": "2026-10-16T21:35", "new_name": "COVER INCI", "revision": revision,
    }
    preview = client.post("/events/split/preview", data=form, headers={"Origin": "http://127.0.0.1"})
    assert preview.status_code == 200
    assert {key: preview.json()[key] for key in ("retained_count", "moved_count", "unknown_count", "manual_count")} == {
        "retained_count": 1, "moved_count": 1, "unknown_count": 1, "manual_count": 1,
    }
    split = client.post("/events/split", data=form, headers={"Origin": "http://127.0.0.1"})
    assert split.status_code == 200
    new_event = split.json()["event_id"]
    assert client.get("/api/index", params={"event_id": event_id}).json()["total_count"] == 2
    assert client.get("/api/index", params={"event_id": new_event}).json()["total_count"] == 1
    assert client.get("/api/index", params={"event_id": "unassigned"}).json()["total_count"] == 1
    assert json.loads(data_path.read_text(encoding="utf-8"))["manual_assignments"][after["asset_id"]] == event_id
    second_preview = client.post(
        "/events/split/preview",
        data={**form, "boundary": "2026-10-16T21:34:30", "revision": split.json()["revision"]},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert second_preview.status_code == 200
    assert {
        key: second_preview.json()[key]
        for key in ("retained_count", "moved_count", "unknown_count", "manual_count")
    } == {"retained_count": 0, "moved_count": 1, "unknown_count": 0, "manual_count": 1}
    moved = client.post(
        "/events/boundary",
        data={
            "csrf_token": token, "event_id": event_id, "session_id": "session-synthetic",
            "edge": "end", "boundary": "2026-10-16T21:34:30", "revision": split.json()["revision"],
        },
        headers={"Origin": "http://127.0.0.1"},
    )
    assert moved.status_code == 200
    assert client.get("/api/index", params={"event_id": event_id}).json()["total_count"] == 1
    assert client.get("/api/index", params={"event_id": new_event}).json()["total_count"] == 2
    restarted = _client(create_app(root, user_data_path=data_path))
    assert restarted.get("/api/index", params={"event_id": new_event}).json()["total_count"] == 2
    restart_token = _csrf(restarted)
    deleted = restarted.post(
        "/events/delete",
        data={"csrf_token": restart_token, "event_id": new_event, "revision": moved.json()["revision"]},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert deleted.status_code == 200
    assert restarted.get("/api/index").json()["total_count"] == 4


def test_v1_event_data_migrates_and_stale_revision_is_rejected(workspace_builder, tmp_path: Path) -> None:
    asset = workspace_builder.add_asset(1)
    workspace_builder.add_analysis(asset, "c" * 64)
    root = workspace_builder.publish()
    path = tmp_path / "legacy.json"
    event_id = "event-" + "a" * 32
    path.write_text(json.dumps({
        "schema_version": 1, "workspace_id": workspace_builder.workspace_id,
        "catalog_names": {}, "display_names": {},
        "events": [{"event_id": event_id, "name": "Legacy", "session_ids": ["session-synthetic"]}],
        "provenance_projection": None,
    }), encoding="utf-8")
    client = _client(create_app(root, user_data_path=path))
    token = _csrf(client)
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2 and migrated["events"][0]["intervals"] == []
    stale = client.post(
        "/events/assign",
        data={"csrf_token": token, "asset_id": asset["asset_id"], "event_id": event_id, "revision": migrated["revision"] - 1},
        headers={"Origin": "http://127.0.0.1"},
    )
    assert stale.status_code == 409


def test_event_edit_drops_intervals_for_removed_sessions(workspace_builder, tmp_path: Path) -> None:
    workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    data_path = tmp_path / "events-v2.json"
    app = create_app(root, user_data_path=data_path)
    store = app.state.user_data_store
    event = store.add_event(
        "Dvě relace",
        ("session-a", "session-b"),
        (
            EventInterval("session-a", None, "2026-10-16T21:35:00+02:00"),
            EventInterval("session-b", "2026-10-17T18:00:00+02:00", None),
        ),
    )

    updated = store.upsert_event(
        event_id=event.event_id,
        name=event.name,
        session_ids=("session-b",),
        valid_session_ids={"session-a", "session-b"},
        expected_revision=store.revision,
    )

    assert updated.session_ids == ("session-b",)
    assert [interval.session_id for interval in updated.intervals] == ["session-b"]
    restarted = create_app(root, user_data_path=data_path)
    assert restarted.state.user_data_store.events[0].session_ids == ("session-b",)
