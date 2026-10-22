from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.api.schemas.research import ResearchBookRiskLegModel
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.request_limits import (
    MAX_RISK_BETA_WINDOW_DAYS,
    MAX_RISK_HORIZON_DAYS,
    MAX_RISK_LOOKBACK_DAYS,
    MAX_RISK_MC_HORIZON_DAYS,
    MAX_RISK_MC_SIMULATIONS,
    MAX_STRATEGY_LAB_ROWS,
)
from src.analytics.stress import VolatilityRegimeAnalysis
from src.application.risk_service import RiskComputationPayload, RiskStressReplayResult
from src.models.portfolio import RiskResults


class RiskComputeRequestModel(BaseModel):
    snapshot: PortfolioSnapshotModel
    source_scope: str = Field(default="portfolio", max_length=32, pattern="^(portfolio|research|research_book)$")
    source_label: str | None = Field(default=None, max_length=160)
    source_object_id: str | None = Field(default=None, max_length=240)
    source_origin: str | None = Field(default=None, max_length=160)
    research_book_return_points: list[TimeSeriesPoint] = Field(default_factory=list, max_length=MAX_STRATEGY_LAB_ROWS)
    research_book_benchmark_points: list[TimeSeriesPoint] | None = Field(default=None, max_length=MAX_STRATEGY_LAB_ROWS)
    research_book_legs: list[ResearchBookRiskLegModel] = Field(default_factory=list, max_length=100)
    alpha: float = Field(default=0.95, gt=0.0, lt=1.0)
    lookback_days: int = Field(default=252, ge=20, le=MAX_RISK_LOOKBACK_DAYS)
    horizon_days: int = Field(default=1, ge=1, le=MAX_RISK_HORIZON_DAYS)
    mc_horizon_days: int = Field(default=10, ge=1, le=MAX_RISK_MC_HORIZON_DAYS)
    mc_simulation_model: str = Field(default="Gaussian", min_length=1, max_length=32)
    mc_num_simulations: int = Field(default=2000, ge=100, le=MAX_RISK_MC_SIMULATIONS)
    beta_window: int = Field(default=126, ge=20, le=MAX_RISK_BETA_WINDOW_DAYS)
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=32)
    include_monte_carlo: bool = True


class RiskStressReplayRequestModel(BaseModel):
    snapshot: PortfolioSnapshotModel
    source_scope: str = Field(default="portfolio", max_length=32, pattern="^(portfolio|research|research_book)$")
    research_book_legs: list[ResearchBookRiskLegModel] = Field(default_factory=list, max_length=100)
    benchmark_symbol: str = Field(default="SPY", min_length=1, max_length=32)


class RiskRegimeStatsModel(BaseModel):
    regime: str
    observation_count: int
    annual_vol: float | None = None
    historical_var: float | None = None
    historical_cvar: float | None = None
    benchmark_correlation: float | None = None
    benchmark_annual_vol: float | None = None


class RiskRegimeAnalysisModel(BaseModel):
    status: str = "unavailable"
    window_days: int = 21
    threshold_annual_vol: float | None = None
    regimes: list[RiskRegimeStatsModel] = Field(default_factory=list)
    observation_count: int = 0
    note: str | None = None
    method: str | None = None

    @classmethod
    def from_domain(cls, analysis: VolatilityRegimeAnalysis | None) -> "RiskRegimeAnalysisModel":
        if analysis is None:
            return cls()
        return cls(
            status=analysis.status,
            window_days=analysis.window_days,
            threshold_annual_vol=analysis.threshold_annual_vol,
            regimes=[RiskRegimeStatsModel(**row.__dict__) for row in analysis.regimes],
            observation_count=analysis.observation_count,
            note=analysis.note,
            method=analysis.method,
        )


class RiskStressLegModel(BaseModel):
    symbol: str
    instrument_id: str | None = None
    display_symbol: str | None = None
    weight: float
    status: str
    episode_return: float | None = None
    pnl: float | None = None
    contribution_share: float | None = None
    start_price_date: str | None = None
    end_price_date: str | None = None
    note: str | None = None


