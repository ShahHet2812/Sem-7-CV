from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Detection,
    MonitoringEvent,
    ProcessingJob,
    TrackSummary,
    ZoneOccupancySample,
)
from app.models.enums import EventType, JobStatus, VideoStatus


def get(db: Session, job_id: uuid.UUID) -> ProcessingJob | None:
    return db.get(ProcessingJob, job_id)


def list_jobs(
    db: Session,
    *,
    video_id: uuid.UUID | None,
    status: str | None,
    offset: int,
    limit: int,
) -> tuple[Sequence[ProcessingJob], int]:
    stmt = select(ProcessingJob)
    if video_id:
        stmt = stmt.where(ProcessingJob.video_id == video_id)
    if status:
        stmt = stmt.where(ProcessingJob.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit)
    return db.scalars(stmt).all(), total


def active_for_video(db: Session, video_id: uuid.UUID) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.video_id == video_id, ProcessingJob.status.in_(JobStatus.active())
        )
    )


def current_for_video(db: Session, video_id: uuid.UUID) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.video_id == video_id, ProcessingJob.is_current.is_(True)
        )
    )


def claim_next_queued(db: Session) -> ProcessingJob | None:
    """Atomically pick the oldest queued job (SKIP LOCKED on PostgreSQL)."""
    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.status == JobStatus.QUEUED)
        .order_by(ProcessingJob.created_at)
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    return db.scalar(stmt)


def purge_results(db: Session, job_id: uuid.UUID) -> None:
    """Delete derived results of a job (detections, tracks, zone events, occupancy).

    Processing-failure events are kept: they document the job's history.
    """
    db.execute(delete(Detection).where(Detection.job_id == job_id))
    db.execute(delete(TrackSummary).where(TrackSummary.job_id == job_id))
    db.execute(delete(ZoneOccupancySample).where(ZoneOccupancySample.job_id == job_id))
    db.execute(
        delete(MonitoringEvent).where(
            MonitoringEvent.job_id == job_id,
            MonitoringEvent.event_type.in_(EventType.zone_types()),
        )
    )


def mark_stale_processing_failed(db: Session) -> int:
    """Jobs left 'processing' by a crashed/restarted server cannot resume."""
    stale = db.scalars(
        select(ProcessingJob).where(ProcessingJob.status == JobStatus.PROCESSING)
    ).all()
    for job in stale:
        purge_results(db, job.id)
        job.status = JobStatus.FAILED
        job.error_message = "Processing was interrupted by a server restart. Retry the job."
        job.video.status = VideoStatus.FAILED
    return len(stale)
