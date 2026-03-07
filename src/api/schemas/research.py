from __future__ import annotations

from pydantic import BaseModel, Field

from src.analytics.risk_metrics import max_drawdown, realized_vol
from src.api.schemas.portfolio import PortfolioSnapshotModel, TimeSeriesPoint, series_to_points
from src.application.research_service import ResearchAnalysisResult
from src.models.app_mode import ResearchScopeType, SyntheticPosition


class SyntheticPositionModel(BaseModel):
    symbol: str
    weight: float

    def to_domain(self) -> SyntheticPosition:
        return SyntheticPosition(symbol=self.symbol, weight=self.weight)


class ResearchAnalyzeRequestModel(BaseModel):
    scope_type: ResearchScopeType
    primary_symbol: str = ""
    synthetic_positions: list[SyntheticPositionModel] = Field(default_factory=list)
    benchmark_symbol: str = "SPY"
    lookback_days: int = 252


class WeightPointModel(BaseModel):
    symbol: str
    weight: float


class ResearchSummaryModel(BaseModel):
    total_return: float | None = None
    annual_return: float | None = None
    annual_vol: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None
    correlation: float | None = None


class ResearchAnalyzeResponseModel(BaseModel):
    scope_type: ResearchScopeType
    benchmark_symbol: str
    observations_count: int
    snapshot: PortfolioSnapshotModel | None = None
    performance_points: list[TimeSeriesPoint]
    benchmark_points: list[TimeSeriesPoint]
    primary_price_points: list[TimeSeriesPoint]
    weights: list[WeightPointModel]
    summary: ResearchSummaryModel
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
            observations_count=int(len(result.perf)),
            snapshot=PortfolioSnapshotModel.from_domain(result.snapshot) if result.snapshot is not None else None,
            performance_points=series_to_points(result.perf),
            benchmark_points=series_to_points(result.benchmark_returns),
            primary_price_points=series_to_points(result.primary_price),
            weights=[WeightPointModel(symbol=str(symbol), weight=float(weight)) for symbol, weight in result.weights.items()],
            summary=ResearchSummaryModel(
                total_return=total_return,
                annual_return=annual_return,
                annual_vol=annual_vol,
                max_drawdown=max_dd,
                beta=beta,
                correlation=correlation,
            ),
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
