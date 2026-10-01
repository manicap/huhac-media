import math

import numpy as np

from video_keyframes.selection import l2_normalize, select_keyframes


def test_embeddings_are_l2_normalized() -> None:
    normalized = l2_normalize(np.array([[3.0, 4.0], [0.0, 2.0]]))

    assert np.allclose(np.linalg.norm(normalized, axis=1), [1.0, 1.0])


def test_greedy_coverage_uses_deterministic_tie_break_and_centroid_representative() -> None:
    angle = math.radians(20)
    embeddings = np.array(
        [
            [math.cos(-angle), math.sin(-angle)],
            [1.0, 0.0],
            [math.cos(angle), math.sin(angle)],
        ]
    )

    selections = select_keyframes(embeddings, 0.75)

    assert len(selections) == 1
    assert selections[0].coverage_candidate_index == 0
    assert selections[0].member_indices == (0, 1, 2)
    assert selections[0].representative_index == 1


def test_coverage_is_repeatable_and_never_crosses_input_array() -> None:
    embeddings = np.array([[1.0, 0.0], [0.99, 0.01], [-1.0, 0.0]])

    first = select_keyframes(embeddings, 0.85)
    second = select_keyframes(embeddings.copy(), 0.85)

    assert first == second
    assert [selection.member_indices for selection in first] == [(0, 1), (2,)]
