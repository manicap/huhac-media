from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import numpy as np

from faces import (
    CLUSTER_PROCESSOR_NAME,
    CLUSTER_PROCESSOR_VERSION,
    PROCESSOR_NAME,
    PROCESSOR_VERSION,
    RESULT_SCHEMA_VERSION,
)
from faces.contract import load_workspace
from faces.models import ClusterConfig, FaceRecord, FacesConfig
from faces.output import (
    canonical_sha256,
    configuration_fingerprint,
    read_reusable_result,
    result_path,
    write_json_atomic,
)


_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class PreparedClustering:
    workspace: Any
    faces_configuration_fingerprint: str
    config: ClusterConfig
    configuration_fingerprint: str
    logical_input_fingerprint: str
    records: tuple[FaceRecord, ...]
    output_path: Path
    action: str


@dataclass(frozen=True)
class ClusterRunResult:
    prepared: PreparedClustering
    cluster_count: int
    uncertain_count: int
    reused: bool
    dry_run: bool


def _load_face_records(workspace, faces_fingerprint: str) -> tuple[FaceRecord, ...]:
    records: list[FaceRecord] = []
    for visual_input in workspace.inputs:
        target = result_path(workspace, faces_fingerprint, visual_input)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result = payload.get("result") if isinstance(payload, dict) else None
        faces = result.get("faces") if isinstance(result, dict) else None
        configuration = payload.get("configuration") if isinstance(payload, dict) else None
        try:
            faces_config = FacesConfig(**configuration) if isinstance(configuration, dict) else None
            if faces_config is None:
                continue
            faces_config.validate()
        except (TypeError, ValueError):
            continue
        if not (
            isinstance(payload, dict)
            and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
            and payload.get("workspace_contract_version") == workspace.contract_version
            and payload.get("workspace_id") == workspace.workspace_id
            and payload.get("asset_id") == visual_input.asset_id
            and payload.get("sha256") == visual_input.sha256
            and payload.get("processor") == {"name": PROCESSOR_NAME, "version": PROCESSOR_VERSION}
            and payload.get("configuration_fingerprint") == faces_fingerprint
            and payload.get("input_kind") == visual_input.kind
            and payload.get("input") == visual_input.provenance
            and payload.get("status") == "success"
            and isinstance(faces, list)
            and configuration_fingerprint(faces_config) == faces_fingerprint
            and read_reusable_result(
                workspace, target, faces_config, faces_fingerprint, visual_input
            )
            is not None
        ):
            continue
        location = target.relative_to(workspace.workspace).as_posix()
        for face in faces:
            if not isinstance(face, dict):
                continue
            face_id = face.get("face_id")
            embedding = face.get("embedding")
            if (
                not isinstance(face_id, str)
                or not isinstance(embedding, list)
                or len(embedding) != 256
            ):
                continue
            try:
                vector = np.asarray(embedding, dtype=np.float64)
            except (TypeError, ValueError):
                continue
            norm = float(np.linalg.norm(vector))
            if not np.isfinite(vector).all() or norm <= 0:
                continue
            normalized = tuple(float(value) for value in vector / norm)
            key = f"{visual_input.sha256}/{visual_input.kind}/{visual_input.input_id}/{face_id}"
            records.append(
                FaceRecord(
                    key,
                    visual_input.asset_id,
                    visual_input.sha256,
                    visual_input.kind,
                    visual_input.input_id,
                    face_id,
                    location,
                    visual_input.provenance,
                    normalized,
                )
            )
    return tuple(sorted(records, key=lambda value: value.key))


def _minimum_similarity(left: tuple[int, ...], right: tuple[int, ...], matrix) -> float:
    return min(float(matrix[a, b]) for a in left for b in right)


def complete_link_clusters(
    embeddings: list[list[float]] | tuple[tuple[float, ...], ...], threshold: float
) -> tuple[tuple[int, ...], ...]:
    if not embeddings:
        return ()
    values = np.asarray(embeddings, dtype=np.float64)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError("Clustering embeddings must be a finite matrix")
    norms = np.linalg.norm(values, axis=1)
    if np.any(norms <= 0):
        raise ValueError("Clustering embeddings must have non-zero norm")
    values = values / norms[:, None]
    similarities = values @ values.T
    clusters: list[tuple[int, ...]] = [(index,) for index in range(len(values))]
    while True:
        candidates: list[tuple[float, tuple[int, ...], tuple[int, ...], int, int]] = []
        for left_index, left in enumerate(clusters):
            for right_index in range(left_index + 1, len(clusters)):
                right = clusters[right_index]
                similarity = _minimum_similarity(left, right, similarities)
                if similarity >= threshold:
                    candidates.append(
                        (-similarity, left, right, left_index, right_index)
                    )
        if not candidates:
            break
        _, left, right, left_index, right_index = min(candidates)
        merged = tuple(sorted(left + right))
        clusters = [
            cluster
            for index, cluster in enumerate(clusters)
            if index not in {left_index, right_index}
        ]
        clusters.append(merged)
        clusters.sort()
    return tuple(sorted(clusters))


