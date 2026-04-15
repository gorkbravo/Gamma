from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.analytics.risk_metrics import max_drawdown, realized_vol
from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.application.instrument_identity import find_identity_by_symbol, snapshot_identity_map
from src.application.research_service import ResearchAnalysisResult
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.research_overview import (
    ResearchOverviewCoverage,
    ResearchOverviewMetricOption,
    ResearchOverviewMetrics,
    ResearchOverviewNode,
    ResearchOverviewRankItem,
    ResearchOverviewRankings,
    ResearchOverviewResult,
    ResearchOverviewSortOption,
    ResearchOverviewSummary,
    ResearchOverviewUniverse,
    ResearchOverviewUniverseInstrument,
)


class SyntheticPositionModel(BaseModel):
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None
    sec_type: str | None = None
    currency: str | None = None
    exchange: str | None = None
    primary_exchange: str | None = None
    provider: str | None = None
    provider_id: str | None = None

    def to_domain(self) -> SyntheticPosition:
        return SyntheticPosition(
            symbol=self.symbol,
            weight=self.weight,
            instrument_id=self.instrument_id,
            display_symbol=self.display_symbol,
            sec_type=self.sec_type,
            currency=self.currency,
            exchange=self.exchange,
            primary_exchange=self.primary_exchange,
            provider=self.provider,
            provider_id=self.provider_id,
        )


class ResearchAnalyzeRequestModel(BaseModel):
    scope_type: ResearchScopeType
    primary_symbol: str = ""
    synthetic_positions: list[SyntheticPositionModel] = Field(default_factory=list)
    benchmark_symbol: str = "SPY"
    lookback_days: int = 252


class ResearchOverviewUniverseInstrumentModel(BaseModel):
    symbol: str
    label: str
    group: str
    sector: str
    industry: str | None = None
    weight: float = 1.0
    market_cap_usd: float | None = None
    index_weight: float | None = None
    sort_rank: int | None = None
    currency: str = "USD"
    exchange: str = "SMART"
    sec_type: str = "STK"

    @classmethod
    def from_domain(cls, row: ResearchOverviewUniverseInstrument) -> "ResearchOverviewUniverseInstrumentModel":
        return cls(
            symbol=row.symbol,
            label=row.label,
            group=row.group,
            sector=row.sector,
            industry=row.industry,
            weight=row.weight,
            market_cap_usd=row.market_cap_usd,
            index_weight=row.index_weight,
            sort_rank=row.sort_rank,
            currency=row.currency,
            exchange=row.exchange,
            sec_type=row.sec_type,
        )


class ResearchOverviewUniverseModel(BaseModel):
    universe_id: str
    label: str
    description: str
    instruments: list[ResearchOverviewUniverseInstrumentModel] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchOverviewUniverse) -> "ResearchOverviewUniverseModel":
        return cls(
            universe_id=row.universe_id,
            label=row.label,
            description=row.description,
            instruments=[ResearchOverviewUniverseInstrumentModel.from_domain(item) for item in row.instruments],
            limitations=list(row.limitations),
        )


class ResearchOverviewMetricOptionModel(BaseModel):
    metric_id: str
    label: str
    description: str

    @classmethod
    def from_domain(cls, row: ResearchOverviewMetricOption) -> "ResearchOverviewMetricOptionModel":
        return cls(**row.__dict__)


class ResearchOverviewSortOptionModel(BaseModel):
    sort_id: str
    label: str
    description: str

    @classmethod
    def from_domain(cls, row: ResearchOverviewSortOption) -> "ResearchOverviewSortOptionModel":
        return cls(**row.__dict__)


class ResearchOverviewMetricsModel(BaseModel):
    total_return: float | None = None
    annual_volatility: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    relative_return: float | None = None
    latest_price: float | None = None
    observation_count: int = 0

    @classmethod
    def from_domain(cls, row: ResearchOverviewMetrics) -> "ResearchOverviewMetricsModel":
        return cls(**row.__dict__)


