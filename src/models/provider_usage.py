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
    # "provider": llamada en la frontera de un adaptador; "http": petición saliente
    # registrada en la capa urllib (GUA-20260903-10).
    kind: str = "provider"


@dataclass(frozen=True)
class ProviderUsageSummary:
    provider_id: str
    call_count: int = 0
    success_count: int = 0
    unavailable_count: int = 0
    error_count: int = 0
    incomplete_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    average_duration_ms: float = 0.0
    last_status: str | None = None
    last_message: str | None = None
    last_error: str | None = None
    last_called_at: datetime | None = None
    endpoints: list[str] = field(default_factory=list)
    # Peticiones HTTP salientes incluidas en call_count (GUA-20260903-10).
    http_request_count: int = 0


@dataclass(frozen=True)
class ProviderUsageHealth:
    provider_id: str
    display_name: str
    health_status: str
    health_label: str
    expected_when: str
    reason: str
    action_label: str | None = None
    call_count: int = 0
    success_count: int = 0
    unavailable_count: int = 0
    error_count: int = 0
    # Requests the provider answered only in part (e.g. a surface that came back
    # with fewer cells than requested). Counted separately from outright errors
    # so a badge never reads 100% success while visible data is missing.
    incomplete_count: int = 0
    # Whether the transport/session is usable, independent of request outcomes.
    session_status: str | None = None
    last_called_at: datetime | None = None


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    generated_at: datetime
    providers: list[ProviderUsageSummary] = field(default_factory=list)
    health: list[ProviderUsageHealth] = field(default_factory=list)
    recent_calls: list[ProviderUsageCall] = field(default_factory=list)
    total_calls: int = 0
    # total_calls es la ventana retenida (las filas suman exactamente eso); lifetime_calls
    # cuenta todo lo registrado desde el arranque y retained_limit es el tamaño de la
    # ventana (GUA-20260903-10).
    lifetime_calls: int = 0
    retained_limit: int = 0
    source_provider: str = "gamma"
    origin: str = "provider_usage_ledger.snapshot"
    transformation_note: str | None = (
        "In-memory provider usage diagnostics collected from Gamma provider boundaries and outbound "
        "urllib HTTP requests since backend startup. Provider rows sum to total_calls, the retained window."
    )
