"""Local file storage for uploads and derived artifacts.

Security rules:
* Files are stored under server-generated UUID names; client filenames are
  metadata only and never used to build paths.
* Every path served or deleted is re-resolved and verified to live inside its
  storage root (``safe_child``), so DB tampering cannot escape the root.
* Absolute paths are never returned to clients.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import PayloadTooLarge, ValidationFailed
from app.cv.video_reader import VideoDecodeError, VideoMetadata, probe_video

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}
# Container families detected from magic bytes that are acceptable per extension.
EXTENSION_FAMILY = {
    ".mp4": "isobmff",
    ".m4v": "isobmff",
    ".mov": "isobmff",
    ".avi": "riff_avi",
    ".mkv": "ebml",
    ".webm": "ebml",
}
BROWSER_CODECS = {"avc1", "h264", "x264", "vp80", "vp8", "vp09", "vp90", "vp9", "av01"}


@dataclass
class StoredVideo:
    storage_filename: str
    original_filename: str
    file_size: int
    content_type: str
    container_format: str
    metadata: VideoMetadata
    thumbnail_filename: str | None


def sniff_family(header: bytes) -> str | None:
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "isobmff"
    if len(header) >= 8 and header[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return "isobmff"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "riff_avi"
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return "ebml"
    return None


def safe_child(root: Path, name: str | None) -> Path | None:
    if not name:
        return None
    root = root.resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root and root not in candidate.parents:
        return None
    return candidate


def is_browser_playable(container: str, codec: str | None) -> bool:
    if container not in ("mp4", "m4v", "mov", "webm"):
        return False
    return codec is None or codec in BROWSER_CODECS


def _clean_filename(name: str | None) -> str:
    base = Path(name or "video").name.strip().replace("\x00", "")
    return base[:255] or "video"


class VideoStorage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def upload_path(self, storage_filename: str) -> Path | None:
        return safe_child(self.settings.uploads_dir, storage_filename)

    def thumbnail_path(self, filename: str | None) -> Path | None:
        return safe_child(self.settings.thumbnails_dir, filename)

    def snapshot_dir(self, video_id: uuid.UUID) -> Path:
        d = self.settings.snapshots_dir / str(video_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def snapshot_path(self, video_id: uuid.UUID, filename: str | None) -> Path | None:
        return safe_child(self.settings.snapshots_dir / str(video_id), filename)

    @staticmethod
    def validate_extension(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationFailed(
                f"Unsupported file type '{ext or 'none'}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
                code="unsupported_file_type",
            )
        return ext

    def save_upload(self, upload: UploadFile) -> StoredVideo:
        """Copy, validate (size, signature, decodability) and register an upload.

        Synchronous on purpose: decoding is CPU-bound, so callers run this in a
        worker thread (FastAPI does that automatically for ``def`` endpoints).
        """
        original = _clean_filename(upload.filename)
        ext = self.validate_extension(original)
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        storage_filename = f"{uuid.uuid4().hex}{ext}"
        final = self.settings.uploads_dir / storage_filename
        tmp = final.with_name(f".{storage_filename}.part")
        size = 0
        try:
            with tmp.open("wb") as out:
                while chunk := upload.file.read(CHUNK):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise PayloadTooLarge(
                            f"File exceeds the maximum upload size of {self.settings.max_upload_mb} MB."
                        )
                    out.write(chunk)
            if size == 0:
                raise ValidationFailed("The uploaded file is empty.", code="empty_file")
            tmp.replace(final)
            return self._finalize(final, original, ext, size)
        except BaseException:
            tmp.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise

    def _finalize(self, path: Path, original: str, ext: str, size: int) -> StoredVideo:
        with path.open("rb") as fh:
            header = fh.read(64)
        family = sniff_family(header)
        if family is None or family != EXTENSION_FAMILY[ext]:
            raise ValidationFailed(
                "File content does not match a supported video container "
                f"for extension '{ext}'.",
                code="invalid_video_content",
            )
        try:
            meta, first_frame = probe_video(path)
        except VideoDecodeError as exc:
            raise ValidationFailed(str(exc), code="undecodable_video") from exc
        thumb = self._write_thumbnail(path.stem, first_frame)
        return StoredVideo(
            storage_filename=path.name,
            original_filename=original,
            file_size=size,
            content_type=ALLOWED_EXTENSIONS[ext],
            container_format=ext.lstrip("."),
            metadata=meta,
            thumbnail_filename=thumb,
        )

    def _write_thumbnail(self, stem: str, frame: np.ndarray) -> str | None:
        try:
            self.settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
            h, w = frame.shape[:2]
            scale = 480 / w if w > 480 else 1.0
            thumb = cv2.resize(frame, (round(w * scale), round(h * scale))) if scale != 1 else frame
            name = f"{stem}.jpg"
            cv2.imwrite(str(self.settings.thumbnails_dir / name), thumb, [cv2.IMWRITE_JPEG_QUALITY, 82])
            return name
        except Exception:  # noqa: BLE001 - a missing thumbnail is not fatal
            logger.warning("Thumbnail generation failed for %s", stem, exc_info=True)
            return None

    def delete_video_files(
        self, video_id: uuid.UUID, storage_filename: str, thumbnail: str | None
    ) -> None:
        for p in (self.upload_path(storage_filename), self.thumbnail_path(thumbnail)):
            if p is not None:
                p.unlink(missing_ok=True)
        snap_dir = safe_child(self.settings.snapshots_dir, str(video_id))
        if snap_dir is not None and snap_dir.is_dir():
            shutil.rmtree(snap_dir, ignore_errors=True)
