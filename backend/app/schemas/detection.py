from __future__ import annotations

import uuid

from pydantic import BaseModel


class DetectionOut(BaseModel):
    bbox: tuple[float, float, float, float]  # normalized x1, y1, x2, y2
    class_id: int
    class_name: str
    confidence: float
    track_id: int | None


class FrameDetections(BaseModel):
    frame_index: int
    timestamp: float
    detections: list[DetectionOut]


class DetectionWindow(BaseModel):
    """Detections for sampled frames with start <= timestamp < end."""

    video_id: uuid.UUID
    job_id: uuid.UUID | None
    start: float
    end: float
    fps: float | None
    frame_stride: int
    sample_interval: float | None
    truncated: bool
    frames: list[FrameDetections]
