"""ORM -> API schema conversion shared by services."""

from __future__ import annotations

from app.models import MonitoringEvent, MonitoringZone, ProcessingJob, Video
from app.models.enums import EVENT_SEVERITY
from app.schemas.event import EventOut
from app.schemas.job import JobOut
from app.schemas.video import VideoOut
from app.schemas.zone import ZoneOut, ZoneStats
from app.services.storage import is_browser_playable
from app.services.time_utils import as_utc

API = "/api/v1"


def job_out(job: ProcessingJob, video_name: str | None = None) -> JobOut:
    out = JobOut.model_validate(job)
    out.video_name = video_name if video_name is not None else (job.video.original_filename if job.video else None)
    return out


def video_out(
    video: Video,
    *,
    latest_job: ProcessingJob | None = None,
    current_job: ProcessingJob | None = None,
    zone_count: int = 0,
    event_count: int = 0,
) -> VideoOut:
    out = VideoOut.model_validate(
        {
            **{c: getattr(video, c) for c in VideoOut.model_fields if hasattr(video, c)},
            "thumbnail_url": f"{API}/videos/{video.id}/preview" if video.thumbnail_filename else None,
            "stream_url": f"{API}/videos/{video.id}/stream",
            "download_url": f"{API}/videos/{video.id}/download",
            "browser_playable": is_browser_playable(video.container_format, video.codec),
            "latest_job": job_out(latest_job, video.original_filename) if latest_job else None,
            "current_job_id": current_job.id if current_job else None,
            "zone_count": zone_count,
            "event_count": event_count,
            "detection_count": current_job.detection_count if current_job else 0,
        }
    )
    out.created_at = as_utc(out.created_at)
    out.updated_at = as_utc(out.updated_at)
    return out


def event_out(e: MonitoringEvent) -> EventOut:
    return EventOut(
        id=e.id,
        video_id=e.video_id,
        video_name=e.video.original_filename if e.video else None,
        zone_id=e.zone_id,
        zone_name=e.zone.name if e.zone else None,
        zone_color=e.zone.color if e.zone else None,
        job_id=e.job_id,
        event_type=e.event_type,
        severity=EVENT_SEVERITY.get(e.event_type, "info"),
        video_timestamp=e.video_timestamp,
        frame_index=e.frame_index,
        occurred_at=as_utc(e.occurred_at),
        class_name=e.class_name,
        track_id=e.track_id,
        confidence=e.confidence,
        occupancy=e.occupancy,
        bbox=e.bbox,
        status=e.status,
        notes=e.notes,
        snapshot_url=f"{API}/events/{e.id}/snapshot" if e.snapshot_filename else None,
        details=e.details or {},
        created_at=as_utc(e.created_at),
        reviewed_at=as_utc(e.reviewed_at) if e.reviewed_at else None,
    )


def zone_out(
    zone: MonitoringZone, counts: dict[str, int] | None = None, peak: int | None = None
) -> ZoneOut:
    counts = counts or {}
    out = ZoneOut.model_validate(zone)
    out.stats = ZoneStats(
        entries=counts.get("zone_entry", 0) + counts.get("restricted_entry", 0),
        exits=counts.get("zone_exit", 0),
        restricted_entries=counts.get("restricted_entry", 0),
        occupancy_alerts=counts.get("occupancy_exceeded", 0),
        peak_occupancy=peak,
    )
    return out
