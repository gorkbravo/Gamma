from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.models.instruments import InstrumentReference, normalize_symbol
from src.models.provenance import FreshnessLabel


@dataclass(frozen=True)
class ResearchOverviewUniverseInstrument:
    symbol: str
    label: str
    group: str
    sector: str
    industry: str | None = None
    weight: float = 1.0
    currency: str = "USD"
    exchange: str = "SMART"
    sec_type: str = "STK"
    instrument_id: str | None = None
    provider: str | None = None
    provider_id: str | None = None

    def normalized_symbol(self) -> str:
        return normalize_symbol(self.symbol)

    def normalized_id(self) -> str:
        return self.instrument_id or self.normalized_symbol()

    def to_reference(self) -> InstrumentReference:
        return InstrumentReference(
            symbol=self.symbol,
            instrument_id=self.instrument_id,
            display_symbol=self.label,
            sec_type=self.sec_type,
            currency=self.currency,
            exchange=self.exchange,
            provider=self.provider,
            provider_id=self.provider_id,
        )


@dataclass(frozen=True)
class ResearchOverviewUniverse:
    universe_id: str
    label: str
    description: str
    instruments: tuple[ResearchOverviewUniverseInstrument, ...]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchOverviewRequest:
    universe_id: str = "sample_equities"
    timeframe: str = "3M"
    benchmark_symbol: str = "SPY"


@dataclass(frozen=True)
class ResearchOverviewMetricOption:
    metric_id: str
    label: str
    description: str


@dataclass(frozen=True)
class ResearchOverviewMetrics:
    total_return: float | None = None
    annual_volatility: float | None = None
    beta: float | None = None
    max_drawdown: float | None = None
    relative_return: float | None = None
    latest_price: float | None = None
    observation_count: int = 0


@dataclass(frozen=True)
class ResearchOverviewNode:
    node_id: str
    normalized_id: str
    label: str
    level: str
    parent_id: str | None
    group: str | None
    sector: str | None
    industry: str | None
    symbol: str | None
    instrument_id: str | None
    weight: float | None
    size: float
    metrics: ResearchOverviewMetrics
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchOverviewCoverage:
    instrument_count: int
    priced_count: int
    missing_symbols: list[str]
    benchmark_symbol: str
    benchmark_available: bool
    benchmark_observation_count: int


@dataclass(frozen=True)
class ResearchOverviewRankItem:
    node_id: str
    label: str
    group: str | None
    symbol: str | None
    value: float | None


@dataclass(frozen=True)
class ResearchOverviewRankings:
    leaders: list[ResearchOverviewRankItem] = field(default_factory=list)
    laggards: list[ResearchOverviewRankItem] = field(default_factory=list)
    highest_volatility: list[ResearchOverviewRankItem] = field(default_factory=list)
    highest_beta: list[ResearchOverviewRankItem] = field(default_factory=list)
    largest_drawdowns: list[ResearchOverviewRankItem] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchOverviewSummary:
    leading_group: ResearchOverviewRankItem | None = None
    lagging_group: ResearchOverviewRankItem | None = None
    highest_volatility_group: ResearchOverviewRankItem | None = None
    coverage_note: str | None = None


@dataclass(frozen=True)
class ResearchOverviewResult:
    universe_id: str
    universe_label: str
    universe_description: str
    timeframe: str
    lookback_days: int
    benchmark_symbol: str
    available_universes: list[ResearchOverviewUniverse]
    available_timeframes: list[str]
    metric_options: list[ResearchOverviewMetricOption]
    nodes: list[ResearchOverviewNode]
    coverage: ResearchOverviewCoverage
    rankings: ResearchOverviewRankings
    summary: ResearchOverviewSummary
    warnings: list[str]
    source_provider: str
    retrieved_at: datetime
    origin: str
    transformation_note: str | None = None
    freshness_label: FreshnessLabel = FreshnessLabel.UNKNOWN


