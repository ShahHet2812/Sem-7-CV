"""Render JPEG evidence snapshots for monitoring events (best effort)."""

from __future__ import annotations

import logging
import uuid

import cv2
import numpy as np
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import MonitoringEvent, MonitoringZone, ProcessingJob, Video
from app.services.storage import VideoStorage

logger = logging.getLogger(__name__)

MAX_SNAPSHOTS_PER_RUN = 300
SNAPSHOT_WIDTH = 640


def _hex_to_bgr(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return (238, 211, 34)
    return (b, g, r)


def render(frame: np.ndarray, event: MonitoringEvent, zone: MonitoringZone | None) -> np.ndarray:
    h, w = frame.shape[:2]
    img = frame.copy()
    if zone is not None:
        pts = np.array([[round(x * w), round(y * h)] for x, y in zone.polygon], dtype=np.int32)
        overlay = img.copy()
        color = _hex_to_bgr(zone.color)
        cv2.fillPoly(overlay, [pts], color)
        img = cv2.addWeighted(overlay, 0.18, img, 0.82, 0)
        cv2.polylines(img, [pts], True, color, max(2, w // 400))
    if event.bbox:
        x1, y1, x2, y2 = event.bbox
        p1, p2 = (round(x1 * w), round(y1 * h)), (round(x2 * w), round(y2 * h))
        cv2.rectangle(img, p1, p2, (0, 0, 255), max(2, w // 320))
        label = f"{event.class_name or ''} #{event.track_id}" if event.track_id is not None else ""
        if label:
            cv2.putText(img, label, (p1[0], max(16, p1[1] - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        max(0.5, w / 1600), (0, 0, 255), 2, cv2.LINE_AA)
    if w > SNAPSHOT_WIDTH:
        img = cv2.resize(img, (SNAPSHOT_WIDTH, round(h * SNAPSHOT_WIDTH / w)))
    return img


def generate_missing_snapshots(video_id: uuid.UUID) -> int:
    """Create snapshots for current-job events of a video that lack one."""
    settings = get_settings()
    storage = VideoStorage(settings)
    created = 0
    try:
        with session_scope() as db:
            video = db.get(Video, video_id)
            if video is None:
                return 0
            path = storage.upload_path(video.storage_filename)
            if path is None or not path.is_file():
                return 0
            events = db.scalars(
                select(MonitoringEvent)
                .join(ProcessingJob, ProcessingJob.id == MonitoringEvent.job_id)
                .where(
                    MonitoringEvent.video_id == video_id,
                    ProcessingJob.is_current.is_(True),
                    MonitoringEvent.snapshot_filename.is_(None),
                    MonitoringEvent.frame_index.is_not(None),
                )
                .order_by(MonitoringEvent.frame_index)
                .limit(MAX_SNAPSHOTS_PER_RUN)
            ).all()
            if not events:
                return 0
            zones = {z.id: z for z in db.scalars(
                select(MonitoringZone).where(MonitoringZone.video_id == video_id)
            )}
            out_dir = storage.snapshot_dir(video_id)
            cap = cv2.VideoCapture(str(path))
            try:
                pos = 0
                frame = None
                for ev in events:
                    target = int(ev.frame_index or 0)
                    if frame is None or target != pos - 1:
                        # Sequential grab is cheaper than seeking for short gaps.
                        if target >= pos and target - pos < 60:
                            while pos < target and cap.grab():
                                pos += 1
                        else:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                            pos = target
                        ok, frame = cap.read()
                        if not ok:
                            frame = None
                            continue
                        pos += 1
                    img = render(frame, ev, zones.get(ev.zone_id) if ev.zone_id else None)
                    name = f"{ev.id.hex}.jpg"
                    if cv2.imwrite(str(out_dir / name), img, [cv2.IMWRITE_JPEG_QUALITY, 80]):
                        ev.snapshot_filename = name
                        created += 1
            finally:
                cap.release()
    except Exception:  # noqa: BLE001 - snapshots are optional evidence
        logger.exception("Snapshot generation failed", extra={"video_id": video_id})
    return created
