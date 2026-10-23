from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Callable
from uuid import UUID


_FIELDS = {
    "schema_version", "operation_id", "state", "workspace_id", "storage_path",
    "workspace_path", "created", "warnings", "error", "restart_required",
}
_CREATED_FIELDS = {
    "storage_directory", "workspace_directory", "workspace_manifest", "empty_catalog", "sqlite",
}


class ArchiveSetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchiveSetupResult:
    operation_id: str
    state: str
    workspace_id: str | None
    storage_path: str
    workspace_path: str
    warnings: tuple[str, ...]
    error_code: str | None
    error_message: str | None
    restart_required: bool

    @property
    def successful(self) -> bool:
        return self.state in {"preflight_ok", "ready", "ready_existing"}


class ArchiveSetupClient:
    def __init__(
        self,
        *,
        executable: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self.executable = executable or sys.executable
        self.runner = runner

    def preflight(self, storage: str, workspace: str) -> ArchiveSetupResult:
        return self._invoke(storage, workspace, preflight=True)

    def initialize(self, storage: str, workspace: str, operation_id: str) -> ArchiveSetupResult:
        return self._invoke(storage, workspace, operation_id=operation_id, preflight=False)

    def _invoke(
        self, storage: str, workspace: str, *, operation_id: str | None = None, preflight: bool
    ) -> ArchiveSetupResult:
        command = [
            self.executable, "-m", "huhac_media", "init", "--storage", storage,
            "--workspace", workspace,
        ]
        if preflight:
            command.append("--preflight")
        else:
            command.extend(("--operation-id", operation_id or "", "--yes"))
        command.append("--json")
        try:
            completed = self.runner(
                command,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30 if preflight else 120,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArchiveSetupError(f"Inicializační příkaz se nepodařilo spustit: {exc}") from exc
        if len(completed.stdout.encode("utf-8")) > 65536:
            raise ArchiveSetupError("Inicializační příkaz vrátil příliš velký výstup.")
        try:
            payload = json.loads(completed.stdout)
            result = _parse_result(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ArchiveSetupError("Inicializační příkaz vrátil neplatný JSON kontrakt.") from exc
        if (completed.returncode == 0) != result.successful:
            raise ArchiveSetupError("Inicializační příkaz vrátil nekonzistentní stav a exit code.")
        return result


def _parse_result(payload: object) -> ArchiveSetupResult:
    if not isinstance(payload, dict) or set(payload) != _FIELDS or payload.get("schema_version") != 1:
        raise ValueError("unsupported envelope")
    operation_id = str(UUID(payload["operation_id"]))
    state = payload["state"]
    if state not in {
        "preflight_ok", "confirmation_required", "ready", "ready_existing", "rejected",
        "failed_recoverable", "failed_requires_manual_action",
    }:
        raise ValueError("unsupported state")
    if not isinstance(payload["storage_path"], str) or not isinstance(payload["workspace_path"], str):
        raise ValueError("invalid paths")
    created = payload["created"]
    if not isinstance(created, dict) or set(created) != _CREATED_FIELDS or any(type(value) is not bool for value in created.values()):
        raise ValueError("invalid created map")
    warnings = payload["warnings"]
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise ValueError("invalid warnings")
    error = payload["error"]
    if error is not None and (
        not isinstance(error, dict) or set(error) != {"code", "message"}
        or not all(isinstance(error[key], str) for key in error)
    ):
        raise ValueError("invalid error")
    workspace_id = payload["workspace_id"]
    if workspace_id is not None:
        workspace_id = str(UUID(workspace_id))
    if type(payload["restart_required"]) is not bool:
        raise ValueError("invalid restart flag")
    if state in {"preflight_ok", "ready", "ready_existing"} and error is not None:
        raise ValueError("successful state contains an error")
    if state in {"ready", "ready_existing"} and workspace_id is None:
        raise ValueError("ready state has no workspace ID")
    return ArchiveSetupResult(
        operation_id=operation_id,
        state=state,
        workspace_id=workspace_id,
        storage_path=payload["storage_path"],
        workspace_path=payload["workspace_path"],
        warnings=tuple(warnings),
        error_code=error["code"] if error else None,
        error_message=error["message"] if error else None,
        restart_required=payload["restart_required"],
    )


class ConfirmationStore:
    def __init__(self, *, ttl_seconds: float = 300, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._items: dict[str, tuple[float, str, str, str]] = {}

    def issue(self, result: ArchiveSetupResult) -> str:
        now = self.clock()
        self._items = {
            key: value for key, value in self._items.items() if value[0] >= now
        }
        while len(self._items) >= 128:
            self._items.pop(next(iter(self._items)))
        nonce = secrets.token_urlsafe(32)
        self._items[nonce] = (
            now + self.ttl_seconds,
            result.operation_id,
            result.storage_path,
            result.workspace_path,
        )
        return nonce

    def consume(self, nonce: str, operation_id: str, storage: str, workspace: str) -> bool:
        item = self._items.pop(nonce, None)
        if item is None:
            return False
        expires, expected_operation, expected_storage, expected_workspace = item
        return (
            self.clock() <= expires
            and secrets.compare_digest(expected_operation, operation_id)
            and secrets.compare_digest(expected_storage, storage)
            and secrets.compare_digest(expected_workspace, workspace)
        )
