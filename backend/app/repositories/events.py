from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import MonitoringEvent, MonitoringZone, Video
from app.repositories.filters import like_pattern


@dataclass
class EventFilters:
    q: str | None = None
    video_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    event_types: Sequence[str] | None = None
    class_name: str | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    track_id: int | None = None


SORTABLE = {
    "occurred_at": MonitoringEvent.occurred_at,
    "video_timestamp": MonitoringEvent.video_timestamp,
    "event_type": MonitoringEvent.event_type,
    "class_name": MonitoringEvent.class_name,
    "confidence": MonitoringEvent.confidence,
}


def apply_filters(stmt: Select, f: EventFilters) -> Select:
    if f.video_id:
        stmt = stmt.where(MonitoringEvent.video_id == f.video_id)
    if f.zone_id:
        stmt = stmt.where(MonitoringEvent.zone_id == f.zone_id)
    if f.event_types:
        stmt = stmt.where(MonitoringEvent.event_type.in_(list(f.event_types)))
    if f.class_name:
        stmt = stmt.where(MonitoringEvent.class_name == f.class_name)
    if f.status:
        stmt = stmt.where(MonitoringEvent.status == f.status)
    if f.date_from:
        stmt = stmt.where(MonitoringEvent.occurred_at >= f.date_from)
    if f.date_to:
        stmt = stmt.where(MonitoringEvent.occurred_at <= f.date_to)
    if f.track_id is not None:
        stmt = stmt.where(MonitoringEvent.track_id == f.track_id)
    if f.q:
        pat = like_pattern(f.q)
        stmt = (
            stmt.join(Video, Video.id == MonitoringEvent.video_id)
            .outerjoin(MonitoringZone, MonitoringZone.id == MonitoringEvent.zone_id)
            .where(
                or_(
                    Video.original_filename.ilike(pat, escape="\\"),
                    MonitoringZone.name.ilike(pat, escape="\\"),
                    MonitoringEvent.class_name.ilike(pat, escape="\\"),
                    MonitoringEvent.event_type.ilike(pat, escape="\\"),
                    MonitoringEvent.notes.ilike(pat, escape="\\"),
                )
            )
        )
    return stmt


def get(db: Session, event_id: uuid.UUID) -> MonitoringEvent | None:
    return db.scalar(
        select(MonitoringEvent)
        .options(joinedload(MonitoringEvent.video), joinedload(MonitoringEvent.zone))
        .where(MonitoringEvent.id == event_id)
    )


def count(db: Session, f: EventFilters) -> int:
    stmt = apply_filters(select(MonitoringEvent.id), f)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def query(
    db: Session,
    f: EventFilters,
    *,
    sort: str = "occurred_at",
    order: str = "desc",
    offset: int = 0,
    limit: int | None = 50,
) -> Sequence[MonitoringEvent]:
    col = SORTABLE.get(sort, MonitoringEvent.occurred_at)
    stmt = apply_filters(
        select(MonitoringEvent).options(
            joinedload(MonitoringEvent.video), joinedload(MonitoringEvent.zone)
        ),
        f,
    )
    stmt = stmt.order_by(
        col.desc().nulls_last() if order == "desc" else col.asc().nulls_last(),
        MonitoringEvent.id,
    ).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return db.scalars(stmt).unique().all()
