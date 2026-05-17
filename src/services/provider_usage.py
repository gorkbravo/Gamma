from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from functools import wraps
from threading import RLock
from typing import Any

from src.models.provider_usage import ProviderUsageCall, ProviderUsageSnapshot, ProviderUsageSummary
from src.utils.time import now_utc


class ProviderUsageLedger:
    def __init__(self, *, max_calls: int = 500, clock: Callable[[], Any] = now_utc) -> None:
        self.max_calls = max(1, int(max_calls))
        self._clock = clock
        self._calls: deque[ProviderUsageCall] = deque(maxlen=self.max_calls)
        self._lock = RLock()

    def record(
        self,
        *,
        provider_id: str,
        endpoint: str,
        status: str,
        cache_status: str | None = None,
        duration_ms: float = 0.0,
        message: str | None = None,
    ) -> None:
        call = ProviderUsageCall(
            provider_id=_clean(provider_id, "unknown"),
            endpoint=_clean(endpoint, "unknown"),
            status=_normalize_status(status),
            cache_status=_normalize_cache_status(cache_status),
            duration_ms=max(0.0, float(duration_ms or 0.0)),
            recorded_at=self._clock(),
            message=str(message)[:500] if message else None,
        )
        with self._lock:
            self._calls.append(call)

    def snapshot(self, *, limit: int = 50) -> ProviderUsageSnapshot:
        with self._lock:
            calls = list(self._calls)
        summaries = _summarize(calls)
        recent_limit = max(0, int(limit))
        return ProviderUsageSnapshot(
            generated_at=self._clock(),
            providers=summaries,
            recent_calls=list(reversed(calls[-recent_limit:])) if recent_limit else [],
            total_calls=len(calls),
        )


class TraceableProvider:
    def __init__(self, provider: Any, ledger: ProviderUsageLedger, *, endpoint_prefix: str | None = None) -> None:
        self._provider = provider
        self._ledger = ledger
        self._endpoint_prefix = endpoint_prefix

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._provider, name)
        if not callable(value) or name.startswith("_"):
            return value

        @wraps(value)
        def traced(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                result = value(*args, **kwargs)
            except Exception as exc:
                self._ledger.record(
                    provider_id=_provider_id(self._provider),
                    endpoint=self._endpoint(name),
                    status="error",
                    duration_ms=(time.perf_counter() - started) * 1000,
                    message=str(exc),
                )
                raise
            self._ledger.record(
                provider_id=_result_provider_id(result) or _provider_id(self._provider),
                endpoint=self._endpoint(name),
                status=_result_status(result),
                cache_status=_result_cache_status(result),
                duration_ms=(time.perf_counter() - started) * 1000,
                message=_result_message(result),
            )
            return result

        return traced

    def _endpoint(self, name: str) -> str:
        return f"{self._endpoint_prefix}.{name}" if self._endpoint_prefix else name

    @property
    def __class__(self):
        return self._provider.__class__


def trace_provider(
    provider: Any,
    ledger: ProviderUsageLedger,
    *,
    endpoint_prefix: str | None = None,
) -> Any:
    return TraceableProvider(provider, ledger, endpoint_prefix=endpoint_prefix)


def _summarize(calls: list[ProviderUsageCall]) -> list[ProviderUsageSummary]:
    grouped: dict[str, list[ProviderUsageCall]] = {}
    for call in calls:
        grouped.setdefault(call.provider_id, []).append(call)

    summaries: list[ProviderUsageSummary] = []
    for provider_id, rows in grouped.items():
        call_count = len(rows)
        durations = [row.duration_ms for row in rows]
        endpoints = sorted({row.endpoint for row in rows})
        last = rows[-1]
        last_error = next((row.message for row in reversed(rows) if row.status == "error" and row.message), None)
        summaries.append(
            ProviderUsageSummary(
                provider_id=provider_id,
                call_count=call_count,
                success_count=sum(1 for row in rows if row.status == "success"),
                unavailable_count=sum(1 for row in rows if row.status == "unavailable"),
                error_count=sum(1 for row in rows if row.status == "error"),
                cache_hit_count=sum(1 for row in rows if row.cache_status == "hit"),
                cache_miss_count=sum(1 for row in rows if row.cache_status == "miss"),
                average_duration_ms=sum(durations) / call_count if call_count else 0.0,
                last_status=last.status,
                last_message=last.message,
                last_error=last_error,
                last_called_at=last.recorded_at,
                endpoints=endpoints,
            )
        )
    return sorted(summaries, key=lambda row: (row.last_called_at is None, row.last_called_at), reverse=True)


def _provider_id(provider: Any) -> str:
    return _clean(getattr(provider, "provider_id", None) or getattr(provider, "source_name", None), "unknown")


def _result_provider_id(result: Any) -> str | None:
    value = getattr(result, "source_provider", None)
    return _clean(value, "") or None


def _result_status(result: Any) -> str:
    freshness = str(getattr(result, "freshness_label", "") or "").lower()
    source_provider = str(getattr(result, "source_provider", "") or "").lower()
    if source_provider == "unavailable" or "unavailable" in freshness:
        return "unavailable"
    if getattr(result, "series", True) is None:
        return "unavailable"
    return "success"


def _result_cache_status(result: Any) -> str | None:
    freshness = str(getattr(result, "freshness_label", "") or "").lower()
    if "cached" in freshness:
        return "hit"
    return None


def _result_message(result: Any) -> str | None:
    warnings = getattr(result, "warnings", None)
    if isinstance(warnings, list) and warnings:
        return str(warnings[0])
    return None


def _normalize_status(value: str) -> str:
    normalized = _clean(value, "success").lower()
    if normalized in {"ok", "hit", "miss"}:
        return "success"
    if normalized in {"unavailable", "empty", "missing"}:
        return "unavailable"
    if normalized in {"error", "failed", "exception"}:
        return "error"
    return normalized


def _normalize_cache_status(value: str | None) -> str | None:
    normalized = _clean(value, "").lower()
    return normalized if normalized in {"hit", "miss", "stale", "bypass"} else None


def _clean(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback
