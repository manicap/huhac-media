from __future__ import annotations

import hashlib
from pathlib import Path
import os

import pytest

from fastapi.testclient import TestClient

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


def test_original_supports_http_range(workspace_builder) -> None:
    image = workspace_builder.add_asset(1)
    root = workspace_builder.publish()
    client = TestClient(create_app(root))

    response = client.get(
        f"/artifacts/original-{image['sha256']}", headers={"Range": "bytes=2-5"}
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["accept-ranges"] == "bytes"


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
    assert "Unsupported workspace contract version" in response.text
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

    response = TestClient(app).get(f"/artifacts/original-{image['sha256']}")

    assert response.status_code == 404
    assert b"secret" not in response.content
