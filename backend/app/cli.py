"""Maintenance commands.

    python -m app.cli init-db          # apply migrations (idempotent)
    python -m app.cli download-model   # fetch/verify the configured YOLO weights
    python -m app.cli reset-results    # drop jobs, detections, events; KEEP videos + zones
    python -m app.cli delete-samples   # delete only videos imported as the sample clip
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select, update

from app.core.config import BACKEND_DIR, get_settings


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    print("Database is at the latest migration.")


def download_model() -> None:
    from app.services.model_provider import get_model_provider

    provider = get_model_provider()
    provider.create_model()
    print(f"Model ready: {provider.weights_path} ({len(provider.class_names() or {})} classes, device={provider.device})")


def _confirm(msg: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{msg} Type 'yes' to continue: ").strip().lower() == "yes"


def reset_results(assume_yes: bool) -> None:
    import shutil

    from app.db.session import session_scope
    from app.models import (
        Detection,
        MonitoringEvent,
        ProcessingJob,
        TrackSummary,
        Video,
        ZoneOccupancySample,
    )
    from app.models.enums import JobStatus, VideoStatus

    if not _confirm("This deletes all processing jobs, detections and events (videos and zones are kept).", assume_yes):
        print("Aborted.")
        return
    with session_scope() as db:
        if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status == JobStatus.PROCESSING)):
            sys.exit("A job is currently processing; stop the backend or cancel it first.")
        for model in (ZoneOccupancySample, MonitoringEvent, TrackSummary, Detection, ProcessingJob):
            db.execute(delete(model))
        db.execute(update(Video).values(status=VideoStatus.UPLOADED))
    shutil.rmtree(get_settings().snapshots_dir, ignore_errors=True)
    get_settings().ensure_directories()
    print("Results cleared. Uploaded videos and zones were kept.")


def delete_samples(assume_yes: bool) -> None:
    from app.db.session import session_scope
    from app.models import Video
    from app.services.storage import VideoStorage

    storage = VideoStorage(get_settings())
    with session_scope() as db:
        samples = db.scalars(select(Video).where(Video.is_sample.is_(True))).all()
        if not samples:
            print("No sample videos found.")
            return
        if not _confirm(f"Delete {len(samples)} sample video(s) and their results?", assume_yes):
            print("Aborted.")
            return
        files = [(v.id, v.storage_filename, v.thumbnail_filename) for v in samples]
        for v in samples:
            db.delete(v)
    for vid, name, thumb in files:
        storage.delete_video_files(vid, name, thumb)
    print(f"Deleted {len(files)} sample video(s). User uploads were not touched.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ZoneVision maintenance")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("download-model")
    for name in ("reset-results", "delete-samples"):
        p = sub.add_parser(name)
        p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)
    if args.cmd == "init-db":
        init_db()
    elif args.cmd == "download-model":
        download_model()
    elif args.cmd == "reset-results":
        reset_results(args.yes)
    elif args.cmd == "delete-samples":
        delete_samples(args.yes)


if __name__ == "__main__":
    main()