class RiskStressEpisodeModel(BaseModel):
    episode_id: str
    label: str
    start: str
    end: str
    description: str
    # Tipo de episodio ("equity" | "commodity") y serie que fija la ventana (GUA-20261021-9).
    kind: str = "equity"
    anchor: str | None = None
    status: str
    book_return: float | None = None
    book_pnl: float | None = None
    benchmark_return: float | None = None
    active_return: float | None = None
    max_drawdown: float | None = None
    worst_day_return: float | None = None
    worst_day_date: str | None = None
    covered_gross_weight: float = 0.0
    gross_weight: float = 0.0
    observation_count: int = 0
    legs: list[RiskStressLegModel] = Field(default_factory=list)
    note: str | None = None


class RiskStressReplayResponseModel(BaseModel):
    episodes: list[RiskStressEpisodeModel] = Field(default_factory=list)
    portfolio_value: float
    base_currency: str
    benchmark_symbol: str
    lookback_days: int
    method: str
    warnings: list[str] = Field(default_factory=list)
    history_start: str | None = None
    history_end: str | None = None
    coverage_summary: str | None = None

    @classmethod
    def from_domain(cls, result: RiskStressReplayResult) -> "RiskStressReplayResponseModel":
        def iso(value) -> str | None:
            return value.isoformat() if value is not None else None

        episodes = []
        for row in result.episodes:
            legs = []
            for leg in row.legs:
                meta = result.leg_metadata.get(leg.key, {})
                legs.append(
                    RiskStressLegModel(
                        symbol=meta.get("symbol") or leg.key,
                        instrument_id=meta.get("instrument_id"),
                        display_symbol=meta.get("display_symbol"),
                        weight=float(leg.weight),
                        status=leg.status,
                        episode_return=_to_float(leg.episode_return),
                        pnl=_to_float(leg.pnl),
                        contribution_share=_to_float(leg.contribution_share),
                        start_price_date=iso(leg.start_price_date),
                        end_price_date=iso(leg.end_price_date),
                        note=leg.note,
                    )
                )
            episodes.append(
                RiskStressEpisodeModel(
                    episode_id=row.episode.episode_id,
                    label=row.episode.label,
                    start=row.episode.start.isoformat(),
                    end=row.episode.end.isoformat(),
                    description=row.episode.description,
                    kind=row.episode.kind,
                    anchor=row.episode.anchor,
                    status=row.status,
                    book_return=_to_float(row.book_return),
                    book_pnl=_to_float(row.book_pnl),
                    benchmark_return=_to_float(row.benchmark_return),
                    active_return=_to_float(row.active_return),
                    max_drawdown=_to_float(row.max_drawdown),
                    worst_day_return=_to_float(row.worst_day_return),
                    worst_day_date=iso(row.worst_day_date),
                    covered_gross_weight=float(row.covered_gross_weight),
                    gross_weight=float(row.gross_weight),
                    observation_count=int(row.observation_count),
                    legs=legs,
                    note=row.note,
                )
            )
        return cls(
            episodes=episodes,
            portfolio_value=float(result.portfolio_value),
            base_currency=result.base_currency,
            benchmark_symbol=result.benchmark_symbol,
            lookback_days=int(result.lookback_days),
            method=result.method,
            warnings=list(result.warnings),
            history_start=iso(result.history_start),
            history_end=iso(result.history_end),
            coverage_summary=result.coverage_summary,
        )


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
    # Contribución al CVaR histórico en moneda base: pérdida media de la posición en los días de cola.
    component_es: float | None = None


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
    # Identificador de columna al que se refieren las celdas (row/column). En una cartera coincide
    # con instrument_id; en un libro de investigación es el leg_id de la posición.
    key: str | None = None


class RiskCorrelationCellModel(BaseModel):
    row: str
    column: str
    correlation: float | None = None


class RiskCorrelationMatrixModel(BaseModel):
    assets: list[RiskCorrelationAssetModel] = Field(default_factory=list)
    cells: list[RiskCorrelationCellModel] = Field(default_factory=list)


class RiskDependencyNetworkNodeModel(BaseModel):
    symbol: str
    label: str
    cluster_id: int
    is_portfolio: bool
    portfolio_weight: float | None = None
    risk_contribution: float | None = None
    annual_vol: float | None = None
    degree: int
    strength: float
    centrality: float
    source_provider: str | None = None


class RiskDependencyNetworkEdgeModel(BaseModel):
    source: str
    target: str
    partial_correlation: float
    strength: float
    sign: int


