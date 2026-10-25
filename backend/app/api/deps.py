from __future__ import annotations

import uuid

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.cv.detector import YoloModelProvider
from app.services.model_provider import get_model_provider
from app.services.storage import VideoStorage
from app.workers.job_worker import JobQueue


class _NoopQueue:
    """Used when the in-process worker is disabled (e.g. an external worker
    process polls the database instead)."""

    def enqueue(self, job_id: uuid.UUID) -> None:
        return None


def get_storage(settings: Settings = Depends(get_settings)) -> VideoStorage:
    return VideoStorage(settings)


def get_queue(request: Request) -> JobQueue:
    return getattr(request.app.state, "worker", None) or _NoopQueue()


def get_provider() -> YoloModelProvider:
    return get_model_provider()
