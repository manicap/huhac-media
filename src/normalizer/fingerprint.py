from __future__ import annotations

import hashlib
import json
from typing import Any

from normalizer.models import NormalizerConfig, WorkspaceInput


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def configuration_fingerprint(config: NormalizerConfig) -> str:
    if config.normalization_rules == "normalized-asset-n1":
        legacy_configuration = {
            key: value for key, value in config.as_dict().items()
            if not key.endswith("_fingerprint")
        }
        return canonical_sha256(
            {
                "processor": {"name": "normalizer", "version": "normalizer-v1"},
                "workspace_contract_version": 1,
                "configuration": legacy_configuration,
                "future_upstream_selection": {
                    "session_grouper": None, "video_keyframes": None,
                    "vision": None, "faces": None,
                },
            }
        )
    return canonical_sha256(
        {
            "processor": {"name": "normalizer", "version": "normalizer-v1"},
            "workspace_contract_version": 1,
            "configuration": config.as_dict(),
            "upstream_selection": config.upstream_selection(),
        }
    )


def input_set_fingerprint(workspace: WorkspaceInput) -> str:
    return canonical_sha256(
        {
            "workspace_id": workspace.workspace_id,
            "workspace_contract_version": workspace.contract_version,
            "manifest": workspace.manifest_semantic,
            "catalog_location": workspace.catalog_location,
            "catalog": workspace.catalog_semantic,
            "metadata": [
                {
                    "asset_id": asset.asset_id,
                    "location": asset.metadata_location,
                    "document": asset.metadata_semantic,
                    "issues": [
                        {"code": issue.code, "location": issue.location}
                        for issue in asset.issues
                    ],
                }
                for asset in workspace.assets
            ],
            "upstream": workspace.upstream_semantic,
        }
    )
