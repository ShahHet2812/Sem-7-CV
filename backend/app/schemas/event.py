from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import EventStatus


class EventOut(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    video_name: str | None
    zone_id: uuid.UUID | None
    zone_name: str | None
    zone_color: str | None
    job_id: uuid.UUID | None
    event_type: str
    severity: str
    video_timestamp: float | None
    frame_index: int | None
    occurred_at: datetime
    class_name: str | None
    track_id: int | None
    confidence: float | None
    occupancy: int | None
    bbox: list[float] | None
    status: str
    notes: str | None
    snapshot_url: str | None
    details: dict[str, Any]
    created_at: datetime
    reviewed_at: datetime | None


class EventUpdate(BaseModel):
    status: EventStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BulkStatusUpdate(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: EventStatus


class BulkStatusResult(BaseModel):
    updated: int


SortField = Literal["occurred_at", "video_timestamp", "event_type", "class_name", "confidence"]
