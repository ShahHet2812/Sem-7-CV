from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.models import MonitoringZone, Video
from app.models.enums import ZoneType
from app.repositories import jobs as jobs_repo
from app.repositories import zones as repo
from app.schemas.zone import OccupancyPoint, ZoneCreate, ZoneOut, ZoneUpdate
from app.services import settings_service
from app.services.serializers import zone_out
from app.services.zone_analysis import recompute_zone_events, refresh_event_count

# Fields whose change alters zone semantics and therefore requires recomputing events.
SEMANTIC_FIELDS = {
    "polygon", "enabled", "emit_entries", "emit_exits", "occupancy_threshold",
    "class_filter", "zone_type",
}

TYPE_DEFAULTS: dict[str, tuple[bool, bool]] = {
    ZoneType.GENERAL: (True, True),
    ZoneType.ENTRY: (True, False),
    ZoneType.EXIT: (False, True),
    ZoneType.RESTRICTED: (True, True),
}


def require_zone(db: Session, zone_id: uuid.UUID) -> MonitoringZone:
    zone = repo.get(db, zone_id)
    if zone is None:
        raise NotFoundError("Zone not found.")
    return zone


def outs(db: Session, zones: Sequence[MonitoringZone]) -> list[ZoneOut]:
    ids = [z.id for z in zones]
    counts = repo.event_counts(db, ids)
    peaks = repo.peak_occupancy(db, ids)
    return [zone_out(z, counts.get(z.id), peaks.get(z.id)) for z in zones]


def list_for_video(db: Session, video_id: uuid.UUID) -> list[ZoneOut]:
    return outs(db, repo.for_video(db, video_id))


def _recompute(db: Session, settings: Settings, video: Video, zones: Sequence[MonitoringZone]) -> int:
    job = jobs_repo.current_for_video(db, video.id)
    if job is None:
        return 0
    params = settings_service.get_processing(db, settings)
    return recompute_zone_events(db, video, job, zones, params)


def create_zone(db: Session, settings: Settings, video: Video, data: ZoneCreate) -> MonitoringZone:
    if repo.name_taken(db, video.id, data.name):
        raise ConflictError(f"A zone named '{data.name}' already exists for this video.")
    d_entries, d_exits = TYPE_DEFAULTS[data.zone_type]
    zone = MonitoringZone(
        video_id=video.id,
        name=data.name,
        zone_type=data.zone_type.value,
        color=data.color.lower(),
        polygon=data.polygon,
        enabled=data.enabled,
        emit_entries=d_entries if data.emit_entries is None else data.emit_entries,
        emit_exits=d_exits if data.emit_exits is None else data.emit_exits,
        occupancy_threshold=data.occupancy_threshold,
        class_filter=data.class_filter,
    )
    db.add(zone)
    db.flush()
    _recompute(db, settings, video, [zone])
    db.commit()
    return zone


def update_zone(db: Session, settings: Settings, zone: MonitoringZone, data: ZoneUpdate) -> MonitoringZone:
    fields = data.model_dump(exclude_unset=True)
    nullable = {"occupancy_threshold", "class_filter"}
    fields = {k: v for k, v in fields.items() if v is not None or k in nullable}
    if "name" in fields and repo.name_taken(db, zone.video_id, fields["name"], exclude_id=zone.id):
        raise ConflictError(f"A zone named '{fields['name']}' already exists for this video.")
    if "zone_type" in fields:
        fields["zone_type"] = ZoneType(fields["zone_type"]).value
        d_entries, d_exits = TYPE_DEFAULTS[fields["zone_type"]]
        fields.setdefault("emit_entries", d_entries)
        fields.setdefault("emit_exits", d_exits)
    if "color" in fields:
        fields["color"] = fields["color"].lower()
    changed = {k for k, v in fields.items() if getattr(zone, k) != v}
    for k in changed:
        setattr(zone, k, fields[k])
    db.flush()
    if changed & SEMANTIC_FIELDS:
        _recompute(db, settings, zone.video, [zone])
    db.commit()
    return zone


def delete_zone(db: Session, zone: MonitoringZone) -> None:
    video_id = zone.video_id
    db.delete(zone)
    db.flush()
    job = jobs_repo.current_for_video(db, video_id)
    if job is not None:
        refresh_event_count(db, job)
    db.commit()


def recompute_all(db: Session, settings: Settings, video: Video) -> tuple[int, int, uuid.UUID | None]:
    zones = repo.for_video(db, video.id)
    job = jobs_repo.current_for_video(db, video.id)
    n = _recompute(db, settings, video, zones) if zones else 0
    db.commit()
    return len(zones), n, job.id if job else None


def occupancy_series(db: Session, zone: MonitoringZone, max_points: int = 2000) -> list[OccupancyPoint]:
    rows = repo.occupancy_series(db, zone.id)
    pts = [OccupancyPoint(t=r.timestamp, occupancy=r.occupancy) for r in rows]
    if len(pts) <= max_points:
        return pts
    # Keep per-bucket maxima so peaks survive downsampling.
    step = len(pts) / max_points
    out: list[OccupancyPoint] = []
    i = 0.0
    while int(i) < len(pts):
        chunk = pts[int(i): int(i + step) or int(i) + 1]
        out.append(max(chunk, key=lambda p: p.occupancy).model_copy(update={"t": chunk[0].t}))
        i += step
    return out
