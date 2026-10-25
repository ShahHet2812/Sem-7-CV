from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MonitoringEvent, MonitoringZone, ProcessingJob, Video
from app.repositories.filters import like_pattern

SORTABLE = {
    "created_at": Video.created_at,
    "original_filename": Video.original_filename,
    "file_size": Video.file_size,
    "duration_seconds": Video.duration_seconds,
    "status": Video.status,
}


def get(db: Session, video_id: uuid.UUID) -> Video | None:
    return db.get(Video, video_id)


def list_videos(
    db: Session,
    *,
    q: str | None,
    status: str | None,
    sort: str,
    order: str,
    offset: int,
    limit: int,
) -> tuple[Sequence[Video], int]:
    stmt = select(Video)
    if q:
        stmt = stmt.where(Video.original_filename.ilike(like_pattern(q), escape="\\"))
    if status:
        stmt = stmt.where(Video.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTABLE.get(sort, Video.created_at)
    stmt = stmt.order_by(col.desc() if order == "desc" else col.asc(), Video.id)
    return db.scalars(stmt.offset(offset).limit(limit)).all(), total


def latest_jobs(db: Session, video_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, ProcessingJob]:
    if not video_ids:
        return {}
    rows = db.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.video_id.in_(video_ids))
        .order_by(ProcessingJob.created_at.desc())
    ).all()
    out: dict[uuid.UUID, ProcessingJob] = {}
    for job in rows:
        out.setdefault(job.video_id, job)
    return out


def current_jobs(db: Session, video_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, ProcessingJob]:
    if not video_ids:
        return {}
    rows = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.video_id.in_(video_ids), ProcessingJob.is_current.is_(True)
        )
    ).all()
    return {j.video_id: j for j in rows}


def zone_counts(db: Session, video_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not video_ids:
        return {}
    rows = db.execute(
        select(MonitoringZone.video_id, func.count())
        .where(MonitoringZone.video_id.in_(video_ids))
        .group_by(MonitoringZone.video_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def event_counts(db: Session, video_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not video_ids:
        return {}
    rows = db.execute(
        select(MonitoringEvent.video_id, func.count())
        .where(MonitoringEvent.video_id.in_(video_ids))
        .group_by(MonitoringEvent.video_id)
    ).all()
    return {r[0]: r[1] for r in rows}
