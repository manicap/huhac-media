from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from huhac_media.domain.enums import MediaType
from huhac_media.services.scanner import Scanner
from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.transfer_service import transfer_run


pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("content", "expected_type", "expected_format", "expected_suffix"),
    [
        (b"\xff\xd8\xff" + b"connector-ingest" * 100, MediaType.IMAGE, "JPEG", "jpg"),
        (
            bytes(bytearray([0x47]) + bytearray(187) + bytearray([0x47]) + bytearray(187) + bytearray([0x47]) + bytearray(223)),
            MediaType.VIDEO,
            "MTS",
            "mts",
        ),
    ],
)
def test_published_cas_payload_is_discovered_by_unchanged_ingest_scanner(
    tmp_path: Path, content: bytes, expected_type: MediaType, expected_format: str, expected_suffix: str
) -> None:
    workspace = tmp_path / "workspace"
    source = tmp_path / "source"
    storage = tmp_path / "storage"
    state = tmp_path / "state"
    work = tmp_path / "work"
    for root in (workspace, source, storage, state, work):
        root.mkdir()
    (workspace / "workspace.json").write_text(
        json.dumps(
            {
                "workspace_contract_version": 1,
                "workspace_id": "12345678-1234-5678-1234-567812345678",
            }
        ),
        encoding="utf-8",
    )
    (source / "misleading.png").write_bytes(content)
    adapter = LocalFilesystemAdapter(source)
    item = adapter.list_page(page_size=10, cursor=None).items[0]
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "contract": "huhac.media-connector.transfer-selection",
                "contract_version": 1,
                "workspace_id": "12345678-1234-5678-1234-567812345678",
                "source": {"adapter_kind": "local", "source_id": adapter.source_id, "source_root": str(source)},
                "items": [{"object_id": item.object_id, "version_token": item.version_token, "logical_path": item.logical_path}],
            }
        ),
        encoding="utf-8",
    )
    result = transfer_run(
        workspace=workspace, media_storage=storage, state_root=state, work_root=work,
        selection_path=selection, operation_id=str(uuid4()),
    )

    scanned = Scanner().scan(storage)
    assert len(scanned) == 1
    assert scanned[0].media_type == expected_type
    assert scanned[0].format == expected_format
    assert scanned[0].sha256 == hashlib.sha256(content).hexdigest()
    assert scanned[0].relative_path.as_posix() == result["run"]["items"][0]["relative_path"]
    assert scanned[0].absolute_path.suffix == f".{expected_suffix}"
