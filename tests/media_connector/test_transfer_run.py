from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.cli import main
from media_connector.transfer_service import transfer_run


WORKSPACE_ID = "12345678-1234-5678-1234-567812345678"


def write_selection(source: Path, target: Path) -> None:
    adapter = LocalFilesystemAdapter(source)
    page = adapter.list_page(page_size=100, cursor=None)
    target.write_text(
        json.dumps(
            {
                "contract": "huhac.media-connector.transfer-selection",
                "contract_version": 1,
                "workspace_id": WORKSPACE_ID,
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
                    for item in page.items
                ],
            }
        ),
        encoding="utf-8",
    )


def run_args(workspace: Path, storage: Path, state: Path, work: Path, selection: Path) -> list[str]:
    return [
        "transfer", "run", "--workspace", str(workspace),
        "--media-storage", str(storage), "--state-root", str(state),
        "--transfer-work-root", str(work), "--selection", str(selection),
        "--operation-id", str(uuid4()), "--yes",
    ]


def roots(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    storage = tmp_path / "storage"
    state = tmp_path / "state"
    work = tmp_path / "work"
    for root in (source, storage, state, work):
        root.mkdir()
    return source, storage, state, work


def test_transfer_publishes_one_object_and_preserves_source(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    media = source / "original.jpeg"
    media.write_bytes(b"\xff\xd8\xff" + b"payload" * 100)
    before = (media.read_bytes(), media.stat().st_mtime_ns)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)

    assert main(run_args(workspace, storage, state, work, selection)) == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["run"]["items"][0]
    expected_hash = hashlib.sha256(before[0]).hexdigest()
    assert item["status"] == "published"
    assert item["content_sha256"] == expected_hash
    published = storage / item["relative_path"]
    assert published.name == "payload.jpg"
    assert published.read_bytes() == before[0]
    assert (media.read_bytes(), media.stat().st_mtime_ns) == before
    manifest_path = Path(payload["run"]["manifest"])
    assert manifest_path.exists()
    manifest = manifest_path.read_text(encoding="utf-8")
    assert str(source) not in manifest


def test_same_content_with_different_names_has_one_physical_object(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    content = b"\xff\xd8\xff" + b"same" * 100
    (source / "one.jpeg").write_bytes(content)
    (source / "two.png").write_bytes(content)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)

    assert main(run_args(workspace, storage, state, work, selection)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["status"] for item in payload["run"]["items"]] == [
        "published", "deduplicated_existing"
    ]
    assert len(list((storage / "objects" / "sha256").rglob("payload.*"))) == 1
    assert all(item["relative_path"].endswith("payload.jpg") for item in payload["run"]["items"])


def test_changed_source_is_not_published(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    media = source / "photo.jpg"
    media.write_bytes(b"\xff\xd8\xfffirst")
    selection = tmp_path / "selection.json"
    write_selection(source, selection)
    media.write_bytes(b"\xff\xd8\xffchanged-and-larger")

    assert main(run_args(workspace, storage, state, work, selection)) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "SOURCE_CHANGED"
    assert not (storage / "objects").exists()


def test_corrupt_existing_object_is_never_overwritten(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    media = source / "photo.jpg"
    content = b"\xff\xd8\xff" + b"payload" * 100
    media.write_bytes(content)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)
    assert main(run_args(workspace, storage, state, work, selection)) == 0
    first = json.loads(capsys.readouterr().out)
    published = storage / first["run"]["items"][0]["relative_path"]
    corruption = b"x" * len(content)
    published.write_bytes(corruption)

    assert main(run_args(workspace, storage, state, work, selection)) == 4
    second = json.loads(capsys.readouterr().out)
    assert second["error"]["code"] == "CONTENT_OBJECT_CORRUPT_OR_COLLISION"
    assert published.read_bytes() == corruption


def test_recovery_adopts_verified_publish_without_source(
    workspace: Path, tmp_path: Path, capsys
) -> None:
    source, storage, state, work = roots(tmp_path)
    content = b"\xff\xd8\xff" + b"recover" * 100
    (source / "photo.jpg").write_bytes(content)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)
    operation_id = str(uuid4())

    with pytest.raises(SystemExit, match="simulated crash"):
        transfer_run(
            workspace=workspace,
            media_storage=storage,
            state_root=state,
            work_root=work,
            selection_path=selection,
            operation_id=operation_id,
            fault_after_publish=True,
        )
    source.rename(tmp_path / "source-offline")

    result = main(
        [
            "transfer", "recover", "--workspace", str(workspace),
            "--media-storage", str(storage), "--state-root", str(state),
            "--transfer-work-root", str(work),
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["recovered_items"] == [
        {"item_id": "000001", "run_id": operation_id, "status": "recovered_published"}
    ]
    published = list((storage / "objects" / "sha256").rglob("payload.jpg"))
    assert len(published) == 1
    assert published[0].read_bytes() == content


def test_recovery_refuses_corrupt_published_evidence(
    workspace: Path, tmp_path: Path, capsys
) -> None:
    source, storage, state, work = roots(tmp_path)
    content = b"\xff\xd8\xff" + b"recover" * 100
    (source / "photo.jpg").write_bytes(content)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)
    with pytest.raises(SystemExit):
        transfer_run(
            workspace=workspace, media_storage=storage, state_root=state,
            work_root=work, selection_path=selection, operation_id=str(uuid4()),
            fault_after_publish=True,
        )
    published = next((storage / "objects" / "sha256").rglob("payload.jpg"))
    corrupted = b"z" * len(content)
    published.write_bytes(corrupted)

    result = main(
        [
            "transfer", "recover", "--workspace", str(workspace),
            "--media-storage", str(storage), "--state-root", str(state),
            "--transfer-work-root", str(work),
        ]
    )
    assert result == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "CONTENT_OBJECT_CORRUPT_OR_COLLISION"
    assert published.read_bytes() == corrupted


def test_recovery_publishes_verified_stage_without_source(
    workspace: Path, tmp_path: Path, capsys
) -> None:
    source, storage, state, work = roots(tmp_path)
    content = b"\xff\xd8\xff" + b"verified-stage" * 100
    (source / "photo.jpg").write_bytes(content)
    selection = tmp_path / "selection.json"
    write_selection(source, selection)
    operation_id = str(uuid4())
    with pytest.raises(SystemExit, match="staged verification"):
        transfer_run(
            workspace=workspace, media_storage=storage, state_root=state,
            work_root=work, selection_path=selection, operation_id=operation_id,
            fault_after_verify=True,
        )
    source.rename(tmp_path / "source-offline")

    assert main(
        [
            "transfer", "recover", "--workspace", str(workspace),
            "--media-storage", str(storage), "--state-root", str(state),
            "--transfer-work-root", str(work),
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["recovered_items"][0]["status"] == "recovered_published"
    published = next((storage / "objects" / "sha256").rglob("payload.jpg"))
    assert published.read_bytes() == content


def test_unknown_target_layout_fails_without_overwrite(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    content = b"\xff\xd8\xff" + b"collision" * 100
    (source / "photo.jpg").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    target = storage / "objects" / "sha256" / digest[:2] / digest
    target.mkdir(parents=True)
    evidence = target / "unknown.bin"
    evidence.write_bytes(b"do-not-touch")
    selection = tmp_path / "selection.json"
    write_selection(source, selection)

    assert main(run_args(workspace, storage, state, work, selection)) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "CONTENT_OBJECT_CORRUPT_OR_COLLISION"
    assert evidence.read_bytes() == b"do-not-touch"


def test_unsupported_content_is_not_published(workspace: Path, tmp_path: Path, capsys) -> None:
    source, storage, state, work = roots(tmp_path)
    media = source / "claimed.jpg"
    media.write_bytes(b"plain text masquerading as media")
    before = media.read_bytes()
    selection = tmp_path / "selection.json"
    write_selection(source, selection)

    assert main(run_args(workspace, storage, state, work, selection)) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "FORMAT_NOT_INGEST_COMPATIBLE"
    assert media.read_bytes() == before
    assert not (storage / "objects").exists()
