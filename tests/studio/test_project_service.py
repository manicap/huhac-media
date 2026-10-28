from __future__ import annotations

import re

import pytest

from huhac_studio.catalog import InMemoryWorkspaceCatalog
from huhac_studio.database import ProjectDatabase
from huhac_studio.errors import ArchivedProjectError, RevisionConflict, ValidationError
from huhac_studio.service import ProjectService

from .conftest import asset_id


@pytest.fixture
def service(tmp_path, catalog):
    return ProjectService(ProjectDatabase(tmp_path / "projects.sqlite3"), catalog)


def test_create_list_update_allows_duplicate_titles_and_normalizes_tags(service):
    first = service.create_project(
        "workspace-test", title="  Koncert  ", description="Popis", tags=["Live", "2026"]
    )
    second = service.create_project("workspace-test", title="Koncert")

    assert re.fullmatch(r"project-[0-9a-f]{32}", first["project_id"])
    assert first["title"] == second["title"] == "Koncert"
    assert first["revision"] == 1
    assert len(service.list_projects("workspace-test")) == 2

    updated = service.update_project(
        first["project_id"], 1, {"title": "Turné", "tags": ["Tour", "Live"]}
    )
    assert updated["revision"] == 2
    assert updated["tags"] == ["Tour", "Live"]


def test_tag_casefold_collision_is_rejected_without_write(service):
    with pytest.raises(ValidationError):
        service.create_project("workspace-test", title="Test", tags=["Live", "LIVE"])
    assert service.list_projects("workspace-test") == []


def test_revision_conflict_is_atomic(service):
    project = service.create_project("workspace-test", title="Original")
    changed = service.update_project(project["project_id"], 1, {"title": "Changed"})

    with pytest.raises(RevisionConflict) as conflict:
        service.update_project(project["project_id"], 1, {"title": "Stale"})
    assert conflict.value.details["current_revision"] == 2
    assert service.get_project(project["project_id"])["title"] == "Changed"
    assert changed["revision"] == 2


def test_archive_restore_preserves_links_and_blocks_mutations(service):
    project = service.create_project("workspace-test", title="Archive")
    linked = service.add_media_links(
        project["project_id"], 1, [{"asset_id": asset_id(1), "role": "deliverable"}]
    )
    archived = service.archive_project(project["project_id"], linked["revision"])

    assert archived["status"] == "archived"
    assert archived["archived_at"] is not None
    with pytest.raises(ArchivedProjectError):
        service.update_project(project["project_id"], archived["revision"], {"title": "No"})
    assert len(service.list_media(project["project_id"])["items"]) == 1

    restored = service.restore_project(project["project_id"], archived["revision"])
    assert restored["status"] == "active"
    assert restored["archived_at"] is None
    assert restored["media_count"] == 1


def test_media_batch_validates_catalog_and_increments_once(service):
    project = service.create_project("workspace-test", title="Links")
    result = service.add_media_links(
        project["project_id"],
        1,
        [
            {"asset_id": asset_id(1), "role": "source", "position": 1},
            {"asset_id": asset_id(2), "role": "reference", "position": 2},
        ],
    )
    assert result["revision"] == 2
    assert result["media_count"] == 2
    media = service.list_media(project["project_id"])
    assert [item["resolution"] for item in media["items"]] == ["resolved", "original_offline"]

    with pytest.raises(ValidationError):
        service.add_media_links(
            project["project_id"], 2, [{"asset_id": asset_id(99), "role": "source"}]
        )
    assert service.get_project(project["project_id"])["revision"] == 2


def test_link_update_and_remove_are_revision_guarded(service):
    project = service.create_project("workspace-test", title="Links")
    linked = service.add_media_links(
        project["project_id"], 1, [{"asset_id": asset_id(1)}]
    )
    updated = service.update_media_link(
        project["project_id"], asset_id(1), linked["revision"], {"role": "deliverable"}
    )
    assert updated["revision"] == 3
    assert service.list_media(project["project_id"])["items"][0]["role"] == "deliverable"

    with pytest.raises(RevisionConflict):
        service.remove_media_link(project["project_id"], asset_id(1), 2)
    removed = service.remove_media_link(project["project_id"], asset_id(1), 3)
    assert removed["revision"] == 4
    assert removed["media_count"] == 0


def test_link_lifecycle_never_changes_catalog_media_file(tmp_path, catalog):
    original = tmp_path / "workspace" / "original.jpg"
    original.parent.mkdir()
    original.write_bytes(b"immutable catalog media")
    service = ProjectService(ProjectDatabase(tmp_path / "projects.sqlite3"), catalog)
    project = service.create_project("workspace-test", title="Safety")

    linked = service.add_media_links(
        project["project_id"], 1, [{"asset_id": asset_id(1), "role": "reference"}]
    )
    service.remove_media_link(project["project_id"], asset_id(1), linked["revision"])

    assert original.read_bytes() == b"immutable catalog media"


def test_existing_link_survives_catalog_and_asset_unavailability(tmp_path, catalog):
    database = ProjectDatabase(tmp_path / "projects.sqlite3")
    service = ProjectService(database, catalog)
    project = service.create_project("workspace-test", title="Offline")
    service.add_media_links(project["project_id"], 1, [{"asset_id": asset_id(1)}])

    unavailable = ProjectService(
        database,
        InMemoryWorkspaceCatalog(
            {"workspace-test": {}}, unavailable_workspaces={"workspace-test"}
        ),
    )
    item = unavailable.list_media(project["project_id"])["items"][0]
    assert item["resolution"] == "catalog_unavailable"
    assert unavailable.get_project(project["project_id"])["media_count"] == 1
    assert unavailable.list_projects("workspace-test")[0]["project_id"] == project["project_id"]


def test_project_cannot_link_asset_from_another_workspace(service):
    project = service.create_project("workspace-second", title="Other")
    with pytest.raises(ValidationError):
        service.add_media_links(project["project_id"], 1, [{"asset_id": asset_id(1)}])
