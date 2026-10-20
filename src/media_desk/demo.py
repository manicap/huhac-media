from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def create_demo(output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Demo target is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    workspace_id = "media-desk-synthetic-demo"
    assets = []
    for index, (name, color) in enumerate(
        (("doors-open.jpg", "#d9ff43"), ("late-set.jpg", "#ff7657")), start=1
    ):
        image = Image.new("RGB", (960, 640), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((48, 48, 912, 592), outline="#0b0d0f", width=8)
        draw.text((84, 90), f"SYNTHETIC MEDIA {index}", fill="#0b0d0f")
        temporary = output / f".demo-{index}.jpg"
        image.save(temporary, "JPEG", quality=88)
        content = temporary.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        preview_location = f"previews/images/{sha256[:2]}/{sha256}.jpg"
        preview = output / preview_location
        preview.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(preview)
        metadata_location = f"metadata/assets/{sha256[:2]}/{sha256}.json"
        _write_json(
            output / metadata_location,
            {
                "schema_version": 1,
                "asset": {
                    "asset_id": f"sha256:{sha256}",
                    "sha256": sha256,
                    "size_bytes": len(content),
                    "media_type": "image",
                    "format": "JPEG",
                    "mime_type": "image/jpeg",
                },
                "capture": {
                    "datetime": f"2026-10-20T2{index}:00:00+02:00",
                    "source": "synthetic:demo",
                    "timezone_offset": "+02:00",
                    "filesystem_fallback": False,
                },
                "technical": {"width": 960, "height": 640},
                "raw_metadata": {},
                "stages": {},
            },
        )
        assets.append(
            {
                "asset_id": f"sha256:{sha256}",
                "sha256": sha256,
                "size_bytes": len(content),
                "media_type": "image",
                "format": "JPEG",
                "mime_type": "image/jpeg",
                "availability": "unavailable",
                "metadata_location": metadata_location,
                "preview_location": preview_location,
                "sources": [
                    {
                        "source_version_id": f"synthetic-{index}",
                        "relative_path": f"demo/{name}",
                        "status": "absent",
                    }
                ],
            }
        )
    now = datetime.now(timezone.utc).isoformat()
    _write_json(
        output / "metadata/catalog.json",
        {
            "workspace_contract_version": 1,
            "workspace_id": workspace_id,
            "generated_at": now,
            "generated_by_run_id": "synthetic-demo",
            "source_root": str((output / "offline-originals").resolve()),
            "assets": assets,
        },
    )
    _write_json(
        output / "workspace.json",
        {
            "asset_catalog": "metadata/catalog.json",
            "schema_version": 1,
            "workspace_contract_version": 1,
            "workspace_id": workspace_id,
        },
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic Media Desk demo workspace")
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        created = create_demo(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(created.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
