"""Derive zone events and occupancy from a job's stored tracked detections.

The detector/tracker output is persisted first; zone logic is a pure function
of (detections, zone polygon, monitor parameters). Running it from storage
means a zone can be added or edited after processing and its events are
rebuilt in seconds without re-running inference, and the processing pipeline
and zone edits share exactly one code path.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.cv.zone_monitor import Observation, ZoneMonitor, ZoneSpec
from app.models import MonitoringEvent, MonitoringZone, ProcessingJob, Video, ZoneOccupancySample
from app.models.enums import EventStatus, EventType
from app.repositories import detections as det_repo
from app.schemas.settings import ProcessingSettings
from app.services.time_utils import as_utc

logger = logging.getLogger(__name__)


def to_spec(zone: MonitoringZone) -> ZoneSpec:
    return ZoneSpec(
        id=zone.id,
        name=zone.name,
        polygon=zone.polygon,
        zone_type=zone.zone_type,
        emit_entries=zone.emit_entries,
        emit_exits=zone.emit_exits,
        occupancy_threshold=zone.occupancy_threshold,
        class_filter=tuple(zone.class_filter) if zone.class_filter else None,
    )


def build_monitor(zones: Sequence[MonitoringZone], params: ProcessingSettings) -> ZoneMonitor:
    return ZoneMonitor(
        [to_spec(z) for z in zones],
        confirm_samples=params.zone_confirm_samples,
        lost_timeout=params.track_lost_timeout,
        occupancy_cooldown=params.occupancy_alert_cooldown,
        anchor_mode=params.anchor_mode,
    )


def recompute_zone_events(
    db: Session,
    video: Video,
    job: ProcessingJob,
    zones: Sequence[MonitoringZone],
    params: ProcessingSettings,
) -> int:
    """Replace zone events/occupancy of ``zones`` for ``job``. Returns #events created.

    Review status and notes of events that are reproduced identically
    (same zone, type, track and frame) are carried over.
    """
    zone_ids = [z.id for z in zones]
    if not zone_ids:
        return 0
    old = db.scalars(
        select(MonitoringEvent).where(
            MonitoringEvent.job_id == job.id,
            MonitoringEvent.zone_id.in_(zone_ids),
            MonitoringEvent.event_type.in_(EventType.zone_types()),
        )
    ).all()
    preserved = {
        (e.zone_id, e.event_type, e.track_id, e.frame_index): e
        for e in old
        if e.status != EventStatus.NEW or e.notes or e.snapshot_filename
    }
    keep = {
        k: (e.status, e.notes, e.reviewed_at, e.snapshot_filename) for k, e in preserved.items()
    }
    db.execute(
        delete(MonitoringEvent).where(
            MonitoringEvent.job_id == job.id,
            MonitoringEvent.zone_id.in_(zone_ids),
            MonitoringEvent.event_type.in_(EventType.zone_types()),
        )
    )
    db.execute(
        delete(ZoneOccupancySample).where(
            ZoneOccupancySample.job_id == job.id, ZoneOccupancySample.zone_id.in_(zone_ids)
        )
    )
    enabled = [z for z in zones if z.enabled]
    if not enabled:
        refresh_event_count(db, job)
        return 0

    monitor = build_monitor(enabled, params)
    fps = video.fps or 25.0
    stride = max(1, job.frame_stride)
    records = []
    prev_idx: int | None = None

    def feed_empty(start: int, stop: int) -> None:
        # Feed sampled frames that had no detections so lost-track timeouts and
        # occupancy advance on the real sampling grid.
        for idx in range(start, stop, stride):
            records.extend(monitor.update(idx / fps, idx, []))

    for idx, ts, dets in det_repo.iter_frames(db, job.id):
        if prev_idx is not None:
            feed_empty(prev_idx + stride, idx)
        obs = [
            Observation(
                track_id=d.track_id,
                class_name=d.class_name,
                confidence=d.confidence,
                bbox=(d.x1, d.y1, d.x2, d.y2),
            )
            for d in dets
        ]
        records.extend(monitor.update(ts, idx, obs))
        prev_idx = idx
    if prev_idx is not None and job.frames_processed:
        feed_empty(prev_idx + stride, job.frames_processed)

    origin = as_utc(video.timeline_origin)
    for r in records:
        key = (r.zone_id, r.event_type, r.track_id, r.frame_index)
        status, notes, reviewed_at, snapshot = keep.get(key, (EventStatus.NEW.value, None, None, None))
        db.add(
            MonitoringEvent(
                video_id=video.id,
                zone_id=r.zone_id,
                job_id=job.id,
                event_type=r.event_type,
                video_timestamp=round(r.timestamp, 3),
                frame_index=r.frame_index,
                occurred_at=origin + timedelta(seconds=r.timestamp),
                class_name=r.class_name,
                track_id=r.track_id,
                confidence=r.confidence,
                occupancy=r.occupancy,
                bbox=list(r.bbox) if r.bbox else None,
                status=status,
                notes=notes,
                reviewed_at=reviewed_at,
                snapshot_filename=snapshot,
                details=r.details,
            )
        )
    samples = [
        {"zone_id": c.zone_id, "job_id": job.id, "timestamp": round(c.timestamp, 3), "occupancy": c.occupancy}
        for c in monitor.occupancy_changes
    ]
    if samples:
        db.execute(insert(ZoneOccupancySample), samples)
    db.flush()
    refresh_event_count(db, job)
    logger.info(
        "Zone analysis: %d zone(s), %d event(s)", len(enabled), len(records),
        extra={"job_id": job.id, "video_id": video.id},
    )
    return len(records)


def refresh_event_count(db: Session, job: ProcessingJob) -> None:
    db.flush()
    job.event_count = (
        db.scalar(
            select(func.count()).where(
                MonitoringEvent.job_id == job.id,
                MonitoringEvent.event_type.in_(EventType.zone_types()),
            )
        )
        or 0
    )
