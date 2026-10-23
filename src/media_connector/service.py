from __future__ import annotations

from pathlib import Path
from typing import Any

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.errors import configuration_error
from media_connector.workspace import read_workspace_id


CONTRACT = "huhac.media-connector.local-discovery"
CONTRACT_VERSION = 1
OPERATION = "local-discovery"


def discover_local(
    *, workspace: Path, source_root: Path, page_size: int, cursor: str | None
) -> dict[str, Any]:
    workspace_id = read_workspace_id(workspace)
    adapter = LocalFilesystemAdapter(source_root)
    workspace_root = workspace.resolve(strict=True)
    if (
        workspace_root == adapter.root
        or workspace_root in adapter.root.parents
        or adapter.root in workspace_root.parents
    ):
        raise configuration_error(
            "SOURCE_WORKSPACE_OVERLAP",
            "source root and workspace must not overlap",
        )
    page = adapter.list_page(page_size=page_size, cursor=cursor)
    return {
        "contract": CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "operation": OPERATION,
        "status": "success",
        "library": {"workspace_id": workspace_id},
        "source": {
            "adapter_kind": adapter.adapter_kind,
            "source_id": adapter.source_id,
            "source_root": str(adapter.root),
        },
        "capabilities": adapter.capabilities.to_dict(),
        "page": page.page_dict(),
        "warnings": [warning.to_dict() for warning in page.warnings],
        "error": None,
    }
