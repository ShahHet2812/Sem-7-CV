from __future__ import annotations


def like_pattern(term: str) -> str:
    """Build a LIKE pattern that treats the user's input literally (escape char '\\')."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
