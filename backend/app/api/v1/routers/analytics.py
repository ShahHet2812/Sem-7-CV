from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.db.session import get_db
from app.schemas.analytics import ActivitySeries, ClassCount, Overview, PerformancePoint, ZoneSummary
from app.services import analytics_service as svc
from app.services.analytics_service import AnalyticsFilters

router = APIRouter(prefix="/analytics", tags=["analytics"])


def analytics_filters(
    video_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    class_name: str | None = Query(None, max_length=64),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> AnalyticsFilters:
    if date_from and date_to and date_from > date_to:
        raise ValidationFailed("'date_from' must be before 'date_to'.")
    return AnalyticsFilters(video_id, zone_id, class_name, date_from, date_to)


@router.get("/overview", response_model=Overview)
def overview(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> Overview:
    return svc.overview(db, f)


@router.get("/detections", response_model=list[ClassCount], summary="Detections and tracks by class")
def detections(
    f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)
) -> list[ClassCount]:
    return svc.detections_by_class(db, f)


@router.get(
    "/activity",
    response_model=ActivitySeries,
    summary="Activity over the video timeline (video_id given) or wall-clock time",
)
def activity(
    f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)
) -> ActivitySeries:
    return svc.activity(db, f)


@router.get("/zones", response_model=list[ZoneSummary])
def zones(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> list[ZoneSummary]:
    return svc.zones_summary(db, f)


@router.get("/performance", response_model=list[PerformancePoint])
def performance(
    f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)
) -> list[PerformancePoint]:
    return svc.performance(db, f)