class RiskDependencyNetworkClusterModel(BaseModel):
    cluster_id: int
    label: str
    node_count: int
    portfolio_node_count: int
    portfolio_weight: float
    average_annual_vol: float | None = None
    density: float
    top_symbols: list[str] = Field(default_factory=list)
    central_symbols: list[str] = Field(default_factory=list)


class RiskDependencyNetworkModel(BaseModel):
    nodes: list[RiskDependencyNetworkNodeModel] = Field(default_factory=list)
    edges: list[RiskDependencyNetworkEdgeModel] = Field(default_factory=list)
    clusters: list[RiskDependencyNetworkClusterModel] = Field(default_factory=list)
    methodology: str | None = None
    universe_size: int = 0
    observation_count: int = 0
    edge_threshold: float | None = None
    warnings: list[str] = Field(default_factory=list)
    source_provider: str = "gamma.risk.dependency_network"


class RiskComputeResponseModel(BaseModel):
    source_scope: str = "portfolio"
    source_label: str | None = None
    source_object_id: str | None = None
    source_origin: str | None = None
    metrics: RiskMetricsModel
    portfolio_return_points: list[TimeSeriesPoint]
    benchmark_return_points: list[TimeSeriesPoint] = Field(default_factory=list)
    contributions: list[RiskContributionModel]
    monte_carlo: MonteCarloChartsModel = Field(default_factory=MonteCarloChartsModel)
    frontier_points: list[RiskFrontierPointModel] = Field(default_factory=list)
    correlation_matrix: RiskCorrelationMatrixModel = Field(default_factory=RiskCorrelationMatrixModel)
    dependency_network: RiskDependencyNetworkModel = Field(default_factory=RiskDependencyNetworkModel)
    excluded_assets: list[ExcludedAssetModel]
    warnings: list[str] = Field(default_factory=list)
    # Días de cola (peor (1 - alpha) de la muestra) sobre los que se reparte el CVaR histórico.
    component_es_tail_days: int | None = None
    regime_analysis: RiskRegimeAnalysisModel = Field(default_factory=RiskRegimeAnalysisModel)

    @classmethod
    def from_service_payload(cls, payload: RiskComputationPayload) -> "RiskComputeResponseModel":
        results = payload.results
        contribution_rows: list[RiskContributionModel] = []
        contribution_returns = (
            payload.contribution_returns_df
            if payload.contribution_returns_df is not None
            else payload.returns_df
        )
        symbols = list(contribution_returns.columns)
        if not payload.contributions.empty:
            symbols.sort(key=lambda symbol: float(payload.contributions.get(symbol, np.nan)), reverse=True)
        for symbol in symbols:
            meta = (payload.contribution_metadata or {}).get(symbol) or _position_meta(payload.snapshot, symbol)
            daily_vol = contribution_returns[symbol].std() if symbol in contribution_returns else None
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
                    component_es=(
                        _to_float(payload.component_es.get(symbol)) if payload.component_es is not None else None
                    ),
                )
            )
        return cls(
            source_scope=payload.source_scope,
            source_label=payload.source_label,
            source_object_id=payload.source_object_id,
            source_origin=payload.source_origin,
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
            dependency_network=RiskDependencyNetworkModel(
                nodes=[RiskDependencyNetworkNodeModel(**row.__dict__) for row in payload.dependency_network.nodes],
                edges=[RiskDependencyNetworkEdgeModel(**row.__dict__) for row in payload.dependency_network.edges],
                clusters=[RiskDependencyNetworkClusterModel(**row.__dict__) for row in payload.dependency_network.clusters],
                methodology=payload.dependency_network.methodology,
                universe_size=payload.dependency_network.universe_size,
                observation_count=payload.dependency_network.observation_count,
                edge_threshold=payload.dependency_network.edge_threshold,
                warnings=list(payload.dependency_network.warnings or []),
                source_provider=payload.dependency_network.source_provider,
            ),
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
            component_es_tail_days=payload.component_es_tail_days,
            regime_analysis=RiskRegimeAnalysisModel.from_domain(payload.regime_analysis),
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
    assets = []
    for column in columns:
        # En un libro de investigación las columnas son posiciones (leg_id), no filas del snapshot.
        meta = (payload.contribution_metadata or {}).get(column) or _position_meta(payload.snapshot, column)
        assets.append(
            RiskCorrelationAssetModel(
                symbol=meta.get("symbol") or column,
                instrument_id=meta.get("instrument_id"),
                display_symbol=meta.get("display_symbol"),
                key=column,
            )
        )
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
