from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import MonitoringZone
from app.schemas.zone import OccupancyPoint, ZoneOut, ZoneUpdate
from app.services import zone_service
from app.services.snapshots import generate_missing_snapshots

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("", response_model=list[ZoneOut], summary="List zones across all videos")
def list_all_zones(
    video_id: uuid.UUID | None = Query(None), db: Session = Depends(get_db)
) -> list[ZoneOut]:
    stmt = select(MonitoringZone).order_by(MonitoringZone.created_at.desc()).limit(500)
    if video_id:
        stmt = stmt.where(MonitoringZone.video_id == video_id)
    return zone_service.outs(db, db.scalars(stmt).all())


@router.get("/{zone_id}", response_model=ZoneOut)
def get_zone(zone_id: uuid.UUID, db: Session = Depends(get_db)) -> ZoneOut:
    return zone_service.outs(db, [zone_service.require_zone(db, zone_id)])[0]


@router.patch("/{zone_id}", response_model=ZoneOut)
def update_zone(
    zone_id: uuid.UUID,
    data: ZoneUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ZoneOut:
    zone = zone_service.update_zone(db, settings, zone_service.require_zone(db, zone_id), data)
    background.add_task(generate_missing_snapshots, zone.video_id)
    return zone_service.outs(db, [zone])[0]


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(zone_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    zone_service.delete_zone(db, zone_service.require_zone(db, zone_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{zone_id}/occupancy",
    response_model=list[OccupancyPoint],
    summary="Occupancy change-points on the source-video timeline",
)
def zone_occupancy(zone_id: uuid.UUID, db: Session = Depends(get_db)) -> list[OccupancyPoint]:
    return zone_service.occupancy_series(db, zone_service.require_zone(db, zone_id))
