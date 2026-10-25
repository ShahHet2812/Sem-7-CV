"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ZoneVision"
    environment: str = Field(default="development", pattern="^(development|production|test)$")
    log_level: str = "INFO"
    log_json: bool = False

    # Primary database is PostgreSQL. SQLite is a documented local fallback,
    # e.g. DATABASE_URL=sqlite:///./storage/zonevision.db
    database_url: str = "postgresql+psycopg://zonevision:zonevision@localhost:5432/zonevision"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    storage_dir: Path = PROJECT_DIR / "storage"
    max_upload_mb: int = Field(default=500, ge=1, le=10_000)

    # Model / CV configuration
    model_weights: str = "yolo11n.pt"
    model_dir: Path | None = None
    model_auto_download: bool = True
    inference_device: str = "auto"  # auto | cpu | cuda:0 ...

    # Defaults for runtime-editable processing settings (persisted in DB once changed)
    default_confidence: float = Field(default=0.35, ge=0.05, le=0.95)
    default_image_size: int = Field(default=640, ge=160, le=1920)
    default_target_fps: float = Field(default=6.0, gt=0, le=60)

    # Background worker
    worker_enabled: bool = True
    worker_poll_interval: float = Field(default=1.0, gt=0)

    # Optional public sample video (fetched only on explicit user request)
    sample_video_url: str = (
        "https://github.com/intel-iot-devkit/sample-videos/raw/master/people-detection.mp4"
    )

    @field_validator("storage_dir", "model_dir", mode="before")
    @classmethod
    def _resolve_path(cls, value: object) -> object:
        if value in (None, ""):
            return None
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = (PROJECT_DIR / path).resolve()
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.storage_dir / "processed"

    @property
    def snapshots_dir(self) -> Path:
        return self.storage_dir / "snapshots"

    @property
    def thumbnails_dir(self) -> Path:
        return self.processed_dir / "thumbnails"

    @property
    def models_dir(self) -> Path:
        return self.model_dir or (self.storage_dir / "models")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_directories(self) -> None:
        for d in (
            self.uploads_dir,
            self.processed_dir,
            self.snapshots_dir,
            self.thumbnails_dir,
            self.models_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
