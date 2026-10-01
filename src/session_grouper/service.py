from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from session_grouper.contract import WorkspaceInput, load_workspace
from session_grouper.grouping import group_assets
from session_grouper.models import GroupingConfig
from session_grouper.output import (
    build_payload,
    read_reusable_payload,
    result_path,
    write_payload_atomic,
)


@dataclass(frozen=True)
class AnalysisResult:
    workspace: WorkspaceInput
    payload: dict
    output_path: Path
    reused: bool
    dry_run: bool


def analyze_workspace(
    workspace_path: Path, config: GroupingConfig, *, dry_run: bool = False
) -> AnalysisResult:
    workspace = load_workspace(workspace_path, config)
    grouping = group_assets(workspace.observations, config)
    payload, config_hash, input_hash = build_payload(workspace, config, grouping)
    target = result_path(workspace, config_hash, input_hash)
    existing = read_reusable_payload(target, config_hash, input_hash)
    if existing is not None:
        return AnalysisResult(workspace, existing, target, reused=True, dry_run=dry_run)
    if not dry_run:
        write_payload_atomic(target, payload)
    return AnalysisResult(workspace, payload, target, reused=False, dry_run=dry_run)
