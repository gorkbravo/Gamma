from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.platform_boundary import ReadOnlyBoundary
from src.models.provider_capabilities import ProviderCapability
from src.models.provider_usage import ProviderUsageCall, ProviderUsageHealth, ProviderUsageSnapshot, ProviderUsageSummary


class ConnectionStateModel(BaseModel):
    connected: bool
    status_text: str
    action_text: str
    action_enabled: bool
    active_account: str | None = None


class HealthResponseModel(BaseModel):
    status: str
    timestamp: datetime


class SystemStatusResponseModel(BaseModel):
    healthy: bool
    app_name: str
    backend: str
    mock_mode: bool
    base_currency: str
    market_data_mode: str
    connection: ConnectionStateModel
    cached_symbols: list[str] = Field(default_factory=list)


class ConnectionRequestModel(BaseModel):
    connected: bool


class MarketDataModeRequestModel(BaseModel):
    market_data_mode: str


class BaseCurrencyRequestModel(BaseModel):
    base_currency: str


class BaseCurrencyResponseModel(SystemStatusResponseModel):
    lines: list[str] = Field(default_factory=list)


class DiagnosticsResponseModel(BaseModel):
    generated_at: datetime
    mock_mode: bool
    base_currency: str
    market_data_mode: str
    connection: ConnectionStateModel
    history_cache: dict[str, float]
    local_history_entries: int
    local_history_path: str
    recent_errors: list[str] = Field(default_factory=list)
    cached_symbols: list[str] = Field(default_factory=list)
    research_scope_type: str = "none"
    research_primary_symbol: str | None = None
    research_synthetic_count: int = 0
    iv_running: bool = False
    iv_status_text: str = "Idle"
    iv_active_symbol: str | None = None


class ActionResponseModel(BaseModel):
    success: bool = True
    lines: list[str] = Field(default_factory=list)


class ProviderCapabilityModel(BaseModel):
    provider_id: str
    display_name: str
    provider_class: str
    status: str
    supported_domains: list[str] = Field(default_factory=list)
    asset_classes: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    data_types: list[str] = Field(default_factory=list)
    supports_live: bool = False
    supports_delayed: bool = False
    supports_historical: bool = False
    freshness_levels: list[str] = Field(default_factory=list)
    historical_depth: str | None = None
    requires_api_key: bool = False
    requires_user_entitlement: bool = False
    credential_env_vars: list[str] = Field(default_factory=list)
    configuration_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance_notes: list[str] = Field(default_factory=list)
    read_only_notes: list[str] = Field(default_factory=list)
    source_provider_values: list[str] = Field(default_factory=list)
    batch_fetching: str | None = None
    background_refresh_safe: bool = False
    safe_for_copilot: bool = True
    source_provider: str
    retrieved_at: datetime | None = None
    origin: str
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: ProviderCapability) -> "ProviderCapabilityModel":
        return cls(**row.__dict__)


class ProviderCapabilityListResponseModel(BaseModel):
    generated_at: datetime
    providers: list[ProviderCapabilityModel] = Field(default_factory=list)
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "provider_capability_registry.list_capabilities"
    transformation_note: str | None = None


class ProviderUsageCallModel(BaseModel):
    provider_id: str
    endpoint: str
    status: str
    cache_status: str | None = None
    duration_ms: float
    recorded_at: datetime
    message: str | None = None

    @classmethod
    def from_domain(cls, row: ProviderUsageCall) -> "ProviderUsageCallModel":
        return cls(**row.__dict__)


class ProviderUsageSummaryModel(BaseModel):
    provider_id: str
    call_count: int
    success_count: int
    unavailable_count: int
    error_count: int
    cache_hit_count: int
    cache_miss_count: int
    average_duration_ms: float
    last_status: str | None = None
    last_message: str | None = None
    last_error: str | None = None
    last_called_at: datetime | None = None
    endpoints: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ProviderUsageSummary) -> "ProviderUsageSummaryModel":
        return cls(**row.__dict__)


class ProviderUsageHealthModel(BaseModel):
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
    last_called_at: datetime | None = None

    @classmethod
    def from_domain(cls, row: ProviderUsageHealth) -> "ProviderUsageHealthModel":
        return cls(**row.__dict__)


class ProviderUsageResponseModel(BaseModel):
    generated_at: datetime
    providers: list[ProviderUsageSummaryModel] = Field(default_factory=list)
    health: list[ProviderUsageHealthModel] = Field(default_factory=list)
    recent_calls: list[ProviderUsageCallModel] = Field(default_factory=list)
    total_calls: int = 0
    source_provider: str = "gamma"
    origin: str = "provider_usage_ledger.snapshot"
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: ProviderUsageSnapshot) -> "ProviderUsageResponseModel":
        return cls(
            generated_at=row.generated_at,
            providers=[ProviderUsageSummaryModel.from_domain(provider) for provider in row.providers],
            health=[ProviderUsageHealthModel.from_domain(health) for health in row.health],
            recent_calls=[ProviderUsageCallModel.from_domain(call) for call in row.recent_calls],
            total_calls=row.total_calls,
            source_provider=row.source_provider,
            origin=row.origin,
            transformation_note=row.transformation_note,
        )


class ReadOnlyBoundaryModel(BaseModel):
    boundary_id: str
    read_only: bool
    allows: list[str] = Field(default_factory=list)
    prohibits: list[str] = Field(default_factory=list)
    hard_operator_locks: list[str] = Field(default_factory=list)
    app_boundary_notes: list[str] = Field(default_factory=list)
    copilot_notes: list[str] = Field(default_factory=list)
    ibkr_tws_notes: list[str] = Field(default_factory=list)
    source_provider: str = "gamma"
    retrieved_at: datetime | None = None
    origin: str = "gamma.system.read_only_boundary"
    transformation_note: str | None = None

    @classmethod
    def from_domain(cls, row: ReadOnlyBoundary) -> "ReadOnlyBoundaryModel":
        return cls(**row.__dict__)
