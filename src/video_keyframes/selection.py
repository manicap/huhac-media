from __future__ import annotations

from typing import Any

from video_keyframes.models import CoverageSelection


def l2_normalize(rows: Any) -> Any:
    import numpy as np

    values = np.asarray(rows, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError("embeddings must be a non-empty two-dimensional array")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if not np.all(np.isfinite(norms)) or np.any(norms == 0):
        raise ValueError("embeddings must contain finite non-zero vectors")
    return values / norms


def select_keyframes(
    embeddings: Any, coverage_similarity: float
) -> tuple[CoverageSelection, ...]:
    import numpy as np

    normalized = l2_normalize(embeddings)
    similarity = normalized @ normalized.T
    uncovered = set(range(normalized.shape[0]))
    groups: list[tuple[int, tuple[int, ...]]] = []

    while uncovered:
        candidate = max(
            range(normalized.shape[0]),
            key=lambda index: (
                sum(similarity[index, member] >= coverage_similarity for member in uncovered),
                -index,
            ),
        )
        members = tuple(
            member
            for member in sorted(uncovered)
            if similarity[candidate, member] >= coverage_similarity
        )
        if not members:
            raise ValueError("coverage threshold failed to cover the candidate itself")
        groups.append((candidate, members))
        uncovered.difference_update(members)

    selections: list[CoverageSelection] = []
    for candidate, members in groups:
        centroid = normalized[list(members)].mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if not np.isfinite(norm) or norm == 0:
            representative = members[0]
        else:
            centroid /= norm
            scores = normalized[list(members)] @ centroid
            representative = max(
                members,
                key=lambda member: (float(scores[members.index(member)]), -member),
            )
        selections.append(CoverageSelection(candidate, representative, members))
    return tuple(selections)
