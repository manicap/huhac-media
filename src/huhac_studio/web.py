from __future__ import annotations

import hmac
import ipaddress
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from huhac_studio.catalog import InMemoryWorkspaceCatalog, WorkspaceCatalog
from huhac_studio.config import default_project_database_path
from huhac_studio.database import ProjectDatabase
from huhac_studio.errors import ConflictError, NotFoundError, ProjectCoreError, ValidationError
from huhac_studio.service import ProjectService

_CSRF_COOKIE = "huhac_studio_csrf"
_MAX_BODY_BYTES = 128 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictModel):
    title: str
    description: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProjectPatch(StrictModel):
    title: str | None = None
    description: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class MediaLinkCreate(StrictModel):
    asset_id: str
    role: str = "reference"
    note: str | None = None
    position: int | None = None


class MediaLinksCreate(StrictModel):
    links: list[MediaLinkCreate]


class MediaLinkPatch(StrictModel):
    role: str | None = None
    note: str | None = None
    position: int | None = None


def _is_loopback(value: str | None) -> bool:
    if not value:
        return False
    if value.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _revision(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail={"code": "revision_required"})
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:].strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(status_code=400, detail={"code": "invalid_revision"})
    return int(value)


def create_app(
    *,
    database_path: Path | None = None,
    catalog: WorkspaceCatalog | None = None,
    bind_host: str = "127.0.0.1",
    frontend_dir: Path | None = None,
) -> FastAPI:
    database = ProjectDatabase(database_path or default_project_database_path())
    service = ProjectService(database, catalog or InMemoryWorkspaceCatalog({}))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            database.close()

    app = FastAPI(
        title="HUHÁČ Studio Project Core", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.project_database = database
    app.state.project_service = service
    app.state.csrf_secret = secrets.token_urlsafe(32)
    app.state.bind_host = bind_host

    @app.exception_handler(ProjectCoreError)
    async def project_error_handler(_request: Request, exc: ProjectCoreError):
        status = 400
        if isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, ConflictError):
            status = 409
        elif isinstance(exc, ValidationError):
            status = 422
        return JSONResponse(
            status_code=status,
            content={"error": {"code": exc.code, "message": exc.message, **exc.details}},
        )

    async def protect_write(request: Request) -> None:
        if not _is_loopback(app.state.bind_host):
            raise HTTPException(status_code=403, detail={"code": "loopback_required"})
        raw_host = request.headers.get("host", "")
        host_name = urlsplit(f"//{raw_host}").hostname
        if not _is_loopback(host_name):
            raise HTTPException(status_code=403, detail={"code": "invalid_host"})
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            expected = f"{request.url.scheme}://{raw_host}".casefold()
            actual = f"{parsed.scheme}://{parsed.netloc}".casefold()
            if actual != expected:
                raise HTTPException(status_code=403, detail={"code": "invalid_origin"})
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > _MAX_BODY_BYTES):
            raise HTTPException(status_code=413, detail={"code": "body_too_large"})
        body = await request.body()
        if len(body) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail={"code": "body_too_large"})
        cookie = request.cookies.get(_CSRF_COOKIE, "")
        token = request.headers.get("x-csrf-token", "")
        secret = app.state.csrf_secret
        if (
            not cookie
            or not token
            or not hmac.compare_digest(cookie, token)
            or not hmac.compare_digest(token, secret)
        ):
            raise HTTPException(status_code=403, detail={"code": "invalid_csrf"})

    @app.get("/api/studio/session")
    def session(response: Response) -> dict:
        token = app.state.csrf_secret
        response.set_cookie(
            _CSRF_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/api/studio",
        )
        workspaces = service.list_workspaces()
        return {
            "csrf_token": token,
            "database_schema_version": 1,
            "workspaces": workspaces,
            "active_workspace_id": next(
                (item["workspace_id"] for item in workspaces if item["status"] == "ready"),
                workspaces[0]["workspace_id"] if workspaces else None,
            ),
        }

    @app.get("/api/studio/workspaces/{workspace_id}/media")
    def list_workspace_media(
        workspace_id: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=100),
    ) -> dict:
        return service.list_workspace_media(workspace_id, page=page, page_size=page_size)

    @app.get("/api/studio/artifacts/{token}")
    def catalog_artifact(token: str):
        selected = service.catalog.artifact(token)
        if selected is None:
            raise HTTPException(status_code=404, detail={"code": "artifact_not_found"})
        try:
            resolved = selected.path.resolve(strict=True)
            allowed_root = selected.authorization_root.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=404, detail={"code": "artifact_unavailable"}) from exc
        if allowed_root not in resolved.parents or not resolved.is_file():
            raise HTTPException(status_code=404, detail={"code": "artifact_unavailable"})
        return FileResponse(
            resolved,
            media_type=selected.media_type,
            headers={
                "ETag": f'"{token}"',
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    @app.get("/api/studio/workspaces/{workspace_id}/projects")
    def list_projects(
        workspace_id: str,
        status: str = Query(default="active"),
    ) -> dict:
        return {"items": service.list_projects(workspace_id, status)}

    @app.post("/api/studio/maintenance/backup", dependencies=[Depends(protect_write)])
    def backup_database() -> dict:
        timestamp = datetime.now(UTC)
        backup_id = f"backup-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex}"
        destination = database.path.parent / "backups" / f"{backup_id}.sqlite3"
        database.backup(destination)
        return {"backup_id": backup_id, "created_at": timestamp.isoformat().replace("+00:00", "Z")}

    @app.post(
        "/api/studio/workspaces/{workspace_id}/projects",
        status_code=201,
        dependencies=[Depends(protect_write)],
    )
    def create_project(workspace_id: str, body: ProjectCreate) -> dict:
        return service.create_project(workspace_id, **body.model_dump())

    @app.get("/api/studio/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        return service.get_project(project_id)

    @app.patch(
        "/api/studio/projects/{project_id}", dependencies=[Depends(protect_write)]
    )
    def update_project(
        project_id: str,
        body: ProjectPatch,
        if_match: str | None = Header(default=None),
    ) -> dict:
        return service.update_project(
            project_id, _revision(if_match), body.model_dump(exclude_unset=True)
        )

    @app.post(
        "/api/studio/projects/{project_id}/archive", dependencies=[Depends(protect_write)]
    )
    def archive_project(project_id: str, if_match: str | None = Header(default=None)) -> dict:
        return service.archive_project(project_id, _revision(if_match))

    @app.post(
        "/api/studio/projects/{project_id}/restore", dependencies=[Depends(protect_write)]
    )
    def restore_project(project_id: str, if_match: str | None = Header(default=None)) -> dict:
        return service.restore_project(project_id, _revision(if_match))

    @app.get("/api/studio/projects/{project_id}/media")
    def list_media(project_id: str) -> dict:
        return service.list_media(project_id)

    @app.post(
        "/api/studio/projects/{project_id}/media-links",
        dependencies=[Depends(protect_write)],
    )
    def add_media_links(
        project_id: str,
        body: MediaLinksCreate,
        if_match: str | None = Header(default=None),
    ) -> dict:
        return service.add_media_links(
            project_id,
            _revision(if_match),
            [item.model_dump() for item in body.links],
        )

    @app.patch(
        "/api/studio/projects/{project_id}/media-links/{asset_id:path}",
        dependencies=[Depends(protect_write)],
    )
    def update_media_link(
        project_id: str,
        asset_id: str,
        body: MediaLinkPatch,
        if_match: str | None = Header(default=None),
    ) -> dict:
        return service.update_media_link(
            project_id,
            asset_id,
            _revision(if_match),
            body.model_dump(exclude_unset=True),
        )

    @app.delete(
        "/api/studio/projects/{project_id}/media-links/{asset_id:path}",
        dependencies=[Depends(protect_write)],
    )
    def remove_media_link(
        project_id: str,
        asset_id: str,
        if_match: str | None = Header(default=None),
    ) -> dict:
        return service.remove_media_link(project_id, asset_id, _revision(if_match))

    if frontend_dir is not None:
        frontend = Path(frontend_dir).resolve()
        index_file = frontend / "index.html"
        assets_dir = frontend / "assets"
        if not index_file.is_file() or not assets_dir.is_dir():
            database.close()
            raise ValueError("frontend_dir must contain index.html and assets/")
        app.mount("/assets", StaticFiles(directory=assets_dir), name="studio-assets")

        @app.get("/", include_in_schema=False)
        @app.get("/modules/{module_path:path}", include_in_schema=False)
        def studio_frontend(module_path: str = ""):
            return FileResponse(index_file, media_type="text/html")

    return app
