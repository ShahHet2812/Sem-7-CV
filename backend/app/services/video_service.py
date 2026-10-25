from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.cv.detector import YoloModelProvider
from app.cv.processor import snapshot_config
from app.models import MonitoringEvent, ProcessingJob, Video
from app.models.enums import JobStatus, VideoStatus
from app.repositories import jobs as jobs_repo
from app.repositories import videos as repo
from app.schemas.common import Page, PageParams
from app.schemas.video import ProcessRequest, VideoOut, VideoUpdate
from app.services import settings_service
from app.services.serializers import video_out
from app.services.storage import StoredVideo, VideoStorage
from app.services.time_utils import as_utc
from app.workers.job_worker import JobQueue

logger = logging.getLogger(__name__)


def require_video(db: Session, video_id: uuid.UUID) -> Video:
    video = repo.get(db, video_id)
    if video is None:
        raise NotFoundError("Video not found.")
    return video


def build_out(db: Session, videos: list[Video]) -> list[VideoOut]:
    ids = [v.id for v in videos]
    latest = repo.latest_jobs(db, ids)
    current = repo.current_jobs(db, ids)
    zones = repo.zone_counts(db, ids)
    events = repo.event_counts(db, ids)
    return [
        video_out(
            v,
            latest_job=latest.get(v.id),
            current_job=current.get(v.id),
            zone_count=zones.get(v.id, 0),
            event_count=events.get(v.id, 0),
        )
        for v in videos
    ]


def list_videos(
    db: Session, *, q: str | None, status: str | None, sort: str, order: str, page: PageParams
) -> Page[VideoOut]:
    videos, total = repo.list_videos(
        db, q=q, status=status, sort=sort, order=order, offset=page.offset, limit=page.page_size
    )
    return Page[VideoOut].build(build_out(db, list(videos)), total, page.page, page.page_size)


def get_out(db: Session, video_id: uuid.UUID) -> VideoOut:
    return build_out(db, [require_video(db, video_id)])[0]


def register(
    db: Session, stored: StoredVideo, *, is_sample: bool = False, recorded_at: datetime | None = None
) -> Video:
    m = stored.metadata
    video = Video(
        original_filename=stored.original_filename,
        storage_filename=stored.storage_filename,
        file_size=stored.file_size,
        content_type=stored.content_type,
        container_format=stored.container_format,
        codec=m.codec,
        duration_seconds=m.duration_seconds,
        fps=m.fps,
        frame_count=m.frame_count,
        width=m.width,
        height=m.height,
        status=VideoStatus.UPLOADED,
        is_sample=is_sample,
        recorded_at=recorded_at,
        thumbnail_filename=stored.thumbnail_filename,
        processing_metadata={"fps_estimated": m.fps_estimated},
    )
    db.add(video)
    db.commit()
    logger.info("Video registered: %s", stored.original_filename, extra={"video_id": video.id})
    return video


def update_video(db: Session, video: Video, data: VideoUpdate) -> Video:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("original_filename"):
        video.original_filename = fields["original_filename"].strip()
    if "recorded_at" in fields:
        video.recorded_at = fields["recorded_at"]
        db.flush()
        origin = as_utc(video.timeline_origin)
        # Re-anchor wall-clock times of timeline events to the new origin.
        for ev in db.scalars(
            select(MonitoringEvent).where(
                MonitoringEvent.video_id == video.id, MonitoringEvent.video_timestamp.is_not(None)
            )
        ):
            ev.occurred_at = origin + timedelta(seconds=ev.video_timestamp or 0)
    db.commit()
    return video


def delete_video(db: Session, storage: VideoStorage, video: Video) -> None:
    active = jobs_repo.active_for_video(db, video.id)
    if active is not None and active.status == JobStatus.PROCESSING:
        raise ConflictError("This video is being processed. Cancel the job before deleting it.")
    vid, filename, thumb = video.id, video.storage_filename, video.thumbnail_filename
    db.delete(video)
    db.commit()
    # Files are removed only after the DB rows are gone, so a failed commit
    # never leaves rows pointing at deleted files.
    storage.delete_video_files(vid, filename, thumb)
    logger.info("Video deleted", extra={"video_id": vid})


def queue_processing(
    db: Session,
    settings: Settings,
    provider: YoloModelProvider,
    queue: JobQueue,
    video: Video,
    overrides: ProcessRequest | None,
) -> ProcessingJob:
    if jobs_repo.active_for_video(db, video.id) is not None:
        raise ConflictError("A processing job for this video is already queued or running.")
    proc = settings_service.get_processing(db, settings)
    config = snapshot_config(proc, overrides.model_dump() if overrides else None)
    settings_service.validate_classes(config.get("classes") or [], provider)
    job = ProcessingJob(video_id=video.id, status=JobStatus.QUEUED, config=config)
    db.add(job)
    video.status = VideoStatus.QUEUED
    db.commit()
    queue.enqueue(job.id)
    logger.info("Job queued", extra={"job_id": job.id, "video_id": video.id})
    return job
