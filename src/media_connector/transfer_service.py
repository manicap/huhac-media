from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.errors import configuration_error
from media_connector.compatibility import PROFILE_ID, classify_content
from media_connector.content_store import CHUNK_SIZE, ContentStore, hash_file
from media_connector.errors import ConnectorError
from media_connector.transfer_contract import TransferSelection, read_selection
from media_connector.transfer_lock import library_lock
from media_connector.transfer_paths import TransferRoots, validate_recovery_roots, validate_roots
from media_connector.transfer_state import TransferRepository
from media_connector.workspace import read_workspace_id


TRANSFER_CONTRACT = "huhac.media-connector.transfer"
TRANSFER_CONTRACT_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _operation_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise configuration_error("INVALID_OPERATION_ID", "operation_id must be a UUID") from exc


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


def _copy_to_stage(adapter: LocalFilesystemAdapter, item: Any, stage_directory: Path) -> tuple[Path, str, int]:
    stage_directory.mkdir(parents=True, exist_ok=False)
    partial = stage_directory / "payload.partial"
    digest = hashlib.sha256()
    size = 0
    try:
        with adapter.open_read(
            object_id=item.object_id,
            logical_path=item.logical_path,
            expected_version=item.version_token,
        ) as source, partial.open("xb") as target:
            while True:
                try:
                    chunk = source.read(CHUNK_SIZE)
                except OSError as exc:
                    raise ConnectorError("SOURCE_IO_ERROR", "source read failed during transfer", 3, True) from exc
                if not chunk:
                    break
                try:
                    target.write(chunk)
                except OSError as exc:
                    raise ConnectorError("TRANSFER_WRITE_FAILED", "staging write failed", 4, True) from exc
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
    except ConnectorError:
        raise
    except OSError as exc:
        raise ConnectorError("TRANSFER_WRITE_FAILED", "staging write failed", 4, True) from exc
    return partial, digest.hexdigest(), size


def _verify_and_name_stage(partial: Path, expected_hash: str, expected_size: int) -> tuple[Path, str]:
    verified_hash, verified_size = hash_file(partial, confinement_root=partial.parent)
    if verified_hash != expected_hash or verified_size != expected_size:
        raise ConnectorError("STAGED_CONTENT_MISMATCH", "staged payload failed independent verification", 4)
    compatible = classify_content(partial)
    payload = partial.with_name(f"payload.{compatible.canonical_suffix}")
    try:
        os.replace(partial, payload)
        if os.name != "nt":
            descriptor = os.open(payload.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise ConnectorError("STAGING_RENAME_FAILED", "verified staging payload cannot be named", 4, True) from exc
    return payload, compatible.canonical_suffix


def _remove_owned_stage(stage_directory: Path, work_root: Path) -> None:
    resolved = stage_directory.resolve(strict=True)
    staging_root = (work_root / "staging").resolve(strict=True)
    if staging_root not in resolved.parents:
        raise ConnectorError("UNSAFE_STAGING_PATH", "staging cleanup escaped its root", 4)
    shutil.rmtree(resolved)


def _manifest(repository: TransferRepository, state_root: Path, workspace_id: str, run_id: str) -> Path:
    items = repository.run_items(run_id)
    payload = {
        "contract": "huhac.media-connector.provenance",
        "contract_version": 1,
        "workspace_id": workspace_id,
        "run_id": run_id,
        "items": [
            {
                "source_id": row["source_id"],
                "object_id": row["object_id"],
                "version_token": row["version_token"],
                "logical_path": row["logical_path"],
                "content_sha256": row["content_sha256"],
                "size_bytes": row["size_bytes"],
                "relative_path": row["final_relative_path"],
                "compatibility_profile": row["profile_id"],
                "status": row["status"],
            }
            for row in items
        ],
    }
    directory = state_root / "manifests"
    directory.mkdir(exist_ok=True)
    target = directory / f"{run_id}.json"
    temporary = directory / f".{run_id}.tmp"
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return target


def transfer_run(
    *,
    workspace: Path,
    media_storage: Path,
    state_root: Path,
    work_root: Path,
    selection_path: Path,
    operation_id: str,
    fault_after_verify: bool = False,
    fault_after_publish: bool = False,
) -> dict[str, Any]:
    run_id = _operation_id(operation_id)
    workspace_id, selection, adapter, roots = prepare_transfer(
        workspace=workspace,
        media_storage=media_storage,
        state_root=state_root,
        work_root=work_root,
        selection_path=selection_path,
    )
    results: list[dict[str, Any]] = []
    with library_lock(roots.state_root):
        repository = TransferRepository(roots.state_root, workspace_id)
        try:
            repository.create_run(run_id, workspace_id, _now())
            store = ContentStore(roots.media_storage)
            for index, item in enumerate(selection.items, 1):
                item_id = f"{index:06d}"
                repository.create_item(
                    run_id=run_id,
                    item_id=item_id,
                    source_id=selection.source_id,
                    object_id=item.object_id,
                    version_token=item.version_token,
                    logical_path=item.logical_path,
                    now=_now(),
                )
                stage = roots.work_root / "staging" / run_id / f"{item_id}.partial"
                try:
                    repository.update_item(run_id, item_id, "transferring", _now(), staging_path=str(stage))
                    partial, content_hash, size = _copy_to_stage(adapter, item, stage)
                    _, suffix = _verify_and_name_stage(partial, content_hash, size)
                    final_directory = store.object_directory(content_hash)
                    final_relative = (final_directory / f"payload.{suffix}").relative_to(roots.media_storage).as_posix()
                    repository.update_item(
                        run_id,
                        item_id,
                        "verified_staged",
                        _now(),
                        content_sha256=content_hash,
                        size_bytes=size,
                        canonical_suffix=suffix,
                        profile_id=PROFILE_ID,
                        staging_path=str(stage),
                        final_relative_path=final_relative,
                    )
                    if fault_after_verify:
                        raise SystemExit("simulated crash after staged verification")
                    existing = store.inspect_existing(content_hash, size)
                    if existing is not None:
                        actual_suffix = existing.suffix
                        actual_relative = existing.relative_path
                        repository.complete_item(
                            run_id=run_id, item_id=item_id, source_id=selection.source_id,
                            object_id=item.object_id, version_token=item.version_token,
                            logical_path=item.logical_path, content_hash=content_hash, size=size,
                            suffix=actual_suffix, profile_id=PROFILE_ID, relative_path=actual_relative,
                            status="deduplicated_existing", now=_now(),
                        )
                        _remove_owned_stage(stage, roots.work_root)
                        result_status = "deduplicated_existing"
                    else:
                        repository.update_item(run_id, item_id, "publishing", _now())
                        try:
                            store.publish(stage, content_hash)
                        except FileExistsError:
                            existing = store.inspect_existing(content_hash, size)
                            if existing is None:
                                raise ConnectorError("ATOMIC_PUBLISH_RACE", "content publish race was not verifiable", 4)
                            actual_suffix = existing.suffix
                            actual_relative = existing.relative_path
                            _remove_owned_stage(stage, roots.work_root)
                            result_status = "deduplicated_existing"
                        else:
                            if fault_after_publish:
                                raise SystemExit("simulated crash after publish")
                            existing = store.inspect_existing(content_hash, size)
                            if existing is None:
                                raise ConnectorError("PUBLISHED_OBJECT_MISSING", "published object disappeared", 4)
                            actual_suffix = suffix
                            actual_relative = existing.relative_path
                            result_status = "published"
                        repository.complete_item(
                            run_id=run_id, item_id=item_id, source_id=selection.source_id,
                            object_id=item.object_id, version_token=item.version_token,
                            logical_path=item.logical_path, content_hash=content_hash, size=size,
                            suffix=actual_suffix, profile_id=PROFILE_ID, relative_path=actual_relative,
                            status=result_status, now=_now(),
                        )
                    results.append(
                        {"item_id": item_id, "logical_path": item.logical_path,
                         "status": result_status, "content_sha256": content_hash,
                         "relative_path": actual_relative, "size_bytes": size}
                    )
                except ConnectorError as exc:
                    repository.update_item(run_id, item_id, "failed", _now(), error_code=exc.code)
                    repository.finish_run(run_id, "failed", _now())
                    _manifest(repository, roots.state_root, workspace_id, run_id)
                    raise
            repository.finish_run(run_id, "complete", _now())
            manifest = _manifest(repository, roots.state_root, workspace_id, run_id)
        finally:
            repository.close()
    return {
        "contract": TRANSFER_CONTRACT,
        "contract_version": TRANSFER_CONTRACT_VERSION,
        "operation": "transfer-run",
        "status": "success",
        "library": {"workspace_id": workspace_id},
        "source": {"adapter_kind": "local", "source_id": selection.source_id},
        "preflight": None,
        "run": {"operation_id": run_id, "status": "complete", "items": results,
                "manifest": str(manifest)},
        "error": None,
    }


def _recovery_stage(path_value: str | None, roots: TransferRoots, suffix: str) -> Path:
    if not path_value:
        raise ConnectorError("RECOVERY_EVIDENCE_MISSING", "staging path is missing", 4)
    stage = Path(path_value)
    try:
        resolved = stage.resolve(strict=True)
        staging_root = (roots.work_root / "staging").resolve(strict=True)
    except OSError as exc:
        raise ConnectorError("RECOVERY_EVIDENCE_MISSING", "staging evidence is unavailable", 4, True) from exc
    if staging_root not in resolved.parents:
        raise ConnectorError("UNSAFE_STAGING_PATH", "recovery staging escaped its root", 4)
    entries = list(resolved.iterdir())
    expected_name = f"payload.{suffix}"
    if len(entries) != 1 or entries[0].name != expected_name or entries[0].is_symlink() or not entries[0].is_file():
        raise ConnectorError("RECOVERY_EVIDENCE_INVALID", "staging evidence layout is invalid", 4)
    return resolved


def transfer_recover(
    *, workspace: Path, media_storage: Path, state_root: Path, work_root: Path
) -> dict[str, Any]:
    workspace_id = read_workspace_id(workspace)
    roots = validate_recovery_roots(
        workspace=workspace, media_storage=media_storage, state_root=state_root, work_root=work_root
    )
    if not (roots.state_root / "connector-state.sqlite3").is_file():
        raise ConnectorError("STATE_NOT_FOUND", "connector transfer state does not exist", 4)
    recovered: list[dict[str, Any]] = []
    with library_lock(roots.state_root):
        repository = TransferRepository(roots.state_root, workspace_id)
        try:
            store = ContentStore(roots.media_storage)
            affected_runs: set[str] = set()
            for row in repository.recoverable_items():
                run_id = row["run_id"]
                item_id = row["item_id"]
                affected_runs.add(run_id)
                if row["status"] == "transferring":
                    repository.update_item(
                        run_id, item_id, "interrupted", _now(), error_code="TRANSFER_INTERRUPTED"
                    )
                    recovered.append({"run_id": run_id, "item_id": item_id, "status": "interrupted"})
                    continue
                content_hash = row["content_sha256"]
                size = row["size_bytes"]
                suffix = row["canonical_suffix"]
                if not isinstance(content_hash, str) or not isinstance(size, int) or not isinstance(suffix, str):
                    raise ConnectorError("RECOVERY_EVIDENCE_INVALID", "write-ahead state is incomplete", 4)
                existing = store.inspect_existing(content_hash, size)
                if existing is None:
                    stage = _recovery_stage(row["staging_path"], roots, suffix)
                    staged_hash, staged_size = hash_file(
                        stage / f"payload.{suffix}", confinement_root=roots.work_root
                    )
                    compatible = classify_content(stage / f"payload.{suffix}")
                    if staged_hash != content_hash or staged_size != size or compatible.canonical_suffix != suffix:
                        raise ConnectorError("RECOVERY_EVIDENCE_INVALID", "staged evidence failed verification", 4)
                    repository.update_item(run_id, item_id, "publishing", _now())
                    try:
                        store.publish(stage, content_hash)
                    except FileExistsError:
                        pass
                    existing = store.inspect_existing(content_hash, size)
                    if existing is None:
                        raise ConnectorError("RECOVERY_EVIDENCE_MISSING", "published object is unavailable", 4)
                repository.complete_item(
                    run_id=run_id,
                    item_id=item_id,
                    source_id=row["source_id"],
                    object_id=row["object_id"],
                    version_token=row["version_token"],
                    logical_path=row["logical_path"],
                    content_hash=content_hash,
                    size=size,
                    suffix=existing.suffix,
                    profile_id=row["profile_id"],
                    relative_path=existing.relative_path,
                    status="recovered_published",
                    now=_now(),
                )
                recovered.append({"run_id": run_id, "item_id": item_id, "status": "recovered_published"})
            manifests: list[str] = []
            for run_id in sorted(affected_runs):
                statuses = {row["status"] for row in repository.run_items(run_id)}
                if statuses <= {"published", "deduplicated_existing", "recovered_published"}:
                    repository.finish_run(run_id, "complete", _now())
                    manifests.append(str(_manifest(repository, roots.state_root, workspace_id, run_id)))
                elif "interrupted" in statuses:
                    repository.finish_run(run_id, "interrupted", _now())
        finally:
            repository.close()
    return {
        "contract": TRANSFER_CONTRACT,
        "contract_version": TRANSFER_CONTRACT_VERSION,
        "operation": "transfer-recover",
        "status": "success",
        "library": {"workspace_id": workspace_id},
        "source": None,
        "preflight": None,
        "run": {"recovered_items": recovered, "manifests": manifests},
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
