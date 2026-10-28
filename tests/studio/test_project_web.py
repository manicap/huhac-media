from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from huhac_studio.catalog import (
    CatalogArtifact,
    CatalogAsset,
    CatalogOriginal,
    InMemoryWorkspaceCatalog,
)
from huhac_studio.web import create_app

from .conftest import asset_id


def _client(tmp_path, catalog, *, bind_host="127.0.0.1"):
    return TestClient(
        create_app(
            database_path=tmp_path / "profile" / "projects.sqlite3",
            catalog=catalog,
            bind_host=bind_host,
        ),
        base_url="http://127.0.0.1",
    )


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.get("/api/studio/session").json()["csrf_token"]
    return {"X-CSRF-Token": token, "Origin": "http://127.0.0.1"}


def _video_catalog(root, *, relative_path="clip.mp4", expected_size=None):
    token = "original-video-token"
    content = (root / relative_path).read_bytes() if (root / relative_path).is_file() else b""
    size = len(content) if expected_size is None else expected_size
    return InMemoryWorkspaceCatalog(
        {
            "workspace-test": {
                asset_id(2): CatalogAsset(
                    asset_id(2),
                    "video",
                    display_name="Stage video",
                    width=1920,
                    height=1080,
                    duration_seconds=12.5,
                    mime_type="video/mp4",
                    size_bytes=size,
                    original_token=token,
                )
            }
        },
        originals={
            token: CatalogOriginal(
                token=token,
                asset_id=asset_id(2),
                media_kind="video",
                relative_paths=(relative_path,),
                source_root=root,
                catalog_source_root=str(root),
                workspace_id="workspace-test",
                media_type="video/mp4",
                binding_epoch="test-binding",
                expected_size=size,
            )
        },
    )


def test_full_http_lifecycle_and_if_match(tmp_path, catalog):
    client = _client(tmp_path, catalog)
    headers = _csrf(client)
    created = client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=headers,
        json={"title": "HTTP", "tags": ["API"]},
    )
    assert created.status_code == 201
    project = created.json()

    stale = client.patch(
        f"/api/studio/projects/{project['project_id']}",
        headers={**headers, "If-Match": '"9"'},
        json={"title": "Stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "revision_conflict"

    linked = client.post(
        f"/api/studio/projects/{project['project_id']}/media-links",
        headers={**headers, "If-Match": '"1"'},
        json={"links": [{"asset_id": asset_id(1), "role": "deliverable"}]},
    )
    assert linked.status_code == 200
    assert linked.json()["revision"] == 2
    media = client.get(f"/api/studio/projects/{project['project_id']}/media").json()
    assert media["items"][0]["role"] == "deliverable"

    archived = client.post(
        f"/api/studio/projects/{project['project_id']}/archive",
        headers={**headers, "If-Match": "2"},
    )
    assert archived.json()["status"] == "archived"
    assert client.get(
        "/api/studio/workspaces/workspace-test/projects?status=archived"
    ).json()["items"][0]["project_id"] == project["project_id"]


def test_writes_require_loopback_origin_csrf_and_revision(tmp_path, catalog):
    client = _client(tmp_path, catalog)
    assert client.post(
        "/api/studio/workspaces/workspace-test/projects", json={"title": "No token"}
    ).status_code == 403

    headers = _csrf(client)
    assert client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers={**headers, "Origin": "http://evil.invalid"},
        json={"title": "Evil"},
    ).status_code == 403
    project = client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=headers,
        json={"title": "Safe"},
    ).json()
    assert client.patch(
        f"/api/studio/projects/{project['project_id']}",
        headers=headers,
        json={"title": "Missing revision"},
    ).status_code == 428

    lan_client = _client(tmp_path / "lan", catalog, bind_host="0.0.0.0")
    lan_headers = _csrf(lan_client)
    assert lan_client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=lan_headers,
        json={"title": "LAN"},
    ).status_code == 403


def test_rejects_unknown_fields_and_unsupported_media_role(tmp_path, catalog):
    client = _client(tmp_path, catalog)
    headers = _csrf(client)
    response = client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=headers,
        json={"title": "Bad", "project_id": "client-owned"},
    )
    assert response.status_code == 422

    project = client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=headers,
        json={"title": "Good"},
    ).json()
    response = client.post(
        f"/api/studio/projects/{project['project_id']}/media-links",
        headers={**headers, "If-Match": "1"},
        json={"links": [{"asset_id": asset_id(1), "role": "output"}]},
    )
    assert response.status_code == 422
    assert client.get(f"/api/studio/projects/{project['project_id']}").json()["revision"] == 1


def test_backup_stays_in_profile_and_does_not_expose_host_path(tmp_path, catalog):
    client = _client(tmp_path, catalog)
    response = client.post("/api/studio/maintenance/backup", headers=_csrf(client))

    assert response.status_code == 200
    assert set(response.json()) == {"backup_id", "created_at"}
    backups = list((tmp_path / "profile" / "backups").glob("*.sqlite3"))
    assert len(backups) == 1


def test_body_limit_is_enforced_before_write(tmp_path, catalog):
    client = _client(tmp_path, catalog)
    response = client.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers={**_csrf(client), "Content-Length": "999999"},
        json={"title": "Too large"},
    )
    assert response.status_code == 413


