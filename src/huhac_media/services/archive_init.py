from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from huhac_media.storage.filesystem_policy import (
    Classifier,
    canonical_target,
    classify_filesystem,
    contains_reparse_or_symlink,
    identity,
    roots_overlap,
    validate_path_text,
)


@dataclass(frozen=True)
class InitError:
    code: str
    message: str


@dataclass
class InitResult:
    operation_id: str
    state: str
    storage_path: str
    workspace_path: str
    workspace_id: str | None = None
    created: dict[str, bool] = field(default_factory=lambda: {
        "storage_directory": False,
        "workspace_directory": False,
        "workspace_manifest": False,
        "empty_catalog": False,
        "sqlite": False,
    })
    warnings: list[str] = field(default_factory=list)
    error: InitError | None = None
    restart_required: bool = False
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def _reject(operation_id: str, storage: Path, workspace: Path, code: str, message: str,
            *, state: str = "rejected") -> InitResult:
    return InitResult(operation_id, state, str(storage), str(workspace), error=InitError(code, message))


def _read_ready_workspace(workspace: Path, storage: Path) -> tuple[str | None, str | None]:
    manifest_path = workspace / "workspace.json"
    if not manifest_path.is_file():
        return None, None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        catalog_path = workspace / manifest["asset_catalog"]
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        workspace_id = str(UUID(manifest["workspace_id"]))
        if manifest.get("schema_version") != 1 or manifest.get("workspace_contract_version") != 1:
            raise ValueError
        if catalog.get("workspace_contract_version") != 1 or catalog.get("workspace_id") != workspace_id:
            raise ValueError
        if not isinstance(catalog.get("assets"), list):
            raise ValueError
        source_root = canonical_target(Path(catalog["source_root"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, "CORRUPT_OR_LEGACY_PARTIAL"
    if source_root != storage:
        return None, "EXISTING_WORKSPACE"
    return workspace_id, None


def preflight_archive_init(
    storage: Path,
    workspace: Path,
    *,
    operation_id: str | None = None,
    classifier: Classifier = classify_filesystem,
) -> InitResult:
    operation_id = operation_id or str(uuid4())
    try:
        UUID(operation_id)
    except (TypeError, ValueError):
        return _reject(str(operation_id), storage, workspace, "INVALID_OPERATION_ID", "operation ID must be a UUID")
    try:
        validate_path_text(storage)
        validate_path_text(workspace)
        storage = canonical_target(storage)
        workspace = canonical_target(workspace)
    except (OSError, ValueError) as exc:
        return _reject(operation_id, storage, workspace, "INVALID_PATH", str(exc))
    if roots_overlap(storage, workspace):
        return _reject(operation_id, storage, workspace, "OVERLAPPING_ROOTS", "storage and workspace roots overlap")
    try:
        if contains_reparse_or_symlink(storage) or contains_reparse_or_symlink(workspace):
            return _reject(operation_id, storage, workspace, "PATH_IDENTITY_CHANGED", "symlink or reparse point is not allowed")
        identity(storage)
        identity(workspace)
    except OSError as exc:
        return _reject(operation_id, storage, workspace, "INVALID_PATH", str(exc))
    workspace_fs = classifier(workspace)
    if workspace_fs != "local":
        return _reject(operation_id, storage, workspace, "UNSUPPORTED_WORKSPACE_FILESYSTEM", f"workspace filesystem is {workspace_fs}")
    warnings: list[str] = []
    storage_fs = classifier(storage)
    if storage_fs != "local":
        warnings.append(f"Media Storage filesystem classified as {storage_fs}; it must remain available for ingest.")
    for candidate, code in ((storage, "STORAGE_NOT_EMPTY"), (workspace, "WORKSPACE_NOT_EMPTY_UNKNOWN")):
        if candidate.exists() and not candidate.is_dir():
            return _reject(operation_id, storage, workspace, "INVALID_PATH", f"not a directory: {candidate}")
        if candidate == workspace and candidate.exists() and (candidate / "workspace.json").exists():
            workspace_id, ready_error = _read_ready_workspace(workspace, storage)
            if workspace_id is not None:
                return InitResult(operation_id, "ready_existing", str(storage), str(workspace), workspace_id=workspace_id)
            return _reject(operation_id, storage, workspace, ready_error or "EXISTING_WORKSPACE", "existing workspace cannot be initialized")
        if candidate.exists() and any(candidate.iterdir()):
            return _reject(operation_id, storage, workspace, code, f"directory is not empty: {candidate}")
    result = InitResult(operation_id, "preflight_ok", str(storage), str(workspace), warnings=warnings)
    result.created["storage_directory"] = not storage.exists()
    result.created["workspace_directory"] = not workspace.exists()
    return result
