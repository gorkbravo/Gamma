from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import Any

from src.models.provider_usage import ProviderUsageCall, ProviderUsageHealth, ProviderUsageSnapshot, ProviderUsageSummary
from src.utils.time import now_utc


@dataclass(frozen=True)
class ProviderActivationCondition:
    provider_id: str
    display_name: str
    expected_when: str
    configured: bool
    active: bool = False
    idle_status: str = "not_requested"
    idle_reason: str = "Provider has not been requested in this backend session."
    action_label: str | None = None


class ProviderUsageLedger:
    def __init__(self, *, max_calls: int = 500, clock: Callable[[], Any] = now_utc) -> None:
        self.max_calls = max(1, int(max_calls))
        self._clock = clock
        self._calls: deque[ProviderUsageCall] = deque(maxlen=self.max_calls)
        self._activation_conditions: dict[str, ProviderActivationCondition] = {}
        self._lock = RLock()

    def register_activation_condition(self, condition: ProviderActivationCondition) -> None:
        with self._lock:
            self._activation_conditions[_clean(condition.provider_id, "unknown")] = condition

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
            conditions = list(self._activation_conditions.values())
        summaries = _summarize(calls)
        recent_limit = max(0, int(limit))
        return ProviderUsageSnapshot(
            generated_at=self._clock(),
            providers=summaries,
            health=_health_rows(summaries, conditions),
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
                    status=_exception_status(exc),
                    duration_ms=(time.perf_counter() - started) * 1000,
                    message=_exception_message(exc, redact=self._endpoint_prefix == "copilot"),
                )
                raise
            self._ledger.record(
                provider_id=_result_provider_id(result) or _provider_id(self._provider),
                endpoint=self._endpoint(name),
                status=_result_status(result),
                cache_status=_result_cache_status(result),
                duration_ms=(time.perf_counter() - started) * 1000,
                message=_result_message(result, redact=self._endpoint_prefix == "copilot"),
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
        last_error = next(
            (
                row.message
                for row in reversed(rows)
                if row.status in {"error", "refused", "incomplete", "cancelled", "timeout"}
                and row.message
            ),
            None,
        )
        summaries.append(
            ProviderUsageSummary(
                provider_id=provider_id,
                call_count=call_count,
                success_count=sum(1 for row in rows if row.status == "success"),
                unavailable_count=sum(1 for row in rows if row.status == "unavailable"),
                error_count=sum(
                    1
                    for row in rows
                    if row.status in {"error", "refused", "incomplete", "cancelled", "timeout"}
                ),
                incomplete_count=sum(1 for row in rows if row.status == "incomplete"),
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


def _health_rows(
    summaries: list[ProviderUsageSummary],
    conditions: list[ProviderActivationCondition],
) -> list[ProviderUsageHealth]:
    by_provider = {row.provider_id: row for row in summaries}
    condition_ids = {condition.provider_id for condition in conditions}
    rows = [_health_for_condition(condition, by_provider.get(condition.provider_id)) for condition in conditions]
    for summary in summaries:
        if summary.provider_id not in condition_ids:
            rows.append(_health_for_summary(summary, summary.provider_id, summary.provider_id, "Provider was requested."))
    return sorted(rows, key=lambda row: (_health_sort_rank(row.health_status), row.provider_id))


def _health_for_condition(
    condition: ProviderActivationCondition,
    summary: ProviderUsageSummary | None,
) -> ProviderUsageHealth:
    if summary is not None:
        return _health_for_summary(summary, condition.provider_id, condition.display_name, condition.expected_when)
    if not condition.configured:
        return ProviderUsageHealth(
            provider_id=condition.provider_id,
            display_name=condition.display_name,
            health_status="needs_config",
            health_label="Needs config",
            expected_when=condition.expected_when,
            reason="Provider is not configured for the current runtime.",
            action_label=condition.action_label,
        )
    status = condition.idle_status if not condition.active else "not_requested"
    return ProviderUsageHealth(
        provider_id=condition.provider_id,
        display_name=condition.display_name,
        health_status=status,
        health_label=_health_label(status),
        expected_when=condition.expected_when,
        reason=condition.idle_reason,
        action_label=condition.action_label,
    )


def _health_for_summary(
    summary: ProviderUsageSummary,
    provider_id: str,
    display_name: str,
    expected_when: str,
) -> ProviderUsageHealth:
    """Health across the whole retained window, not just the last request.

    GUA-20260903-5: a badge derived only from `last_status` reported IBKR as
    Healthy with 86/86 successes while user-visible requests inside that window
    had failed or come back partial. Session reachability and request outcomes
    are now reported as separate facts.
    """
    session_status = "connected" if summary.last_status != "error" else "unstable"
    failed = int(summary.error_count or 0)
    partial = int(summary.incomplete_count or 0)
    unavailable = int(summary.unavailable_count or 0)

    if summary.last_status in {"error", "refused", "cancelled", "timeout"}:
        status = "degraded"
        reason = summary.last_error or summary.last_message or "Recent provider request failed."
    elif summary.last_status == "incomplete":
        status = "degraded"
        reason = summary.last_message or "The most recent provider request returned incomplete data."
    elif summary.last_status == "unavailable":
        status = "unavailable"
        reason = summary.last_message or "Provider was requested but returned unavailable data."
    elif failed or partial or unavailable:
        # The last call succeeded, but requests inside this window did not.
        status = "degraded"
        parts = []
        if failed:
            parts.append(f"{failed} failed")
        if partial:
            parts.append(f"{partial} returned partial data")
        if unavailable:
            parts.append(f"{unavailable} returned no data")
        reason = (
            f"The last request succeeded, but {' and '.join(parts)} out of {summary.call_count} recent "
            f"{display_name} requests."
        )
    else:
        status = "healthy"
        reason = summary.last_message or "Recent provider requests succeeded."
    return ProviderUsageHealth(
        provider_id=provider_id,
        display_name=display_name,
        health_status=status,
        health_label=_health_label(status),
        expected_when=expected_when,
        reason=reason,
        call_count=summary.call_count,
        success_count=summary.success_count,
        unavailable_count=summary.unavailable_count,
        error_count=summary.error_count,
        incomplete_count=partial,
        session_status=session_status,
        last_called_at=summary.last_called_at,
    )


def _health_label(status: str) -> str:
    return {
        "healthy": "Healthy",
        "degraded": "Degraded",
        "unavailable": "Unavailable",
        "needs_config": "Needs config",
        "idle_by_design": "Idle by design",
        "not_requested": "Not requested",
    }.get(status, status.replace("_", " ").title())


def _health_sort_rank(status: str) -> int:
    return {
        "degraded": 0,
        "unavailable": 1,
        "needs_config": 2,
        "healthy": 3,
        "idle_by_design": 4,
        "not_requested": 5,
    }.get(status, 9)


def _provider_id(provider: Any) -> str:
    return _clean(
        getattr(provider, "provider_id", None)
        or getattr(provider, "source_name", None)
        or getattr(provider, "provider_name", None),
        "unknown",
    )


def _result_provider_id(result: Any) -> str | None:
    value = getattr(result, "source_provider", None)
    return _clean(value, "") or None


def _result_status(result: Any) -> str:
    terminal_status = str(getattr(result, "status", "") or "").strip().lower()
    if terminal_status in {"ready", "completed", "complete", "success", "ok"}:
        return "success"
    if terminal_status in {"unavailable", "disabled", "unconfigured"}:
        return "unavailable"
    if terminal_status in {"refused", "incomplete", "cancelled", "canceled", "timeout", "timed_out"}:
        return _normalize_status(terminal_status)
    if terminal_status in {"error", "failed", "failure"}:
        return "error"
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


def _result_message(result: Any, *, redact: bool = False) -> str | None:
    if redact:
        status = _result_status(result)
        model = _clean(getattr(result, "model", None), "")
        return f"status={status}" + (f"; model={model}" if model else "")
    warnings = getattr(result, "warnings", None)
    if isinstance(warnings, list) and warnings:
        return str(warnings[0])
    return None


def _exception_status(exc: Exception) -> str:
    reason = str(getattr(exc, "reason", "") or "").strip().lower()
    if reason in {"timeout", "timed_out"}:
        return "timeout"
    if exc.__class__.__name__ == "CopilotRunCancelled":
        return "cancelled"
    if isinstance(exc, TimeoutError) or "timeout" in exc.__class__.__name__.lower():
        return "timeout"
    return "error"


def _exception_message(exc: Exception, *, redact: bool = False) -> str:
    if redact:
        reason = _clean(getattr(exc, "reason", None), "")
        return exc.__class__.__name__ + (f": {reason}" if reason else "")
    return str(exc)


def _normalize_status(value: str) -> str:
    normalized = _clean(value, "success").lower()
    if normalized in {"ok", "hit", "miss"}:
        return "success"
    if normalized in {"unavailable", "empty", "missing"}:
        return "unavailable"
    if normalized in {"error", "failed", "exception"}:
        return "error"
    if normalized in {"canceled"}:
        return "cancelled"
    if normalized in {"timed_out"}:
        return "timeout"
    return normalized


def _normalize_cache_status(value: str | None) -> str | None:
    normalized = _clean(value, "").lower()
    return normalized if normalized in {"hit", "miss", "stale", "bypass"} else None


def _clean(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback
