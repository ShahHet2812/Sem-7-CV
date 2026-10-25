from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_queue
from app.db.session import get_db
from app.models.enums import JobStatus
from app.schemas.common import Page, PageParams
from app.schemas.job import JobOut
from app.services import job_service
from app.services.serializers import job_out
from app.workers.job_worker import JobQueue

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobOut])
def list_jobs(
    video_id: uuid.UUID | None = None,
    status: JobStatus | None = Query(None),
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
) -> Page[JobOut]:
    return job_service.list_jobs(
        db, video_id=video_id, status=status.value if status else None, page=page
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    return job_out(job_service.require_job(db, job_id))


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(
    job_id: uuid.UUID, db: Session = Depends(get_db), queue: JobQueue = Depends(get_queue)
) -> JobOut:
    return job_out(job_service.retry(db, queue, job_service.require_job(db, job_id)))


@router.post("/{job_id}/cancel", response_model=JobOut, status_code=202)
def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobOut:
    return job_out(job_service.cancel(db, job_service.require_job(db, job_id)))
