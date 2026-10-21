from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from media_desk.contract import ContractError, load_workspace
from media_desk.models import WorkspaceSnapshot


WorkspaceState = Literal["connected", "unavailable", "invalid", "unset"]


@dataclass(frozen=True)
class WorkspaceValidation:
    state: WorkspaceState
    label: str
    message: str
    requested_path: Path | None
    resolved_path: Path | None = None
    snapshot: WorkspaceSnapshot | None = None

    @property
    def valid(self) -> bool:
        return self.snapshot is not None and self.state == "connected"


def validate_workspace(
    workspace: Path | None,
    keyframe_fingerprint: str | None = None,
) -> WorkspaceValidation:
    """Validate an existing workspace exclusively through the public read-only contract."""
    if workspace is None:
        return WorkspaceValidation(
            "unset",
            "Nenastaveno",
            "Vyberte adresář existujícího workspace, který obsahuje workspace.json.",
            None,
        )
    requested = Path(workspace)
    try:
        resolved = requested.resolve(strict=True)
    except (FileNotFoundError, PermissionError, OSError):
        return WorkspaceValidation(
            "unavailable",
            "Nedostupné",
            "Cesta nyní není dostupná. Připojte disk nebo síťové úložiště a zkuste to znovu.",
            requested,
        )
    if not resolved.is_dir():
        return WorkspaceValidation(
            "invalid",
            "Neplatné",
            "Zadaná cesta není adresář workspace.",
            requested,
            resolved,
        )
    try:
        snapshot = load_workspace(resolved, keyframe_fingerprint)
    except ContractError as exc:
        detail = str(exc).casefold()
        cause = exc.__cause__
        if isinstance(cause, PermissionError) or "permission" in detail:
            state: WorkspaceState = "unavailable"
            label = "Nedostupné"
            message = "Server nemá oprávnění workspace přečíst. Nastavení nebylo změněno."
        elif "unsupported workspace contract version" in detail:
            state = "invalid"
            label = "Neplatné"
            message = "Workspace používá nepodporovanou verzi kontraktu; Media Desk vyžaduje verzi 1."
        elif "json" in detail:
            state = "invalid"
            label = "Neplatné"
            message = "Workspace obsahuje neplatný JSON manifest, katalog nebo metadata."
        else:
            state = "invalid"
            label = "Neplatné"
            message = "Adresář nesplňuje veřejný workspace kontrakt verze 1."
        return WorkspaceValidation(state, label, message, requested, resolved)
    return WorkspaceValidation(
        "connected",
        "Připojeno",
        f"Workspace {snapshot.workspace_id} je čitelný a kompatibilní.",
        requested,
        resolved,
        snapshot,
    )
