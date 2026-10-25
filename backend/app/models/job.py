from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import JobStatus

if TYPE_CHECKING:
    from app.models.video import Video


class ProcessingJob(Base):
    """One attempt-series of running the CV pipeline over a video.

    Only one job per video is ``is_current``: its detections, tracks and zone
    events are the ones shown in the UI and analytics. Results of older jobs are
    purged when a newer job completes, so analytics never double count.
    """

    __tablename__ = "processing_jobs"
    __table_args__ = (Index("ix_processing_jobs_video_current", "video_id", "is_current"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    progress: Mapped[float | None] = mapped_column(Float)
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    frames_sampled: Mapped[int] = mapped_column(Integer, default=0)
    total_frames: Mapped[int | None] = mapped_column(Integer)
    frame_stride: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    device: Mapped[str | None] = mapped_column(String(32))
    model_name: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_seconds: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    video: Mapped[Video] = relationship(back_populates="jobs")

    @property
    def sampled_fps(self) -> float | None:
        if self.processing_seconds and self.processing_seconds > 0:
            return self.frames_sampled / self.processing_seconds
        return None
