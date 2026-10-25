from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import EventStatus
from app.models.video import Video
from app.models.zone import MonitoringZone


class MonitoringEvent(Base):
    __tablename__ = "monitoring_events"
    __table_args__ = (
        Index("ix_events_video_occurred", "video_id", "occurred_at"),
        Index("ix_events_zone_type", "zone_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitoring_zones.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    # Position on the source-video timeline (seconds) and the sampled frame index.
    video_timestamp: Mapped[float | None] = mapped_column(Float)
    frame_index: Mapped[int | None] = mapped_column(Integer)
    # Wall-clock time: video.recorded_at (or upload time) + video_timestamp.
    occurred_at: Mapped[datetime] = mapped_column(index=True)
    class_name: Mapped[str | None] = mapped_column(String(64), index=True)
    track_id: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    occupancy: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default=EventStatus.NEW, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    snapshot_filename: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None]

    video: Mapped[Video] = relationship()
    zone: Mapped[MonitoringZone | None] = relationship()