class ResearchOverviewNodeModel(BaseModel):
    node_id: str
    normalized_id: str
    label: str
    level: str
    parent_id: str | None = None
    group: str | None = None
    sector: str | None = None
    industry: str | None = None
    symbol: str | None = None
    instrument_id: str | None = None
    weight: float | None = None
    market_cap_usd: float | None = None
    index_weight: float | None = None
    sort_rank: int | None = None
    size: float
    metrics: ResearchOverviewMetricsModel
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchOverviewNode) -> "ResearchOverviewNodeModel":
        payload = dict(row.__dict__)
        payload["metrics"] = ResearchOverviewMetricsModel.from_domain(row.metrics)
        payload["freshness_label"] = row.freshness_label.value
        return cls(**payload)


class ResearchOverviewCoverageModel(BaseModel):
    instrument_count: int
    priced_count: int
    missing_symbols: list[str] = Field(default_factory=list)
    benchmark_symbol: str
    benchmark_available: bool
    benchmark_observation_count: int

    @classmethod
    def from_domain(cls, row: ResearchOverviewCoverage) -> "ResearchOverviewCoverageModel":
        return cls(**row.__dict__)


class ResearchOverviewRankItemModel(BaseModel):
    node_id: str
    label: str
    group: str | None = None
    symbol: str | None = None
    value: float | None = None

    @classmethod
    def from_domain(cls, row: ResearchOverviewRankItem) -> "ResearchOverviewRankItemModel":
        return cls(**row.__dict__)


class ResearchOverviewRankingsModel(BaseModel):
    leaders: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    laggards: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    highest_volatility: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    highest_beta: list[ResearchOverviewRankItemModel] = Field(default_factory=list)
    largest_drawdowns: list[ResearchOverviewRankItemModel] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, row: ResearchOverviewRankings) -> "ResearchOverviewRankingsModel":
        return cls(
            leaders=[ResearchOverviewRankItemModel.from_domain(item) for item in row.leaders],
            laggards=[ResearchOverviewRankItemModel.from_domain(item) for item in row.laggards],
            highest_volatility=[ResearchOverviewRankItemModel.from_domain(item) for item in row.highest_volatility],
            highest_beta=[ResearchOverviewRankItemModel.from_domain(item) for item in row.highest_beta],
            largest_drawdowns=[ResearchOverviewRankItemModel.from_domain(item) for item in row.largest_drawdowns],
        )


class ResearchOverviewSummaryModel(BaseModel):
    leading_group: ResearchOverviewRankItemModel | None = None
    lagging_group: ResearchOverviewRankItemModel | None = None
    highest_volatility_group: ResearchOverviewRankItemModel | None = None
    coverage_note: str | None = None

    @classmethod
    def from_domain(cls, row: ResearchOverviewSummary) -> "ResearchOverviewSummaryModel":
        return cls(
            leading_group=ResearchOverviewRankItemModel.from_domain(row.leading_group) if row.leading_group else None,
            lagging_group=ResearchOverviewRankItemModel.from_domain(row.lagging_group) if row.lagging_group else None,
            highest_volatility_group=(
                ResearchOverviewRankItemModel.from_domain(row.highest_volatility_group)
                if row.highest_volatility_group
                else None
            ),
            coverage_note=row.coverage_note,
        )


