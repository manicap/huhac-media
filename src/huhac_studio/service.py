from __future__ import annotations

import re
import sqlite3
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Iterable, Mapping, Sequence

from huhac_studio.catalog import WorkspaceCatalog
from huhac_studio.database import ProjectDatabase
from huhac_studio.errors import (
    ArchivedProjectError,
    ConflictError,
    NotFoundError,
    RevisionConflict,
    ValidationError,
)

_PROJECT_ID = re.compile(r"project-[0-9a-f]{32}\Z")
_ASSET_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROLES = frozenset({"source", "reference", "deliverable"})
_STATUSES = frozenset({"active", "archived"})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _plain_text(value: object, field: str, *, minimum: int = 0, maximum: int) -> str | None:
    if value is None:
        if minimum:
            raise ValidationError(f"{field} is required", field=field)
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string", field=field)
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) < minimum or len(normalized) > maximum:
        raise ValidationError(
            f"{field} length is outside the allowed range",
            field=field,
            minimum=minimum,
            maximum=maximum,
        )
    if any(unicodedata.category(char) == "Cc" and char not in "\n\r\t" for char in normalized):
        raise ValidationError(f"{field} contains control characters", field=field)
    return normalized or None


def _workspace_id(value: object) -> str:
    result = _plain_text(value, "workspace_id", minimum=1, maximum=128)
    assert result is not None
    if any(char in result for char in "/\\"):
        raise ValidationError("workspace_id is invalid", field="workspace_id")
    return result


