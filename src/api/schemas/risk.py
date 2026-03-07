from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.application.risk_service import RiskComputationPayload
from src.models.portfolio import RiskResults


class RiskComputeRequestModel(BaseModel):
    snapshot: PortfolioSnapshotModel
    alpha: float = 0.95
    lookback_days: int = 252
    horizon_days: int = 1
    mc_horizon_days: int = 10
    mc_simulation_model: str = "Gaussian"
    mc_num_simulations: int = 2000
    beta_window: int = 126
    benchmark_symbol: str = "SPY"


class RiskMetricsModel(BaseModel):
    alpha: float
    lookback_days: int
    horizon_days: int
    portfolio_value: float
    historical_var: float | None = None
    historical_cvar: float | None = None
    parametric_var: float | None = None
    daily_vol: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
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
    aligned_obs_count: int | None = None
    benchmark_overlap_count: int | None = None
    concentration_hhi: float | None = None
    top5_weight: float | None = None
    effective_bets: float | None = None

    @classmethod
    def from_domain(cls, results: RiskResults) -> "RiskMetricsModel":
        return cls(**{field: getattr(results, field) for field in cls.model_fields})


class RiskContributionModel(BaseModel):
    symbol: str
    weight: float | None = None
    daily_vol: float | None = None
    variance_contribution_pct: float | None = None
    marginal_contribution_to_risk: float | None = None
    component_var: float | None = None


class ExcludedAssetModel(BaseModel):
    symbol: str
    reason: str


class RiskComputeResponseModel(BaseModel):
    metrics: RiskMetricsModel
    portfolio_return_points: list[TimeSeriesPoint]
    contributions: list[RiskContributionModel]
    excluded_assets: list[ExcludedAssetModel]
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_service_payload(cls, payload: RiskComputationPayload) -> "RiskComputeResponseModel":
        results = payload.results
        contribution_rows: list[RiskContributionModel] = []
        symbols = list(payload.returns_df.columns)
        if not payload.contributions.empty:
            symbols.sort(key=lambda symbol: float(payload.contributions.get(symbol, np.nan)), reverse=True)
        for symbol in symbols:
            daily_vol = payload.returns_df[symbol].std() if symbol in payload.returns_df else None
            contribution_rows.append(
                RiskContributionModel(
                    symbol=symbol,
                    weight=_to_float(payload.weights.get(symbol)),
                    daily_vol=_to_float(daily_vol),
                    variance_contribution_pct=_to_float(payload.contributions.get(symbol)),
                    marginal_contribution_to_risk=_to_float(payload.marginal_contribution_to_risk.get(symbol)),
                    component_var=_to_float(payload.component_var.get(symbol)),
                )
            )
        return cls(
            metrics=RiskMetricsModel.from_domain(results),
            portfolio_return_points=series_to_points(payload.portfolio_returns),
            contributions=contribution_rows,
            excluded_assets=[
                ExcludedAssetModel(symbol=symbol, reason=reason)
                for symbol, reason in sorted(results.excluded_assets.items())
            ],
            warnings=list(results.warnings),
        )


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    if np.isnan(numeric):
        return None
    return numeric
