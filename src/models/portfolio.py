from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd

from src.models.instruments import build_instrument_id, normalize_symbol


class PortfolioSnapshotState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class PortfolioHistoryState(str, Enum):
    READY = "ready"
    EMPTY = "empty"
    RECOVERED = "recovered"
    DEGRADED = "degraded"
    FAILED = "failed"


class PortfolioPerformanceState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass
class PortfolioHistoryHealth:
    status: PortfolioHistoryState = PortfolioHistoryState.EMPTY
    point_count: int = 0
    base_currency: str | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    malformed_row_count: int = 0
    duplicate_row_count: int = 0
    recovery_archive_name: str | None = None
    last_write_at: datetime | None = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class PortfolioHistoryLoadResult:
    frame: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    health: PortfolioHistoryHealth = field(default_factory=PortfolioHistoryHealth)


@dataclass(frozen=True)
class PortfolioHistoryClearResult:
    archived: bool
    archive_name: str | None = None


@dataclass
class PositionItem:
    symbol: str
    sec_type: str
    currency: str
    quantity: float
    avg_cost: float | None
    market_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    weight: float | None = None
    base_market_value: float | None = None
    fx_rate: float | None = None
    instrument_id: str | None = None
    display_symbol: str | None = None
    exchange: str | None = None
    primary_exchange: str | None = None
    provider: str | None = None
    provider_id: str | None = None

    def resolved_symbol(self) -> str:
        return normalize_symbol(self.symbol)

    def resolved_display_symbol(self) -> str:
        return normalize_symbol(self.display_symbol or self.symbol)

    def resolved_instrument_id(self) -> str:
        return str(
            self.instrument_id
            or build_instrument_id(
                provider=self.provider or "portfolio",
                provider_id=self.provider_id,
                symbol=self.symbol,
                sec_type=self.sec_type,
                exchange=self.exchange,
                primary_exchange=self.primary_exchange,
                currency=self.currency,
            )
        )


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    base_currency: str
    account_summary: Dict[str, str]
    positions: List[PositionItem]
    total_market_value: float | None = None
    total_cash: float | None = None
    net_liquidation: float | None = None
    day_pnl: float | None = None
    day_pnl_pct: float | None = None
    day_pnl_source: str | None = None
    state: PortfolioSnapshotState = PortfolioSnapshotState.READY
    source_provider: str = "unknown"
    retrieved_at: datetime | None = None
    origin: str = "gamma.portfolio.snapshot"
    freshness_label: str = "unknown"
    transformation_note: str | None = None
    quote_mode: str = "Snapshot"
    market_data_mode: str = "unknown"
    complete: bool = True
    connection_ready: bool = False
    account_summary_available: bool = False
    account_subscription_usable: bool = False
    requested_position_count: int = 0
    quoted_position_count: int = 0
    missing_quote_count: int = 0
    missing_quote_symbols: List[str] = field(default_factory=list)
    cached_quote_count: int = 0
    cached_quote_symbols: List[str] = field(default_factory=list)
    delayed_quote_count: int = 0
    delayed_quote_symbols: List[str] = field(default_factory=list)
    available_value_count: int = 0
    history_store_health: PortfolioHistoryHealth | None = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class RiskResults:
    alpha: float
    lookback_days: int
    horizon_days: int
    portfolio_value: float
    historical_var: float | None
    historical_cvar: float | None
    parametric_var: float | None
    daily_vol: float | None
    annual_vol: float | None
    max_drawdown: float | None
    beta: float | None = None
    correlation: float | None = None
    alpha_annual: float | None = None
    covered_portfolio_value: float | None = None
    covered_risk_basis_value: float | None = None
    risk_basis_value: float | None = None
    risk_coverage_ratio: float | None = None
    historical_var_total_estimate: float | None = None
    historical_cvar_total_estimate: float | None = None
    parametric_var_total_estimate: float | None = None
    monte_carlo_model: str | None = None
    monte_carlo_horizon_days: int | None = None
    monte_carlo_num_simulations: int | None = None
    monte_carlo_var: float | None = None
    monte_carlo_cvar: float | None = None
    monte_carlo_var_total_estimate: float | None = None
    monte_carlo_cvar_total_estimate: float | None = None
    monte_carlo_terminal_returns: pd.Series | None = None
    monte_carlo_fan_percentiles: pd.DataFrame | None = None
    monte_carlo_sample_paths: pd.DataFrame | None = None
    aligned_obs_count: int | None = None
    # GUA-20260903-4: the requested horizon, the window actually analysed, and the
    # row reconciliation between them, so a "252D" run can never silently report an
    # unexplained 281-row sample.
    requested_lookback_days: int | None = None
    effective_start_date: str | None = None
    effective_end_date: str | None = None
    effective_span_calendar_days: int | None = None
    raw_observation_count: int | None = None
    dropped_observation_count: int | None = None
    return_calendar_basis: str | None = None
    benchmark_overlap_count: int | None = None
    concentration_hhi: float | None = None
    top5_weight: float | None = None
    effective_bets: float | None = None
    excluded_assets: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