def _expected_revision(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValidationError("Expected revision must be a positive integer", field="revision")
    return value


def _position(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationError("position must be a non-negative integer or null", field="position")
    return value


def _role(value: object) -> str:
    if not isinstance(value, str) or value not in _ROLES:
        raise ValidationError("role must be source, reference, or deliverable", field="role")
    return value


def _tags(values: object) -> list[tuple[str, str]]:
    if not isinstance(values, list):
        raise ValidationError("tags must be an array", field="tags")
    if len(values) > 20:
        raise ValidationError("A project may have at most 20 tags", field="tags")
    result: list[tuple[str, str]] = []
    keys: set[str] = set()
    for value in values:
        display = _plain_text(value, "tag", minimum=1, maximum=80)
        assert display is not None
        key = unicodedata.normalize("NFKC", display).casefold()
        if key in keys:
            raise ValidationError("tags must be unique ignoring case", field="tags")
        keys.add(key)
        result.append((key, display))
    return result


class ProjectService:
    def __init__(self, database: ProjectDatabase, catalog: WorkspaceCatalog) -> None:
        self.database = database
        self.catalog = catalog

    def _require_workspace(self, workspace_id: str) -> None:
        state = self.catalog.workspace_state(workspace_id)
        if state != "available":
            raise NotFoundError(
                "Workspace is not available in the Studio catalog registry",
                workspace_id=workspace_id,
                workspace_state=state,
            )

    def list_workspaces(self) -> list[dict]:
        with self.database.read() as connection:
            stored = {
                row[0]
                for row in connection.execute("SELECT DISTINCT workspace_id FROM projects")
            }
        workspace_ids = sorted(stored | set(self.catalog.workspace_ids()))
        return [
            {
                "workspace_id": workspace_id,
                "status": (
                    "ready"
                    if self.catalog.workspace_state(workspace_id) == "available"
                    else "offline"
                ),
            }
            for workspace_id in workspace_ids
        ]

    def list_workspace_media(
        self, workspace_id: object, *, page: int = 1, page_size: int = 100
    ) -> dict:
        workspace = _workspace_id(workspace_id)
        self._require_workspace(workspace)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValidationError("Invalid media page", field="page")
        assets = list(self.catalog.assets(workspace))
        assets.sort(key=lambda item: ((item.capture_time or ""), item.asset_id), reverse=True)
        start = (page - 1) * page_size
        items = assets[start : start + page_size]
        return {
            "workspace_id": workspace,
            "page": page,
            "page_size": page_size,
            "total": len(assets),
            "items": [
                {
                    "asset_id": asset.asset_id,
                    "media_type": asset.media_type,
                    "availability": asset.availability,
                    "original_access_state": asset.original_access_state,
                    "display_name": asset.display_name or asset.source_name or asset.asset_id,
                    "capture_time": asset.capture_time,
                    "width": asset.width,
                    "height": asset.height,
                    "rotation": asset.rotation,
                    "duration_seconds": asset.duration_seconds,
                    "mime_type": asset.mime_type,
                    "size_bytes": asset.size_bytes,
                    "original_available": asset.original_token is not None,
                    "original_url": (
                        f"/api/studio/originals/{asset.original_token}"
                        if asset.media_type == "video" and asset.original_token
                        else None
                    ),
                    "preview_url": (
                        f"/api/studio/artifacts/{asset.preview_token}"
                        if asset.preview_token
                        else None
                    ),
                }
                for asset in items
            ],
        }

    @staticmethod
    def _project_row(connection: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        if not _PROJECT_ID.fullmatch(project_id):
            raise NotFoundError("Project not found", project_id=project_id)
        row = connection.execute(
            "SELECT * FROM projects WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Project not found", project_id=project_id)
        return row

    @staticmethod
    def _check_revision(row: sqlite3.Row, expected_revision: object) -> int:
        expected = _expected_revision(expected_revision)
        current = int(row["revision"])
        if expected != current:
            raise RevisionConflict(expected, current)
        return current

    @staticmethod
    def _check_active(row: sqlite3.Row) -> None:
        if row["status"] != "active":
            raise ArchivedProjectError(
                "Archived projects are read-only; restore the project first",
                project_id=row["project_id"],
            )

    @staticmethod
    def _serialize_project(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        tags = [
            item["display_name"]
            for item in connection.execute(
                "SELECT display_name FROM project_tags WHERE project_id=? ORDER BY position",
                (row["project_id"],),
            )
        ]
        media_count = connection.execute(
            "SELECT COUNT(*) FROM project_media_links WHERE project_id=?", (row["project_id"],)
        ).fetchone()[0]
        return {
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "title": row["title"],
            "description": row["description"],
            "notes": row["notes"],
            "tags": tags,
            "status": row["status"],
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "archived_at": row["archived_at"],
            "media_count": media_count,
        }

    def create_project(
        self,
        workspace_id: object,
        *,
        title: object,
        description: object = None,
        notes: object = None,
        tags: object = None,
    ) -> dict:
        workspace = _workspace_id(workspace_id)
        self._require_workspace(workspace)
        clean_title = _plain_text(title, "title", minimum=1, maximum=240)
        clean_description = _plain_text(description, "description", maximum=2_000)
        clean_notes = _plain_text(notes, "notes", maximum=20_000)
        clean_tags = _tags([] if tags is None else tags)
        project_id = f"project-{uuid.uuid4().hex}"
        timestamp = _utc_now()
        with self.database.write() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    project_id, workspace_id, title, description, notes, status,
                    revision, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, 'active', 1, ?, ?, NULL)
                """,
                (project_id, workspace, clean_title, clean_description, clean_notes, timestamp, timestamp),
            )
            self._replace_tags(connection, project_id, clean_tags)
            row = self._project_row(connection, project_id)
            return self._serialize_project(connection, row)

    def list_projects(self, workspace_id: object, status: str = "active") -> list[dict]:
        workspace = _workspace_id(workspace_id)
        if status not in _STATUSES | {"all"}:
            raise ValidationError("status must be active, archived, or all", field="status")
        sql = "SELECT * FROM projects WHERE workspace_id=?"
        parameters: list[object] = [workspace]
        if status != "all":
            sql += " AND status=?"
            parameters.append(status)
        sql += " ORDER BY updated_at DESC, project_id"
        with self.database.read() as connection:
            return [
                self._serialize_project(connection, row)
                for row in connection.execute(sql, parameters)
            ]

    def get_project(self, project_id: str) -> dict:
        with self.database.read() as connection:
            return self._serialize_project(connection, self._project_row(connection, project_id))

    @staticmethod
    def _replace_tags(
        connection: sqlite3.Connection, project_id: str, tags: Sequence[tuple[str, str]]
    ) -> None:
        connection.execute("DELETE FROM project_tags WHERE project_id=?", (project_id,))
        connection.executemany(
            "INSERT INTO project_tags(project_id, normalized_key, display_name, position) VALUES (?, ?, ?, ?)",
            ((project_id, key, display, index) for index, (key, display) in enumerate(tags)),
        )

    def update_project(
        self, project_id: str, expected_revision: object, changes: Mapping[str, object]
    ) -> dict:
        allowed = {"title", "description", "notes", "tags"}
        unknown = set(changes) - allowed
        if unknown or not changes:
            raise ValidationError("Patch contains no supported fields", fields=sorted(unknown))
        prepared: dict[str, object] = {}
        if "title" in changes:
            prepared["title"] = _plain_text(changes["title"], "title", minimum=1, maximum=240)
        if "description" in changes:
            prepared["description"] = _plain_text(changes["description"], "description", maximum=2_000)
        if "notes" in changes:
            prepared["notes"] = _plain_text(changes["notes"], "notes", maximum=20_000)
        clean_tags = _tags(changes["tags"]) if "tags" in changes else None
        with self.database.write() as connection:
            row = self._project_row(connection, project_id)
            revision = self._check_revision(row, expected_revision)
            self._check_active(row)
            timestamp = _utc_now()
            assignments = [f"{field}=?" for field in prepared]
            values = list(prepared.values())
            assignments.extend(["revision=?", "updated_at=?"])
            values.extend([revision + 1, timestamp, project_id])
            connection.execute(
                f"UPDATE projects SET {', '.join(assignments)} WHERE project_id=?", values
            )
            if clean_tags is not None:
                self._replace_tags(connection, project_id, clean_tags)
            return self._serialize_project(connection, self._project_row(connection, project_id))

    def _transition(self, project_id: str, expected_revision: object, target: str) -> dict:
        with self.database.write() as connection:
            row = self._project_row(connection, project_id)
            revision = self._check_revision(row, expected_revision)
            if row["status"] == target:
                raise ConflictError(f"Project is already {target}", project_id=project_id)
            timestamp = _utc_now()
            archived_at = timestamp if target == "archived" else None
            connection.execute(
                "UPDATE projects SET status=?, revision=?, updated_at=?, archived_at=? WHERE project_id=?",
                (target, revision + 1, timestamp, archived_at, project_id),
            )
            return self._serialize_project(connection, self._project_row(connection, project_id))

    def archive_project(self, project_id: str, expected_revision: object) -> dict:
        return self._transition(project_id, expected_revision, "archived")

    def restore_project(self, project_id: str, expected_revision: object) -> dict:
        return self._transition(project_id, expected_revision, "active")

    def add_media_links(
        self, project_id: str, expected_revision: object, links: object
    ) -> dict:
        if not isinstance(links, list) or not links or len(links) > 500:
            raise ValidationError("links must contain between 1 and 500 items", field="links")
        clean: list[dict] = []
        seen: set[str] = set()
        with self.database.read() as connection:
            workspace_id = self._project_row(connection, project_id)["workspace_id"]
        self._require_workspace(workspace_id)
        for item in links:
            if not isinstance(item, dict) or set(item) - {"asset_id", "role", "note", "position"}:
                raise ValidationError("Invalid media link object", field="links")
            asset_id = item.get("asset_id")
            if not isinstance(asset_id, str) or not _ASSET_ID.fullmatch(asset_id):
                raise ValidationError("Invalid asset_id", field="asset_id")
            if asset_id in seen:
                raise ValidationError("Duplicate asset_id in batch", asset_id=asset_id)
            asset = self.catalog.asset(workspace_id, asset_id)
            if asset is None or asset.media_type not in {"image", "video"}:
                raise ValidationError(
                    "Asset is not present in this workspace catalog", asset_id=asset_id
                )
            seen.add(asset_id)
            clean.append(
                {
                    "asset_id": asset_id,
                    "role": _role(item.get("role", "reference")),
                    "note": _plain_text(item.get("note"), "note", maximum=2_000),
                    "position": _position(item.get("position")),
                }
            )
        with self.database.write() as connection:
            row = self._project_row(connection, project_id)
            revision = self._check_revision(row, expected_revision)
            self._check_active(row)
            existing = {
                item[0]
                for item in connection.execute(
                    f"SELECT asset_id FROM project_media_links WHERE project_id=? AND asset_id IN ({','.join('?' for _ in clean)})",
                    (project_id, *(item["asset_id"] for item in clean)),
                )
            }
            if existing:
                raise ConflictError("Media link already exists", asset_ids=sorted(existing))
            timestamp = _utc_now()
            connection.executemany(
                """
                INSERT INTO project_media_links(
                    project_id, asset_id, role, note, position, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        project_id,
                        item["asset_id"],
                        item["role"],
                        item["note"],
                        item["position"],
                        timestamp,
                        timestamp,
                    )
                    for item in clean
                ),
            )
            connection.execute(
                "UPDATE projects SET revision=?, updated_at=? WHERE project_id=?",
                (revision + 1, timestamp, project_id),
            )
            return self._serialize_project(connection, self._project_row(connection, project_id))

    def update_media_link(
        self,
        project_id: str,
        asset_id: str,
        expected_revision: object,
        changes: Mapping[str, object],
    ) -> dict:
        if not _ASSET_ID.fullmatch(asset_id):
            raise NotFoundError("Media link not found", asset_id=asset_id)
        allowed = {"role", "note", "position"}
        if not changes or set(changes) - allowed:
            raise ValidationError("Patch contains no supported media-link fields")
        prepared: dict[str, object] = {}
        if "role" in changes:
            prepared["role"] = _role(changes["role"])
        if "note" in changes:
            prepared["note"] = _plain_text(changes["note"], "note", maximum=2_000)
        if "position" in changes:
            prepared["position"] = _position(changes["position"])
        with self.database.write() as connection:
            project = self._project_row(connection, project_id)
            revision = self._check_revision(project, expected_revision)
            self._check_active(project)
            link = connection.execute(
                "SELECT 1 FROM project_media_links WHERE project_id=? AND asset_id=?",
                (project_id, asset_id),
            ).fetchone()
            if link is None:
                raise NotFoundError("Media link not found", asset_id=asset_id)
            timestamp = _utc_now()
            assignments = [f"{field}=?" for field in prepared] + ["updated_at=?"]
            values = [*prepared.values(), timestamp, project_id, asset_id]
            connection.execute(
                f"UPDATE project_media_links SET {', '.join(assignments)} WHERE project_id=? AND asset_id=?",
                values,
            )
            connection.execute(
                "UPDATE projects SET revision=?, updated_at=? WHERE project_id=?",
                (revision + 1, timestamp, project_id),
            )
            return self._serialize_project(connection, self._project_row(connection, project_id))

    def remove_media_link(
        self, project_id: str, asset_id: str, expected_revision: object
    ) -> dict:
        if not _ASSET_ID.fullmatch(asset_id):
            raise NotFoundError("Media link not found", asset_id=asset_id)
        with self.database.write() as connection:
            project = self._project_row(connection, project_id)
            revision = self._check_revision(project, expected_revision)
            self._check_active(project)
            deleted = connection.execute(
                "DELETE FROM project_media_links WHERE project_id=? AND asset_id=?",
                (project_id, asset_id),
            ).rowcount
            if not deleted:
                raise NotFoundError("Media link not found", asset_id=asset_id)
            timestamp = _utc_now()
            connection.execute(
                "UPDATE projects SET revision=?, updated_at=? WHERE project_id=?",
                (revision + 1, timestamp, project_id),
            )
            return self._serialize_project(connection, self._project_row(connection, project_id))

    def list_media(self, project_id: str) -> dict:
        with self.database.read() as connection:
            project = self._project_row(connection, project_id)
            links = connection.execute(
                """
                SELECT * FROM project_media_links WHERE project_id=?
                ORDER BY position IS NULL, position, created_at, asset_id
                """,
                (project_id,),
            ).fetchall()
        workspace_id = project["workspace_id"]
        workspace_state = self.catalog.workspace_state(workspace_id)
        result = []
        for link in links:
            asset = self.catalog.asset(workspace_id, link["asset_id"])
            if workspace_state != "available":
                resolution, reason = "catalog_unavailable", "workspace_catalog_unavailable"
            elif asset is None:
                resolution, reason = "unresolved", "asset_missing_from_catalog"
            elif asset.availability != "available":
                resolution, reason = "unresolved", "asset_unavailable"
            elif asset.original_access_state == "offline":
                resolution, reason = "original_offline", "original_offline"
            else:
                resolution, reason = "resolved", None
            result.append(
                {
                    "asset_id": link["asset_id"],
                    "role": link["role"],
                    "note": link["note"],
                    "position": link["position"],
                    "created_at": link["created_at"],
                    "updated_at": link["updated_at"],
                    "resolution": resolution,
                    "resolution_reason": reason,
                    "media_type": asset.media_type if asset else None,
                }
            )
        return {
            "project_id": project_id,
            "workspace_id": workspace_id,
            "revision": project["revision"],
            "items": result,
        }
