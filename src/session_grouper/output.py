from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

from session_grouper import PROCESSOR_NAME, PROCESSOR_VERSION, RESULT_SCHEMA_VERSION
from session_grouper.contract import WorkspaceInput
from session_grouper.models import (
    AssetObservation,
    GroupingConfig,
    GroupingResult,
    Session,
    TimestampConfidence,
)


class OutputError(RuntimeError):
    pass


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def configuration_fingerprint(config: GroupingConfig) -> str:
    return _canonical_sha256(config.as_dict())


def input_fingerprint(workspace: WorkspaceInput) -> str:
    assets = []
    for asset in workspace.observations:
        timestamp = asset.timestamp
        assets.append(
            {
                "asset_id": asset.asset_id,
                "sha256": asset.sha256,
                "media_type": asset.media_type,
                "availability": asset.availability,
                "metadata_location": asset.metadata_location,
                "timestamp_issue": asset.timestamp_issue,
                "timestamp": None
                if timestamp is None
                else {
                    "value": timestamp.value,
                    "source": timestamp.source,
                    "timezone_offset": timestamp.timezone_offset,
                    "filesystem_fallback": timestamp.filesystem_fallback,
                    "confidence": timestamp.confidence.value,
                },
            }
        )
    return _canonical_sha256(
        {
            "workspace_contract_version": workspace.contract_version,
            "workspace_id": workspace.workspace_id,
            "assets": assets,
        }
    )


def result_path(
    workspace: WorkspaceInput, config_fingerprint: str, input_fingerprint: str
) -> Path:
    return (
        workspace.workspace
        / "analysis"
        / PROCESSOR_NAME
        / PROCESSOR_VERSION
        / config_fingerprint
        / f"{input_fingerprint}.json"
    )


def _timestamp_payload(asset: AssetObservation) -> dict | None:
    if asset.timestamp is None:
        return None
    return {
        "datetime": asset.timestamp.value,
        "source": asset.timestamp.source,
        "timezone_offset": asset.timestamp.timezone_offset,
        "filesystem_fallback": asset.timestamp.filesystem_fallback,
        "confidence": asset.timestamp.confidence.value,
    }


def _asset_payload(asset: AssetObservation, assignment_reason: str) -> dict:
    return {
        "asset_id": asset.asset_id,
        "sha256": asset.sha256,
        "media_type": asset.media_type,
        "captured_at": asset.timestamp.value if asset.timestamp else None,
        "timestamp": _timestamp_payload(asset),
        "assignment_confidence": (
            asset.timestamp.confidence.value
            if asset.timestamp
            else TimestampConfidence.UNUSABLE.value
        ),
        "assignment_reason": assignment_reason,
    }


def _session_payload(session: Session, config_fingerprint: str) -> dict:
    ordered = sorted(
        session.assets,
        key=lambda asset: (
            asset.timestamp.wall_time if asset.timestamp else datetime.min,
            asset.asset_id,
        ),
    )
    identity = [
        {
            "asset_id": asset.asset_id,
            "captured_at": asset.timestamp.value if asset.timestamp else None,
        }
        for asset in ordered
    ]
    session_id = "session-" + _canonical_sha256(
        {
            "processor_version": PROCESSOR_VERSION,
            "configuration_fingerprint": config_fingerprint,
            "assets": identity,
        }
    )[:20]
    confidence_rank = {
        TimestampConfidence.STRONG: 3,
        TimestampConfidence.MEDIUM: 2,
        TimestampConfidence.LOW: 1,
        TimestampConfidence.UNUSABLE: 0,
    }
    confidence = min(
        (asset.timestamp.confidence for asset in ordered if asset.timestamp),
        key=lambda value: confidence_rank[value],
    )
    times = [asset.timestamp.wall_time for asset in ordered if asset.timestamp]
    media_types = Counter(asset.media_type for asset in ordered)
    return {
        "session_id": session_id,
        "start": min(times).isoformat(),
        "end": max(times).isoformat(),
        "time_basis": "capture_local_wall_clock",
        "operational_day": session.operational_day,
        "boundary_reason": session.boundary_reason,
        "confidence": confidence.value,
        "asset_count": len(ordered),
        "media_types": dict(sorted(media_types.items())),
        "assets": [
            _asset_payload(
                asset,
                "filesystem_fallback_near_single_session"
                if asset.timestamp
                and asset.timestamp.confidence == TimestampConfidence.LOW
                else "trusted_timestamp_sequence",
            )
            for asset in ordered
        ],
    }


def build_payload(
    workspace: WorkspaceInput,
    config: GroupingConfig,
    grouping: GroupingResult,
    *,
    created_at: str | None = None,
) -> tuple[dict, str, str]:
    config_hash = configuration_fingerprint(config)
    input_hash = input_fingerprint(workspace)
    sessions = [_session_payload(session, config_hash) for session in grouping.sessions]
    unassigned = [
        {
            "asset_id": item.asset.asset_id,
            "sha256": item.asset.sha256,
            "media_type": item.asset.media_type,
            "reason": item.reason,
            "timestamp": _timestamp_payload(item.asset),
        }
        for item in grouping.unassigned
    ]
    assigned_count = sum(session["asset_count"] for session in sessions)
    payload = {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "workspace_contract_version": workspace.contract_version,
        "workspace_id": workspace.workspace_id,
        "processor": {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION},
        "model": None,
        "configuration": config.as_dict(),
        "configuration_fingerprint": config_hash,
        "input": {
            "asset_catalog": workspace.catalog_location,
            "catalog_generated_at": workspace.catalog_generated_at,
            "catalog_run_id": workspace.catalog_run_id,
            "logical_fingerprint": input_hash,
            "asset_count": len(workspace.observations),
        },
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "error": None,
        "result": {
            "sessions": sessions,
            "unassigned": unassigned,
            "summary": {
                "session_count": len(sessions),
                "assigned_asset_count": assigned_count,
                "unassigned_asset_count": len(unassigned),
            },
        },
    }
    return payload, config_hash, input_hash


@contextmanager
def _atomic_target(target: Path) -> Iterator[Path]:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        yield temporary
        with temporary.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_payload_atomic(target: Path, payload: dict) -> None:
    with _atomic_target(target) as temporary:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())


def read_reusable_payload(target: Path, config_hash: str, input_hash: str) -> dict | None:
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputError(f"Existing result is invalid: {target}: {exc}") from exc
    valid = (
        isinstance(payload, dict)
        and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
        and payload.get("processor")
        == {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
        and payload.get("configuration_fingerprint") == config_hash
        and isinstance(payload.get("input"), dict)
        and payload["input"].get("logical_fingerprint") == input_hash
        and payload.get("status") == "success"
    )
    if not valid:
        raise OutputError(f"Existing result does not match its deterministic path: {target}")
    return payload
