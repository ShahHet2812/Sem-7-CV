from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, Boolean, Float, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.enums import VideoStatus

if TYPE_CHECKING:
    from app.models.job import ProcessingJob
    from app.models.zone import MonitoringZone


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    # Server-generated filename relative to the uploads directory (never a client path).
    storage_filename: Mapped[str] = mapped_column(String(255), unique=True)
    file_size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(100))
    container_format: Mapped[str] = mapped_column(String(16))
    codec: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=VideoStatus.UPLOADED, index=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    # Optional wall-clock start of the footage; used to place events on a real timeline.
    recorded_at: Mapped[datetime | None]
    thumbnail_filename: Mapped[str | None] = mapped_column(String(255))
    processing_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )
    zones: Mapped[list[MonitoringZone]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def timeline_origin(self) -> datetime:
        """Wall-clock instant corresponding to t=0 of the source video."""
        return self.recorded_at or self.created_at
