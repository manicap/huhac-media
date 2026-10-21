from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from media_desk.contract import ContractError, load_workspace
from media_desk.index import CursorError, LibraryIndex, QuerySpec, capture_label
from media_desk.models import Artifact, Asset, WorkspaceSnapshot


_PACKAGE_ROOT = Path(__file__).parent
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


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


def create_app(workspace: Path, keyframe_fingerprint: str | None = None) -> FastAPI:
    app = FastAPI(title="Huháč Media Desk", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_PACKAGE_ROOT / "templates"))
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_ROOT / "static")), name="static")
    try:
        snapshot = load_workspace(workspace, keyframe_fingerprint)
        startup_error: str | None = None
    except ContractError as exc:
        snapshot = None
        startup_error = str(exc)
    app.state.snapshot = snapshot
    app.state.startup_error = startup_error
    app.state.library_index = LibraryIndex(snapshot) if snapshot is not None else None

    def require_snapshot() -> WorkspaceSnapshot:
        current = app.state.snapshot
        if current is None:
            raise HTTPException(status_code=503, detail=app.state.startup_error)
        return current

    @app.get("/", response_class=HTMLResponse)
    def gallery(
        request: Request,
        media_type: str = Query("all", pattern="^(all|image|video)$"),
        q: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(24, ge=1, le=100),
    ):
        if app.state.snapshot is None:
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"message": app.state.startup_error},
                status_code=503,
            )
        current: WorkspaceSnapshot = app.state.snapshot
        assets = _filtered(current, media_type, q)
        total = len(assets)
        pages = max(1, (total + page_size - 1) // page_size)
        if page > pages:
            page = pages
        start = (page - 1) * page_size
        return templates.TemplateResponse(
            request=request,
            name="gallery.html",
            context={
                "workspace": current,
                "assets": assets[start : start + page_size],
                "media_type": media_type,
                "query": q,
                "page": page,
                "pages": pages,
                "page_size": page_size,
                "total": total,
            },
        )

    @app.get("/assets/{sha256}", response_class=HTMLResponse)
    def detail(request: Request, sha256: str):
        current = require_snapshot()
        asset = next((item for item in current.assets if item.sha256 == sha256), None)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return templates.TemplateResponse(
            request=request,
            name="detail.html",
            context={
                "workspace": current,
                "asset": asset,
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
        return FileResponse(resolved, media_type=selected.media_type)

    @app.get("/health")
    def health():
        if app.state.snapshot is None:
            return JSONResponse({"status": "error", "message": app.state.startup_error}, status_code=503)
        return {"status": "ok", "workspace_id": app.state.snapshot.workspace_id}

    return app
