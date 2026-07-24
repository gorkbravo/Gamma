from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from src.utils.time import now_utc


@dataclass
class ResearchHistoryCache:
    _entries: dict[str, tuple[pd.Series, int, datetime]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, symbol: str, series: pd.Series, lookback_days: int) -> None:
        key = str(symbol or "").strip().upper()
        if not key:
            return
        lookback = max(int(lookback_days or 0), 0)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                existing_series, existing_lookback, _stored_at = existing
                # Refreshes must be able to replace overlapping older observations. Merge
                # non-overlapping history, but let the newly fetched payload win by date.
                series = pd.concat([existing_series, series])
                series = series[~series.index.duplicated(keep="last")].sort_index()
                lookback = max(lookback, existing_lookback)
            self._entries[key] = (series, lookback, now_utc())

    def get(
        self,
        symbol: str,
        min_lookback_days: int = 0,
        *,
        max_age_seconds: int | float | None = None,
    ) -> pd.Series | None:
        key = str(symbol or "").strip().upper()
        if not key:
            return None
        required = max(int(min_lookback_days or 0), 0)
        with self._lock:
            cached = self._entries.get(key)
        if cached is None:
            return None
        if len(cached) == 2:
            series, lookback = cached  # type: ignore[misc]
            stored_at = now_utc()
        else:
            series, lookback, stored_at = cached
        if lookback < required:
            return None
        if max_age_seconds is not None and float(max_age_seconds) >= 0:
            age_seconds = (now_utc() - stored_at).total_seconds()
            if age_seconds > float(max_age_seconds):
                return None
        return series

    def clear(self) -> None:
        with self._lock:
            self._entries = {}

    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._entries.keys())
