from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import Detection, TrackSummary


def bulk_insert(db: Session, rows: Sequence[dict[str, Any]]) -> None:
    if rows:
        db.execute(insert(Detection), list(rows))


def bulk_insert_tracks(db: Session, rows: Sequence[dict[str, Any]]) -> None:
    if rows:
        db.execute(insert(TrackSummary), list(rows))


def window(
    db: Session,
    job_id: uuid.UUID,
    *,
    start: float,
    end: float,
    class_names: Sequence[str] | None,
    min_confidence: float | None,
    limit: int,
) -> Sequence[Detection]:
    stmt = select(Detection).where(
        Detection.job_id == job_id, Detection.timestamp >= start, Detection.timestamp < end
    )
    if class_names:
        stmt = stmt.where(Detection.class_name.in_(class_names))
    if min_confidence is not None:
        stmt = stmt.where(Detection.confidence >= min_confidence)
    stmt = stmt.order_by(Detection.frame_index, Detection.id).limit(limit)
    return db.scalars(stmt).all()


def iter_frames(db: Session, job_id: uuid.UUID) -> Iterator[tuple[int, float, list[Detection]]]:
    """Stream stored detections grouped by sampled frame, in timeline order."""
    stmt = (
        select(Detection)
        .where(Detection.job_id == job_id)
        .order_by(Detection.frame_index, Detection.id)
        .execution_options(yield_per=5000)
    )
    current: list[Detection] = []
    current_idx: int | None = None
    current_ts = 0.0
    for det in db.scalars(stmt):
        if current_idx is not None and det.frame_index != current_idx:
            yield current_idx, current_ts, current
            current = []
        current_idx, current_ts = det.frame_index, det.timestamp
        current.append(det)
    if current_idx is not None:
        yield current_idx, current_ts, current
