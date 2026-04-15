from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.platform_boundary import ReadOnlyBoundary
from src.models.provider_capabilities import ProviderCapability


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
