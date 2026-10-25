"""Test configuration.

Tests use an isolated SQLite database and storage directory created via the
real Alembic migrations, no background worker, and a scripted fake tracker
instead of YOLO, so they run offline without model weights or a GPU.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="zonevision-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "STORAGE_DIR": str(_TMP / "storage"),
        "WORKER_ENABLED": "false",
        "MODEL_AUTO_DOWNLOAD": "false",
        "MODEL_WEIGHTS": "not-downloaded-in-tests.pt",
        "LOG_LEVEL": "WARNING",
        "MAX_UPLOAD_MB": "20",
    }
)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.config import BACKEND_DIR, get_settings  # noqa: E402
from app.cv.detector import RawDetection  # noqa: E402
from app.cv.processor import TrackerHandle, VideoProcessor  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.workers.job_worker import JobWorker  # noqa: E402


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _database():
    command.upgrade(alembic_config(os.environ["DATABASE_URL"]), "head")
    yield
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(delete(table))
    for sub in ("uploads", "snapshots", "processed"):
        shutil.rmtree(get_settings().storage_dir / sub, ignore_errors=True)
    get_settings().ensure_directories()


@pytest.fixture
def client():
    from app.main import create_app

    with TestClient(create_app(start_worker=False)) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def write_video(path: Path, *, frames: int = 40, fps: float = 10.0, size=(160, 120)) -> Path:
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert writer.isOpened(), "OpenCV cannot write mp4v test videos in this environment"
    for i in range(frames):
        img = np.full((h, w, 3), 40, np.uint8)
        x = int(i / max(1, frames - 1) * (w - 20))
        cv2.rectangle(img, (x, h // 2 - 10), (x + 20, h // 2 + 10), (0, 200, 255), -1)
        writer.write(img)
    writer.release()
    return path


@pytest.fixture
def video_file(tmp_path) -> Path:
    return write_video(tmp_path / "walk.mp4")


class ScriptedTracker:
    """Moves one 'person' (track 1) from the left to the right edge.

    The bottom-center anchor x goes from ~0.05 to ~0.95 over the video, so a
    zone covering the right half is entered exactly once.
    """

    def __init__(self, total_frames: int = 40):
        self.calls = 0
        self.total = total_frames

    def update(self, frame: np.ndarray) -> list[RawDetection]:
        h, w = frame.shape[:2]
        i = self.calls
        self.calls += 1
        cx = (0.05 + 0.9 * min(1.0, i / max(1, self.total // 2 - 1))) * w
        return [
            RawDetection(
                xyxy=(cx - 8, h * 0.3, cx + 8, h * 0.9),
                class_id=0, class_name="person", confidence=0.9, track_id=1,
            )
        ]


def fake_factory(config) -> TrackerHandle:
    return TrackerHandle(ScriptedTracker(), "fake-model", "cpu")


@pytest.fixture
def run_worker():
    """Run queued jobs synchronously with a given tracker factory."""

    def _run(factory=fake_factory) -> list:
        worker = JobWorker(VideoProcessor(tracker_factory=factory))
        done = []
        while (job_id := worker.run_once()) is not None:
            done.append(job_id)
        return done

    return _run


def upload(client: TestClient, path: Path, name: str | None = None):
    with path.open("rb") as fh:
        return client.post("/api/v1/videos", files={"file": (name or path.name, fh, "video/mp4")})
