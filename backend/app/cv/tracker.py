"""Multi-object tracking via Ultralytics' built-in ByteTrack / BoT-SORT.

A ``TrackingSession`` wraps one model instance whose tracker state persists
across calls, so it must be fed frames of a single video in timeline order.
Track IDs are short-term identities: they can change after occlusion, when an
object leaves and re-enters the frame, or when detections are missed.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from app.cv.detector import RawDetection

TRACKER_CONFIGS = {"bytetrack": "bytetrack.yaml", "botsort": "botsort.yaml"}


class FrameTracker(Protocol):
    def update(self, frame: np.ndarray) -> list[RawDetection]: ...


class TrackingSession:
    def __init__(
        self,
        model: Any,
        *,
        confidence: float,
        image_size: int,
        class_ids: list[int] | None,
        tracker: str = "bytetrack",
        device: str = "cpu",
    ):
        if tracker not in TRACKER_CONFIGS:
            raise ValueError(f"Unsupported tracker '{tracker}'")
        self.model = model
        self.names: dict[int, str] = {int(k): str(v) for k, v in model.names.items()}
        self.kwargs = {
            "persist": True,
            "conf": confidence,
            "imgsz": image_size,
            "classes": class_ids or None,
            "tracker": TRACKER_CONFIGS[tracker],
            "device": device,
            "verbose": False,
        }

    def update(self, frame: np.ndarray) -> list[RawDetection]:
        result = self.model.track(frame, **self.kwargs)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        conf = boxes.conf.cpu().numpy()
        # Ultralytics only returns IDs for confirmed tracks; on frames where no
        # track is active it returns raw detections without IDs.
        ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
        out: list[RawDetection] = []
        for i in range(len(cls)):
            out.append(
                RawDetection(
                    xyxy=tuple(float(v) for v in xyxy[i]),  # type: ignore[arg-type]
                    class_id=int(cls[i]),
                    class_name=self.names.get(int(cls[i]), str(cls[i])),
                    confidence=float(conf[i]),
                    track_id=int(ids[i]) if ids is not None else None,
                )
            )
        return out
