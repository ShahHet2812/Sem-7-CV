from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import ProcessingJob
from app.models.enums import JobStatus, VideoStatus
from app.repositories import jobs as repo
from app.schemas.common import Page, PageParams
from app.schemas.job import JobOut
from app.services.serializers import job_out
from app.workers.job_worker import JobQueue


def require_job(db: Session, job_id: uuid.UUID) -> ProcessingJob:
    job = repo.get(db, job_id)
    if job is None:
        raise NotFoundError("Processing job not found.")
    return job


def list_jobs(
    db: Session, *, video_id: uuid.UUID | None, status: str | None, page: PageParams
) -> Page[JobOut]:
    jobs, total = repo.list_jobs(
        db, video_id=video_id, status=status, offset=page.offset, limit=page.page_size
    )
    return Page[JobOut].build([job_out(j) for j in jobs], total, page.page, page.page_size)


def retry(db: Session, queue: JobQueue, job: ProcessingJob) -> ProcessingJob:
    """Re-queue a failed/cancelled job with its original configuration.

    Partial results from the failed attempt are purged first; the video's
    current (previously completed) results stay untouched until the retry
    completes, so nothing is duplicated or corrupted.
    """
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise ConflictError(f"Only failed or cancelled jobs can be retried (status: {job.status}).")
    if repo.active_for_video(db, job.video_id) is not None:
        raise ConflictError("Another job for this video is already queued or running.")
    repo.purge_results(db, job.id)
    job.status = JobStatus.QUEUED
    job.attempt += 1
    job.error_message = None
    job.cancel_requested = False
    job.progress = None
    job.frames_processed = job.frames_sampled = 0
    job.detection_count = job.track_count = job.event_count = 0
    job.started_at = job.finished_at = None
    job.processing_seconds = None
    job.video.status = VideoStatus.QUEUED
    db.commit()
    queue.enqueue(job.id)
    return job


def cancel(db: Session, job: ProcessingJob) -> ProcessingJob:
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        has_current = repo.current_for_video(db, job.video_id) is not None
        job.video.status = VideoStatus.COMPLETED if has_current else VideoStatus.CANCELLED
    elif job.status == JobStatus.PROCESSING:
        # The worker checks this flag between batches and cleans up itself.
        job.cancel_requested = True
    else:
        raise ConflictError(f"Job cannot be cancelled in status '{job.status}'.")
    db.commit()
    return job
