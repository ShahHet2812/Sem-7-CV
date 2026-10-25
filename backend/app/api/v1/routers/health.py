from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import get_provider
from app.core.config import Settings, get_settings
from app.cv.detector import YoloModelProvider
from app.db.session import check_database

router = APIRouter(tags=["health"])


def health_payload(request: Request, settings: Settings, provider: YoloModelProvider) -> tuple[int, dict]:
    db_ok, db_error = check_database()
    storage_ok = settings.uploads_dir.is_dir() and os.access(settings.uploads_dir, os.W_OK)
    worker = getattr(request.app.state, "worker", None)
    worker_ok = worker.alive if worker is not None else not settings.worker_enabled
    model = provider.status()
    checks = {
        "database": {"ok": db_ok, "error": db_error},
        "storage": {"ok": storage_ok},
        "worker": {"ok": worker_ok, "enabled": settings.worker_enabled},
        # Model weights are downloaded lazily, so missing weights only degrade.
        "model": {"ok": model["weights_present"] or model["auto_download"], **model},
    }
    critical_ok = db_ok and storage_ok
    status = "ok" if critical_ok and all(c["ok"] for c in checks.values()) else (
        "degraded" if critical_ok else "unavailable"
    )
    body = {"status": status, "version": __version__, "environment": settings.environment, "checks": checks}
    return (200 if critical_ok else 503), body


@router.get("/health", summary="Dependency-aware health check")
def health(
    request: Request,
    settings: Settings = Depends(get_settings),
    provider: YoloModelProvider = Depends(get_provider),
) -> JSONResponse:
    code, body = health_payload(request, settings, provider)
    return JSONResponse(status_code=code, content=body)
