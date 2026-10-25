from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_storage
from app.core.errors import NotFoundError
from app.db.session import SessionLocal, get_db
from app.models.enums import EventStatus, EventType
from app.repositories.events import EventFilters
from app.schemas.common import Page, PageParams
from app.schemas.event import BulkStatusResult, BulkStatusUpdate, EventOut, EventUpdate
from app.services import event_service
from app.services.serializers import event_out
from app.services.storage import VideoStorage

router = APIRouter(prefix="/events", tags=["events"])

SortField = Literal["occurred_at", "video_timestamp", "event_type", "class_name", "confidence"]


def event_filters(
    q: str | None = Query(None, max_length=200, description="Search video, zone, class, type, notes"),
    video_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    event_type: list[EventType] | None = Query(None),
    class_name: str | None = Query(None, max_length=64),
    status: EventStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    track_id: int | None = Query(None, ge=0),
) -> EventFilters:
    return EventFilters(
        q=q.strip() if q and q.strip() else None,
        video_id=video_id,
        zone_id=zone_id,
        event_types=[e.value for e in event_type] if event_type else None,
        class_name=class_name,
        status=status.value if status else None,
        date_from=date_from,
        date_to=date_to,
        track_id=track_id,
    )


@router.get("", response_model=Page[EventOut])
def list_events(
    f: EventFilters = Depends(event_filters),
    sort: SortField = "occurred_at",
    order: Literal["asc", "desc"] = "desc",
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
) -> Page[EventOut]:
    return event_service.list_events(db, f, sort=sort, order=order, page=page)


@router.get("/export", summary="Export filtered events as CSV", response_class=StreamingResponse)
def export_events(
    f: EventFilters = Depends(event_filters),
    sort: SortField = "occurred_at",
    order: Literal["asc", "desc"] = "desc",
) -> StreamingResponse:
    def stream() -> Iterator[str]:
        # The request-scoped session is closed before streaming starts,
        # so the generator owns its own session.
        db = SessionLocal()
        try:
            yield from event_service.export_csv(db, f, sort=sort, order=order)
        finally:
            db.close()

    name = f"zonevision-events-{datetime.now(UTC):%Y%m%d-%H%M%S}.csv"
    return StreamingResponse(
        stream(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.post("/bulk-status", response_model=BulkStatusResult)
def bulk_status(data: BulkStatusUpdate, db: Session = Depends(get_db)) -> BulkStatusResult:
    return BulkStatusResult(updated=event_service.bulk_status(db, data.ids, data.status))


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)) -> EventOut:
    return event_out(event_service.require_event(db, event_id))


@router.patch("/{event_id}", response_model=EventOut)
def update_event(event_id: uuid.UUID, data: EventUpdate, db: Session = Depends(get_db)) -> EventOut:
    ev = event_service.update_event(db, event_service.require_event(db, event_id), data)
    return event_out(event_service.require_event(db, ev.id))


@router.get("/{event_id}/snapshot", response_class=FileResponse)
def event_snapshot(
    event_id: uuid.UUID, db: Session = Depends(get_db), storage: VideoStorage = Depends(get_storage)
) -> FileResponse:
    ev = event_service.require_event(db, event_id)
    path = storage.snapshot_path(ev.video_id, ev.snapshot_filename)
    if path is None or not path.is_file():
        raise NotFoundError("No snapshot available for this event.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
