from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MonitoringEvent, MonitoringZone, ZoneOccupancySample


def get(db: Session, zone_id: uuid.UUID) -> MonitoringZone | None:
    return db.get(MonitoringZone, zone_id)


def for_video(db: Session, video_id: uuid.UUID, *, enabled_only: bool = False) -> Sequence[MonitoringZone]:
    stmt = select(MonitoringZone).where(MonitoringZone.video_id == video_id)
    if enabled_only:
        stmt = stmt.where(MonitoringZone.enabled.is_(True))
    return db.scalars(stmt.order_by(MonitoringZone.created_at)).all()


def name_taken(
    db: Session, video_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(MonitoringZone.id).where(
        MonitoringZone.video_id == video_id, func.lower(MonitoringZone.name) == name.lower()
    )
    if exclude_id:
        stmt = stmt.where(MonitoringZone.id != exclude_id)
    return db.scalar(stmt) is not None


def event_counts(db: Session, zone_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    if not zone_ids:
        return {}
    rows = db.execute(
        select(MonitoringEvent.zone_id, MonitoringEvent.event_type, func.count())
        .where(MonitoringEvent.zone_id.in_(zone_ids))
        .group_by(MonitoringEvent.zone_id, MonitoringEvent.event_type)
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for zone_id, etype, n in rows:
        out.setdefault(zone_id, {})[etype] = n
    return out


def peak_occupancy(db: Session, zone_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not zone_ids:
        return {}
    rows = db.execute(
        select(ZoneOccupancySample.zone_id, func.max(ZoneOccupancySample.occupancy))
        .where(ZoneOccupancySample.zone_id.in_(zone_ids))
        .group_by(ZoneOccupancySample.zone_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def occupancy_series(db: Session, zone_id: uuid.UUID) -> Sequence[ZoneOccupancySample]:
    return db.scalars(
        select(ZoneOccupancySample)
        .where(ZoneOccupancySample.zone_id == zone_id)
        .order_by(ZoneOccupancySample.timestamp)
    ).all()
