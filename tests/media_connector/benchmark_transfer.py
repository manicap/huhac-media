from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from media_connector.adapters.local import LocalFilesystemAdapter
from media_connector.transfer_service import transfer_run


WORKSPACE_ID = "12345678-1234-5678-1234-567812345678"


def _selection(source: Path, target: Path) -> None:
    adapter = LocalFilesystemAdapter(source)
    item = adapter.list_page(page_size=10, cursor=None).items[0]
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
                ],
            }
        ),
        encoding="utf-8",
    )


def run(size_mib: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix="connector-benchmark-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        storage = root / "storage"
        state = root / "state"
        work = root / "work"
        source = root / "source"
        second_source = root / "source-duplicate"
        for path in (workspace, storage, state, work, source, second_source):
            path.mkdir()
        (workspace / "workspace.json").write_text(
            json.dumps({"workspace_contract_version": 1, "workspace_id": WORKSPACE_ID}),
            encoding="utf-8",
        )
        payload = source / "benchmark.jpg"
        with payload.open("wb") as stream:
            stream.write(b"\xff\xd8\xff")
            block = b"x" * (1024 * 1024)
            remaining = size_mib * 1024 * 1024 - 3
            while remaining:
                chunk = block[:remaining]
                stream.write(chunk)
                remaining -= len(chunk)
        duplicate = second_source / "different-name.jpeg"
        duplicate.write_bytes(payload.read_bytes())
        first_selection = root / "first.json"
        second_selection = root / "second.json"
        _selection(source, first_selection)
        _selection(second_source, second_selection)

        started = time.perf_counter()
        transfer_run(
            workspace=workspace, media_storage=storage, state_root=state, work_root=work,
            selection_path=first_selection, operation_id=str(uuid4()),
        )
        publish_seconds = time.perf_counter() - started
        started = time.perf_counter()
        transfer_run(
            workspace=workspace, media_storage=storage, state_root=state, work_root=work,
            selection_path=second_selection, operation_id=str(uuid4()),
        )
        dedup_seconds = time.perf_counter() - started
        return {
            "size_mib": size_mib,
            "publish_seconds": round(publish_seconds, 6),
            "publish_mib_per_second": round(size_mib / publish_seconds, 2),
            "dedup_seconds": round(dedup_seconds, 6),
            "dedup_mib_per_second": round(size_mib / dedup_seconds, 2),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mib", type=int, default=32)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.size_mib), sort_keys=True))


if __name__ == "__main__":
    main()
