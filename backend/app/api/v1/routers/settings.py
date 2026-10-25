from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_provider
from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailable
from app.cv.detector import ModelUnavailableError, YoloModelProvider
from app.db.session import get_db
from app.schemas.settings import SettingsOut, SettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: YoloModelProvider = Depends(get_provider),
) -> SettingsOut:
    return settings_service.build_settings_out(db, settings, provider)


@router.patch("", response_model=SettingsOut)
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: YoloModelProvider = Depends(get_provider),
) -> SettingsOut:
    settings_service.update_processing(db, settings, provider, data.processing)
    return settings_service.build_settings_out(db, settings, provider)


@router.post(
    "/model/load",
    response_model=SettingsOut,
    summary="Load (and if needed download) the configured model weights",
)
def load_model(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: YoloModelProvider = Depends(get_provider),
) -> SettingsOut:
    try:
        provider.create_model()
    except ModelUnavailableError as exc:
        raise ServiceUnavailable(str(exc), code="model_unavailable") from exc
    return settings_service.build_settings_out(db, settings, provider)
