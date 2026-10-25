from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, utcnow
from app.models.enums import ZoneType

if TYPE_CHECKING:
    from app.models.video import Video


class MonitoringZone(Base):
    """A polygon in normalized source-frame coordinates (x, y in [0, 1])."""

    __tablename__ = "monitoring_zones"
    __table_args__ = (UniqueConstraint("video_id", "name", name="uq_zone_video_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    zone_type: Mapped[str] = mapped_column(String(16), default=ZoneType.GENERAL)
    color: Mapped[str] = mapped_column(String(9), default="#22d3ee")
    polygon: Mapped[list[list[float]]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    emit_entries: Mapped[bool] = mapped_column(Boolean, default=True)
    emit_exits: Mapped[bool] = mapped_column(Boolean, default=True)
    occupancy_threshold: Mapped[int | None] = mapped_column(Integer)
    # Restrict monitoring to these class names (empty/None = all tracked classes).
    class_filter: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    video: Mapped[Video] = relationship(back_populates="zones")


class ZoneOccupancySample(Base):
    """Change-points of estimated zone occupancy over the source-video timeline."""

    __tablename__ = "zone_occupancy_samples"
    __table_args__ = (Index("ix_zone_occupancy_zone_ts", "zone_id", "timestamp"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("monitoring_zones.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[float] = mapped_column(Float)
    occupancy: Mapped[int] = mapped_column(Integer)
