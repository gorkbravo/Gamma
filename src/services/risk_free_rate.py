from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from src.services.cache import CacheService


class RiskFreeRateService:
    """Fetches and caches a USD daily risk-free return proxy from FRED."""

    FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
    SOFR_INDEX_SERIES_ID = "SOFRINDEX"

    def __init__(
        self,
        cache: CacheService | None = None,
        fred_api_key: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.cache = cache
        self.fred_api_key = (fred_api_key or os.getenv("FRED_API_KEY", "")).strip() or None
        self.timeout_seconds = timeout_seconds

    def get_usd_daily_returns(
        self,
        start_date: date | datetime | pd.Timestamp,
        end_date: date | datetime | pd.Timestamp,
    ) -> Tuple[pd.Series | None, List[str]]:
        warnings: List[str] = []
        start_ts = pd.Timestamp(start_date).normalize()
        end_ts = pd.Timestamp(end_date).normalize()
        if start_ts > end_ts:
            start_ts, end_ts = end_ts, start_ts

        index_series = self._get_sofr_index_series(start_ts, end_ts, warnings)
        if index_series is None or index_series.empty:
            return None, warnings

        rf = index_series.pct_change().dropna()
        if rf.empty:
            warnings.append("Risk-free series unavailable after SOFR Index conversion")
            return None, warnings
        rf = rf[(rf.index >= start_ts) & (rf.index <= end_ts)].sort_index()
        if rf.empty:
            warnings.append("Risk-free series has no observations in requested window")
            return None, warnings
        return rf.astype(float), warnings

    def _get_sofr_index_series(
        self,
        start_ts: pd.Timestamp,
        end_ts: pd.Timestamp,
        warnings: List[str],
    ) -> Optional[pd.Series]:
        cache_key = "fred_sofrindex"
        cached = self.cache.get(cache_key) if self.cache is not None else None
        if cached is not None and not cached.empty:
            cached = cached.sort_index()
            if cached.index.min() <= start_ts and cached.index.max() >= end_ts:
                return cached.astype(float)

        fetch_start = (start_ts - pd.Timedelta(days=30)).date()
        fetch_end = (end_ts + pd.Timedelta(days=5)).date()
        series = self._fetch_fred_series(self.SOFR_INDEX_SERIES_ID, fetch_start, fetch_end, warnings)
        if series is None or series.empty:
            return cached.astype(float) if cached is not None and not cached.empty else None
        if self.cache is not None:
            self.cache.set(cache_key, series)
        return series.astype(float)

    def _fetch_fred_series(
        self,
        series_id: str,
        observation_start: date,
        observation_end: date,
        warnings: List[str],
    ) -> Optional[pd.Series]:
        params = {
            "series_id": series_id,
            "file_type": "json",
            "observation_start": observation_start.isoformat(),
            "observation_end": observation_end.isoformat(),
        }
        if self.fred_api_key:
            params["api_key"] = self.fred_api_key
        url = f"{self.FRED_OBSERVATIONS_URL}?{urlencode(params)}"
        try:
            with urlopen(url, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            warnings.append(f"Risk-free fetch failed (FRED {series_id}): {exc}")
            return None

        observations = payload.get("observations", [])
        if not observations:
            warnings.append(f"Risk-free fetch returned no observations (FRED {series_id})")
            return None

        rows = []
        for obs in observations:
            value = str(obs.get("value", "")).strip()
            if value in {"", "."}:
                continue
            try:
                rows.append((pd.Timestamp(obs["date"]), float(value)))
            except Exception:
                continue
        if not rows:
            warnings.append(f"Risk-free series {series_id} contained no numeric observations")
            return None
        series = pd.Series({ts: val for ts, val in rows}, dtype=float).sort_index()
        series = series[~series.index.duplicated(keep="last")]
        return series
