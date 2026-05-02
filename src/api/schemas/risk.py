from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.risk_service import RiskComputationPayload
from src.models.portfolio import RiskResults


class RiskComputeRequestModel(BaseModel):
    snapshot: PortfolioSnapshotModel
    source_scope: str = "portfolio"
    alpha: float = 0.95
    lookback_days: int = 252
    horizon_days: int = 1
    mc_horizon_days: int = 10
    mc_simulation_model: str = "Gaussian"
    mc_num_simulations: int = 2000
    beta_window: int = 126
    benchmark_symbol: str = "SPY"
    include_monte_carlo: bool = True


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
    instrument_id: str | None = None
    display_symbol: str | None = None
    weight: float | None = None
    daily_vol: float | None = None
    variance_contribution_pct: float | None = None
    marginal_contribution_to_risk: float | None = None
    component_var: float | None = None


class IndexedValuePoint(BaseModel):
    index: int
    value: float


class MonteCarloChartsModel(BaseModel):
    terminal_returns: list[float] = Field(default_factory=list)
    fan_percentiles: dict[str, list[IndexedValuePoint]] = Field(default_factory=dict)
    sample_paths: dict[str, list[IndexedValuePoint]] = Field(default_factory=dict)


class ExcludedAssetModel(BaseModel):
    symbol: str
    instrument_id: str | None = None
    display_symbol: str | None = None
    reason: str


class RiskFrontierWeightModel(BaseModel):
    symbol: str
    instrument_id: str | None = None
    display_symbol: str | None = None
    weight: float


class RiskFrontierPointModel(BaseModel):
    label: str
    kind: str
    annual_return: float
    annual_vol: float
    sharpe: float | None = None
    weights: list[RiskFrontierWeightModel] = Field(default_factory=list)
    history_rows: int | None = None
    history_start: str | None = None
    history_end: str | None = None
    source_provider: str | None = None


class RiskCorrelationAssetModel(BaseModel):
    symbol: str
    instrument_id: str | None = None
    display_symbol: str | None = None


class RiskCorrelationCellModel(BaseModel):
    row: str
    column: str
    correlation: float | None = None


class RiskCorrelationMatrixModel(BaseModel):
    assets: list[RiskCorrelationAssetModel] = Field(default_factory=list)
    cells: list[RiskCorrelationCellModel] = Field(default_factory=list)


class RiskComputeResponseModel(BaseModel):
    metrics: RiskMetricsModel
    portfolio_return_points: list[TimeSeriesPoint]
    benchmark_return_points: list[TimeSeriesPoint] = Field(default_factory=list)
    contributions: list[RiskContributionModel]
    monte_carlo: MonteCarloChartsModel = Field(default_factory=MonteCarloChartsModel)
    frontier_points: list[RiskFrontierPointModel] = Field(default_factory=list)
    correlation_matrix: RiskCorrelationMatrixModel = Field(default_factory=RiskCorrelationMatrixModel)
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
            meta = _position_meta(payload.snapshot, symbol)
            daily_vol = payload.returns_df[symbol].std() if symbol in payload.returns_df else None
            contribution_rows.append(
                RiskContributionModel(
                    symbol=meta.get("symbol") or symbol,
                    instrument_id=meta.get("instrument_id"),
                    display_symbol=meta.get("display_symbol"),
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
            benchmark_return_points=series_to_points(payload.benchmark_returns),
            contributions=contribution_rows,
            monte_carlo=MonteCarloChartsModel(
                terminal_returns=_series_to_float_list(results.monte_carlo_terminal_returns),
                fan_percentiles=_fan_percentiles_to_payload(results.monte_carlo_fan_percentiles),
                sample_paths=_fan_percentiles_to_payload(results.monte_carlo_sample_paths),
            ),
            frontier_points=[
                RiskFrontierPointModel(
                    label=point.label,
                    kind=point.kind,
                    annual_return=float(point.annual_return),
                    annual_vol=float(point.annual_vol),
                    sharpe=_to_float(point.sharpe),
                    history_rows=point.history_rows,
                    history_start=point.history_start,
                    history_end=point.history_end,
                    source_provider=point.source_provider,
                    weights=[
                        RiskFrontierWeightModel(
                            symbol=weight.symbol,
                            instrument_id=weight.instrument_id,
                            display_symbol=weight.display_symbol,
                            weight=float(weight.weight),
                        )
                        for weight in point.weights
                    ],
                )
                for point in payload.frontier_points
            ],
            correlation_matrix=_correlation_matrix_to_payload(payload),
            excluded_assets=[
                ExcludedAssetModel(
                    symbol=_position_meta(payload.snapshot, symbol).get("symbol") or symbol,
                    instrument_id=_position_meta(payload.snapshot, symbol).get("instrument_id"),
                    display_symbol=_position_meta(payload.snapshot, symbol).get("display_symbol"),
                    reason=reason,
                )
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


def _series_to_float_list(series) -> list[float]:
    if series is None or series.empty:
        return []
    clean = series.dropna()
    return [float(value) for value in clean.tolist()]


def _correlation_matrix_to_payload(payload: RiskComputationPayload) -> RiskCorrelationMatrixModel:
    frame = payload.correlation_matrix
    if frame is None or frame.empty:
        return RiskCorrelationMatrixModel()
    columns = [str(column) for column in frame.columns]
    assets = [
        RiskCorrelationAssetModel(
            symbol=_position_meta(payload.snapshot, column).get("symbol") or column,
            instrument_id=_position_meta(payload.snapshot, column).get("instrument_id"),
            display_symbol=_position_meta(payload.snapshot, column).get("display_symbol"),
        )
        for column in columns
    ]
    cells: list[RiskCorrelationCellModel] = []
    for row in columns:
        for column in columns:
            cells.append(
                RiskCorrelationCellModel(
                    row=row,
                    column=column,
                    correlation=_to_float(frame.loc[row, column]) if row in frame.index and column in frame.columns else None,
                )
            )
    return RiskCorrelationMatrixModel(assets=assets, cells=cells)


def _fan_percentiles_to_payload(frame) -> dict[str, list[IndexedValuePoint]]:
    if frame is None or frame.empty:
        return {}
    payload: dict[str, list[IndexedValuePoint]] = {}
    for column in frame.columns:
        series = frame[column].dropna()
        payload[str(column)] = [
            IndexedValuePoint(index=int(index), value=float(value))
            for index, value in series.items()
        ]
    return payload


def _position_meta(snapshot, instrument_id: str) -> dict[str, str | None]:
    identity = snapshot_identity_map(snapshot).get(instrument_id)
    if identity is not None:
        return {
            "instrument_id": identity.instrument_id,
            "symbol": identity.symbol,
            "display_symbol": identity.display_symbol,
        }
    fallback = find_identity_by_symbol(snapshot, instrument_id)
    if fallback is not None:
        return {
            "instrument_id": fallback.instrument_id,
            "symbol": fallback.symbol,
            "display_symbol": fallback.display_symbol,
        }
    return {"instrument_id": None, "symbol": None, "display_symbol": None}
