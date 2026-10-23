from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from media_connector.errors import configuration_error


MAX_MANIFEST_BYTES = 1_048_576


def read_workspace_id(workspace: Path) -> str:
    manifest = workspace / "workspace.json"
    try:
        size = manifest.stat().st_size
    except FileNotFoundError as exc:
        raise configuration_error(
            "WORKSPACE_NOT_FOUND", "workspace.json was not found"
        ) from exc
    except OSError as exc:
        raise configuration_error(
            "WORKSPACE_INVALID", f"workspace.json cannot be inspected: {exc}"
        ) from exc

    if not manifest.is_file() or size > MAX_MANIFEST_BYTES:
        raise configuration_error(
            "WORKSPACE_INVALID", "workspace.json is not a bounded regular file"
        )
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise configuration_error(
            "WORKSPACE_INVALID", f"workspace.json is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise configuration_error("WORKSPACE_INVALID", "workspace.json must be an object")

    contract_version = payload.get("workspace_contract_version")
    if not isinstance(contract_version, int) or isinstance(contract_version, bool):
        raise configuration_error(
            "WORKSPACE_INVALID", "workspace_contract_version must be an integer"
        )
    if contract_version != 1:
        raise configuration_error(
            "UNSUPPORTED_WORKSPACE_CONTRACT",
            f"workspace contract version {contract_version} is not supported",
        )

    raw_workspace_id = payload.get("workspace_id")
    if not isinstance(raw_workspace_id, str):
        raise configuration_error("WORKSPACE_INVALID", "workspace_id must be a UUID string")
    try:
        return str(UUID(raw_workspace_id))
    except ValueError as exc:
        raise configuration_error(
            "WORKSPACE_INVALID", "workspace_id must be a valid UUID"
        ) from exc
