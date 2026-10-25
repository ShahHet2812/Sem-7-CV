from fastapi import APIRouter

from app.api.v1.routers import analytics, events, health, jobs, settings, videos, zones

api_router = APIRouter(prefix="/api/v1")
for r in (health.router, videos.router, zones.router, jobs.router, events.router, analytics.router, settings.router):
    api_router.include_router(r)
