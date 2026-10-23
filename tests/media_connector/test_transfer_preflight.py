from __future__ import annotations

import json
from pathlib import Path

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.cli import main


def _selection(workspace_id: str, source: Path, media: Path, target: Path) -> None:
    adapter = LocalFilesystemAdapter(source)
    item = adapter.list_page(page_size=10, cursor=None).items[0]
    target.write_text(
        json.dumps(
            {
                "contract": "huhac.media-connector.transfer-selection",
                "contract_version": 1,
                "workspace_id": workspace_id,
                "source": {
                    "adapter_kind": "local",
                    "source_id": adapter.source_id,
                    "source_root": str(source),
                },
                "items": [
                    {
                        "object_id": item.object_id,
                        "version_token": item.version_token,
                        "logical_path": item.logical_path,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_preflight_is_read_only(workspace: Path, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    storage = tmp_path / "storage"
    state = tmp_path / "state"
    work = tmp_path / "work"
    for root in (source, storage, state, work):
        root.mkdir()
    (source / "photo.jpg").write_bytes(b"\xff\xd8\xffpayload")
    selection = tmp_path / "selection.json"
    _selection("12345678-1234-5678-1234-567812345678", source, source / "photo.jpg", selection)
    before = {path: tuple(path.iterdir()) for path in (storage, state, work)}

    result = main(
        [
            "transfer", "preflight", "--workspace", str(workspace),
            "--media-storage", str(storage), "--state-root", str(state),
            "--transfer-work-root", str(work), "--selection", str(selection),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract"] == "huhac.media-connector.transfer"
    assert payload["preflight"]["writes_performed"] is False
    assert {path: tuple(path.iterdir()) for path in (storage, state, work)} == before


def test_preflight_rejects_overlapping_roots(workspace: Path, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    storage = tmp_path / "storage"
    state = tmp_path / "state"
    for root in (source, storage, state):
        root.mkdir()
    work = storage / "work"
    work.mkdir()
    media = source / "photo.jpg"
    media.write_bytes(b"\xff\xd8\xffpayload")
    selection = tmp_path / "selection.json"
    _selection("12345678-1234-5678-1234-567812345678", source, media, selection)

    result = main(
        [
            "transfer", "preflight", "--workspace", str(workspace),
            "--media-storage", str(storage), "--state-root", str(state),
            "--transfer-work-root", str(work), "--selection", str(selection),
        ]
    )
    assert result == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "ROOT_OVERLAP"

