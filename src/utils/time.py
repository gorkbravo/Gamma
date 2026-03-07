from __future__ import annotations

from datetime import datetime


def now_utc() -> datetime:
    return datetime.utcnow()


def format_ts(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")