def _logical_fingerprint(workspace_id: str, faces_fingerprint: str, records) -> str:
    return canonical_sha256(
        {
            "workspace_id": workspace_id,
            "faces_configuration_fingerprint": faces_fingerprint,
            "faces": [
                {"key": record.key, "embedding": list(record.embedding)} for record in records
            ],
        }
    )


def _output_path(workspace, cluster_fingerprint: str, logical_fingerprint: str) -> Path:
    target = (
        workspace.workspace
        / "analysis"
        / PROCESSOR_NAME
        / CLUSTER_PROCESSOR_VERSION
        / cluster_fingerprint
        / f"{logical_fingerprint}.json"
    ).resolve(strict=False)
    if workspace.workspace.resolve(strict=False) not in target.parents:
        raise ValueError("Faces clustering output path escapes the workspace")
    return target


def _is_reusable(prepared: PreparedClustering) -> bool:
    try:
        payload = json.loads(prepared.output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("result_schema_version") == RESULT_SCHEMA_VERSION
        and payload.get("workspace_contract_version") == prepared.workspace.contract_version
        and payload.get("workspace_id") == prepared.workspace.workspace_id
        and payload.get("processor")
        == {"name": CLUSTER_PROCESSOR_NAME, "version": CLUSTER_PROCESSOR_VERSION}
        and payload.get("configuration") == prepared.config.as_dict()
        and payload.get("configuration_fingerprint") == prepared.configuration_fingerprint
        and payload.get("logical_input_fingerprint") == prepared.logical_input_fingerprint
        and payload.get("faces_configuration_fingerprint")
        == prepared.faces_configuration_fingerprint
        and payload.get("status") == "success"
        and isinstance(payload.get("result"), dict)
        and isinstance(payload["result"].get("clusters"), list)
    )


def prepare_clustering(
    workspace_path: Path,
    faces_fingerprint: str,
    config: ClusterConfig,
    *,
    keyframe_fingerprint: str | None = None,
    force: bool = False,
) -> PreparedClustering:
    config.validate()
    if not _SHA256.fullmatch(faces_fingerprint):
        raise ValueError("faces fingerprint must be 64 lowercase hexadecimal characters")
    workspace = load_workspace(workspace_path, keyframe_fingerprint)
    records = _load_face_records(workspace, faces_fingerprint)
    cluster_fingerprint = canonical_sha256(config.as_dict())
    logical_fingerprint = _logical_fingerprint(workspace.workspace_id, faces_fingerprint, records)
    target = _output_path(workspace, cluster_fingerprint, logical_fingerprint)
    provisional = PreparedClustering(
        workspace,
        faces_fingerprint,
        config,
        cluster_fingerprint,
        logical_fingerprint,
        records,
        target,
        "process",
    )
    action = "reuse" if not force and _is_reusable(provisional) else "process"
    return PreparedClustering(
        workspace,
        faces_fingerprint,
        config,
        cluster_fingerprint,
        logical_fingerprint,
        records,
        target,
        action,
    )


def execute_clustering(prepared: PreparedClustering, *, dry_run: bool) -> ClusterRunResult:
    if prepared.action == "reuse":
        payload = json.loads(prepared.output_path.read_text(encoding="utf-8"))
        clusters = payload["result"]["clusters"]
        return ClusterRunResult(
            prepared,
            len(clusters),
            sum(cluster["status"] == "uncertain" for cluster in clusters),
            reused=True,
            dry_run=dry_run,
        )
    groups = complete_link_clusters(
        tuple(record.embedding for record in prepared.records),
        prepared.config.similarity_threshold,
    )
    clusters: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        members = []
        for member_index in group:
            record = prepared.records[member_index]
            members.append(
                {
                    "asset_id": record.asset_id,
                    "sha256": record.sha256,
                    "input_kind": record.input_kind,
                    "input_id": record.input_id,
                    "face_id": record.face_id,
                    "faces_result_location": record.result_location,
                    "provenance": record.provenance,
                }
            )
        clusters.append(
            {
                "cluster_id": f"face-cluster-{index:04d}",
                "status": "uncertain" if len(group) == 1 else "core",
                "member_count": len(group),
                "members": members,
            }
        )
    if not dry_run:
        payload = {
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "workspace_contract_version": prepared.workspace.contract_version,
            "workspace_id": prepared.workspace.workspace_id,
            "processor": {
                "name": CLUSTER_PROCESSOR_NAME,
                "version": CLUSTER_PROCESSOR_VERSION,
            },
            "model": None,
            "configuration": prepared.config.as_dict(),
            "configuration_fingerprint": prepared.configuration_fingerprint,
            "logical_input_fingerprint": prepared.logical_input_fingerprint,
            "faces_configuration_fingerprint": prepared.faces_configuration_fingerprint,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "error": None,
            "result": {"face_count": len(prepared.records), "clusters": clusters},
        }
        write_json_atomic(prepared.output_path, payload)
    return ClusterRunResult(
        prepared,
        len(clusters),
        sum(cluster["status"] == "uncertain" for cluster in clusters),
        reused=False,
        dry_run=dry_run,
    )
