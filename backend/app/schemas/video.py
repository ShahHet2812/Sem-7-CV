from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.job import JobOut


class VideoOut(ORMModel):
    id: uuid.UUID
    original_filename: str
    file_size: int
    content_type: str
    container_format: str
    codec: str | None
    duration_seconds: float | None
    fps: float | None
    frame_count: int | None
    width: int
    height: int
    status: str
    is_sample: bool
    recorded_at: datetime | None
    created_at: datetime
    updated_at: datetime
    processing_metadata: dict[str, Any]
    thumbnail_url: str | None = None
    stream_url: str
    download_url: str
    browser_playable: bool = True
    latest_job: JobOut | None = None
    current_job_id: uuid.UUID | None = None
    zone_count: int = 0
    event_count: int = 0
    detection_count: int = 0


class VideoUpdate(BaseModel):
    original_filename: str | None = Field(default=None, min_length=1, max_length=255)
    recorded_at: datetime | None = None


class SampleZoneOut(BaseModel):
    name: str
    zone_type: str
    polygon: list[list[float]]
    color: str
    occupancy_threshold: int | None = None


class SampleOut(BaseModel):
    key: str
    title: str
    category: str
    description: str
    objects: list[str]
    license: str
    attribution: str
    source_page: str
    approx_mb: float
    duration_s: float | None
    fixed_camera: bool
    scenario: str | None
    zones: list[SampleZoneOut]
    imported_video_id: uuid.UUID | None = None


class SampleImportRequest(BaseModel):
    setup_scenario: bool = Field(
        default=True, description="Create the preset zones and queue processing with sample overrides"
    )


class ProcessRequest(BaseModel):
    """Optional per-job overrides of the saved processing settings."""

    confidence_threshold: float | None = Field(default=None, ge=0.05, le=0.95)
    image_size: int | None = Field(default=None, ge=160, le=1920, multiple_of=32)
    target_sample_fps: float | None = Field(default=None, gt=0, le=60)
    classes: list[str] | None = None
