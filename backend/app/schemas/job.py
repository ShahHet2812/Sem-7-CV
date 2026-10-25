from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class JobOut(ORMModel):
    id: uuid.UUID
    video_id: uuid.UUID
    video_name: str | None = None
    status: str
    is_current: bool
    attempt: int
    progress: float | None
    frames_processed: int
    frames_sampled: int
    total_frames: int | None
    frame_stride: int
    config: dict[str, Any]
    device: str | None
    model_name: str | None
    error_message: str | None
    cancel_requested: bool
    detection_count: int
    track_count: int
    event_count: int
    processing_seconds: float | None
    sampled_fps: float | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
