from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    market_cap_usd: float | None = None
    index_weight: float | None = None
    sort_rank: int | None = None
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
    metadata_source_label: str = "Static Gamma reference list"
    coverage_label: str = "Partial research universe"
    is_complete_universe: bool = False


@dataclass(frozen=True)
class ResearchOverviewRequest:
    universe_id: str = "broad_us_market"
    timeframe: str = "DoD"
    benchmark_symbol: str = "SPY"
    provider_policy: str = "research_overview"
    force_refresh: bool = False


@dataclass(frozen=True)
class ResearchOverviewMetricOption:
    metric_id: str
    label: str
    description: str


@dataclass(frozen=True)
class ResearchOverviewSortOption:
    sort_id: str
    label: str
    description: str


@dataclass(frozen=True)
class ResearchOverviewMetrics:
    total_return: float | None = None
    latest_daily_return: float | None = None
    latest_daily_return_at: datetime | None = None
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
    market_cap_usd: float | None
    index_weight: float | None
    sort_rank: int | None
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
    coverage_ratio: float = 0.0
    missing_count: int = 0
    thin_history_symbols: list[str] = field(default_factory=list)
    min_observation_count: int = 0
    max_observation_count: int = 0
    coverage_label: str = "Partial research universe"
    history_source_label: str = "Unknown history source"
    metadata_source_label: str = "Static Gamma reference list"


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
    sort_options: list[ResearchOverviewSortOption]
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
    history_source_label: str = "Unknown history source"
    metadata_source_label: str = "Static Gamma reference list"
    coverage_label: str = "Partial research universe"


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


RESEARCH_OVERVIEW_SORT_OPTIONS: tuple[ResearchOverviewSortOption, ...] = (
    ResearchOverviewSortOption(
        sort_id="market_cap_desc",
        label="Market Cap",
        description="Tile area by static market-cap proxy where available.",
    ),
    ResearchOverviewSortOption(
        sort_id="universe_weight_desc",
        label="Universe Weight",
        description="Tile area by universe weight or equal-weight fallback.",
    ),
    ResearchOverviewSortOption(
        sort_id="return_desc",
        label="Return",
        description="Tile area by total return over the selected timeframe.",
    ),
    ResearchOverviewSortOption(
        sort_id="volatility_desc",
        label="Volatility",
        description="Tile area by annualized volatility over the selected timeframe.",
    ),
    ResearchOverviewSortOption(
        sort_id="beta_desc",
        label="Beta",
        description="Tile area by benchmark beta where available.",
    ),
    ResearchOverviewSortOption(
        sort_id="drawdown_desc",
        label="Drawdown",
        description="Tile area by absolute maximum drawdown over the selected timeframe.",
    ),
)


RESEARCH_OVERVIEW_TIMEFRAMES: dict[str, int] = {
    "DoD": 1,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}


def _cap_usd(value: str) -> float:
    raw = value.strip().upper()
    if raw.endswith("T"):
        return float(raw[:-1]) * 1_000_000_000_000
    if raw.endswith("B"):
        return float(raw[:-1]) * 1_000_000_000
    if raw.endswith("M"):
        return float(raw[:-1]) * 1_000_000
    return float(raw)


def _overview_equity(
    rank: int,
    symbol: str,
    label: str,
    market_cap: str,
    sector: str,
    industry: str,
) -> ResearchOverviewUniverseInstrument:
    market_cap_usd = _cap_usd(market_cap)
    return ResearchOverviewUniverseInstrument(
        symbol=symbol,
        label=label,
        group=sector,
        sector=sector,
        industry=industry,
        weight=market_cap_usd,
        market_cap_usd=market_cap_usd,
        sort_rank=rank,
    )


def _overview_index(
    rank: int,
    symbol: str,
    label: str,
    group: str,
) -> ResearchOverviewUniverseInstrument:
    return ResearchOverviewUniverseInstrument(
        symbol=symbol,
        label=label,
        group=group,
        sector=group,
        industry=label,
        weight=max(1.0, 100.0 - rank),
        index_weight=max(1.0, 100.0 - rank),
        sort_rank=rank,
        sec_type="IND",
        exchange="INDEX",
        provider="yfinance",
        instrument_id=f"yfinance:index:{symbol}",
    )


