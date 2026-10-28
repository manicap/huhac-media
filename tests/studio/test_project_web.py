from __future__ import annotations

from fastapi.testclient import TestClient

from huhac_studio.catalog import CatalogArtifact, CatalogAsset, InMemoryWorkspaceCatalog
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
