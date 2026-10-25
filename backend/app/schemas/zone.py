from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.cv.geometry import PolygonError, validate_polygon
from app.models.enums import ZoneType
from app.schemas.common import ORMModel

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


def _polygon(value: list[list[float]]) -> list[list[float]]:
    try:
        return validate_polygon(value)
    except PolygonError as exc:
        raise ValueError(str(exc)) from exc


def _classes(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    cleaned = sorted({v.strip() for v in value if v and v.strip()})
    if any(len(v) > 64 for v in cleaned):
        raise ValueError("Class names must be at most 64 characters")
    return cleaned or None


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    zone_type: ZoneType = ZoneType.GENERAL
    color: str = Field(default="#22d3ee", pattern=HEX_COLOR)
    polygon: list[list[float]]
    enabled: bool = True
    emit_entries: bool | None = None
    emit_exits: bool | None = None
    occupancy_threshold: int | None = Field(default=None, ge=0, le=10_000)
    class_filter: list[str] | None = None

    @field_validator("polygon")
    @classmethod
    def _v_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        return _polygon(v)

    @field_validator("class_filter")
    @classmethod
    def _v_classes(cls, v: list[str] | None) -> list[str] | None:
        return _classes(v)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    zone_type: ZoneType | None = None
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    polygon: list[list[float]] | None = None
    enabled: bool | None = None
    emit_entries: bool | None = None
    emit_exits: bool | None = None
    occupancy_threshold: int | None = Field(default=None, ge=0, le=10_000)
    class_filter: list[str] | None = None

    @field_validator("polygon")
    @classmethod
    def _v_polygon(cls, v: list[list[float]] | None) -> list[list[float]] | None:
        return None if v is None else _polygon(v)

    @field_validator("class_filter")
    @classmethod
    def _v_classes(cls, v: list[str] | None) -> list[str] | None:
        return _classes(v)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Name must not be blank")
        return v


class ZoneStats(BaseModel):
    entries: int = 0
    exits: int = 0
    restricted_entries: int = 0
    occupancy_alerts: int = 0
    peak_occupancy: int | None = None


class ZoneOut(ORMModel):
    id: uuid.UUID
    video_id: uuid.UUID
    name: str
    zone_type: str
    color: str
    polygon: list[list[float]]
    enabled: bool
    emit_entries: bool
    emit_exits: bool
    occupancy_threshold: int | None
    class_filter: list[str] | None
    created_at: datetime
    updated_at: datetime
    stats: ZoneStats = ZoneStats()


class OccupancyPoint(BaseModel):
    t: float
    occupancy: int


class ZoneRecomputeResult(BaseModel):
    zones: int
    events: int
    job_id: uuid.UUID | None