BROAD_US_MARKET_INSTRUMENTS: tuple[ResearchOverviewUniverseInstrument, ...] = (
    _overview_equity(1, "NVDA", "NVIDIA", "4.85T", "Information Technology", "Semiconductors"),
    _overview_equity(2, "GOOGL", "Alphabet Class A", "4.04T", "Communication Services", "Interactive Media & Services"),
    _overview_equity(3, "GOOG", "Alphabet Class C", "4.01T", "Communication Services", "Interactive Media & Services"),
    _overview_equity(4, "AAPL", "Apple", "3.89T", "Information Technology", "Technology Hardware, Storage & Peripherals"),
    _overview_equity(5, "MSFT", "Microsoft", "3.03T", "Information Technology", "Systems Software"),
    _overview_equity(6, "AMZN", "Amazon", "2.67T", "Consumer Discretionary", "Broadline Retail"),
    _overview_equity(7, "AVGO", "Broadcom", "1.87T", "Information Technology", "Semiconductors"),
    _overview_equity(8, "META", "Meta Platforms", "1.71T", "Communication Services", "Interactive Media & Services"),
    _overview_equity(9, "TSLA", "Tesla", "1.47T", "Consumer Discretionary", "Automobile Manufacturers"),
    _overview_equity(10, "BRK-B", "Berkshire Hathaway Class B", "1.03T", "Financials", "Multi-Sector Holdings"),
    _overview_equity(11, "WMT", "Walmart", "986.82B", "Consumer Staples", "Consumer Staples Merchandise Retail"),
    _overview_equity(12, "JPM", "JPMorgan Chase", "816.52B", "Financials", "Diversified Banks"),
    _overview_equity(13, "LLY", "Eli Lilly", "801.75B", "Health Care", "Pharmaceuticals"),
    _overview_equity(14, "XOM", "Exxon Mobil", "617.00B", "Energy", "Integrated Oil & Gas"),
    _overview_equity(15, "V", "Visa", "598.49B", "Financials", "Transaction & Payment Processing Services"),
    _overview_equity(16, "JNJ", "Johnson & Johnson", "572.29B", "Health Care", "Pharmaceuticals"),
    _overview_equity(17, "MU", "Micron Technology", "504.68B", "Information Technology", "Semiconductors"),
    _overview_equity(18, "ORCL", "Oracle", "487.09B", "Information Technology", "Application Software"),
    _overview_equity(19, "MA", "Mastercard", "462.40B", "Financials", "Transaction & Payment Processing Services"),
    _overview_equity(20, "NFLX", "Netflix", "448.12B", "Communication Services", "Movies & Entertainment"),
    _overview_equity(21, "COST", "Costco Wholesale", "433.76B", "Consumer Staples", "Consumer Staples Merchandise Retail"),
    _overview_equity(22, "AMD", "Advanced Micro Devices", "417.53B", "Information Technology", "Semiconductors"),
    _overview_equity(23, "BAC", "Bank of America", "386.58B", "Financials", "Diversified Banks"),
    _overview_equity(24, "CVX", "Chevron", "368.26B", "Energy", "Integrated Oil & Gas"),
    _overview_equity(25, "ABBV", "AbbVie", "364.29B", "Health Care", "Biotechnology"),
    _overview_equity(26, "CAT", "Caterpillar", "355.01B", "Industrials", "Construction Machinery & Heavy Transportation Equipment"),
    _overview_equity(27, "HD", "Home Depot", "336.58B", "Consumer Discretionary", "Home Improvement Retail"),
    _overview_equity(28, "PLTR", "Palantir Technologies", "334.50B", "Information Technology", "Application Software"),
    _overview_equity(29, "PG", "Procter & Gamble", "332.74B", "Consumer Staples", "Personal Care Products"),
    _overview_equity(30, "INTC", "Intel", "328.27B", "Information Technology", "Semiconductors"),
    _overview_equity(31, "GE", "GE Aerospace", "327.67B", "Industrials", "Aerospace & Defense"),
    _overview_equity(32, "LRCX", "Lam Research", "327.07B", "Information Technology", "Semiconductor Materials & Equipment"),
    _overview_equity(33, "KO", "Coca-Cola", "324.02B", "Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    _overview_equity(34, "CSCO", "Cisco Systems", "320.26B", "Information Technology", "Communications Equipment"),
    _overview_equity(35, "AMAT", "Applied Materials", "306.37B", "Information Technology", "Semiconductor Materials & Equipment"),
    _overview_equity(36, "MS", "Morgan Stanley", "302.04B", "Financials", "Investment Banking & Brokerage"),
    _overview_equity(37, "MRK", "Merck", "289.87B", "Health Care", "Pharmaceuticals"),
    _overview_equity(38, "UNH", "UnitedHealth Group", "283.43B", "Health Care", "Managed Health Care"),
    _overview_equity(39, "GS", "Goldman Sachs", "276.88B", "Financials", "Investment Banking & Brokerage"),
    _overview_equity(40, "RTX", "RTX", "266.76B", "Industrials", "Aerospace & Defense"),
    _overview_equity(41, "GEV", "GE Vernova", "266.71B", "Industrials", "Heavy Electrical Equipment"),
    _overview_equity(42, "WFC", "Wells Fargo", "248.64B", "Financials", "Diversified Banks"),
    _overview_equity(43, "PM", "Philip Morris International", "245.62B", "Consumer Staples", "Tobacco"),
    _overview_equity(44, "LIN", "Linde", "229.43B", "Materials", "Industrial Gases"),
    _overview_equity(45, "IBM", "IBM", "229.18B", "Information Technology", "IT Consulting & Other Services"),
    _overview_equity(46, "AXP", "American Express", "226.18B", "Financials", "Consumer Finance"),
    _overview_equity(47, "KLAC", "KLA", "225.01B", "Information Technology", "Semiconductor Materials & Equipment"),
    _overview_equity(48, "C", "Citigroup", "224.73B", "Financials", "Diversified Banks"),
    _overview_equity(49, "MCD", "McDonald's", "217.19B", "Consumer Discretionary", "Restaurants"),
    _overview_equity(50, "PEP", "PepsiCo", "210.92B", "Consumer Staples", "Soft Drinks & Non-alcoholic Beverages"),
    _overview_equity(51, "TMUS", "T-Mobile US", "210.21B", "Communication Services", "Wireless Telecommunication Services"),
    _overview_equity(52, "TMO", "Thermo Fisher Scientific", "195.76B", "Health Care", "Life Sciences Tools & Services"),
    _overview_equity(53, "TXN", "Texas Instruments", "194.69B", "Information Technology", "Semiconductors"),
    _overview_equity(54, "ANET", "Arista Networks", "191.12B", "Information Technology", "Communications Equipment"),
    _overview_equity(55, "VZ", "Verizon", "188.29B", "Communication Services", "Integrated Telecommunication Services"),
    _overview_equity(56, "NEE", "NextEra Energy", "188.26B", "Utilities", "Multi-Utilities"),
    _overview_equity(57, "AMGN", "Amgen", "186.60B", "Health Care", "Biotechnology"),
    _overview_equity(58, "DIS", "Walt Disney", "181.94B", "Communication Services", "Movies & Entertainment"),
    _overview_equity(59, "APH", "Amphenol", "179.13B", "Information Technology", "Electronic Components"),
    _overview_equity(60, "T", "AT&T", "178.43B", "Communication Services", "Integrated Telecommunication Services"),
    _overview_equity(61, "TJX", "TJX Companies", "177.26B", "Consumer Discretionary", "Apparel Retail"),
    _overview_equity(62, "ABT", "Abbott Laboratories", "176.55B", "Health Care", "Health Care Equipment"),
    _overview_equity(63, "BA", "Boeing", "175.19B", "Industrials", "Aerospace & Defense"),
    _overview_equity(64, "SCHW", "Charles Schwab", "172.71B", "Financials", "Investment Banking & Brokerage"),
    _overview_equity(65, "GILD", "Gilead Sciences", "172.07B", "Health Care", "Biotechnology"),
    _overview_equity(66, "BLK", "BlackRock", "170.63B", "Financials", "Asset Management & Custody Banks"),
    _overview_equity(67, "ADI", "Analog Devices", "168.24B", "Information Technology", "Semiconductors"),
    _overview_equity(68, "ISRG", "Intuitive Surgical", "166.71B", "Health Care", "Health Care Equipment"),
    _overview_equity(69, "CRM", "Salesforce", "163.27B", "Information Technology", "Application Software"),
    _overview_equity(70, "BX", "Blackstone", "159.60B", "Financials", "Asset Management & Custody Banks"),
    _overview_equity(71, "UBER", "Uber Technologies", "156.41B", "Industrials", "Passenger Ground Transportation"),
    _overview_equity(72, "DE", "Deere", "155.22B", "Industrials", "Agricultural & Farm Machinery"),
    _overview_equity(73, "PFE", "Pfizer", "153.87B", "Health Care", "Pharmaceuticals"),
    _overview_equity(74, "APP", "AppLovin", "153.45B", "Information Technology", "Application Software"),
    _overview_equity(75, "ETN", "Eaton", "151.64B", "Industrials", "Electrical Components & Equipment"),
    _overview_equity(76, "WELL", "Welltower", "147.73B", "Real Estate", "Health Care REITs"),
    _overview_equity(77, "BKNG", "Booking Holdings", "147.45B", "Consumer Discretionary", "Hotels, Resorts & Cruise Lines"),
    _overview_equity(78, "UNP", "Union Pacific", "146.98B", "Industrials", "Rail Transportation"),
    _overview_equity(79, "HON", "Honeywell", "145.80B", "Industrials", "Industrial Conglomerates"),
    _overview_equity(80, "COP", "ConocoPhillips", "144.98B", "Energy", "Oil & Gas Exploration & Production"),
)


GLOBAL_INDEX_INSTRUMENTS: tuple[ResearchOverviewUniverseInstrument, ...] = (
    _overview_index(1, "^GSPC", "S&P 500", "US"),
    _overview_index(2, "^DJI", "DJIA", "US"),
    _overview_index(3, "^IXIC", "Nasdaq Composite", "US"),
    _overview_index(4, "^RUT", "Russell 2000", "US"),
    _overview_index(5, "^GSPTSE", "S&P/TSX Composite", "Canada"),
    _overview_index(6, "^STOXX50E", "Euro Stoxx 50", "Europe"),
    _overview_index(7, "^FTSE", "FTSE 100", "UK"),
    _overview_index(8, "^GDAXI", "DAX", "Germany"),
    _overview_index(9, "^FCHI", "CAC 40", "France"),
    _overview_index(10, "^IBEX", "IBEX 35", "Spain"),
    _overview_index(11, "^N225", "Nikkei 225", "Japan"),
    _overview_index(12, "^HSI", "Hang Seng", "Hong Kong"),
)


def _sector_slug(sector: str) -> str:
    return sector.strip().lower().replace("&", "and").replace(" ", "_")


def _sector_universe(sector: str) -> ResearchOverviewUniverse:
    instruments = tuple(
        replace(instrument, group=instrument.industry or sector)
        for instrument in BROAD_US_MARKET_INSTRUMENTS
        if instrument.sector == sector
    )
    return ResearchOverviewUniverse(
        universe_id=f"sector_{_sector_slug(sector)}",
        label=sector,
        description=(
            f"Zoomed view of {sector} constituents from the Broad US Market universe, "
            "grouped by industry."
        ),
        instruments=instruments,
        limitations=(
            f"This is a sector slice of the Broad US Market seed list, not complete {sector} index coverage.",
            "Sector membership and market-cap tile sizing are static proxy metadata and may drift until a live reference provider is added.",
            "IBKR/TWS history coverage is entitlement, symbol, session, and pacing dependent.",
        ),
        metadata_source_label="Static S&P 500-derived proxy metadata",
        coverage_label="Sector slice of static Broad US Market seed",
        is_complete_universe=False,
    )


_BROAD_US_SECTORS: tuple[str, ...] = tuple(
    dict.fromkeys(instrument.sector for instrument in BROAD_US_MARKET_INSTRUMENTS)
)
_SECTOR_UNIVERSES: tuple[ResearchOverviewUniverse, ...] = tuple(
    _sector_universe(sector) for sector in _BROAD_US_SECTORS
)


RESEARCH_OVERVIEW_UNIVERSES: tuple[ResearchOverviewUniverse, ...] = (
    ResearchOverviewUniverse(
        universe_id="broad_us_market",
        label="Broad US Market",
        description=(
            "Large-cap US equity map seeded from static S&P 500-derived proxy metadata; "
            "not live index membership or complete market coverage."
        ),
        instruments=BROAD_US_MARKET_INSTRUMENTS,
        limitations=(
            "This first pass uses a static seed of large S&P 500-derived names, not complete or live index membership.",
            "Sector, industry, and market-cap tile sizing are static proxy metadata and may drift until a live reference provider is added.",
            "Breadth and leadership statistics only cover the loaded seed list and must not be read as whole-market breadth.",
            "IBKR/TWS history coverage is entitlement, symbol, session, and pacing dependent.",
        ),
        metadata_source_label="Static S&P 500-derived proxy metadata",
        coverage_label="Static large-cap US seed, partial coverage",
        is_complete_universe=False,
    ),
    ResearchOverviewUniverse(
        universe_id="global_indices",
        label="Global Indices",
        description=(
            "Worldwide cash-index board for SITREP, using direct public index symbols where the "
            "configured listed-market provider supports them."
        ),
        instruments=GLOBAL_INDEX_INSTRUMENTS,
        limitations=(
            "This board uses direct public index symbols rather than ETF proxies.",
            "Direct index coverage depends on the configured SITREP listed-market provider; yfinance supports these symbols, while IBKR may require exchange-specific index contracts and entitlements.",
            "Yahoo Finance/yfinance remains an unofficial public source and should be treated as live-ish research context rather than institutional quote truth.",
        ),
        metadata_source_label="Curated Gamma global cash-index symbol list",
        coverage_label="Curated global cash-index board, provider-dependent coverage",
        is_complete_universe=False,
    ),
    *_SECTOR_UNIVERSES,
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
        metadata_source_label="Local sample/watchlist metadata",
        coverage_label="Sample watchlist, partial coverage",
        is_complete_universe=False,
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
        metadata_source_label="Curated Gamma ETF basket",
        coverage_label="Curated ETF basket, partial coverage",
        is_complete_universe=False,
    ),
)
