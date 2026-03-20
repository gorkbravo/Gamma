from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.services.cache import CacheService
from src.utils.time import now_utc


JsonFetcher = Callable[[str, dict[str, Any] | None], Any]


@dataclass(frozen=True)
class FredObservation:
    timestamp: datetime
    value: float


def default_fred_fetcher(url: str, params: dict[str, Any] | None = None) -> Any:
    cleaned = {
        key: value
        for key, value in (params or {}).items()
        if value is not None and value != "" and value != []
    }
    target_url = url
    if cleaned:
        target_url = f"{url}?{urlencode(cleaned, doseq=True)}"
    request = Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Gamma/0.1 macro-research",
        },
    )
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


class FredClient:
    OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(
        self,
        cache: CacheService | None = None,
        *,
        api_key: str | None = None,
        fetch_json: JsonFetcher | None = None,
    ) -> None:
        self.cache = cache
        self.api_key = (api_key or os.getenv("FRED_API_KEY", "")).strip() or None
        self.fetch_json = fetch_json or default_fred_fetcher

    def get_series_observations(
        self,
        series_id: str,
        *,
        observation_start: date | datetime | None = None,
        observation_end: date | datetime | None = None,
        units: str | None = None,
        frequency: str | None = None,
        aggregation_method: str | None = None,
        ttl: timedelta | None = None,
        force_refresh: bool = False,
    ) -> tuple[list[FredObservation], datetime]:
        params: dict[str, Any] = {
            "series_id": series_id,
            "file_type": "json",
            "sort_order": "asc",
            "observation_start": _to_date_string(observation_start),
            "observation_end": _to_date_string(observation_end),
            "units": units,
            "frequency": frequency,
            "aggregation_method": aggregation_method,
        }
        if self.api_key:
            params["api_key"] = self.api_key

        payload: Any
        retrieved_at: datetime
        cache_key = ""
        if self.cache is not None:
            cache_key = self.cache.make_key(
                "fred",
                series_id,
                str(params.get("observation_start") or "start"),
                str(params.get("observation_end") or "end"),
                str(units or "raw"),
                str(frequency or "native"),
                str(aggregation_method or "default"),
            )
            if not force_refresh:
                cached = self.cache.get_json(cache_key, max_age=ttl)
                if isinstance(cached, dict) and "payload" in cached and "retrieved_at" in cached:
                    cached_at = _parse_datetime(cached.get("retrieved_at")) or now_utc()
                    return self._normalize_observations(cached.get("payload")), cached_at

        payload = self.fetch_json(self.OBSERVATIONS_URL, params)
        retrieved_at = now_utc()
        if self.cache is not None and cache_key:
            self.cache.set_json(
                cache_key,
                {
                    "retrieved_at": retrieved_at.isoformat(),
                    "payload": payload,
                },
            )
        return self._normalize_observations(payload), retrieved_at

    @staticmethod
    def _normalize_observations(payload: Any) -> list[FredObservation]:
        observations = payload.get("observations", []) if isinstance(payload, dict) else []
        rows: list[FredObservation] = []
        for observation in observations:
            value = str(observation.get("value", "")).strip()
            if value in {"", "."}:
                continue
            try:
                rows.append(
                    FredObservation(
                        timestamp=datetime.fromisoformat(str(observation["date"])),
                        value=float(value),
                    )
                )
            except Exception:
                continue
        rows.sort(key=lambda row: row.timestamp)
        return rows


def _to_date_string(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed
