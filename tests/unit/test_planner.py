from pathlib import Path, PurePosixPath

from huhac_media.domain.enums import MediaType, PlanKind
from huhac_media.domain.models import ExistingSource, PlanItem, ScannedFile
from huhac_media.services.planner import CatalogSnapshot, Planner


def media(path: str, digest: str) -> ScannedFile:
    return ScannedFile(
        absolute_path=Path(path),
        relative_path=PurePosixPath(path),
        filename=Path(path).name,
        size_bytes=1,
        filesystem_mtime_ns=1,
        media_type=MediaType.IMAGE,
        format="JPEG",
        mime_type="image/jpeg",
        sha256=digest,
    )


def test_planner_classifies_known_changed_new_and_duplicates() -> None:
    old = ExistingSource("p1", "v1", "known.jpg", "sha256:" + "a" * 64)
    changed = ExistingSource("p2", "v2", "changed.jpg", "sha256:" + "b" * 64)
    catalog = CatalogSnapshot(
        sources_by_path={"known.jpg": old, "changed.jpg": changed},
        asset_source_counts={old.asset_id: 1, changed.asset_id: 1},
        failed_assets=frozenset({old.asset_id}),
    )

    unsupported = ScannedFile(
        absolute_path=Path("notes.txt"),
        relative_path=PurePosixPath("notes.txt"),
        filename="notes.txt",
        size_bytes=2,
        filesystem_mtime_ns=1,
        media_type=MediaType.UNSUPPORTED,
        format=None,
        mime_type=None,
        sha256=None,
    )
    plan = Planner().plan(
        [
            media("known.jpg", "a" * 64),
            media("changed.jpg", "c" * 64),
            media("new.jpg", "a" * 64),
            unsupported,
        ],
        catalog,
    )

    assert [item.kind for item in plan.items] == [PlanKind.KNOWN, PlanKind.CHANGED, PlanKind.NEW]
    assert all(isinstance(item, PlanItem) for item in plan.items)
    assert plan.unsupported == [unsupported]
    assert isinstance(plan.unsupported[0], ScannedFile)
    assert plan.items[0].previous_failure
    assert plan.items[2].exact_duplicate
