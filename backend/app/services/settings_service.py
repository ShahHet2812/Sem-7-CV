from __future__ import annotations

import platform
import shutil
import sys
from importlib import metadata

from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings
from app.core.errors import ValidationFailed
from app.cv.detector import YoloModelProvider
from app.repositories import settings as repo
from app.schemas.settings import ProcessingSettings, ProcessingSettingsUpdate, SettingsOut
from app.services.storage import ALLOWED_EXTENSIONS

PROCESSING_KEY = "processing"
DEFAULT_CLASSES = ["bicycle", "bus", "car", "motorcycle", "person", "truck"]


def defaults(settings: Settings) -> ProcessingSettings:
    return ProcessingSettings(
        confidence_threshold=settings.default_confidence,
        image_size=settings.default_image_size,
        target_sample_fps=settings.default_target_fps,
        classes=DEFAULT_CLASSES,
    )


def get_processing(db: Session, settings: Settings) -> ProcessingSettings:
    base = defaults(settings).model_dump()
    stored = repo.get_value(db, PROCESSING_KEY) or {}
    merged = {**base, **{k: v for k, v in stored.items() if k in base}}
    try:
        return ProcessingSettings.model_validate(merged)
    except ValueError:
        # Stored values became invalid (e.g. after a schema change): fall back.
        return defaults(settings)


def validate_classes(classes: list[str], provider: YoloModelProvider) -> None:
    names = provider.class_names()
    if names is None or not classes:
        return
    unknown = sorted(set(classes) - set(names.values()))
    if unknown:
        raise ValidationFailed(
            f"Unknown class name(s) for model {provider.model_name}: {', '.join(unknown)}",
            details={"unknown": unknown},
        )


def update_processing(
    db: Session, settings: Settings, provider: YoloModelProvider, update: ProcessingSettingsUpdate
) -> ProcessingSettings:
    current = get_processing(db, settings)
    data = {**current.model_dump(), **update.model_dump(exclude_unset=True, exclude_none=True)}
    new = ProcessingSettings.model_validate(data)
    validate_classes(new.classes, provider)
    repo.set_value(db, PROCESSING_KEY, new.model_dump())
    db.commit()
    return new


def _pkg_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _dir_size(path) -> int:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    return total


def build_settings_out(db: Session, settings: Settings, provider: YoloModelProvider) -> SettingsOut:
    names = provider.class_names()
    disk = shutil.disk_usage(settings.storage_dir) if settings.storage_dir.exists() else None
    return SettingsOut(
        processing=get_processing(db, settings),
        model={
            **provider.status(),
            "source": "Ultralytics YOLO pretrained on COCO (AGPL-3.0)",
            "class_count": len(names) if names else None,
            "trackers": ["bytetrack", "botsort"],
        },
        supported_classes=sorted(names.values()) if names else [],
        upload={
            "max_upload_mb": settings.max_upload_mb,
            "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
            "configured_via": "MAX_UPLOAD_MB environment variable",
        },
        storage={
            "uploads_bytes": _dir_size(settings.uploads_dir),
            "processed_bytes": _dir_size(settings.processed_dir),
            "snapshots_bytes": _dir_size(settings.snapshots_dir),
            "disk_free_bytes": disk.free if disk else None,
            "disk_total_bytes": disk.total if disk else None,
        },
        system={
            "app_name": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "database": "sqlite" if settings.is_sqlite else "postgresql",
            "python": sys.version.split()[0],
            "platform": platform.platform(terse=True),
            "torch": _pkg_version("torch"),
            "opencv": _pkg_version("opencv-python-headless") or _pkg_version("opencv-python"),
            "ultralytics": _pkg_version("ultralytics"),
            "inference_device": provider.device,
            "worker_enabled": settings.worker_enabled,
        },
    )
