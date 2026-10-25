from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.event import EventOut
from app.schemas.job import JobOut


class Overview(BaseModel):
    total_videos: int
    processed_videos: int
    total_detections: int
    unique_tracks: int
    zone_entries: int
    zone_exits: int
    restricted_entries: int
    occupancy_alerts: int
    processing_failures: int
    unreviewed_alerts: int
    total_zones: int
    video_status: dict[str, int]
    job_status: dict[str, int]
    events_by_type: dict[str, int]
    recent_jobs: list[JobOut]
    recent_events: list[EventOut]


class ClassCount(BaseModel):
    class_name: str
    detections: int
    tracks: int
    avg_confidence: float | None


class ActivityPoint(BaseModel):
    bucket: str  # ISO datetime (wall clock) or seconds (video timeline)
    label: str
    detections: int
    entries: int
    exits: int
    alerts: int


class ActivitySeries(BaseModel):
    mode: str  # "video_time" | "wall_clock"
    bucket_size: str
    points: list[ActivityPoint]


class ZoneSummary(BaseModel):
    zone_id: uuid.UUID
    zone_name: str
    zone_type: str
    color: str
    video_id: uuid.UUID
    video_name: str
    enabled: bool
    entries: int
    exits: int
    restricted_entries: int
    occupancy_alerts: int
    total_events: int
    peak_occupancy: int | None


class PerformancePoint(BaseModel):
    job_id: uuid.UUID
    video_name: str
    finished_at: datetime | None
    processing_seconds: float | None
    frames_sampled: int
    sampled_fps: float | None
    realtime_factor: float | None
    device: str | None
    model_name: str | None
