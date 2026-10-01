from __future__ import annotations

from datetime import datetime, timedelta

from session_grouper.models import (
    AssetObservation,
    GroupingConfig,
    GroupingResult,
    Session,
    TimestampConfidence,
    UnassignedAsset,
)


def operational_day(value: datetime, rollover_hour: int) -> str:
    return (value - timedelta(hours=rollover_hour)).date().isoformat()


def _sort_key(asset: AssetObservation) -> tuple[datetime, str]:
    assert asset.timestamp is not None
    return asset.timestamp.wall_time, asset.asset_id


def _distance_to_anchor(asset: AssetObservation, session: Session) -> timedelta:
    assert asset.timestamp is not None
    value = asset.timestamp.wall_time
    if value < session.anchor_start:
        return session.anchor_start - value
    if value > session.anchor_end:
        return value - session.anchor_end
    return timedelta(0)


def group_assets(
    observations: tuple[AssetObservation, ...] | list[AssetObservation],
    config: GroupingConfig,
) -> GroupingResult:
    config.validate()
    trusted: list[AssetObservation] = []
    fallback: list[AssetObservation] = []
    unassigned: list[UnassignedAsset] = []

    for asset in observations:
        if asset.availability != "available":
            unassigned.append(UnassignedAsset(asset, "asset_unavailable"))
        elif asset.timestamp is None:
            unassigned.append(
                UnassignedAsset(asset, asset.timestamp_issue or "missing_usable_timestamp")
            )
        elif asset.timestamp.confidence == TimestampConfidence.LOW:
            fallback.append(asset)
        else:
            trusted.append(asset)

    trusted.sort(key=_sort_key)
    sessions: list[Session] = []
    max_gap = timedelta(hours=config.max_gap_hours)
    for asset in trusted:
        assert asset.timestamp is not None
        value = asset.timestamp.wall_time
        day = operational_day(value, config.rollover_hour)
        boundary_reason = "first_trusted_asset"
        if sessions:
            current = sessions[-1]
            gap = value - current.anchor_end
            if day == current.operational_day and gap <= max_gap:
                current.assets.append(asset)
                current.anchor_end = value
                continue
            boundary_reason = (
                "operational_day_changed"
                if day != current.operational_day
                else "maximum_gap_exceeded"
            )
        sessions.append(
            Session(
                operational_day=day,
                boundary_reason=boundary_reason,
                anchor_start=value,
                anchor_end=value,
                assets=[asset],
            )
        )

    fallback.sort(key=_sort_key)
    if config.assign_filesystem_fallback:
        tolerance = timedelta(minutes=config.fallback_attach_minutes)
        for asset in fallback:
            candidates = [
                session
                for session in sessions
                if _distance_to_anchor(asset, session) <= tolerance
            ]
            if len(candidates) == 1:
                candidates[0].assets.append(asset)
            else:
                reason = (
                    "ambiguous_filesystem_fallback"
                    if len(candidates) > 1
                    else "filesystem_fallback_outside_session"
                )
                unassigned.append(UnassignedAsset(asset, reason))
    else:
        unassigned.extend(
            UnassignedAsset(asset, "filesystem_fallback_disabled") for asset in fallback
        )

    for session in sessions:
        session.assets.sort(key=_sort_key)
    unassigned.sort(key=lambda item: item.asset.asset_id)
    return GroupingResult(tuple(sessions), tuple(unassigned))
