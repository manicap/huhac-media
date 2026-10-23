from __future__ import annotations

from pathlib import Path
from typing import Any

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.errors import configuration_error
from media_connector.transfer_contract import TransferSelection, read_selection
from media_connector.transfer_paths import TransferRoots, validate_roots
from media_connector.workspace import read_workspace_id


TRANSFER_CONTRACT = "huhac.media-connector.transfer"
TRANSFER_CONTRACT_VERSION = 1


def prepare_transfer(
    *, workspace: Path, media_storage: Path, state_root: Path, work_root: Path, selection_path: Path
) -> tuple[str, TransferSelection, LocalFilesystemAdapter, TransferRoots]:
    workspace_id = read_workspace_id(workspace)
    selection = read_selection(selection_path)
    if selection.workspace_id != workspace_id:
        raise configuration_error(
            "SELECTION_LIBRARY_MISMATCH", "selection belongs to another workspace"
        )
    adapter = LocalFilesystemAdapter(selection.source_root)
    if adapter.source_id != selection.source_id:
        raise configuration_error("SELECTION_SOURCE_MISMATCH", "selection source identity changed")
    roots = validate_roots(
        workspace=workspace,
        media_storage=media_storage,
        state_root=state_root,
        work_root=work_root,
        source_root=adapter.root,
    )
    return workspace_id, selection, adapter, roots


def transfer_preflight(
    *, workspace: Path, media_storage: Path, state_root: Path, work_root: Path, selection_path: Path
) -> dict[str, Any]:
    workspace_id, selection, adapter, roots = prepare_transfer(
        workspace=workspace,
        media_storage=media_storage,
        state_root=state_root,
        work_root=work_root,
        selection_path=selection_path,
    )
    return {
        "contract": TRANSFER_CONTRACT,
        "contract_version": TRANSFER_CONTRACT_VERSION,
        "operation": "transfer-preflight",
        "status": "success",
        "library": {"workspace_id": workspace_id},
        "source": {"adapter_kind": "local", "source_id": adapter.source_id},
        "preflight": {
            "item_count": len(selection.items),
            "media_storage": str(roots.media_storage),
            "state_root": str(roots.state_root),
            "transfer_work_root": str(roots.work_root),
            "same_filesystem_staging": True,
            "writes_performed": False,
        },
        "run": None,
        "error": None,
    }


def transfer_error_envelope(operation: str, error: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": TRANSFER_CONTRACT,
        "contract_version": TRANSFER_CONTRACT_VERSION,
        "operation": operation,
        "status": "error",
        "library": None,
        "source": None,
        "preflight": None,
        "run": None,
        "error": error,
    }

