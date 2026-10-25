"""Database-backed job queue with in-process worker threads.

The ``processing_jobs`` table *is* the queue: a job with status ``queued`` is
pending. Workers claim the oldest queued job (``SELECT ... FOR UPDATE SKIP
LOCKED`` on PostgreSQL, so several workers or processes can run safely) and
hand it to ``VideoProcessor``.

To move to Redis/RQ/Celery later, implement ``JobQueue.enqueue`` to push the
job ID onto the broker and run ``VideoProcessor.run`` in the external worker;
the API layer only depends on ``JobQueue``.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.cv.processor import VideoProcessor
from app.db.session import SessionLocal
from app.models.enums import JobStatus, VideoStatus
from app.repositories import jobs as jobs_repo

logger = logging.getLogger(__name__)


class JobQueue(Protocol):
    def enqueue(self, job_id: uuid.UUID) -> None: ...


class JobWorker:
    def __init__(
        self,
        processor: VideoProcessor | None = None,
        *,
        session_factory: sessionmaker[Session] = SessionLocal,
        poll_interval: float = 1.0,
        concurrency: int = 1,
    ):
        self.processor = processor or VideoProcessor(session_factory=session_factory)
        self.session_factory = session_factory
        self.poll_interval = poll_interval
        self.concurrency = max(1, concurrency)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []
        self.current_jobs: set[uuid.UUID] = set()

    # JobQueue interface: jobs are persisted as 'queued' by the service layer.
    def enqueue(self, job_id: uuid.UUID) -> None:
        self._wake.set()

    def recover_interrupted(self) -> None:
        with self.session_factory() as db:
            n = jobs_repo.mark_stale_processing_failed(db)
            db.commit()
            if n:
                logger.warning("Marked %d interrupted job(s) as failed", n)

    def start(self) -> None:
        self.recover_interrupted()
        for i in range(self.concurrency):
            t = threading.Thread(target=self._loop, name=f"zonevision-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        logger.info("Job worker started with %d thread(s)", self.concurrency)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        for t in self._threads:
            t.join(timeout)
        self._threads.clear()

    @property
    def alive(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def _claim(self) -> uuid.UUID | None:
        with self.session_factory() as db:
            job = jobs_repo.claim_next_queued(db)
            if job is None:
                db.rollback()
                return None
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.now(UTC)
            job.finished_at = None
            job.error_message = None
            job.video.status = VideoStatus.PROCESSING
            db.commit()
            return job.id

    def run_once(self) -> uuid.UUID | None:
        job_id = self._claim()
        if job_id is None:
            return None
        self.current_jobs.add(job_id)
        try:
            self.processor.run(job_id)
        finally:
            self.current_jobs.discard(job_id)
        return job_id

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.run_once() is not None:
                    continue
            except Exception:  # noqa: BLE001 - keep the worker alive (e.g. DB briefly down)
                logger.exception("Worker iteration failed")
            self._wake.wait(self.poll_interval)
            self._wake.clear()
