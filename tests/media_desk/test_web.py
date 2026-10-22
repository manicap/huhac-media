from __future__ import annotations

import hashlib
from pathlib import Path
import os

import pytest

from fastapi.testclient import TestClient

from media_desk.config import ORIGINALS_MAPPING_VERIFICATION, OriginalsMapping, Settings
from media_desk.web import create_app


def _state(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        str(path.relative_to(root)): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def _original_url(client: TestClient, sha256: str) -> str:
    response = client.get(f"/api/assets/{sha256}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["original_online"] is False
    assert payload["original_access_state"] == "unchecked"
    assert payload["original_url"]
    return payload["original_url"]


def test_filtering_and_pagination(workspace_builder) -> None:
    workspace_builder.add_asset(1, source_name="night/poster.jpg")
    workspace_builder.add_asset(2, source_name="night/crowd.jpg")
    video = workspace_builder.add_asset(3, "video", source_name="stage/clip.mp4")
    workspace_builder.add_keyframes(video, "a" * 64)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    page = client.get("/api/assets", params={"media_type": "image", "page": 1, "page_size": 1})
    search = client.get("/api/assets", params={"q": "clip"})

    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["assets"]) == 1
    assert search.json()["total"] == 1
    assert search.json()["assets"][0]["media_type"] == "video"


def test_library_uses_virtualized_client_and_cursor_api(workspace_builder) -> None:
    for number in range(1, 121):
        workspace_builder.add_asset(number)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    page = client.get("/library", params={"media_type": "image", "q": "media"})
    script = client.get("/static/library.js")
    logo = client.get("/static/huhac-logo.png")
    batch = client.get("/api/assets", params={"limit": 50, "start": 50})

    assert page.status_code == 200
    assert 'class="brand-logo"' in page.text
    assert 'alt="HUHÁČ"' in page.text
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert "library-viewport" in page.text
    assert "pagination" not in page.text
    assert script.status_code == 200
    assert "maxCachedBatches = 12" in script.text
    assert "__MEDIA_DESK_DEBUG__" in script.text
    assert "jumpToPeriod" in script.text
    assert "time-navigator" in page.text
    assert 'class="app-main"' in page.text
    assert 'class="nav-toggle"' in page.text
    assert "scrollRoot.addEventListener" in script.text
    assert 'name="density"' in page.text
    assert 'localStorage.setItem("mediaDesk.libraryDensity"' in script.text
    assert 'getPropertyValue("--tile-row-height")' in script.text
    assert "formatCaptureLabel" in script.text
    assert "rowHeight = 324" not in script.text
    assert batch.json()["start_index"] == 50
    assert len(batch.json()["items"]) == 50


def test_artifact_registry_blocks_traversal_and_sqlite(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    sqlite = root / "state/catalog.sqlite3"
    sqlite.parent.mkdir(parents=True)
    sqlite.write_bytes(b"private")
    client = TestClient(create_app(root))
    sha256 = image["sha256"]

    assert client.get(f"/artifacts/preview-{sha256}").status_code == 200
    assert client.get("/artifacts/..%2Fstate%2Fcatalog.sqlite3").status_code == 404
    assert client.get("/artifacts/state%2Fcatalog.sqlite3").status_code == 404
    assert b"private" not in client.get("/api/assets").content


def test_original_supports_http_range(workspace_builder, monkeypatch) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    url = _original_url(client, image["sha256"])
    original_open = Path.open
    opened = []

    def counted_open(path: Path, *args, **kwargs):
        if str(path).startswith(str(workspace_builder.originals)):
            opened.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)
    response = client.get(url, headers={"Range": "bytes=2-5"})
    invalid = client.get(url, headers={"Range": "bytes=999-1000"})

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "no-store"
    assert invalid.status_code == 416
    assert len(opened) == 2


def test_original_full_get_is_verified_and_opened_on_demand(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    response = client.get(_original_url(client, image["sha256"]))

    assert response.status_code == 200
    assert response.content == b"0123456789-original-media"
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["cache-control"] == "no-store"


def test_preview_has_identity_cache_headers(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))
    url = f"/artifacts/preview-{image['sha256']}"

    first = client.get(url)
    cached = client.get(url, headers={"If-None-Match": first.headers["etag"]})

    assert first.status_code == 200
    assert "immutable" in first.headers["cache-control"]
    assert cached.status_code == 304


def test_detail_preserves_filtered_return_and_neighbors(workspace_builder) -> None:
    first = workspace_builder.add_asset(1)
    second = workspace_builder.add_asset(2)
    workspace_builder.add_asset(3, "video")
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    response = client.get(
        f"/assets/{second['sha256']}",
        params={"return_to": "/library?media_type=image&q=media"},
    )
    unsafe = client.get(
        f"/assets/{first['sha256']}", params={"return_to": "//example.invalid/steal"}
    )

    assert response.status_code == 200
    assert "Předchozí" in response.text or "Další" in response.text
    assert "media_type=image" in response.text
    assert "ArrowLeft" in response.text
    assert "example.invalid" not in unsafe.text


def test_requests_do_not_modify_workspace(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    before = _state(root)
    client = TestClient(create_app(root))

    assert client.get("/").status_code == 200
    assert client.get(f"/assets/{image['sha256']}").status_code == 200
    assert client.get("/api/assets").status_code == 200
    assert client.get(f"/artifacts/preview-{image['sha256']}").status_code == 200

    assert _state(root) == before


def test_invalid_workspace_renders_safe_error(workspace_builder) -> None:
    root = workspace_builder.publish(version=9)
    client = TestClient(create_app(root))

    response = client.get("/")

    assert response.status_code == 503
    assert "nepodporovanou verzi kontraktu" in response.text
    assert "Traceback" not in response.text


def test_original_symlink_swap_is_blocked(workspace_builder, tmp_path: Path) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    app = create_app(root)
    original = workspace_builder.originals / "set/media-1.jpg"
    outside = tmp_path / "outside-secret.bin"
    outside.write_bytes(b"secret")
    original.unlink()
    try:
        os.symlink(outside, original)
    except OSError:
        pytest.skip("Symlink creation is unavailable on this Windows host")

    client = TestClient(app)
    response = client.get(_original_url(client, image["sha256"]))

    assert response.status_code == 404
    assert b"secret" not in response.content


def test_original_deleted_after_start_fails_closed(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))
    url = _original_url(client, image["sha256"])
    (workspace_builder.originals / "set/media-1.jpg").unlink()

    response = client.get(url)

    assert response.status_code == 404


def test_original_nested_symlink_created_after_start_is_blocked(
    workspace_builder, tmp_path: Path
) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))
    url = _original_url(client, image["sha256"])
    source_dir = workspace_builder.originals / "set"
    source_file = source_dir / "media-1.jpg"
    source_file.unlink()
    source_dir.rmdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "media-1.jpg").write_bytes(b"nested-secret")
    try:
        os.symlink(outside_dir, source_dir, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlink creation is unavailable on this Windows host")

    response = client.get(url)

    assert response.status_code == 404
    assert b"nested-secret" not in response.content


def test_mapping_epoch_invalidates_old_original_token(workspace_builder, tmp_path: Path) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    source_root = str(workspace_builder.originals.resolve())
    second_root = tmp_path / "second-originals"
    second_file = second_root / "set/media-1.jpg"
    second_file.parent.mkdir(parents=True)
    second_file.write_bytes(b"second-root")
    first_mapping = OriginalsMapping(
        workspace_builder.workspace_id,
        source_root,
        workspace_builder.originals.resolve(),
        ORIGINALS_MAPPING_VERIFICATION,
        1,
        1,
    )
    second_mapping = OriginalsMapping(
        workspace_builder.workspace_id,
        source_root,
        second_root.resolve(),
        ORIGINALS_MAPPING_VERIFICATION,
        1,
        1,
    )
    first = TestClient(
        create_app(settings=Settings(root, originals_mapping=first_mapping))
    )
    second = TestClient(
        create_app(settings=Settings(root, originals_mapping=second_mapping))
    )
    first_url = _original_url(first, image["sha256"])
    second_url = _original_url(second, image["sha256"])

    assert first_url != second_url
    assert second.get(first_url).status_code == 404
    assert second.get(second_url).content == b"second-root"


def test_startup_and_metadata_gets_do_not_touch_individual_originals(
    workspace_builder, monkeypatch
) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    original_root = workspace_builder.originals.absolute()
    calls = []
    original_resolve = Path.resolve
    original_stat = Path.stat
    original_open = Path.open

    def is_child(path: Path) -> bool:
        value = str(path.absolute())
        return value.startswith(str(original_root) + os.sep)

    def guarded_resolve(path: Path, *args, **kwargs):
        if is_child(path):
            calls.append(("resolve", path))
        return original_resolve(path, *args, **kwargs)

    def guarded_stat(path: Path, *args, **kwargs):
        if is_child(path):
            calls.append(("stat", path))
        return original_stat(path, *args, **kwargs)

    def guarded_open(path: Path, *args, **kwargs):
        if is_child(path):
            calls.append(("open", path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    monkeypatch.setattr(Path, "stat", guarded_stat)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(
        "media_desk.originals._sha256_file",
        lambda _path: pytest.fail("startup and browsing must not hash originals"),
    )

    client = TestClient(create_app(root))
    assert client.get("/").status_code == 200
    assert client.get("/library").status_code == 200
    assert client.get("/api/index").status_code == 200
    assert client.get(f"/assets/{image['sha256']}").status_code == 200
    assert calls == []
