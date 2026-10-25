from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.api import api_router
from app.api.v1.routers import health
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(*, start_worker: bool | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    settings.ensure_directories()
    # Keep Ultralytics' settings file inside project storage (writable in Docker too).
    os.environ.setdefault("YOLO_CONFIG_DIR", str(settings.storage_dir / "ultralytics"))
    run_worker = settings.worker_enabled if start_worker is None else start_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker = None
        if run_worker:
            from app.workers.job_worker import JobWorker

            worker = JobWorker(poll_interval=settings.worker_poll_interval)
            try:
                worker.start()
            except Exception:  # noqa: BLE001 - API stays up; health reports the worker down
                logger.exception("Could not start job worker (is the database reachable?)")
            app.state.worker = worker
        logger.info("%s API %s started (%s)", settings.app_name, __version__, settings.environment)
        yield
        if worker is not None:
            worker.stop()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description=(
            "Vision-Based Object Detection and Zone Monitoring Platform. "
            "Upload videos, run YOLO detection + ByteTrack tracking, define polygon zones, "
            "and query zone events and analytics."
        ),
        lifespan=lifespan,
    )
    app.state.worker = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Content-Range", "Accept-Ranges"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)  # GET /health
    app.include_router(api_router)  # /api/v1/...
    return app


app = create_app()
