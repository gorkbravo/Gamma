from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


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
    benchmark_overlap_count: int | None = None
    concentration_hhi: float | None = None
    top5_weight: float | None = None
    effective_bets: float | None = None
    excluded_assets: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
