from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.cv.detector import YoloModelProvider


@lru_cache
def get_model_provider() -> YoloModelProvider:
    return YoloModelProvider(get_settings())