def test_session_and_workspace_media_expose_read_only_catalog_projection(tmp_path):
    preview_root = tmp_path / "workspace" / "previews"
    preview_root.mkdir(parents=True)
    preview = preview_root / "asset.jpg"
    preview.write_bytes(b"preview bytes")
    token = "preview-token"
    catalog = InMemoryWorkspaceCatalog(
        {
            "workspace-test": {
                asset_id(1): CatalogAsset(
                    asset_id(1),
                    "image",
                    display_name="Stage wide",
                    capture_time="2026-10-28T08:00:00Z",
                    preview_token=token,
                )
            }
        },
        artifacts={
            token: CatalogArtifact(token, preview, preview_root, "image/jpeg")
        },
    )
    client = _client(tmp_path, catalog)

    session = client.get("/api/studio/session").json()
    assert session["active_workspace_id"] == "workspace-test"
    assert session["mode"] == "online"
    assert session["runtime_id"].startswith("runtime-")
    assert client.get("/api/studio/session").headers["cache-control"] == "no-store"
    assert session["workspaces"] == [
        {"workspace_id": "workspace-test", "status": "ready"}
    ]
    media = client.get("/api/studio/workspaces/workspace-test/media").json()
    assert media["total"] == 1
    assert media["items"][0]["display_name"] == "Stage wide"
    assert media["items"][0]["preview_url"] == f"/api/studio/artifacts/{token}"
    artifact = client.get(media["items"][0]["preview_url"])
    assert artifact.content == b"preview bytes"
    assert artifact.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_offline_session_does_not_activate_stored_workspace(tmp_path, catalog):
    online = _client(tmp_path, catalog)
    created = online.post(
        "/api/studio/workspaces/workspace-test/projects",
        headers=_csrf(online),
        json={"title": "Stored offline"},
    )
    assert created.status_code == 201
    online.app.state.project_database.close()

    offline = _client(tmp_path, InMemoryWorkspaceCatalog({}))
    response = offline.get("/api/studio/session")
    session = response.json()

    assert response.headers["cache-control"] == "no-store"
    assert session["mode"] == "offline"
    assert session["active_workspace_id"] is None
    assert session["workspaces"] == [
        {"workspace_id": "workspace-test", "status": "offline"}
    ]
    projects = offline.get(
        "/api/studio/workspaces/workspace-test/projects?status=all"
    ).json()["items"]
    assert [project["title"] for project in projects] == ["Stored offline"]


def test_video_original_supports_full_and_range_responses(tmp_path):
    original_root = tmp_path / "originals"
    original_root.mkdir()
    content = b"0123456789-video-content"
    (original_root / "clip.mp4").write_bytes(content)
    client = _client(tmp_path, _video_catalog(original_root))

    media = client.get("/api/studio/workspaces/workspace-test/media").json()["items"][0]
    assert media["width"] == 1920
    assert media["height"] == 1080
    assert media["duration_seconds"] == 12.5
    assert media["mime_type"] == "video/mp4"
    assert media["original_available"] is True
    assert media["original_access_state"] == "unchecked"
    assert media["original_url"] == "/api/studio/originals/original-video-token"

    full = client.get(media["original_url"])
    ranged = client.get(media["original_url"], headers={"Range": "bytes=3-7"})
    invalid = client.get(media["original_url"], headers={"Range": "bytes=999-1000"})

    assert full.status_code == 200
    assert full.content == content
    assert full.headers["content-length"] == str(len(content))
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["cache-control"] == "no-store"
    assert ranged.status_code == 206
    assert ranged.content == content[3:8]
    assert ranged.headers["content-range"] == f"bytes 3-7/{len(content)}"
    assert ranged.headers["content-length"] == "5"
    assert ranged.headers["content-type"].startswith("video/mp4")
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == f"bytes */{len(content)}"


def test_video_original_rejects_unknown_token_and_catalog_path_escape(tmp_path):
    original_root = tmp_path / "originals"
    original_root.mkdir()
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"must stay private")
    catalog = _video_catalog(original_root, relative_path="../secret.mp4", expected_size=len(secret.read_bytes()))
    client = _client(tmp_path, catalog)

    assert client.get("/api/studio/originals/unknown-token").status_code == 404
    escaped = client.get("/api/studio/originals/original-video-token")
    assert escaped.status_code == 404
    assert secret.read_bytes() not in escaped.content


def test_video_original_rejects_symlink_escape(tmp_path):
    original_root = tmp_path / "originals"
    original_root.mkdir()
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"must stay private")
    link = original_root / "clip.mp4"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("Symlink creation is not available on this platform")
    client = _client(tmp_path, _video_catalog(original_root))

    response = client.get("/api/studio/originals/original-video-token")
    assert response.status_code == 404
    assert secret.read_bytes() not in response.content


def test_frontend_build_is_served_without_shadowing_api(tmp_path, catalog):
    frontend = tmp_path / "dist"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text("<main>Studio shell</main>", encoding="utf-8")
    (frontend / "assets" / "app.js").write_text("console.log('studio')", encoding="utf-8")
    client = TestClient(
        create_app(
            database_path=tmp_path / "projects.sqlite3",
            catalog=catalog,
            frontend_dir=frontend,
        ),
        base_url="http://127.0.0.1",
    )

    assert client.get("/").text == "<main>Studio shell</main>"
    assert client.get("/modules/projects").text == "<main>Studio shell</main>"
    assert client.get("/assets/app.js").text == "console.log('studio')"
    assert client.get("/api/studio/session").status_code == 200
