from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import MonitoringEvent
from app.models.enums import EVENT_SEVERITY, EventStatus
from app.repositories import events as repo
from app.repositories.events import EventFilters
from app.schemas.common import Page, PageParams
from app.schemas.event import EventOut, EventUpdate
from app.services.serializers import event_out
from app.services.time_utils import as_utc

EXPORT_LIMIT = 100_000


def require_event(db: Session, event_id: uuid.UUID) -> MonitoringEvent:
    ev = repo.get(db, event_id)
    if ev is None:
        raise NotFoundError("Event not found.")
    return ev


def list_events(
    db: Session, f: EventFilters, *, sort: str, order: str, page: PageParams
) -> Page[EventOut]:
    total = repo.count(db, f)
    rows = repo.query(db, f, sort=sort, order=order, offset=page.offset, limit=page.page_size)
    return Page[EventOut].build([event_out(e) for e in rows], total, page.page, page.page_size)


def _apply_status(ev: MonitoringEvent, status: str) -> None:
    ev.status = status
    ev.reviewed_at = None if status == EventStatus.NEW else datetime.now(UTC)


def update_event(db: Session, ev: MonitoringEvent, data: EventUpdate) -> MonitoringEvent:
    fields = data.model_dump(exclude_unset=True)
    if fields.get("status"):
        _apply_status(ev, EventStatus(fields["status"]).value)
    if "notes" in fields:
        ev.notes = (fields["notes"] or "").strip() or None
    db.commit()
    return ev


def bulk_status(db: Session, ids: list[uuid.UUID], status: EventStatus) -> int:
    events = db.scalars(select(MonitoringEvent).where(MonitoringEvent.id.in_(ids))).all()
    for ev in events:
        _apply_status(ev, status.value)
    db.commit()
    return len(events)


CSV_COLUMNS = [
    "event_id", "occurred_at_utc", "video_timestamp_s", "frame_index", "event_type", "severity",
    "video", "zone", "class_name", "track_id", "confidence", "occupancy", "status", "notes",
]


def _safe_cell(value: object) -> object:
    # Neutralize spreadsheet formula injection (=, +, -, @ prefixes).
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def export_csv(db: Session, f: EventFilters, *, sort: str, order: str) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    yield buf.getvalue()
    offset, batch = 0, 1000
    while offset < EXPORT_LIMIT:
        rows = repo.query(db, f, sort=sort, order=order, offset=offset, limit=batch)
        if not rows:
            break
        buf.seek(0)
        buf.truncate()
        for e in rows:
            writer.writerow(
                [_safe_cell(v) for v in (
                    str(e.id),
                    as_utc(e.occurred_at).isoformat(),
                    e.video_timestamp,
                    e.frame_index,
                    e.event_type,
                    EVENT_SEVERITY.get(e.event_type, "info"),
                    e.video.original_filename if e.video else "",
                    e.zone.name if e.zone else "",
                    e.class_name or "",
                    e.track_id if e.track_id is not None else "",
                    e.confidence if e.confidence is not None else "",
                    e.occupancy if e.occupancy is not None else "",
                    e.status,
                    e.notes or "",
                )]
            )
        yield buf.getvalue()
        offset += batch
