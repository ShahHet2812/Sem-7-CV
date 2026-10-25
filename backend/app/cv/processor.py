"""End-to-end processing of one job: decode -> detect+track -> persist -> zones.

Pipeline for a job (already claimed and marked ``processing`` by the worker):

1. Remove any partial results this job may have from an earlier attempt, so
   retries are idempotent.
2. Decode the video sequentially and run detection + tracking on every
   ``stride``-th frame (stride derived from the target sampling rate).
3. Buffer detection rows and bulk-insert them in batches; progress is
   committed with each batch and cancellation is checked between batches.
4. Persist per-track summaries, then derive zone events from the stored
   detections (see ``services.zone_analysis``).
5. Atomically promote the job to the video's *current* job and purge the
   previous current job's results, so analytics never double count.

Failures roll back the partial work, mark the job failed with a user-facing
message, and record a ``processing_failure`` event.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.cv.detector import ModelUnavailableError
from app.cv.geometry import normalize_bbox
from app.cv.tracker import FrameTracker, TrackingSession
from app.cv.video_reader import VideoDecodeError, VideoReader, compute_stride
from app.db.session import SessionLocal
from app.models import MonitoringEvent, ProcessingJob, Video
from app.models.enums import EventType, JobStatus, VideoStatus
from app.repositories import detections as det_repo
from app.repositories import jobs as jobs_repo
from app.repositories import zones as zones_repo
from app.schemas.settings import ProcessingSettings
from app.services import settings_service
from app.services.storage import VideoStorage
from app.services.zone_analysis import recompute_zone_events

logger = logging.getLogger(__name__)

BATCH_FRAMES = 20
BATCH_ROWS = 2000


class JobCancelled(Exception):
    pass


@dataclass
class TrackerHandle:
    tracker: FrameTracker
    model_name: str
    device: str


TrackerFactory = Callable[[dict[str, Any]], TrackerHandle]


def default_tracker_factory(config: dict[str, Any]) -> TrackerHandle:
    from app.services.model_provider import get_model_provider

    provider = get_model_provider()
    model = provider.create_model()
    names = {int(k): str(v) for k, v in model.names.items()}
    wanted = set(config.get("classes") or [])
    class_ids = sorted(i for i, n in names.items() if n in wanted) if wanted else None
    if wanted and not class_ids:
        raise ModelUnavailableError(
            "None of the selected object classes are supported by the loaded model."
        )
    session = TrackingSession(
        model,
        confidence=float(config["confidence_threshold"]),
        image_size=int(config["image_size"]),
        class_ids=class_ids,
        tracker=config.get("tracker", "bytetrack"),
        device=provider.device,
    )
    return TrackerHandle(session, provider.model_name, provider.device)


def user_message(exc: BaseException) -> str:
    if isinstance(exc, (ModelUnavailableError, VideoDecodeError)):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return "The source video file is missing from storage."
    return f"Processing failed due to an internal error ({exc.__class__.__name__}). See server logs."


class VideoProcessor:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        tracker_factory: TrackerFactory = default_tracker_factory,
        settings: Settings | None = None,
    ):
        self.session_factory = session_factory
        self.tracker_factory = tracker_factory
        self.settings = settings or get_settings()
        self.storage = VideoStorage(self.settings)

    def run(self, job_id: uuid.UUID) -> str:
        """Process a job that is in ``processing`` state. Returns the final status."""
        db = self.session_factory()
        try:
            job = db.get(ProcessingJob, job_id)
            if job is None or job.status != JobStatus.PROCESSING:
                return job.status if job else "missing"
            video = job.video
            try:
                self._execute(db, job, video)
                return JobStatus.COMPLETED.value
            except JobCancelled:
                db.rollback()
                self._finish_cancelled(db, job_id)
                return JobStatus.CANCELLED.value
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
                db.rollback()
                logger.exception("Job failed", extra={"job_id": job_id})
                self._finish_failed(db, job_id, exc)
                return JobStatus.FAILED.value
        finally:
            db.close()

    # ------------------------------------------------------------------ steps
    def _execute(self, db: Session, job: ProcessingJob, video: Video) -> None:
        path = self.storage.upload_path(video.storage_filename)
        if path is None or not path.is_file():
            raise FileNotFoundError(video.storage_filename)

        jobs_repo.purge_results(db, job.id)
        config = job.config
        fps = video.fps or 25.0
        stride = compute_stride(fps, float(config["target_sample_fps"]))
        job.frame_stride = stride
        job.total_frames = video.frame_count
        job.frames_processed = job.frames_sampled = job.detection_count = 0
        job.progress = 0.0 if video.frame_count else None
        video.status = VideoStatus.PROCESSING
        db.commit()

        handle = self.tracker_factory(config)
        job.model_name, job.device = handle.model_name, handle.device
        db.commit()

        started = time.perf_counter()
        buffer: list[dict[str, Any]] = []
        tracks: dict[int, dict[str, Any]] = {}
        sampled = 0
        detections = 0

        def flush(frames_read: int) -> None:
            nonlocal buffer
            det_repo.bulk_insert(db, buffer)
            buffer = []
            job.frames_processed = frames_read
            job.frames_sampled = sampled
            job.detection_count = detections
            if video.frame_count:
                job.progress = min(0.99, frames_read / video.frame_count)
            db.commit()
            db.refresh(job, ["cancel_requested"])
            if job.cancel_requested:
                raise JobCancelled()

        with VideoReader(path, fps) as reader:
            for frame in reader.iter_sampled(stride):
                h, w = frame.image.shape[:2]
                for d in handle.tracker.update(frame.image):
                    x1, y1, x2, y2 = normalize_bbox(d.xyxy, w, h)
                    if x2 <= x1 or y2 <= y1:
                        continue
                    detections += 1
                    buffer.append(
                        {
                            "video_id": video.id,
                            "job_id": job.id,
                            "frame_index": frame.index,
                            "timestamp": round(frame.timestamp, 4),
                            "x1": round(x1, 5),
                            "y1": round(y1, 5),
                            "x2": round(x2, 5),
                            "y2": round(y2, 5),
                            "class_id": d.class_id,
                            "class_name": d.class_name,
                            "confidence": round(d.confidence, 4),
                            "track_id": d.track_id,
                        }
                    )
                    if d.track_id is not None:
                        _accumulate_track(tracks, d.track_id, d.class_name, d.confidence, frame.timestamp)
                sampled += 1
                if sampled % BATCH_FRAMES == 0 or len(buffer) >= BATCH_ROWS:
                    flush(reader.frames_read)
            flush(reader.frames_read)
            frames_read = reader.frames_read

        if sampled == 0:
            raise VideoDecodeError("No frames could be decoded from the video.")

        det_repo.bulk_insert_tracks(
            db,
            [
                {
                    "video_id": video.id,
                    "job_id": job.id,
                    "track_id": tid,
                    "class_name": max(t["classes"], key=t["classes"].get),
                    "first_seen": round(t["first"], 3),
                    "last_seen": round(t["last"], 3),
                    "detection_count": t["count"],
                    "avg_confidence": round(t["conf_sum"] / t["count"], 4),
                }
                for tid, t in tracks.items()
            ],
        )
        job.track_count = len(tracks)
        job.frames_processed = frames_read
        db.flush()

        params = settings_service.get_processing(db, self.settings)
        zones = zones_repo.for_video(db, video.id)
        recompute_zone_events(db, video, job, zones, params)

        previous = jobs_repo.current_for_video(db, video.id)
        if previous is not None and previous.id != job.id:
            jobs_repo.purge_results(db, previous.id)
            previous.is_current = False
            db.flush()

        elapsed = time.perf_counter() - started
        job.is_current = True
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.processing_seconds = round(elapsed, 3)
        job.finished_at = datetime.now(UTC)
        job.error_message = None
        video.status = VideoStatus.COMPLETED
        # Actual decoded duration can differ from the container's estimate.
        if not video.duration_seconds and frames_read:
            video.duration_seconds = round(frames_read / fps, 3)
        if not video.frame_count:
            video.frame_count = frames_read
        video.processing_metadata = {
            **(video.processing_metadata or {}),
            "last_job_id": str(job.id),
            "frames_decoded": frames_read,
            "frame_stride": stride,
            "sample_interval": round(stride / fps, 4),
        }
        db.commit()
        logger.info(
            "Job completed: %d sampled frames, %d detections, %d tracks in %.1fs",
            sampled, detections, len(tracks), elapsed, extra={"job_id": job.id},
        )

        if config.get("generate_snapshots", True):
            from app.services.snapshots import generate_missing_snapshots

            generate_missing_snapshots(video.id)

    def _finish_cancelled(self, db: Session, job_id: uuid.UUID) -> None:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        jobs_repo.purge_results(db, job.id)
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        job.progress = None
        has_current = jobs_repo.current_for_video(db, job.video_id) is not None
        job.video.status = VideoStatus.COMPLETED if has_current else VideoStatus.CANCELLED
        db.commit()

    def _finish_failed(self, db: Session, job_id: uuid.UUID, exc: BaseException) -> None:
        try:
            job = db.get(ProcessingJob, job_id)
            if job is None:
                return
            jobs_repo.purge_results(db, job.id)
            message = user_message(exc)
            job.status = JobStatus.FAILED
            job.error_message = message
            job.finished_at = datetime.now(UTC)
            job.is_current = False
            video = job.video
            video.status = VideoStatus.FAILED
            now = datetime.now(UTC)
            db.add(
                MonitoringEvent(
                    video_id=video.id,
                    job_id=job.id,
                    event_type=EventType.PROCESSING_FAILURE,
                    occurred_at=now,
                    details={"message": message, "attempt": job.attempt},
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Could not record job failure", extra={"job_id": job_id})


def _accumulate_track(
    tracks: dict[int, dict[str, Any]], tid: int, cls: str, conf: float, ts: float
) -> None:
    t = tracks.get(tid)
    if t is None:
        tracks[tid] = {"first": ts, "last": ts, "count": 1, "conf_sum": conf, "classes": {cls: 1}}
        return
    t["last"] = ts
    t["count"] += 1
    t["conf_sum"] += conf
    t["classes"][cls] = t["classes"].get(cls, 0) + 1


def snapshot_config(proc: ProcessingSettings, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = proc.model_dump()
    for k, v in (overrides or {}).items():
        if v is not None:
            cfg[k] = v
    return cfg
