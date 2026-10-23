from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from media_connector.errors import configuration_error


SELECTION_CONTRACT = "huhac.media-connector.transfer-selection"
SELECTION_VERSION = 1
MAX_SELECTION_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TransferSelectionItem:
    object_id: str
    version_token: str
    logical_path: str


@dataclass(frozen=True, slots=True)
class TransferSelection:
    workspace_id: str
    adapter_kind: str
    source_id: str
    source_root: Path
    items: tuple[TransferSelectionItem, ...]


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > 16_384:
        raise configuration_error("INVALID_SELECTION", f"{key} must be a bounded string")
    return value


def read_selection(path: Path) -> TransferSelection:
    try:
        info = path.stat()
        if not path.is_file() or info.st_size > MAX_SELECTION_BYTES:
            raise configuration_error(
                "INVALID_SELECTION", "selection must be a bounded regular file"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise configuration_error("INVALID_SELECTION", f"selection cannot be read: {exc}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise configuration_error("INVALID_SELECTION", "selection is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise configuration_error("INVALID_SELECTION", "selection must be a JSON object")
    if payload.get("contract") != SELECTION_CONTRACT or payload.get("contract_version") != SELECTION_VERSION:
        raise configuration_error("INVALID_SELECTION", "selection contract is unsupported")

    workspace_id = _required_string(payload, "workspace_id")
    try:
        workspace_id = str(UUID(workspace_id))
    except ValueError as exc:
        raise configuration_error("INVALID_SELECTION", "workspace_id must be a UUID") from exc

    source = payload.get("source")
    if not isinstance(source, dict):
        raise configuration_error("INVALID_SELECTION", "source must be an object")
    adapter_kind = _required_string(source, "adapter_kind")
    if adapter_kind != "local":
        raise configuration_error("UNSUPPORTED_ADAPTER", "only the local adapter is supported")
    source_id = _required_string(source, "source_id")
    source_root = Path(_required_string(source, "source_root"))

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items or len(raw_items) > 100_000:
        raise configuration_error("INVALID_SELECTION", "items must contain 1 to 100000 objects")
    items: list[TransferSelectionItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise configuration_error("INVALID_SELECTION", "each item must be an object")
        item = TransferSelectionItem(
            object_id=_required_string(raw, "object_id"),
            version_token=_required_string(raw, "version_token"),
            logical_path=_required_string(raw, "logical_path"),
        )
        if item.object_id in seen:
            raise configuration_error("INVALID_SELECTION", "duplicate object_id in selection")
        seen.add(item.object_id)
        items.append(item)
    return TransferSelection(workspace_id, adapter_kind, source_id, source_root, tuple(items))
