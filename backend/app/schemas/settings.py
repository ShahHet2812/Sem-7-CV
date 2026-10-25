from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProcessingSettings(BaseModel):
    confidence_threshold: float = Field(ge=0.05, le=0.95)
    image_size: int = Field(ge=160, le=1920, multiple_of=32)
    target_sample_fps: float = Field(gt=0, le=60)
    classes: list[str] = Field(default_factory=list, max_length=80)
    tracker: Literal["bytetrack", "botsort"] = "bytetrack"
    zone_confirm_samples: int = Field(default=2, ge=1, le=10)
    track_lost_timeout: float = Field(default=2.0, ge=0.2, le=60)
    occupancy_alert_cooldown: float = Field(default=10.0, ge=0, le=3600)
    anchor_mode: Literal["bottom_center", "center"] = "bottom_center"
    edge_entries: bool = True
    generate_snapshots: bool = True

    @field_validator("classes")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return sorted({c.strip() for c in v if c.strip()})


class ProcessingSettingsUpdate(BaseModel):
    confidence_threshold: float | None = Field(default=None, ge=0.05, le=0.95)
    image_size: int | None = Field(default=None, ge=160, le=1920, multiple_of=32)
    target_sample_fps: float | None = Field(default=None, gt=0, le=60)
    classes: list[str] | None = Field(default=None, max_length=80)
    tracker: Literal["bytetrack", "botsort"] | None = None
    zone_confirm_samples: int | None = Field(default=None, ge=1, le=10)
    track_lost_timeout: float | None = Field(default=None, ge=0.2, le=60)
    occupancy_alert_cooldown: float | None = Field(default=None, ge=0, le=3600)
    anchor_mode: Literal["bottom_center", "center"] | None = None
    edge_entries: bool | None = None
    generate_snapshots: bool | None = None


class SettingsUpdate(BaseModel):
    processing: ProcessingSettingsUpdate


class SettingsOut(BaseModel):
    processing: ProcessingSettings
    model: dict[str, Any]
    supported_classes: list[str]
    upload: dict[str, Any]
    storage: dict[str, Any]
    system: dict[str, Any]
