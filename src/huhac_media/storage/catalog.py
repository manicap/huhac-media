from __future__ import annotations

from huhac_media.domain.models import ExistingSource
from huhac_media.services.planner import CatalogSnapshot
from huhac_media.storage.database import Database


def read_catalog(database: Database) -> CatalogSnapshot:
    with database.transaction() as connection:
        sources = {
            row["relative_path"]: ExistingSource(
                source_path_id=row["source_path_id"],
                source_version_id=row["source_version_id"],
                relative_path=row["relative_path"],
                asset_id=row["asset_id"],
                stage_failures=row["stage_failures"],
            )
            for row in connection.execute(
                """
                SELECT sp.id AS source_path_id, sv.id AS source_version_id,
                       sp.relative_path, sv.asset_id,
                       (SELECT COUNT(*) FROM asset_stages ast
                        WHERE ast.asset_id = sv.asset_id AND ast.status = 'failed') AS stage_failures
                FROM source_paths sp
                JOIN source_versions sv ON sv.id = sp.current_source_version_id
                """
            )
        }
        counts = {
            row["asset_id"]: row["count"]
            for row in connection.execute(
                "SELECT asset_id, COUNT(*) AS count FROM source_versions "
                "WHERE status = 'active' GROUP BY asset_id"
            )
        }
        failures = frozenset(
            row["asset_id"]
            for row in connection.execute(
                "SELECT DISTINCT asset_id FROM asset_stages WHERE status = 'failed'"
            )
        )
    return CatalogSnapshot(sources, counts, failures)

