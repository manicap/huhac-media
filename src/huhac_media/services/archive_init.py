from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable
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
from huhac_media.storage.atomic import write_json_atomic
from huhac_media.storage.catalog import CatalogStore
from huhac_media.storage.contract import ASSET_CATALOG, WORKSPACE_CONTRACT_VERSION, export_asset_catalog
from huhac_media.storage.database import Database
from huhac_media.storage.init_operation import (
    LOCK_NAME,
    MARKER_NAME,
    InitializationBusyError,
    init_lock,
    read_marker,
    write_marker,
)
from huhac_media.storage.workspace import WORKSPACE_DIRECTORIES


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


class SimulatedInterruption(RuntimeError):
    pass


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
        database_path = workspace / "state" / "catalog.sqlite3"
        uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            if connection.execute("SELECT COUNT(*) FROM workspace WHERE id = ?", (workspace_id,)).fetchone()[0] != 1:
                raise ValueError
            run_id = catalog["generated_by_run_id"]
            if connection.execute("SELECT COUNT(*) FROM runs WHERE id = ? AND status = 'success'", (run_id,)).fetchone()[0] != 1:
                raise ValueError
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError, json.JSONDecodeError):
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
    requested_operation_id = operation_id
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
        if candidate == workspace and candidate.exists() and (candidate / MARKER_NAME).is_file():
            try:
                marker = read_marker(candidate)
                assert marker is not None
                marker_operation = str(UUID(marker["operation_id"]))
                if requested_operation_id is not None and operation_id != marker_operation:
                    return _reject(operation_id, storage, workspace, "INCOMPLETE_OPERATION_MISMATCH", "use the original operation ID")
                if Path(marker["storage_path"]) != storage or Path(marker["workspace_path"]) != workspace:
                    raise ValueError("marker roots do not match")
                operation_id = marker_operation
            except (AssertionError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return _reject(operation_id, storage, workspace, "CORRUPT_OR_LEGACY_PARTIAL", str(exc), state="failed_requires_manual_action")
            allowed = {MARKER_NAME, LOCK_NAME, *(Path(item).parts[0] for item in WORKSPACE_DIRECTORIES)}
            unknown = {item.name for item in candidate.iterdir()} - allowed
            if unknown:
                return _reject(operation_id, storage, workspace, "WORKSPACE_CHANGED", "unrecognized workspace content", state="failed_requires_manual_action")
            continue
        if candidate.exists() and any(candidate.iterdir()):
            return _reject(operation_id, storage, workspace, code, f"directory is not empty: {candidate}")
    result = InitResult(operation_id, "preflight_ok", str(storage), str(workspace), warnings=warnings)
    return result


def _phase(marker: dict, workspace: Path, name: str, hook: Callable[[str], None] | None) -> None:
    marker["phase"] = name
    write_marker(workspace, marker)
    if hook is not None:
        hook(name)


def initialize_archive(
    storage: Path,
    workspace: Path,
    operation_id: str,
    *,
    classifier: Classifier = classify_filesystem,
    phase_hook: Callable[[str], None] | None = None,
) -> InitResult:
    first = preflight_archive_init(storage, workspace, operation_id=operation_id, classifier=classifier)
    if first.state == "ready_existing":
        try:
            marker = read_marker(Path(first.workspace_path))
        except (OSError, ValueError, json.JSONDecodeError):
            marker = None
        if marker and marker.get("operation_id") == operation_id and marker.get("status") != "complete":
            try:
                with init_lock(Path(first.workspace_path)):
                    marker["phase"] = "complete"
                    marker["status"] = "complete"
                    write_marker(Path(first.workspace_path), marker)
            except InitializationBusyError as exc:
                return _reject(operation_id, storage, workspace, "INITIALIZATION_BUSY", str(exc), state="failed_recoverable")
        return first
    if first.state != "preflight_ok":
        return first
    storage = Path(first.storage_path)
    workspace = Path(first.workspace_path)
    workspace_created = not workspace.exists()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        with init_lock(workspace):
            second = preflight_archive_init(storage, workspace, operation_id=operation_id, classifier=classifier)
            if second.state == "ready_existing":
                return second
            # The lock itself is the only allowed new item between preflight and validation.
            if second.state != "preflight_ok" and not (
                second.error and second.error.code == "WORKSPACE_NOT_EMPTY_UNKNOWN"
                and {item.name for item in workspace.iterdir()} == {LOCK_NAME}
            ):
                if second.error:
                    second.error = InitError("PREFLIGHT_STALE", second.error.message)
                return second
            existing_marker = read_marker(workspace)
            workspace_id = str(UUID(existing_marker["workspace_id"])) if existing_marker else str(uuid4())
            marker = existing_marker or {
                "schema_version": 1,
                "operation_id": operation_id,
                "workspace_id": workspace_id,
                "storage_path": str(storage),
                "workspace_path": str(workspace),
                "phase": "reserved",
                "status": "initializing",
            }
            if marker["operation_id"] != operation_id:
                return _reject(operation_id, storage, workspace, "INCOMPLETE_OPERATION_MISMATCH", "operation ID differs from marker", state="failed_requires_manual_action")
            write_marker(workspace, marker)
            if phase_hook:
                phase_hook("reserved")
            storage_created = not storage.exists()
            storage.mkdir(parents=True, exist_ok=True)
            if any(storage.iterdir()):
                return _reject(operation_id, storage, workspace, "STORAGE_CHANGED", "storage is no longer empty", state="failed_recoverable")
            _phase(marker, workspace, "storage_ready", phase_hook)
            for relative in WORKSPACE_DIRECTORIES:
                (workspace / relative).mkdir(parents=True, exist_ok=True)
            _phase(marker, workspace, "layout_ready", phase_hook)

            database = Database(workspace / "state" / "catalog.sqlite3")
            with database.transaction() as connection:
                connection.execute("SELECT 1")
            _phase(marker, workspace, "sqlite_ready", phase_hook)
            store = CatalogStore(database)
            store.ensure_workspace(workspace_id)
            _phase(marker, workspace, "workspace_row_ready", phase_hook)
            effective = {
                "operation_kind": "initialize",
                "operation_id": operation_id,
                "storage_path": str(storage),
                "workspace_path": str(workspace),
            }
            store.ensure_initialization_run(operation_id, storage, workspace, effective)
            _phase(marker, workspace, "run_started", phase_hook)
            report_path = workspace / "runs" / f"init_{operation_id}" / "report.json"
            write_json_atomic(report_path, {
                "schema_version": 1,
                "operation_id": operation_id,
                "workspace_id": workspace_id,
                "operation_kind": "initialize",
                "counts": {"assets": 0, "hashes": 0, "imports": 0, "processors": 0},
                "storage_path": str(storage),
                "workspace_path": str(workspace),
            })
            _phase(marker, workspace, "report_ready", phase_hook)
            if any(storage.iterdir()):
                return _reject(operation_id, storage, workspace, "STORAGE_CHANGED", "storage changed during initialization", state="failed_recoverable")
            with database.transaction() as connection:
                if connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] != 0:
                    return _reject(operation_id, storage, workspace, "WORKSPACE_CHANGED", "database contains assets", state="failed_requires_manual_action")
            export_asset_catalog(database, workspace, storage, workspace_id, operation_id)
            _phase(marker, workspace, "catalog_ready", phase_hook)
            store.finish_run(operation_id, "success", {"assets": 0, "operation_kind": "initialize"})
            _phase(marker, workspace, "run_finished", phase_hook)
            manifest = {
                "schema_version": 1,
                "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
                "workspace_id": workspace_id,
                "asset_catalog": ASSET_CATALOG.as_posix(),
            }
            write_json_atomic(workspace / "workspace.json", manifest)
            if phase_hook:
                phase_hook("manifest_ready")
            marker["phase"] = "complete"
            marker["status"] = "complete"
            write_marker(workspace, marker)
            return InitResult(
                operation_id,
                "ready",
                str(storage),
                str(workspace),
                workspace_id=workspace_id,
                created={
                    "storage_directory": storage_created,
                    "workspace_directory": workspace_created,
                    "workspace_manifest": True,
                    "empty_catalog": True,
                    "sqlite": True,
                },
                warnings=first.warnings,
                restart_required=True,
            )
    except InitializationBusyError as exc:
        return _reject(operation_id, storage, workspace, "INITIALIZATION_BUSY", str(exc), state="failed_recoverable")
    except (KeyboardInterrupt, SimulatedInterruption):
        return _reject(operation_id, storage, workspace, "INTERRUPTED", "initialization was interrupted", state="failed_recoverable")
    except PermissionError as exc:
        if Path(workspace).is_dir() and (Path(workspace) / LOCK_NAME).exists():
            try:
                with init_lock(Path(workspace)):
                    pass
            except InitializationBusyError:
                return _reject(operation_id, storage, workspace, "INITIALIZATION_BUSY", "archive initialization is already running", state="failed_recoverable")
        return _reject(operation_id, storage, workspace, "PERMISSION_DENIED", str(exc), state="failed_recoverable")
    except OSError as exc:
        return _reject(operation_id, storage, workspace, "INITIALIZATION_FAILED", str(exc), state="failed_recoverable")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _reject(operation_id, storage, workspace, "WORKSPACE_CHANGED", str(exc), state="failed_requires_manual_action")
