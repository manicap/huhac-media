from __future__ import annotations

import calendar as calendar_module
from datetime import datetime
import hmac
from importlib.metadata import PackageNotFoundError, version
import ipaddress
import json
from pathlib import Path
import re
import secrets
from typing import Iterator
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_desk.config import ConfigurationError, Settings, save_profile_workspace, user_config_path
from media_desk.index import CursorError, LibraryIndex, QuerySpec, capture_date, capture_label
from media_desk.models import Artifact, Asset, WorkspaceSnapshot
from media_desk.workspace_status import WorkspaceValidation, validate_workspace


_PACKAGE_ROOT = Path(__file__).parent
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")
_MAX_FORM_BYTES = 8192
_MAX_WORKSPACE_PATH = 4096
_CSRF_COOKIE = "media_desk_csrf"
_SOURCE_LABELS = {
    "default": "nenastaveno",
    "profile": "profil",
    "cli": "CLI",
    "env": "ENV",
    "explicit_config": "explicitní config",
}


def _app_version() -> str:
    try:
        return version("huhac-media")
    except PackageNotFoundError:
        return "0.1.0"


def _is_loopback(value: str | None) -> bool:
    if not value:
        return False
    candidate = value.strip().strip("[]").casefold()
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _safe_path_input(value: str) -> str:
    if not value or len(value) > _MAX_WORKSPACE_PATH:
        raise ValueError("Cesta musí mít 1 až 4096 znaků.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("Cesta obsahuje nepovolené řídicí znaky.")
    return value


def _asset_payload(asset: Asset) -> dict:
    return {
        "asset_id": asset.asset_id,
        "sha256": asset.sha256,
        "media_type": asset.media_type,
        "format": asset.format,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "availability": asset.availability,
        "source_name": asset.source_name,
        "capture_time": asset.capture_time,
        "capture_source": asset.capture_source,
        "capture_timezone": asset.capture_timezone,
        "capture_filesystem_fallback": asset.capture_filesystem_fallback,
        "capture_label": capture_label(asset),
        "technical": asset.technical,
        "preview_status": asset.preview_status,
        "preview_url": f"/artifacts/{asset.preview.token}" if asset.preview else None,
        "original_online": asset.original_online,
        "original_url": f"/artifacts/{asset.original.token}" if asset.original else None,
        "sessions": [reference.__dict__ for reference in asset.sessions],
        "vision_result_count": len(asset.vision),
        "faces_result_count": len(asset.faces),
        "anonymous_face_clusters": [reference.__dict__ for reference in asset.face_clusters],
    }


def _size_cs(value: int) -> str:
    units = ("B", "kB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1000 or unit == units[-1]:
            digits = 0 if unit == "B" else 1
            return f"{amount:.{digits}f}".replace(".", ",") + f" {unit}"
        amount /= 1000
    return f"{value} B"


def _datetime_cs(value: str | None) -> str:
    if not value:
        return "Čas neznámý"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return f"{parsed.day}. {parsed.month}. {parsed.year} · {parsed:%H:%M}"


def _filtered(snapshot: WorkspaceSnapshot, media_type: str, query: str) -> list[Asset]:
    assets = list(snapshot.assets)
    if media_type in {"image", "video"}:
        assets = [asset for asset in assets if asset.media_type == media_type]
    normalized = query.strip().casefold()
    if normalized:
        assets = [
            asset
            for asset in assets
            if normalized in asset.source_name.casefold()
            or normalized in asset.asset_id.casefold()
        ]
    return assets


def _byte_range(value: str, size: int) -> tuple[int, int]:
    match = _RANGE.fullmatch(value.strip())
    if match is None or "," in value:
        raise HTTPException(status_code=416, detail="Invalid byte range")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise HTTPException(status_code=416, detail="Invalid byte range")
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise HTTPException(status_code=416, detail="Invalid byte range")
        return max(size - length, 0), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start >= size or end < start:
        raise HTTPException(status_code=416, detail="Range outside file")
    return start, min(end, size - 1)


def _chunks(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as stream:
        stream.seek(start)
        while remaining:
            chunk = stream.read(min(1024 * 256, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _serve_original(request: Request, artifact: Artifact, resolved: Path):
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Original is offline") from exc
    range_header = request.headers.get("range")
    common = {"Accept-Ranges": "bytes", "Content-Disposition": "inline"}
    if not range_header:
        return FileResponse(resolved, media_type=artifact.media_type, headers=common)
    start, end = _byte_range(range_header, size)
    headers = {
        **common,
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    return StreamingResponse(
        _chunks(resolved, start, end),
        status_code=206,
        media_type=artifact.media_type,
        headers=headers,
    )


def create_app(
    workspace: Path | None = None,
    keyframe_fingerprint: str | None = None,
    *,
    settings: Settings | None = None,
) -> FastAPI:
    if settings is None:
        settings = Settings(
            workspace=workspace,
            keyframe_fingerprint=keyframe_fingerprint,
            profile_config_path=user_config_path(),
            workspace_source="cli" if workspace is not None else "default",
        )
    workspace = settings.workspace
    keyframe_fingerprint = settings.keyframe_fingerprint
    app = FastAPI(title="Huháč Media Desk", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_PACKAGE_ROOT / "templates"))
    templates.env.filters["size_cs"] = _size_cs
    templates.env.filters["datetime_cs"] = _datetime_cs
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_ROOT / "static")), name="static")
    validation = validate_workspace(workspace, keyframe_fingerprint, settings.originals_mapping)
    snapshot = validation.snapshot
    app.state.snapshot = snapshot
    app.state.workspace_validation = validation
    app.state.startup_error = None if validation.valid else validation.message
    app.state.library_index = LibraryIndex(snapshot) if snapshot is not None else None
    app.state.settings = settings
    app.state.csrf_secret = secrets.token_urlsafe(32)
    templates.env.globals["active_workspace_id"] = snapshot.workspace_id if snapshot else "none"

    def require_snapshot() -> WorkspaceSnapshot:
        current = app.state.snapshot
        if current is None:
            raise HTTPException(status_code=503, detail=app.state.startup_error)
        return current

    def settings_context(
        request: Request,
        *,
        candidate: str | None = None,
        candidate_validation: WorkspaceValidation | None = None,
        error: str | None = None,
        notice: str | None = None,
    ) -> dict:
        current_settings: Settings = app.state.settings
        return {
            "request": request,
            "workspace_validation": app.state.workspace_validation,
            "workspace_path": str(current_settings.workspace or ""),
            "workspace_source": _SOURCE_LABELS.get(
                current_settings.workspace_source, current_settings.workspace_source
            ),
            "workspace_editable": current_settings.workspace_editable,
            "candidate": candidate,
            "candidate_validation": candidate_validation,
            "error": error,
            "notice": notice,
            "config_path": current_settings.profile_config_path or user_config_path(),
            "app_version": _app_version(),
            "csrf_token": request.cookies.get(_CSRF_COOKIE) or app.state.csrf_secret,
            "active_asset_id": None,
        }

    def render_settings(request: Request, **values):
        response = templates.TemplateResponse(
            request=request,
            name="settings.html",
            context=settings_context(request, **values),
        )
        if request.cookies.get(_CSRF_COOKIE) != app.state.csrf_secret:
            response.set_cookie(
                _CSRF_COOKIE,
                app.state.csrf_secret,
                httponly=True,
                samesite="strict",
                secure=False,
                path="/",
            )
        return response

    async def protected_form(request: Request) -> dict[str, str]:
        current_settings: Settings = app.state.settings
        if not _is_loopback(current_settings.host):
            raise HTTPException(status_code=403, detail="Změny nastavení jsou povoleny jen při loopback bindu.")
        raw_host = request.headers.get("host", "")
        host_name = urlsplit(f"//{raw_host}").hostname
        if not _is_loopback(host_name):
            raise HTTPException(status_code=403, detail="Neplatný Host pro změnu nastavení.")
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urlsplit(origin)
            expected = f"{request.url.scheme}://{raw_host}".casefold()
            if f"{parsed_origin.scheme}://{parsed_origin.netloc}".casefold() != expected:
                raise HTTPException(status_code=403, detail="Cizí Origin není povolen.")
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > _MAX_FORM_BYTES):
            raise HTTPException(status_code=413, detail="Formulář je příliš velký.")
        body = await request.body()
        if len(body) > _MAX_FORM_BYTES:
            raise HTTPException(status_code=413, detail="Formulář je příliš velký.")
        try:
            parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=4)
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Neplatný formulář.") from exc
        if set(parsed) != {"csrf_token", "workspace"} or any(len(items) != 1 for items in parsed.values()):
            raise HTTPException(status_code=400, detail="Formulář obsahuje neočekávaná pole.")
        cookie = request.cookies.get(_CSRF_COOKIE, "")
        token = parsed["csrf_token"][0]
        if not cookie or not hmac.compare_digest(cookie, token) or not hmac.compare_digest(token, app.state.csrf_secret):
            raise HTTPException(status_code=403, detail="Neplatný CSRF token.")
        return {key: items[0] for key, items in parsed.items()}

    @app.exception_handler(HTTPException)
    async def friendly_workspace_error(request: Request, exc: HTTPException):
        if exc.status_code == 503 and app.state.snapshot is None and not request.url.path.startswith("/api/"):
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={
                    "message": app.state.startup_error,
                    "workspace_validation": app.state.workspace_validation,
                    "active_asset_id": None,
                },
                status_code=503,
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, recheck: bool = False):
        current_settings: Settings = app.state.settings
        if recheck and current_settings.workspace is not None:
            checked = validate_workspace(current_settings.workspace, keyframe_fingerprint)
            notice = "Cesta je dostupná. Pro načtení knihovny restartujte Media Desk." if checked.valid and app.state.snapshot is None else None
            return render_settings(
                request,
                candidate=str(current_settings.workspace),
                candidate_validation=checked,
                notice=notice,
            )
        return render_settings(request)

    @app.post("/settings/validate", response_class=HTMLResponse)
    async def validate_settings(request: Request):
        fields = await protected_form(request)
        if not app.state.settings.workspace_editable:
            return render_settings(request, error="Aktivní cestu určuje vyšší priorita; změňte ji při spuštění." )
        try:
            candidate = _safe_path_input(fields["workspace"])
        except ValueError as exc:
            return render_settings(request, candidate=fields["workspace"], error=str(exc))
        checked = validate_workspace(Path(candidate).expanduser(), keyframe_fingerprint)
        return render_settings(request, candidate=candidate, candidate_validation=checked)

    @app.post("/settings/save", response_class=HTMLResponse)
    async def save_settings(request: Request):
        fields = await protected_form(request)
        current_settings: Settings = app.state.settings
        if not current_settings.workspace_editable:
            return render_settings(request, error="Aktivní cestu určuje vyšší priorita; profil nelze upravit." )
        try:
            candidate = _safe_path_input(fields["workspace"])
        except ValueError as exc:
            return render_settings(request, candidate=fields["workspace"], error=str(exc))
        checked = validate_workspace(Path(candidate).expanduser(), keyframe_fingerprint)
        if not checked.valid or checked.resolved_path is None:
            return render_settings(request, candidate=candidate, candidate_validation=checked)
        try:
            save_profile_workspace(
                current_settings.profile_config_path or user_config_path(), checked.resolved_path
            )
        except ConfigurationError as exc:
            return render_settings(
                request,
                candidate=candidate,
                candidate_validation=checked,
                error=f"Konfiguraci se nepodařilo uložit: {exc}",
            )
        return render_settings(
            request,
            candidate=candidate,
            candidate_validation=checked,
            notice="Cesta byla bezpečně uložena. Pro její aktivaci restartujte Media Desk.",
        )

    @app.get("/", response_class=HTMLResponse)
    def overview(
        request: Request,
        active_asset_id: str | None = None,
    ):
        if app.state.snapshot is None:
            return templates.TemplateResponse(
                request=request,
                name="setup.html",
                context={
                    **settings_context(request),
                    "fresh_setup": app.state.workspace_validation.state == "unset",
                },
                status_code=200 if app.state.workspace_validation.state == "unset" else 503,
            )
        current: WorkspaceSnapshot = app.state.snapshot
        index = app.state.library_index
        calendar = index.calendar(QuerySpec())
        recent_months = []
        for year, year_data in sorted(calendar["years"].items(), reverse=True):
            for month, month_data in sorted(year_data["months"].items(), reverse=True):
                recent_months.append({"year": year, "month": month, **month_data})
        return templates.TemplateResponse(
            request=request,
            name="overview.html",
            context={
                "workspace": current,
                "image_count": sum(asset.media_type == "image" for asset in current.assets),
                "video_count": sum(asset.media_type == "video" for asset in current.assets),
                "recent_months": recent_months[:6],
                "recent_sessions": sorted(current.sessions, key=lambda item: item.start or "", reverse=True)[:5],
                "active_asset_id": active_asset_id,
            },
        )

    @app.get("/assets/{sha256}", response_class=HTMLResponse)
    def detail(request: Request, sha256: str, return_to: str | None = None, active_asset_id: str | None = None):
        current = require_snapshot()
        asset = next((item for item in current.assets if item.sha256 == sha256), None)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        allowed_returns = ("/library", "/calendar", "/relations")
        safe_return = return_to if return_to and return_to.startswith(allowed_returns) and not return_to.startswith("//") else "/library"
        query = parse_qs(urlsplit(safe_return).query)
        spec = QuerySpec(
            query.get("media_type", ["all"])[0],
            query.get("q", [""])[0],
            query.get("sort", ["captured_desc"])[0],
            query.get("date_from", [None])[0],
            query.get("date_to", [None])[0],
        )
        ordered = app.state.library_index.query(spec)
        position = next((index for index, item in enumerate(ordered) if item.asset_id == asset.asset_id), None)
        previous_asset = ordered[position - 1] if position is not None and position > 0 else None
        next_asset = ordered[position + 1] if position is not None and position + 1 < len(ordered) else None
        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={
                "workspace": current,
                "asset": asset,
                "active_asset_id": active_asset_id or asset.asset_id,
                "return_to": safe_return,
                "previous_asset": previous_asset,
                "next_asset": next_asset,
                "technical_json": json.dumps(asset.technical, ensure_ascii=False, indent=2, sort_keys=True),
            },
        )

    @app.get("/api/assets")
    def api_assets(
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(24, ge=1, le=100),
        sort: str = Query("captured_desc", pattern="^(captured_desc|captured_asc)$"),
        limit: int | None = Query(None, ge=10, le=100),
        cursor: str | None = None,
        start: int | None = Query(None, ge=0),
        snapshot_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        current = require_snapshot()
        if limit is not None or cursor is not None or start is not None or snapshot_id is not None:
            spec = QuerySpec(media_type, q, sort, date_from, date_to)
            try:
                batch = app.state.library_index.batch(spec, limit or 50, cursor, start, snapshot_id)
            except CursorError as exc:
                return JSONResponse(
                    {"error": "snapshot_changed", "message": str(exc), "snapshot_id": app.state.library_index.snapshot_id},
                    status_code=409,
                )
            return {**batch, "items": [_asset_payload(asset) for asset in batch["items"]]}
        assets = _filtered(current, media_type, q)
        start = (page - 1) * page_size
        return {
            "workspace_id": current.workspace_id,
            "page": page,
            "page_size": page_size,
            "total": len(assets),
            "assets": [_asset_payload(asset) for asset in assets[start : start + page_size]],
        }

    @app.get("/library", response_class=HTMLResponse)
    def library(
        request: Request,
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        sort: str = Query("captured_desc", pattern="^(captured_desc|captured_asc)$"),
        active_asset_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        current = require_snapshot()
        return templates.TemplateResponse(
            request=request,
            name="library.html",
            context={
                "workspace": current,
                "media_type": media_type,
                "query": q,
                "sort": sort,
                "active_asset_id": active_asset_id,
                "date_from": date_from,
                "date_to": date_to,
                "snapshot_id": app.state.library_index.snapshot_id,
            },
        )

    @app.get("/calendar", response_class=HTMLResponse)
    def calendar_view(
        request: Request,
        year: int | None = None,
        month: int | None = Query(None, ge=1, le=12),
        day: int | None = Query(None, ge=1, le=31),
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        active_asset_id: str | None = None,
    ):
        current = require_snapshot()
        active = next((asset for asset in current.assets if asset.asset_id == active_asset_id), None)
        active_date = capture_date(active) if active else None
        if active_date and year is None:
            year, month, day = active_date.year, active_date.month, active_date.day
        spec = QuerySpec(media_type, q)
        calendar = app.state.library_index.calendar(spec)
        if year is None and calendar["years"]:
            year = max(calendar["years"])
        day_assets = ()
        if year and month and day:
            date_value = f"{year:04d}-{month:02d}-{day:02d}"
            day_assets = app.state.library_index.query(
                QuerySpec(media_type, q, "captured_desc", date_value, date_value)
            )
        month_weeks = calendar_module.Calendar(firstweekday=0).monthdayscalendar(year, month) if year and month else ()
        return templates.TemplateResponse(
            request=request,
            name="calendar.html",
            context={
                "workspace": current,
                "calendar": calendar,
                "year": year,
                "month": month,
                "day": day,
                "day_assets": day_assets,
                "month_weeks": month_weeks,
                "active_asset_id": active_asset_id,
                "active_date_unknown": active is not None and active_date is None,
                "media_type": media_type,
                "query": q,
                "month_names": (
                    "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
                    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
                ),
            },
        )

    @app.get("/relations", response_class=HTMLResponse)
    def relations_view(
        request: Request,
        order: str = Query("desc", pattern="^(asc|desc)$"),
        year: int | None = None,
        active_asset_id: str | None = None,
    ):
        current = require_snapshot()
        sessions = list(current.sessions)
        sessions.sort(key=lambda item: item.start or "", reverse=order == "desc")
        grouped: dict[str, list[dict]] = {}
        for session in sessions:
            group_year = (session.operational_day or session.start or "Neznámý rok")[:4]
            if year is not None and group_year != str(year):
                continue
            first = next((asset for asset in current.assets if asset.asset_id in session.asset_ids and asset.preview), None)
            grouped.setdefault(group_year, []).append({"session": session, "cover": first})
        unassigned = next(
            (item for item in current.session_unassigned if item.asset_id == active_asset_id), None
        )
        active_in_session = any(active_asset_id in session.asset_ids for session in current.sessions) if active_asset_id else False
        return templates.TemplateResponse(
            request=request,
            name="relations.html",
            context={
                "workspace": current,
                "groups": grouped,
                "order": order,
                "year": year,
                "active_asset_id": active_asset_id,
                "active_in_session": active_in_session,
                "unassigned": unassigned,
            },
        )

    @app.get("/api/index")
    def api_index(
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        sort: str = Query("captured_desc", pattern="^(captured_desc|captured_asc)$"),
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        require_snapshot()
        spec = QuerySpec(media_type, q, sort, date_from, date_to)
        index = app.state.library_index
        return {
            "snapshot_id": index.snapshot_id,
            "total_count": len(index.query(spec)),
            "segments": index.time_segments(spec),
        }

    @app.get("/api/locate")
    def api_locate(
        asset_id: str | None = None,
        year: int | None = None,
        month: int | None = Query(None, ge=1, le=12),
        day: int | None = Query(None, ge=1, le=31),
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        sort: str = Query("captured_desc", pattern="^(captured_desc|captured_asc)$"),
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        require_snapshot()
        if asset_id is None and year is None:
            raise HTTPException(status_code=422, detail="asset_id or year is required")
        spec = QuerySpec(media_type, q, sort, date_from, date_to)
        found = app.state.library_index.locate(
            spec, asset_id=asset_id, year=year, month=month, day=day
        )
        if found is None:
            raise HTTPException(status_code=404, detail="Položka není v aktuálním výsledku")
        return {"snapshot_id": app.state.library_index.snapshot_id, **found}

    @app.get("/api/calendar")
    def api_calendar(
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        sort: str = Query("captured_desc", pattern="^(captured_desc|captured_asc)$"),
    ):
        require_snapshot()
        return app.state.library_index.calendar(QuerySpec(media_type, q, sort))

    @app.get("/api/assets/{sha256}")
    def api_detail(sha256: str):
        current = require_snapshot()
        asset = next((item for item in current.assets if item.sha256 == sha256), None)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        payload = _asset_payload(asset)
        payload["vision"] = [result.__dict__ for result in asset.vision]
        payload["faces"] = [result.__dict__ for result in asset.faces]
        return JSONResponse(payload)

    @app.get("/artifacts/{token}")
    def artifact(request: Request, token: str):
        current = require_snapshot()
        selected = current.artifacts.get(token)
        if selected is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        try:
            resolved = selected.path.resolve(strict=True)
            allowed_root = selected.authorization_root.resolve(strict=True)
        except OSError as exc:
            raise HTTPException(status_code=404, detail="Artifact is unavailable") from exc
        if allowed_root not in resolved.parents or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Artifact is unavailable")
        if selected.kind == "original":
            return _serve_original(request, selected, resolved)
        etag = f'"{token}"'
        headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return FileResponse(resolved, media_type=selected.media_type, headers=headers)

    @app.get("/health")
    def health():
        if app.state.snapshot is None:
            return JSONResponse(
                {
                    "status": "running",
                    "ready": False,
                    "workspace_status": app.state.workspace_validation.state,
                    "message": app.state.startup_error,
                },
                status_code=503,
            )
        return {"status": "ok", "workspace_id": app.state.snapshot.workspace_id}

    return app
