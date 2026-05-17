from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ProviderUsageCall:
    provider_id: str
    endpoint: str
    status: str
    cache_status: str | None
    duration_ms: float
    recorded_at: datetime
    message: str | None = None


@dataclass(frozen=True)
class ProviderUsageSummary:
    provider_id: str
    call_count: int = 0
    success_count: int = 0
    unavailable_count: int = 0
    error_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    average_duration_ms: float = 0.0
    last_status: str | None = None
    last_message: str | None = None
    last_error: str | None = None
    last_called_at: datetime | None = None
    endpoints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    generated_at: datetime
    providers: list[ProviderUsageSummary] = field(default_factory=list)
    recent_calls: list[ProviderUsageCall] = field(default_factory=list)
    total_calls: int = 0
    source_provider: str = "gamma"
    origin: str = "provider_usage_ledger.snapshot"
    transformation_note: str | None = (
        "In-memory provider usage diagnostics collected from Gamma provider boundaries since backend startup."
    )
