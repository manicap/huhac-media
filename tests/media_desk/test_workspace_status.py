from __future__ import annotations

from pathlib import Path

from media_desk.workspace_status import validate_workspace


def test_unset_and_unavailable_workspace_have_distinct_states(tmp_path: Path) -> None:
    unset = validate_workspace(None)
    unavailable = validate_workspace(tmp_path / "missing")

    assert unset.state == "unset"
    assert unset.label == "Nenastaveno"
    assert unavailable.state == "unavailable"
    assert unavailable.label == "Nedostupné"


def test_validator_uses_contract_and_accepts_offline_originals(workspace_builder) -> None:
    workspace_builder.add_asset(1, original=False)
    root = workspace_builder.publish()

    result = validate_workspace(root)

    assert result.state == "connected"
    assert result.valid is True
    assert result.snapshot is not None
    assert result.snapshot.assets[0].original_online is False


def test_invalid_contract_is_not_reported_as_unavailable(workspace_builder) -> None:
    root = workspace_builder.publish(version=9)

    result = validate_workspace(root)

    assert result.state == "invalid"
    assert result.label == "Neplatné"
    assert "verzi 1" in result.message
