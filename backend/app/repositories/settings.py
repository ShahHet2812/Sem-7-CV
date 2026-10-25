from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import ApplicationSetting


def get_value(db: Session, key: str) -> Any | None:
    row = db.get(ApplicationSetting, key)
    return row.value if row else None


def set_value(db: Session, key: str, value: Any) -> None:
    row = db.get(ApplicationSetting, key)
    if row is None:
        db.add(ApplicationSetting(key=key, value=value))
    else:
        row.value = value
