"""OpenCV-based video probing and sequential frame sampling."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

FALLBACK_FPS = 25.0


class VideoDecodeError(Exception):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    width: int
    height: int
    fps: float
    fps_estimated: bool
    frame_count: int | None
    duration_seconds: float | None
    codec: str | None


def _fourcc(cap: cv2.VideoCapture) -> str | None:
    code = int(cap.get(cv2.CAP_PROP_FOURCC))
    if code <= 0:
        return None
    chars = "".join(chr((code >> (8 * i)) & 0xFF) for i in range(4))
    return chars.strip("\x00 ").lower() or None


def _open(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise VideoDecodeError(
            "The video could not be opened. The container or codec may be unsupported "
            "by the installed OpenCV/FFmpeg build."
        )
    return cap


def probe_video(path: Path) -> tuple[VideoMetadata, np.ndarray]:
    """Read container metadata and decode the first frame (proves decodability)."""
    cap = _open(path)
    try:
        ok, frame = cap.read()
        if not ok or frame is None or frame.size == 0:
            raise VideoDecodeError(
                "No frames could be decoded. The file may be corrupt or use an unsupported codec."
            )
        height, width = frame.shape[:2]
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps_estimated = not (math.isfinite(fps) and 0.5 < fps < 1000)
        if fps_estimated:
            fps = FALLBACK_FPS
        raw_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        frame_count = int(raw_count) if raw_count and math.isfinite(raw_count) and raw_count > 0 else None
        duration = frame_count / fps if frame_count and not fps_estimated else None
        return (
            VideoMetadata(
                width=width,
                height=height,
                fps=round(fps, 4),
                fps_estimated=fps_estimated,
                frame_count=frame_count,
                duration_seconds=round(duration, 3) if duration else None,
                codec=_fourcc(cap),
            ),
            frame,
        )
    finally:
        cap.release()


@dataclass
class SampledFrame:
    index: int
    timestamp: float  # seconds on the source timeline (index / fps)
    image: np.ndarray


class VideoReader:
    """Decode a video once, sequentially, yielding every ``stride``-th frame.

    Skipped frames use ``grab()`` (no BGR conversion), so each frame is decoded
    at most once and never re-read. Timestamps assume constant frame rate:
    ``t = frame_index / fps``, which is what HTML5 video uses for CFR files.
    """

    def __init__(self, path: Path, fps: float):
        self.path = path
        self.fps = fps
        self.frames_read = 0
        self._cap: cv2.VideoCapture | None = None

    def __enter__(self) -> VideoReader:
        self._cap = _open(self.path)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def iter_sampled(self, stride: int) -> Iterator[SampledFrame]:
        if self._cap is None:
            raise RuntimeError("VideoReader must be used as a context manager")
        stride = max(1, int(stride))
        index = 0
        while True:
            if index % stride == 0:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    break
                self.frames_read = index + 1
                yield SampledFrame(index=index, timestamp=index / self.fps, image=frame)
            else:
                if not self._cap.grab():
                    break
                self.frames_read = index + 1
            index += 1


def read_frame_at(path: Path, frame_index: int) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return None
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


def compute_stride(fps: float, target_fps: float) -> int:
    """Frame stride that approximates ``target_fps`` sampled frames per second."""
    if target_fps <= 0 or target_fps >= fps:
        return 1
    return max(1, round(fps / target_fps))
