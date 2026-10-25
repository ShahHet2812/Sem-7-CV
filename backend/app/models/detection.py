from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK


class Detection(Base):
    """A single detected object on a sampled frame.

    Bounding boxes are stored normalized to the source frame: (x1, y1) is the
    top-left and (x2, y2) the bottom-right corner, each in [0, 1]. Multiply by
    the video's width/height to get source pixels.
    """

    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_job_ts", "job_id", "timestamp"),
        Index("ix_detections_job_class", "job_id", "class_name"),
        Index("ix_detections_job_track", "job_id", "track_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    frame_index: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    class_id: Mapped[int] = mapped_column(Integer)
    class_name: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    track_id: Mapped[int | None] = mapped_column(Integer)


class TrackSummary(Base):
    """Aggregate of one tracker ID within one job.

    A track ID is the tracker's short-term identity. Occlusion or leaving the
    frame can start a new track for the same real-world object, so track
    counts are an upper bound on unique objects, not a count of people.
    """

    __tablename__ = "track_summaries"
    __table_args__ = (UniqueConstraint("job_id", "track_id", name="uq_track_job_track"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[int] = mapped_column(Integer)
    class_name: Mapped[str] = mapped_column(String(64))
    first_seen: Mapped[float] = mapped_column(Float)
    last_seen: Mapped[float] = mapped_column(Float)
    detection_count: Mapped[int] = mapped_column(Integer)
    avg_confidence: Mapped[float] = mapped_column(Float)