RESEARCH_OVERVIEW_METRIC_OPTIONS: tuple[ResearchOverviewMetricOption, ...] = (
    ResearchOverviewMetricOption(
        metric_id="return",
        label="Return",
        description="Total return over the selected timeframe.",
    ),
    ResearchOverviewMetricOption(
        metric_id="volatility",
        label="Volatility",
        description="Annualized volatility from daily returns over the selected timeframe.",
    ),
    ResearchOverviewMetricOption(
        metric_id="beta",
        label="Beta",
        description="Benchmark beta where benchmark history overlaps the node.",
    ),
    ResearchOverviewMetricOption(
        metric_id="drawdown",
        label="Drawdown",
        description="Maximum drawdown over the selected timeframe.",
    ),
    ResearchOverviewMetricOption(
        metric_id="relative_return",
        label="Relative",
        description="Total return minus benchmark total return where benchmark history is available.",
    ),
)


RESEARCH_OVERVIEW_TIMEFRAMES: dict[str, int] = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}


RESEARCH_OVERVIEW_UNIVERSES: tuple[ResearchOverviewUniverse, ...] = (
    ResearchOverviewUniverse(
        universe_id="sample_equities",
        label="Sample equities",
        description="Small offline-friendly listed-equity sample used to prove the Research Overview data contract.",
        instruments=(
            ResearchOverviewUniverseInstrument(
                symbol="AAPL",
                label="Apple",
                group="US Mega-Cap Tech",
                sector="Information Technology",
                industry="Consumer Electronics",
                weight=1.0,
            ),
            ResearchOverviewUniverseInstrument(
                symbol="MSFT",
                label="Microsoft",
                group="US Mega-Cap Tech",
                sector="Information Technology",
                industry="Software",
                weight=1.0,
            ),
            ResearchOverviewUniverseInstrument(
                symbol="SAP",
                label="SAP",
                group="International Software",
                sector="Information Technology",
                industry="Enterprise Software",
                weight=1.0,
                currency="EUR",
            ),
        ),
        limitations=(
            "This is a narrow sample/watchlist universe, not a complete market map.",
            "Tile size is equal-weight because market-cap weights are not available in this first pass.",
        ),
    ),
    ResearchOverviewUniverse(
        universe_id="major_etfs",
        label="Major ETFs",
        description="Curated ETF basket for a broad first-pass market lens when provider history is available.",
        instruments=(
            ResearchOverviewUniverseInstrument("SPY", "S&P 500 ETF", "Broad Market", "Broad Market", "Large Cap", 1.0),
            ResearchOverviewUniverseInstrument("QQQ", "Nasdaq 100 ETF", "Growth / Tech", "Broad Market", "Growth", 1.0),
            ResearchOverviewUniverseInstrument("IWM", "Russell 2000 ETF", "Small Cap", "Broad Market", "Small Cap", 1.0),
            ResearchOverviewUniverseInstrument("XLK", "Technology Select Sector", "Sector ETFs", "Information Technology", None, 1.0),
            ResearchOverviewUniverseInstrument("XLF", "Financial Select Sector", "Sector ETFs", "Financials", None, 1.0),
            ResearchOverviewUniverseInstrument("XLV", "Health Care Select Sector", "Sector ETFs", "Health Care", None, 1.0),
            ResearchOverviewUniverseInstrument("XLE", "Energy Select Sector", "Sector ETFs", "Energy", None, 1.0),
            ResearchOverviewUniverseInstrument("XLI", "Industrial Select Sector", "Sector ETFs", "Industrials", None, 1.0),
            ResearchOverviewUniverseInstrument("XLY", "Consumer Discretionary", "Sector ETFs", "Consumer Discretionary", None, 1.0),
            ResearchOverviewUniverseInstrument("XLP", "Consumer Staples", "Sector ETFs", "Consumer Staples", None, 1.0),
            ResearchOverviewUniverseInstrument("XLU", "Utilities Select Sector", "Sector ETFs", "Utilities", None, 1.0),
            ResearchOverviewUniverseInstrument("XLB", "Materials Select Sector", "Sector ETFs", "Materials", None, 1.0),
            ResearchOverviewUniverseInstrument("XLRE", "Real Estate Select Sector", "Sector ETFs", "Real Estate", None, 1.0),
        ),
        limitations=(
            "This is a curated ETF basket, not a complete exchange universe.",
            "Tile size is equal-weight until market-cap or index-weight data is available.",
        ),
    ),
)
