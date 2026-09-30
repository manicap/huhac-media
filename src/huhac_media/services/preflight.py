from __future__ import annotations

from collections import Counter
from pathlib import Path

from huhac_media.domain.enums import MediaType, PlanKind
from huhac_media.domain.models import IngestPlan


def _size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def render_preflight(
    input_path: Path,
    work_path: Path,
    plan: IngestPlan,
    *,
    exists: bool,
    show_workspace_status: bool = True,
) -> str:
    images = [item for item in plan.items if item.scanned.media_type == MediaType.IMAGE]
    videos = [item for item in plan.items if item.scanned.media_type == MediaType.VIDEO]
    formats = Counter(item.scanned.format or "UNKNOWN" for item in plan.items)
    total_size = sum(item.scanned.size_bytes for item in plan.items + plan.unsupported)
    lines = [
        "HUHÁČ MEDIA INGEST",
        "",
        f"INPUT: {input_path}",
        f"WORK:  {work_path}",
        "",
        "Found:",
        f"  Images ................. {len(images)}",
        f"  Videos ................. {len(videos)}",
        f"  Unsupported ............ {len(plan.unsupported)}",
        f"  Total size ............. {_size(total_size)}",
        "",
        "Formats:",
    ]
    if show_workspace_status:
        lines.insert(4, f"WORKSPACE: {'existing (will be reused)' if exists else 'new'}")
    lines.extend(f"  {name:<22} {count}" for name, count in sorted(formats.items()))
    lines.extend(
        [
            "",
            "Plan:",
            f"  Already known .......... {plan.count(PlanKind.KNOWN)}",
            f"  New .................... {plan.count(PlanKind.NEW)}",
            f"  Changed ................ {plan.count(PlanKind.CHANGED)}",
            f"  Exact duplicates ....... {plan.duplicate_count}",
            f"  Previous failures ...... {plan.previous_failure_count}",
            "",
            "Original files will not be modified.",
        ]
    )
    return "\n".join(lines)
