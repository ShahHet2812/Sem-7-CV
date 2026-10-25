"""Analytics computed from persisted results of each video's *current* job.

Definitions (also documented in README):
* detections   - stored boxes on sampled frames (one object seen on N sampled
                 frames counts N times);
* unique tracks - distinct (job, tracker ID) pairs; an upper bound on distinct
                 objects because trackers can re-assign IDs after occlusion;
* entries      - zone_entry + restricted_entry events; exits - zone_exit;
* occupancy    - tracks currently confirmed inside a zone (see ZoneMonitor).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Integer, and_, cast, false, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Detection,
    MonitoringEvent,
    MonitoringZone,
    ProcessingJob,
    Video,
    ZoneOccupancySample,
)
from app.models.enums import EventStatus, EventType, JobStatus
from app.repositories import events as events_repo
from app.repositories.events import EventFilters
from app.schemas.analytics import (
    ActivityPoint,
    ActivitySeries,
    ClassCount,
    Overview,
    PerformancePoint,
    ZoneSummary,
)
from app.services.serializers import event_out, job_out
from app.services.time_utils import as_utc

ALERT_TYPES = (
    EventType.RESTRICTED_ENTRY.value,
    EventType.OCCUPANCY_EXCEEDED.value,
    EventType.PROCESSING_FAILURE.value,
)
NICE_BUCKETS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]


@dataclass
class AnalyticsFilters:
    video_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    class_name: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def events(self) -> EventFilters:
        return EventFilters(
            video_id=self.video_id,
            zone_id=self.zone_id,
            class_name=self.class_name,
            date_from=self.date_from,
            date_to=self.date_to,
        )


def _floor_div(db: Session, col, divisor: float):
    """floor(col / divisor) as INTEGER on both dialects.

    PostgreSQL rounds on CAST(float AS int) while SQLite truncates, so use
    FLOOR() explicitly where available (timestamps are non-negative).
    """
    expr = col / divisor
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        expr = func.floor(expr)
    return cast(expr, Integer)


def _current_job_ids():
    return select(ProcessingJob.id).where(ProcessingJob.is_current.is_(True))


def _time_clause(db: Session, f: AnalyticsFilters):
    """Translate a wall-clock range into per-video source-timestamp ranges."""
    if not (f.date_from or f.date_to):
        return None
    stmt = select(Video.id, Video.recorded_at, Video.created_at)
    if f.video_id:
        stmt = stmt.where(Video.id == f.video_id)
    clauses = []
    for vid, recorded, created in db.execute(stmt):
        origin = as_utc(recorded or created)
        conds = [Detection.video_id == vid]
        if f.date_from:
            conds.append(Detection.timestamp >= (as_utc(f.date_from) - origin).total_seconds())
        if f.date_to:
            conds.append(Detection.timestamp <= (as_utc(f.date_to) - origin).total_seconds())
        clauses.append(and_(*conds))
    return or_(*clauses) if clauses else false()


def _detection_query(db: Session, f: AnalyticsFilters, *cols):
    stmt = select(*cols).where(Detection.job_id.in_(_current_job_ids()))
    if f.video_id:
        stmt = stmt.where(Detection.video_id == f.video_id)
    if f.class_name:
        stmt = stmt.where(Detection.class_name == f.class_name)
    tc = _time_clause(db, f)
    if tc is not None:
        stmt = stmt.where(tc)
    return stmt


def _event_type_counts(db: Session, f: AnalyticsFilters) -> dict[str, int]:
    stmt = events_repo.apply_filters(
        select(MonitoringEvent.event_type, func.count()), f.events()
    ).group_by(MonitoringEvent.event_type)
    return {t: n for t, n in db.execute(stmt)}


def overview(db: Session, f: AnalyticsFilters) -> Overview:
    video_stmt = select(Video.status, func.count()).group_by(Video.status)
    job_stmt = select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)
    if f.video_id:
        video_stmt = video_stmt.where(Video.id == f.video_id)
        job_stmt = job_stmt.where(ProcessingJob.video_id == f.video_id)
    video_status = {s: n for s, n in db.execute(video_stmt)}
    job_status = {s: n for s, n in db.execute(job_stmt)}

    processed_stmt = select(func.count(func.distinct(ProcessingJob.video_id))).where(
        ProcessingJob.is_current.is_(True)
    )
    if f.video_id:
        processed_stmt = processed_stmt.where(ProcessingJob.video_id == f.video_id)

    total_detections = db.scalar(
        select(func.count()).select_from(_detection_query(db, f, Detection.id).subquery())
    ) or 0
    track_sub = (
        _detection_query(db, f, Detection.job_id, Detection.track_id)
        .where(Detection.track_id.is_not(None))
        .distinct()
        .subquery()
    )
    unique_tracks = db.scalar(select(func.count()).select_from(track_sub)) or 0

    by_type = _event_type_counts(db, f)
    unreviewed_stmt = events_repo.apply_filters(
        select(func.count(MonitoringEvent.id)), f.events()
    ).where(MonitoringEvent.status == EventStatus.NEW, MonitoringEvent.event_type.in_(ALERT_TYPES))
    zones_stmt = select(func.count(MonitoringZone.id))
    if f.video_id:
        zones_stmt = zones_stmt.where(MonitoringZone.video_id == f.video_id)

    recent_jobs_stmt = select(ProcessingJob).order_by(ProcessingJob.created_at.desc()).limit(6)
    if f.video_id:
        recent_jobs_stmt = recent_jobs_stmt.where(ProcessingJob.video_id == f.video_id)
    recent_events = events_repo.query(db, f.events(), sort="occurred_at", order="desc", limit=8)

    return Overview(
        total_videos=sum(video_status.values()),
        processed_videos=db.scalar(processed_stmt) or 0,
        total_detections=total_detections,
        unique_tracks=unique_tracks,
        zone_entries=by_type.get(EventType.ZONE_ENTRY, 0) + by_type.get(EventType.RESTRICTED_ENTRY, 0),
        zone_exits=by_type.get(EventType.ZONE_EXIT, 0),
        restricted_entries=by_type.get(EventType.RESTRICTED_ENTRY, 0),
        occupancy_alerts=by_type.get(EventType.OCCUPANCY_EXCEEDED, 0),
        processing_failures=by_type.get(EventType.PROCESSING_FAILURE, 0),
        unreviewed_alerts=db.scalar(unreviewed_stmt) or 0,
        total_zones=db.scalar(zones_stmt) or 0,
        video_status=video_status,
        job_status=job_status,
        events_by_type=by_type,
        recent_jobs=[job_out(j) for j in db.scalars(recent_jobs_stmt)],
        recent_events=[event_out(e) for e in recent_events],
    )


def detections_by_class(db: Session, f: AnalyticsFilters) -> list[ClassCount]:
    rows = db.execute(
        _detection_query(
            db, f, Detection.class_name, func.count(Detection.id), func.avg(Detection.confidence)
        ).group_by(Detection.class_name)
    ).all()
    sub = (
        _detection_query(db, f, Detection.class_name, Detection.job_id, Detection.track_id)
        .where(Detection.track_id.is_not(None))
        .distinct()
        .subquery()
    )
    track_rows = db.execute(
        select(sub.c.class_name, func.count()).group_by(sub.c.class_name)
    ).all()
    tracks = {c: n for c, n in track_rows}
    out = [
        ClassCount(
            class_name=c, detections=n, tracks=tracks.get(c, 0),
            avg_confidence=round(float(a), 4) if a is not None else None,
        )
        for c, n, a in rows
    ]
    return sorted(out, key=lambda c: c.detections, reverse=True)


def _fmt_seconds(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _classify(event_type: str) -> str | None:
    if event_type in EventType.entry_types():
        return "entries"
    if event_type == EventType.ZONE_EXIT:
        return "exits"
    if event_type in ALERT_TYPES:
        return "alerts"
    return None


def activity(db: Session, f: AnalyticsFilters, max_points: int = 120) -> ActivitySeries:
    if f.video_id:
        return _activity_video_time(db, f, max_points)
    return _activity_wall_clock(db, f)


def _activity_video_time(db: Session, f: AnalyticsFilters, max_points: int) -> ActivitySeries:
    video = db.get(Video, f.video_id)
    duration = (video.duration_seconds if video else None) or 0
    if not duration:
        max_ts = db.scalar(_detection_query(db, f, func.max(Detection.timestamp)))
        duration = float(max_ts or 0) + 1
    bucket = next((b for b in NICE_BUCKETS if duration / b <= max_points), NICE_BUCKETS[-1])
    n_buckets = int(duration // bucket) + 1
    det_bucket = _floor_div(db, Detection.timestamp, bucket)
    det_counts = {
        int(k): n
        for k, n in db.execute(
            _detection_query(db, f, det_bucket.label("b"), func.count()).group_by("b")
        )
    }
    series: dict[int, dict[str, int]] = defaultdict(lambda: {"entries": 0, "exits": 0, "alerts": 0})
    ev_stmt = events_repo.apply_filters(
        select(MonitoringEvent.video_timestamp, MonitoringEvent.event_type), f.events()
    ).where(MonitoringEvent.video_timestamp.is_not(None))
    for ts, etype in db.execute(ev_stmt):
        key = _classify(etype)
        if key:
            series[int(ts // bucket)][key] += 1
    points = [
        ActivityPoint(
            bucket=str(i * bucket),
            label=_fmt_seconds(i * bucket),
            detections=det_counts.get(i, 0),
            **series.get(i, {"entries": 0, "exits": 0, "alerts": 0}),
        )
        for i in range(n_buckets)
    ]
    return ActivitySeries(mode="video_time", bucket_size=f"{bucket}s", points=points)


def _activity_wall_clock(db: Session, f: AnalyticsFilters) -> ActivitySeries:
    origins = {
        vid: as_utc(rec or created)
        for vid, rec, created in db.execute(select(Video.id, Video.recorded_at, Video.created_at))
    }
    minute = _floor_div(db, Detection.timestamp, 60)
    minute_counts: list[tuple[datetime, int]] = []
    for vid, m, n in db.execute(
        _detection_query(db, f, Detection.video_id, minute.label("m"), func.count()).group_by(
            Detection.video_id, "m"
        )
    ):
        if vid in origins:
            minute_counts.append((origins[vid] + timedelta(minutes=int(m)), n))
    ev_stmt = events_repo.apply_filters(
        select(MonitoringEvent.occurred_at, MonitoringEvent.event_type), f.events()
    )
    events = [(as_utc(t), et) for t, et in db.execute(ev_stmt)]
    times = [t for t, _ in minute_counts] + [t for t, _ in events]
    if not times:
        return ActivitySeries(mode="wall_clock", bucket_size="hour", points=[])
    start = as_utc(f.date_from) if f.date_from else min(times)
    end = as_utc(f.date_to) if f.date_to else max(times)
    span = end - start
    unit = "hour" if span <= timedelta(days=3) else "day"

    def floor(t: datetime) -> datetime:
        t = t.replace(minute=0, second=0, microsecond=0)
        return t.replace(hour=0) if unit == "day" else t

    step = timedelta(hours=1) if unit == "hour" else timedelta(days=1)
    buckets: dict[datetime, dict[str, int]] = {}
    cur = floor(start)
    while cur <= end and len(buckets) < 2000:
        buckets[cur] = {"detections": 0, "entries": 0, "exits": 0, "alerts": 0}
        cur += step
    for t, n in minute_counts:
        b = buckets.get(floor(t))
        if b is not None:
            b["detections"] += n
    for t, et in events:
        key = _classify(et)
        b = buckets.get(floor(t))
        if key and b is not None:
            b[key] += 1
    fmt = "%d %b %H:00" if unit == "hour" else "%d %b %Y"
    points = [
        ActivityPoint(bucket=k.isoformat(), label=k.strftime(fmt), **v) for k, v in buckets.items()
    ]
    return ActivitySeries(mode="wall_clock", bucket_size=unit, points=points)


def zones_summary(db: Session, f: AnalyticsFilters) -> list[ZoneSummary]:
    stmt = select(MonitoringZone, Video.original_filename).join(Video, Video.id == MonitoringZone.video_id)
    if f.video_id:
        stmt = stmt.where(MonitoringZone.video_id == f.video_id)
    if f.zone_id:
        stmt = stmt.where(MonitoringZone.id == f.zone_id)
    zones = db.execute(stmt).all()
    ids = [z.id for z, _ in zones]
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    if ids:
        ev_stmt = events_repo.apply_filters(
            select(MonitoringEvent.zone_id, MonitoringEvent.event_type, func.count()), f.events()
        ).where(MonitoringEvent.zone_id.in_(ids)).group_by(
            MonitoringEvent.zone_id, MonitoringEvent.event_type
        )
        for zid, et, n in db.execute(ev_stmt):
            counts[zid][et] = n
    peaks = {}
    if ids:
        peaks = {
            zid: p
            for zid, p in db.execute(
                select(ZoneOccupancySample.zone_id, func.max(ZoneOccupancySample.occupancy))
                .where(ZoneOccupancySample.zone_id.in_(ids))
                .group_by(ZoneOccupancySample.zone_id)
            )
        }
    out = []
    for z, vname in zones:
        c = counts.get(z.id, {})
        out.append(
            ZoneSummary(
                zone_id=z.id, zone_name=z.name, zone_type=z.zone_type, color=z.color,
                video_id=z.video_id, video_name=vname, enabled=z.enabled,
                entries=c.get(EventType.ZONE_ENTRY, 0) + c.get(EventType.RESTRICTED_ENTRY, 0),
                exits=c.get(EventType.ZONE_EXIT, 0),
                restricted_entries=c.get(EventType.RESTRICTED_ENTRY, 0),
                occupancy_alerts=c.get(EventType.OCCUPANCY_EXCEEDED, 0),
                total_events=sum(c.values()),
                peak_occupancy=peaks.get(z.id),
            )
        )
    return sorted(out, key=lambda s: s.total_events, reverse=True)


def performance(db: Session, f: AnalyticsFilters, limit: int = 50) -> list[PerformancePoint]:
    stmt = (
        select(ProcessingJob, Video)
        .join(Video, Video.id == ProcessingJob.video_id)
        .where(ProcessingJob.status == JobStatus.COMPLETED)
        .order_by(ProcessingJob.finished_at.desc())
        .limit(limit)
    )
    if f.video_id:
        stmt = stmt.where(ProcessingJob.video_id == f.video_id)
    out = []
    for job, video in db.execute(stmt):
        video_seconds = job.frames_processed / video.fps if video.fps else None
        rt = (
            round(video_seconds / job.processing_seconds, 3)
            if video_seconds and job.processing_seconds
            else None
        )
        out.append(
            PerformancePoint(
                job_id=job.id,
                video_name=video.original_filename,
                finished_at=as_utc(job.finished_at) if job.finished_at else None,
                processing_seconds=job.processing_seconds,
                frames_sampled=job.frames_sampled,
                sampled_fps=round(job.sampled_fps, 2) if job.sampled_fps else None,
                realtime_factor=rt,
                device=job.device,
                model_name=job.model_name,
            )
        )
    return out
