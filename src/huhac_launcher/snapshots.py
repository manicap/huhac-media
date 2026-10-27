from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re

from media_desk.contract import ContractError, load_workspace
from media_desk.normalizer_adapter import attach_normalizer_snapshot

from huhac_launcher.config import LauncherConfig, LauncherProfile


_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class NormalizerChoice:
    configuration_fingerprint: str
    input_set_fingerprint: str
    created_at: str | None
    asset_count: int | None
    state: str
    message: str

    @property
    def key(self) -> tuple[str, str]:
        return self.configuration_fingerprint, self.input_set_fingerprint

    @property
    def valid(self) -> bool:
        return self.state == "available"

    @property
    def label(self) -> str:
        count = f"{self.asset_count} médií" if self.asset_count is not None else "? médií"
        created = _date_label(self.created_at)
        status = {
            "available": "platný", "invalid": "neplatný", "stale": "zastaralý",
            "ambiguous": "nejednoznačný", "missing": "chybí",
        }.get(self.state, self.state)
        return (
            f"Normalizer v1 · {count} · {created} · "
            f"{self.configuration_fingerprint[:8]} / {self.input_set_fingerprint[:8]} · {status}"
        )


def _date_label(value: str | None) -> str:
    if not value:
        return "datum neznámé"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "datum neplatné"
    return f"{parsed.day}. {parsed.month}. {parsed.year}"


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def scan_normalizer_snapshots(workspace: Path) -> tuple[str, tuple[NormalizerChoice, ...]]:
    """List public snapshots and delegate full validation to Media Desk's adapter."""
    base = load_workspace(Path(workspace))
    root = base.root / "analysis" / "normalizer" / "normalizer-v1"
    if not root.exists():
        return base.workspace_id, ()
    try:
        if root.is_symlink():
            raise ContractError("Normalizer namespace nesmí být symlink")
        resolved_root = root.resolve(strict=True)
        if not resolved_root.is_dir() or not _inside(base.root, resolved_root):
            raise ContractError("Normalizer namespace opouští workspace")
    except OSError as exc:
        raise ContractError(f"Normalizer namespace nelze načíst: {exc}") from exc

    choices: list[NormalizerChoice] = []
    try:
        configurations = sorted(root.iterdir())
    except OSError as exc:
        raise ContractError(f"Normalizer namespace nelze načíst: {exc}") from exc
    for configuration in configurations:
        if configuration.is_symlink() or not configuration.is_dir() or _SHA256.fullmatch(configuration.name) is None:
            continue
        try:
            inputs = sorted(configuration.iterdir())
        except OSError:
            continue
        for input_set in inputs:
            if input_set.is_symlink() or not input_set.is_dir() or _SHA256.fullmatch(input_set.name) is None:
                continue
            checked = attach_normalizer_snapshot(base, configuration.name, input_set.name)
            status = checked.normalizer
            created_at: str | None = None
            asset_count: int | None = None
            try:
                if status.state != "available":
                    raise ValueError("neplatný snapshot se znovu nečte")
                resolved = input_set.resolve(strict=True)
                if not _inside(resolved_root, resolved):
                    raise ValueError("snapshot opouští namespace")
                manifest = json.loads((resolved / "manifest.json").read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    if isinstance(manifest.get("created_at"), str):
                        created_at = manifest["created_at"]
                    summary = manifest.get("summary")
                    if isinstance(summary, dict) and isinstance(summary.get("asset_count"), int):
                        asset_count = summary["asset_count"]
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            choices.append(NormalizerChoice(
                configuration.name, input_set.name, created_at, asset_count,
                status.state, status.message,
            ))
    return base.workspace_id, tuple(choices)


def validate_profile_selection(profile: LauncherProfile) -> str:
    """Return workspace id or raise a user-facing contract/configuration error."""
    snapshot = load_workspace(profile.workspace, profile.keyframe_fingerprint)
    if profile.keyframe_fingerprint is not None:
        videos = [asset for asset in snapshot.assets if asset.media_type == "video"]
        if not videos or not any(
            asset.preview_status.startswith("Video keyframe") for asset in videos
        ):
            raise ContractError(
                "Video Keyframes fingerprint není kompatibilní s vybraným workspace"
            )
    selection = profile.normalizer_selection
    if selection is not None:
        checked = attach_normalizer_snapshot(snapshot, *selection)
        if checked.normalizer.state != "available":
            raise ContractError(
                f"Normalizer snapshot nelze aktivovat: {checked.normalizer.message}"
            )
    return snapshot.workspace_id


def validate_runtime(config: LauncherConfig) -> str:
    return validate_profile_selection(LauncherProfile(
        id="runtime", name="runtime", workspace=config.workspace,
        profile=config.profile, port=config.port,
        keyframe_fingerprint=config.keyframe_fingerprint,
        normalizer_configuration_fingerprint=config.normalizer_configuration_fingerprint,
        normalizer_input_set_fingerprint=config.normalizer_input_set_fingerprint,
    ))
