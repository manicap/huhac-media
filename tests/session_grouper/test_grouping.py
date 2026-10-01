from datetime import datetime

from session_grouper.grouping import group_assets
from session_grouper.models import (
    AssetObservation,
    GroupingConfig,
    TimestampConfidence,
    TimestampEvidence,
)
from session_grouper.output import configuration_fingerprint


def asset(
    name: str,
    timestamp: str | None,
    *,
    media_type: str = "image",
    confidence: TimestampConfidence = TimestampConfidence.STRONG,
    availability: str = "available",
) -> AssetObservation:
    evidence = None
    if timestamp is not None:
        evidence = TimestampEvidence(
            value=timestamp,
            wall_time=datetime.fromisoformat(timestamp).replace(tzinfo=None),
            source=(
                "filesystem:mtime"
                if confidence == TimestampConfidence.LOW
                else "EXIF:DateTimeOriginal"
            ),
            timezone_offset=None,
            filesystem_fallback=confidence == TimestampConfidence.LOW,
            confidence=confidence,
        )
    return AssetObservation(
        asset_id=f"sha256:{name}",
        sha256=name,
        media_type=media_type,
        availability=availability,
        metadata_location=f"metadata/{name}.json",
        timestamp=evidence,
        timestamp_issue="missing_capture_timestamp" if evidence is None else None,
    )


def test_evening_crosses_midnight_but_next_evening_starts_new_session() -> None:
    observations = [
        asset("a", "2026-09-26T19:30:00"),
        asset("b", "2026-09-26T23:58:00", media_type="video"),
        asset("c", "2026-09-27T00:31:00"),
        asset("d", "2026-09-27T01:24:00"),
        asset("e", "2026-09-27T19:00:00"),
    ]

    result = group_assets(observations, GroupingConfig())

    assert [[item.asset_id for item in session.assets] for session in result.sessions] == [
        ["sha256:a", "sha256:b", "sha256:c", "sha256:d"],
        ["sha256:e"],
    ]
    assert {item.media_type for item in result.sessions[0].assets} == {"image", "video"}
    assert result.sessions[0].operational_day == "2026-09-26"
    assert result.sessions[1].boundary_reason == "operational_day_changed"


def test_large_gap_same_evening_is_kept_but_excessive_gap_is_split() -> None:
    kept = group_assets(
        [asset("a", "2026-09-26T18:00:00"), asset("b", "2026-09-26T23:00:00")],
        GroupingConfig(),
    )
    split = group_assets(
        [asset("a", "2026-09-26T07:00:00"), asset("b", "2026-09-26T16:00:01")],
        GroupingConfig(),
    )

    assert len(kept.sessions) == 1
    assert len(split.sessions) == 2
    assert split.sessions[1].boundary_reason == "maximum_gap_exceeded"


def test_filesystem_fallback_is_unassigned_unless_uniquely_near_session() -> None:
    observations = [
        asset("anchor", "2026-09-26T20:00:00"),
        asset("fallback", "2026-09-26T20:20:00", confidence=TimestampConfidence.LOW),
        asset("missing", None),
    ]

    conservative = group_assets(observations, GroupingConfig())
    attached = group_assets(
        observations,
        GroupingConfig(assign_filesystem_fallback=True, fallback_attach_minutes=30),
    )

    assert {item.reason for item in conservative.unassigned} == {
        "filesystem_fallback_disabled",
        "missing_capture_timestamp",
    }
    assert [item.asset_id for item in attached.sessions[0].assets] == [
        "sha256:anchor",
        "sha256:fallback",
    ]
    assert [item.asset.asset_id for item in attached.unassigned] == ["sha256:missing"]


def test_ordering_and_configuration_fingerprint_are_deterministic() -> None:
    observations = [
        asset("b", "2026-09-26T20:00:00", confidence=TimestampConfidence.MEDIUM),
        asset("a", "2026-09-26T20:00:00"),
    ]
    first = group_assets(observations, GroupingConfig())
    second = group_assets(list(reversed(observations)), GroupingConfig())

    assert [item.asset_id for item in first.sessions[0].assets] == [
        "sha256:a",
        "sha256:b",
    ]
    assert [item.asset_id for item in second.sessions[0].assets] == [
        "sha256:a",
        "sha256:b",
    ]
    assert configuration_fingerprint(GroupingConfig()) == configuration_fingerprint(
        GroupingConfig()
    )
    assert configuration_fingerprint(GroupingConfig()) != configuration_fingerprint(
        GroupingConfig(max_gap_hours=7)
    )


def test_unavailable_asset_is_explicitly_unassigned() -> None:
    result = group_assets(
        [asset("gone", "2026-09-26T20:00:00", availability="unavailable")],
        GroupingConfig(),
    )

    assert not result.sessions
    assert result.unassigned[0].reason == "asset_unavailable"
