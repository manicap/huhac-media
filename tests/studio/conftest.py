from __future__ import annotations

import pytest

from huhac_studio.catalog import CatalogAsset, InMemoryWorkspaceCatalog


def asset_id(index: int) -> str:
    return f"sha256:{index:064x}"


@pytest.fixture
def catalog() -> InMemoryWorkspaceCatalog:
    return InMemoryWorkspaceCatalog(
        {
            "workspace-test": {
                asset_id(1): CatalogAsset(asset_id(1), "image"),
                asset_id(2): CatalogAsset(asset_id(2), "video", original_access_state="offline"),
                asset_id(3): CatalogAsset(asset_id(3), "image", availability="unavailable"),
            },
            "workspace-second": {},
        }
    )
