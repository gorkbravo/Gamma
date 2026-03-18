from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
