from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ResearchHistoryCache:
    _entries: dict[str, tuple[pd.Series, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, symbol: str, series: pd.Series, lookback_days: int) -> None:
        key = str(symbol or "").strip().upper()
        if not key:
            return
        lookback = max(int(lookback_days or 0), 0)
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                existing_series, existing_lookback = existing
                if existing_lookback > lookback and len(existing_series) >= len(series):
                    return
            self._entries[key] = (series, lookback)

    def get(self, symbol: str, min_lookback_days: int = 0) -> pd.Series | None:
        key = str(symbol or "").strip().upper()
        if not key:
            return None
        required = max(int(min_lookback_days or 0), 0)
        with self._lock:
            cached = self._entries.get(key)
        if cached is None:
            return None
        series, lookback = cached
        if lookback < required:
            return None
        return series

    def clear(self) -> None:
        with self._lock:
            self._entries = {}

    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._entries.keys())