class ResearchOverviewResponseModel(BaseModel):
    universe_id: str
    universe_label: str
    universe_description: str
    timeframe: str
    lookback_days: int
    benchmark_symbol: str
    available_universes: list[ResearchOverviewUniverseModel] = Field(default_factory=list)
    available_timeframes: list[str] = Field(default_factory=list)
    metric_options: list[ResearchOverviewMetricOptionModel] = Field(default_factory=list)
    sort_options: list[ResearchOverviewSortOptionModel] = Field(default_factory=list)
    nodes: list[ResearchOverviewNodeModel] = Field(default_factory=list)
    coverage: ResearchOverviewCoverageModel
    rankings: ResearchOverviewRankingsModel
    summary: ResearchOverviewSummaryModel
    warnings: list[str] = Field(default_factory=list)
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: str

    @classmethod
    def from_domain(cls, row: ResearchOverviewResult) -> "ResearchOverviewResponseModel":
        return cls(
            universe_id=row.universe_id,
            universe_label=row.universe_label,
            universe_description=row.universe_description,
            timeframe=row.timeframe,
            lookback_days=row.lookback_days,
            benchmark_symbol=row.benchmark_symbol,
            available_universes=[ResearchOverviewUniverseModel.from_domain(item) for item in row.available_universes],
            available_timeframes=list(row.available_timeframes),
            metric_options=[ResearchOverviewMetricOptionModel.from_domain(item) for item in row.metric_options],
            sort_options=[ResearchOverviewSortOptionModel.from_domain(item) for item in row.sort_options],
            nodes=[ResearchOverviewNodeModel.from_domain(item) for item in row.nodes],
            coverage=ResearchOverviewCoverageModel.from_domain(row.coverage),
            rankings=ResearchOverviewRankingsModel.from_domain(row.rankings),
            summary=ResearchOverviewSummaryModel.from_domain(row.summary),
            warnings=list(row.warnings),
            source_provider=row.source_provider,
            retrieved_at=row.retrieved_at,
            origin=row.origin,
            transformation_note=row.transformation_note,
            freshness_label=row.freshness_label.value,
        )


class WeightPointModel(BaseModel):
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None


class ResearchSummaryModel(BaseModel):
    total_return: float | None = None
    annual_return: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None
    correlation: float | None = None


class ResearchStructureModel(BaseModel):
    total_weight: float | None = None
    top_weight: float | None = None
    top5_weight: float | None = None
    concentration_hhi: float | None = None
    effective_positions: float | None = None
    aligned_symbol_count: int = 0


class ResearchCoverageModel(BaseModel):
    available_symbols: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)
    benchmark_overlap_count: int = 0


class ResearchConstituentModel(BaseModel):
    symbol: str
    weight: float
    instrument_id: str | None = None
    display_symbol: str | None = None
    total_return: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
    weighted_return: float | None = None


class ResearchAnalyzeResponseModel(BaseModel):
    scope_type: ResearchScopeType
    benchmark_symbol: str
    primary_symbol: str | None = None
    observations_count: int
    snapshot: PortfolioSnapshotModel | None = None
    performance_points: list[TimeSeriesPoint]
    benchmark_points: list[TimeSeriesPoint]
    primary_price_points: list[TimeSeriesPoint]
    weights: list[WeightPointModel]
    summary: ResearchSummaryModel
    structure: ResearchStructureModel
    coverage: ResearchCoverageModel
    constituents: list[ResearchConstituentModel]
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_service_result(cls, result: ResearchAnalysisResult) -> "ResearchAnalyzeResponseModel":
        total_return = None
        annual_return = None
        annual_vol = None
        max_dd = None
        beta = None
        correlation = None
        if not result.perf.empty:
            cumulative = (1.0 + result.perf).cumprod()
            total_return = float(cumulative.iloc[-1] - 1.0)
            annual_return = _annualized_return(result.perf)
            _daily_vol, annual_vol = realized_vol(result.perf)
            max_dd = max_drawdown(result.perf)
            beta, correlation = _beta_corr(result.perf, result.benchmark_returns)

        return cls(
            scope_type=result.scope_type,
            benchmark_symbol=result.benchmark_symbol,
            primary_symbol=result.primary_symbol,
            observations_count=int(len(result.perf)),
            snapshot=PortfolioSnapshotModel.from_domain(result.snapshot) if result.snapshot is not None else None,
            performance_points=series_to_points(result.perf),
            benchmark_points=series_to_points(result.benchmark_returns),
            primary_price_points=series_to_points(result.primary_price),
            weights=[
                _weight_point_model(result.snapshot, str(instrument_id), float(weight))
                for instrument_id, weight in result.weights.items()
            ],
            summary=ResearchSummaryModel(
                total_return=total_return,
                annual_return=annual_return,
                annual_vol=annual_vol,
                max_drawdown=max_dd,
                beta=beta,
                correlation=correlation,
            ),
            structure=_structure_from_weights(result.weights),
            coverage=ResearchCoverageModel(
                available_symbols=list(result.available_symbols),
                missing_symbols=list(result.missing_symbols),
                benchmark_overlap_count=result.benchmark_overlap_count,
            ),
            constituents=_constituents_from_result(result),
            warnings=list(result.warnings),
        )


