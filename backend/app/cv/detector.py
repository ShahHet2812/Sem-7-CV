"""Ultralytics YOLO model loading and device selection.

Weights are resolved in this order:
1. ``MODEL_WEIGHTS`` if it is an existing absolute/relative file path;
2. ``<models_dir>/<MODEL_WEIGHTS>`` if already downloaded;
3. if ``MODEL_AUTO_DOWNLOAD`` is true and the name is an official Ultralytics
   asset (e.g. ``yolo11n.pt``), Ultralytics downloads it into ``models_dir``.

If none succeeds a ``ModelUnavailableError`` is raised with setup
instructions. Detections are never fabricated.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ModelUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawDetection:
    xyxy: tuple[float, float, float, float]  # source pixels
    class_id: int
    class_name: str
    confidence: float
    track_id: int | None


def resolve_device(preference: str) -> str:
    if preference and preference != "auto":
        return preference
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001 - torch missing or broken: fall back to CPU
        pass
    return "cpu"


def resolve_weights_path(settings: Settings) -> Path:
    candidate = Path(settings.model_weights).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    return settings.models_dir / candidate.name


class YoloModelProvider:
    """Thread-safe lazy loader; each processing job gets its own model instance
    because Ultralytics trackers keep per-model state (``persist=True``)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._names: dict[int, str] | None = None
        self._error: str | None = None
        self.device = resolve_device(settings.inference_device)

    @property
    def weights_path(self) -> Path:
        return resolve_weights_path(self.settings)

    @property
    def model_name(self) -> str:
        return self.weights_path.name

    def weights_present(self) -> bool:
        return self.weights_path.is_file()

    def create_model(self) -> Any:
        with self._lock:
            path = self.weights_path
            if not path.is_file() and not self.settings.model_auto_download:
                self._error = "weights_missing"
                raise ModelUnavailableError(
                    f"Model weights '{path.name}' were not found in the models directory and "
                    "automatic download is disabled. Download the weights (see README, "
                    "'Model weights') or set MODEL_AUTO_DOWNLOAD=true."
                )
            os.environ.setdefault(
                "YOLO_CONFIG_DIR", str(self.settings.storage_dir / "ultralytics")
            )
            try:
                from ultralytics import YOLO
                from ultralytics.utils import SETTINGS as UL_SETTINGS

                UL_SETTINGS.update({"sync": False})  # no usage analytics
            except Exception as exc:  # noqa: BLE001
                self._error = "ultralytics_import_failed"
                raise ModelUnavailableError(
                    "The 'ultralytics' package could not be imported. Install backend requirements."
                ) from exc
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                # For official asset names Ultralytics downloads to exactly this path.
                model = YOLO(str(path))
            except Exception as exc:  # noqa: BLE001
                self._error = "load_failed"
                logger.exception("Failed to load YOLO weights from %s", path)
                raise ModelUnavailableError(
                    f"Model '{path.name}' could not be loaded. If this machine is offline, "
                    "download the weights manually into the models directory. "
                    f"Reason: {exc.__class__.__name__}"
                ) from exc
            self._names = {int(k): str(v) for k, v in model.names.items()}
            self._error = None
            return model

    def class_names(self, load: bool = False) -> dict[int, str] | None:
        if self._names is None and load:
            try:
                self.create_model()
            except ModelUnavailableError:
                return None
        return self._names

    def status(self) -> dict[str, Any]:
        return {
            "name": self.model_name,
            "weights_present": self.weights_present(),
            "loaded": self._names is not None,
            "error": self._error,
            "device": self.device,
            "auto_download": self.settings.model_auto_download,
        }
