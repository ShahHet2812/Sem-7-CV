from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_provider, get_queue, get_storage
from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, PayloadTooLarge, ServiceUnavailable, ValidationFailed
from app.cv.detector import YoloModelProvider
from app.db.session import get_db
from app.repositories import detections as det_repo
from app.repositories import jobs as jobs_repo
from app.repositories.events import EventFilters
from app.schemas.common import Page, PageParams
from app.schemas.detection import DetectionOut, DetectionWindow, FrameDetections
from app.schemas.event import EventOut
from app.schemas.job import JobOut
from app.schemas.video import ProcessRequest, VideoOut, VideoUpdate
from app.schemas.zone import ZoneCreate, ZoneOut, ZoneRecomputeResult
from app.services import event_service, video_service, zone_service
from app.services.serializers import job_out
from app.services.snapshots import generate_missing_snapshots
from app.services.storage import VideoStorage
from app.workers.job_worker import JobQueue

router = APIRouter(prefix="/videos", tags=["videos"])

MAX_WINDOW_SECONDS = 120.0
MAX_WINDOW_ROWS = 20_000


@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED, summary="Upload a video")
def upload_video(
    request: Request,
    file: UploadFile = File(..., description="MP4, MOV, AVI, MKV, WEBM or M4V video"),
    recorded_at: datetime | None = Form(None, description="Optional wall-clock start of the footage"),
    db: Session = Depends(get_db),
    storage: VideoStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> VideoOut:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_upload_bytes + 1024 * 1024:
        raise PayloadTooLarge(f"File exceeds the maximum upload size of {settings.max_upload_mb} MB.")
    stored = storage.save_upload(file)
    try:
        video = video_service.register(db, stored, recorded_at=recorded_at)
    except Exception:
        storage.delete_video_files(uuid.uuid4(), stored.storage_filename, stored.thumbnail_filename)
        raise
    return video_service.get_out(db, video.id)


@router.post(
    "/sample",
    response_model=VideoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Import the optional public sample video (requires internet access)",
)
def import_sample(
    db: Session = Depends(get_db),
    storage: VideoStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> VideoOut:
    try:
        stored = storage.import_from_url(settings.sample_video_url, "sample-people-detection.mp4")
    except (ValidationFailed, PayloadTooLarge):
        raise
    except Exception as exc:  # noqa: BLE001 - network problems
        raise ServiceUnavailable(
            "The sample video could not be downloaded. Check internet access or upload your own video.",
            code="sample_download_failed",
        ) from exc
    video = video_service.register(db, stored, is_sample=True)
    return video_service.get_out(db, video.id)


@router.get("", response_model=Page[VideoOut], summary="List videos")
def list_videos(
    q: str | None = Query(None, max_length=200),
    status_: str | None = Query(None, alias="status"),
    sort: Literal["created_at", "original_filename", "file_size", "duration_seconds", "status"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
) -> Page[VideoOut]:
    return video_service.list_videos(db, q=q, status=status_, sort=sort, order=order, page=page)


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: uuid.UUID, db: Session = Depends(get_db)) -> VideoOut:
    return video_service.get_out(db, video_id)


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(video_id: uuid.UUID, data: VideoUpdate, db: Session = Depends(get_db)) -> VideoOut:
    video = video_service.require_video(db, video_id)
    video_service.update_video(db, video, data)
    return video_service.get_out(db, video_id)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: uuid.UUID, db: Session = Depends(get_db), storage: VideoStorage = Depends(get_storage)
) -> Response:
    video_service.delete_video(db, storage, video_service.require_video(db, video_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{video_id}/process",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a processing job",
)
def process_video(
    video_id: uuid.UUID,
    body: ProcessRequest | None = Body(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    provider: YoloModelProvider = Depends(get_provider),
    queue: JobQueue = Depends(get_queue),
) -> JobOut:
    video = video_service.require_video(db, video_id)
    job = video_service.queue_processing(db, settings, provider, queue, video, body)
    return job_out(job, video.original_filename)


@router.get(
    "/{video_id}/detections",
    response_model=DetectionWindow,
    summary="Detections of the current job in a time window, grouped by sampled frame",
)
def get_detections(
    video_id: uuid.UUID,
    start: float = Query(0.0, ge=0),
    end: float | None = Query(None, gt=0),
    classes: list[str] | None = Query(None),
    min_confidence: float | None = Query(None, ge=0, le=1),
    db: Session = Depends(get_db),
) -> DetectionWindow:
    video = video_service.require_video(db, video_id)
    end = end if end is not None else start + 30.0
    if end <= start:
        raise ValidationFailed("'end' must be greater than 'start'.")
    if end - start > MAX_WINDOW_SECONDS:
        raise ValidationFailed(f"Time window may not exceed {MAX_WINDOW_SECONDS:.0f} seconds.")
    job = jobs_repo.current_for_video(db, video.id)
    frames: list[FrameDetections] = []
    truncated = False
    if job is not None:
        rows = det_repo.window(
            db, job.id, start=start, end=end, class_names=classes,
            min_confidence=min_confidence, limit=MAX_WINDOW_ROWS + 1,
        )
        truncated = len(rows) > MAX_WINDOW_ROWS
        by_frame: dict[int, FrameDetections] = {}
        for d in rows[:MAX_WINDOW_ROWS]:
            fr = by_frame.get(d.frame_index)
            if fr is None:
                fr = by_frame[d.frame_index] = FrameDetections(
                    frame_index=d.frame_index, timestamp=d.timestamp, detections=[]
                )
            fr.detections.append(
                DetectionOut(
                    bbox=(d.x1, d.y1, d.x2, d.y2), class_id=d.class_id, class_name=d.class_name,
                    confidence=d.confidence, track_id=d.track_id,
                )
            )
        frames = list(by_frame.values())
    stride = job.frame_stride if job else 1
    return DetectionWindow(
        video_id=video.id,
        job_id=job.id if job else None,
        start=start,
        end=end,
        fps=video.fps,
        frame_stride=stride,
        sample_interval=round(stride / video.fps, 4) if video.fps else None,
        truncated=truncated,
        frames=frames,
    )


@router.get("/{video_id}/events", response_model=Page[EventOut])
def video_events(
    video_id: uuid.UUID,
    event_type: list[str] | None = Query(None),
    zone_id: uuid.UUID | None = None,
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
) -> Page[EventOut]:
    video_service.require_video(db, video_id)
    f = EventFilters(video_id=video_id, zone_id=zone_id, event_types=event_type)
    return event_service.list_events(db, f, sort="video_timestamp", order="asc", page=page)


@router.get("/{video_id}/preview", summary="Thumbnail image", response_class=FileResponse)
def preview(
    video_id: uuid.UUID, db: Session = Depends(get_db), storage: VideoStorage = Depends(get_storage)
) -> FileResponse:
    video = video_service.require_video(db, video_id)
    path = storage.thumbnail_path(video.thumbnail_filename)
    if path is None or not path.is_file():
        raise NotFoundError("No preview available for this video.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


def _video_file(db: Session, storage: VideoStorage, video_id: uuid.UUID):
    video = video_service.require_video(db, video_id)
    path = storage.upload_path(video.storage_filename)
    if path is None or not path.is_file():
        raise NotFoundError("The video file is missing from storage.")
    return video, path


@router.get("/{video_id}/stream", summary="Stream the source video (supports HTTP Range)", response_class=FileResponse)
def stream(
    video_id: uuid.UUID, db: Session = Depends(get_db), storage: VideoStorage = Depends(get_storage)
) -> FileResponse:
    video, path = _video_file(db, storage, video_id)
    return FileResponse(path, media_type=video.content_type, content_disposition_type="inline",
                        filename=video.original_filename)


@router.get("/{video_id}/download", summary="Download the original video", response_class=FileResponse)
def download(
    video_id: uuid.UUID, db: Session = Depends(get_db), storage: VideoStorage = Depends(get_storage)
) -> FileResponse:
    video, path = _video_file(db, storage, video_id)
    return FileResponse(path, media_type=video.content_type, filename=video.original_filename)


@router.get("/{video_id}/zones", response_model=list[ZoneOut], tags=["zones"])
def list_zones(video_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ZoneOut]:
    video_service.require_video(db, video_id)
    return zone_service.list_for_video(db, video_id)


@router.post("/{video_id}/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED, tags=["zones"])
def create_zone(
    video_id: uuid.UUID,
    data: ZoneCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ZoneOut:
    video = video_service.require_video(db, video_id)
    zone = zone_service.create_zone(db, settings, video, data)
    background.add_task(generate_missing_snapshots, video.id)
    return zone_service.outs(db, [zone])[0]


@router.post(
    "/{video_id}/zones/recompute",
    response_model=ZoneRecomputeResult,
    tags=["zones"],
    summary="Rebuild zone events from stored detections using current settings",
)
def recompute_zones(
    video_id: uuid.UUID,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ZoneRecomputeResult:
    video = video_service.require_video(db, video_id)
    zones, events, job_id = zone_service.recompute_all(db, settings, video)
    background.add_task(generate_missing_snapshots, video.id)
    return ZoneRecomputeResult(zones=zones, events=events, job_id=job_id)