def _annualized_return(perf):
    if perf.empty:
        return None
    cumulative = float((1.0 + perf).prod())
    periods = int(len(perf))
    if periods <= 0 or cumulative <= 0:
        return None
    return float(cumulative ** (252.0 / periods) - 1.0)


def _beta_corr(perf, benchmark_returns):
    if perf.empty or benchmark_returns.empty:
        return None, None
    aligned = perf.to_frame("portfolio").join(benchmark_returns.to_frame("benchmark"), how="inner").dropna()
    if len(aligned) < 2:
        return None, None
    benchmark_var = float(aligned["benchmark"].var())
    corr = float(aligned["portfolio"].corr(aligned["benchmark"])) if len(aligned) > 1 else None
    if benchmark_var <= 0:
        return None, corr
    cov = float(aligned["portfolio"].cov(aligned["benchmark"]))
    return cov / benchmark_var, corr


def _structure_from_weights(weights) -> ResearchStructureModel:
    if weights.empty:
        return ResearchStructureModel()
    absolute_weights = weights.abs().astype(float)
    total_weight = float(absolute_weights.sum())
    if total_weight <= 0:
        return ResearchStructureModel(total_weight=total_weight, aligned_symbol_count=int(len(weights)))
    normalized = absolute_weights / total_weight
    hhi = float((normalized**2).sum())
    return ResearchStructureModel(
        total_weight=total_weight,
        top_weight=float(normalized.max()),
        top5_weight=float(normalized.sort_values(ascending=False).head(5).sum()),
        concentration_hhi=hhi,
        effective_positions=float(1.0 / hhi) if hhi > 0 else None,
        aligned_symbol_count=int(len(weights)),
    )


def _constituents_from_result(result: ResearchAnalysisResult) -> list[ResearchConstituentModel]:
    if result.weights.empty:
        return []
    rows: list[ResearchConstituentModel] = []
    for instrument_id, weight in result.weights.sort_values(ascending=False).items():
        position_meta = _position_meta(result.snapshot, str(instrument_id))
        total_return = _series_value(result.constituent_total_returns, instrument_id)
        annual_vol = _series_value(result.constituent_annual_vol, instrument_id)
        max_dd = _series_value(result.constituent_max_drawdown, instrument_id)
        rows.append(
            ResearchConstituentModel(
                symbol=position_meta.get("symbol") or str(instrument_id),
                weight=float(weight),
                instrument_id=position_meta.get("instrument_id"),
                display_symbol=position_meta.get("display_symbol"),
                total_return=total_return,
                annual_vol=annual_vol,
                max_drawdown=max_dd,
                weighted_return=float(weight) * total_return if total_return is not None else None,
            )
        )
    return rows


def _series_value(series, symbol: str) -> float | None:
    if series is None or getattr(series, "empty", True):
        return None
    value = series.get(symbol)
    return None if value is None else float(value)


def _weight_point_model(snapshot, instrument_id: str, weight: float) -> WeightPointModel:
    position_meta = _position_meta(snapshot, instrument_id)
    return WeightPointModel(
        symbol=position_meta.get("symbol") or instrument_id,
        weight=weight,
        instrument_id=position_meta.get("instrument_id"),
        display_symbol=position_meta.get("display_symbol"),
    )


def _position_meta(snapshot, instrument_id: str) -> dict[str, str | None]:
    identity_map = snapshot_identity_map(snapshot)
    identity = identity_map.get(instrument_id)
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
    if snapshot is None:
        return {"instrument_id": None, "symbol": None, "display_symbol": None}
    return {"instrument_id": None, "symbol": None, "display_symbol": None}
