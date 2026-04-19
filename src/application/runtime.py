from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from src.application.copilot_service import CopilotService
from src.application.commodities_service import CommoditiesService
from src.application.crypto_service import CryptoService
from src.application.fundamentals_service import FundamentalsService
from src.application.iv_service import IVService
from src.application.macro_service import MacroService
from src.application.maritime_service import MaritimeService
from src.application.portfolio_service import PortfolioService
from src.application.prediction_market_service import PredictionMarketService
from src.application.provider_capability_registry import (
    ProviderCapabilityRegistry,
    build_default_provider_capability_registry,
)
from src.application.research_service import ResearchService
from src.application.risk_service import RiskService
from src.application.system_service import normalize_market_data_mode
from src.models.instruments import InstrumentDefaults
from src.services.cache import CacheService
from src.services.copilot_provider import UnavailableCopilotProvider
from src.services.commodities_adapters import (
    EiaCommoditiesDataProvider,
    SampleCommoditiesDataProvider,
)
from src.services.crypto_adapters import CoinGeckoAdapter, GeckoTerminalAdapter
from src.services.fundamentals_adapters import IbkrValuationAdapter, SecFundamentalsAdapter
from src.services.fundamentals_store import FundamentalsResearchStore
from src.services.fred import FredClient
from src.services.macro_adapters import IBKRMacroFXAdapter, FredMacroAdapter, TreasuryCurveAdapter, USMacroEventsAdapter
from src.services.maritime_adapters import (
    AisstreamMaritimeDataProvider,
    SampleMaritimeDataProvider,
    parse_aisstream_bounding_boxes,
)
from src.services.mock_copilot_provider import MockCopilotProvider
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
from src.services.prediction_market_adapters import KalshiAdapter, PolymarketAdapter
from src.services.data_providers import PortfolioDataProvider, ResearchDataProvider
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.portfolio_history_store import PortfolioHistoryStore
from src.services.research_cache import ResearchHistoryCache
from src.services.saved_research_store import SavedResearchStore
from src.services.risk_free_rate import RiskFreeRateService
from src.utils.logging_config import setup_logging

if TYPE_CHECKING:
    from src.services.app_context import AppDataContext


@dataclass
class DesktopRuntimeState:
    app_context: AppDataContext


@dataclass
class ApplicationRuntime:
    base_currency: str
    auto_refresh_seconds: int
    default_lookback_days: int
    quote_timeout_seconds: float
    market_data_mode: str
    mock_mode: bool
    research_cache: ResearchHistoryCache
    mock_service: MockDataService
    client: IBKRClient
    cache: CacheService
    provider_capabilities: ProviderCapabilityRegistry
    market_data: MarketDataService
    fx_service: FXService
    portfolio_history: PortfolioHistoryStore
    saved_research_store: SavedResearchStore
    risk_free_service: RiskFreeRateService
    portfolio_provider: PortfolioDataProvider
    research_provider: ResearchDataProvider
    portfolio_service: PortfolioService
    research_service: ResearchService
    prediction_market_service: PredictionMarketService
    macro_service: MacroService
    commodities_service: CommoditiesService
    maritime_service: MaritimeService
    crypto_service: CryptoService
    fundamentals_service: FundamentalsService
    copilot_service: CopilotService
    risk_service: RiskService
    iv_service: IVService
    desktop: DesktopRuntimeState | None = None

    @property
    def app_context(self) -> AppDataContext | None:
        if self.desktop is None:
            return None
        return self.desktop.app_context

    def set_market_data_mode(self, value: str | None) -> str:
        normalized = normalize_market_data_mode(value)
        self.market_data_mode = normalized
        self.market_data.set_market_data_mode(normalized)
        self.client.set_market_data_mode(normalized)
        self.iv_service.set_market_data_mode(normalized)
        return normalized

    def set_base_currency(self, value: str | None) -> tuple[str, list[str]]:
        normalized = self._normalize_base_currency(value)
        notes: list[str] = []
        if normalized == self.base_currency:
            return normalized, [f"Base currency already set to {normalized}."]
        self.base_currency = normalized
        self.research_provider.base_currency = normalized
        self.portfolio_history.clear()
        notes.append(f"Base currency set to {normalized}.")
        notes.append("Local portfolio history was cleared because stored snapshots are base-currency specific.")
        notes.append("Re-run research and risk views to refresh any previously loaded analytics.")
        return normalized, notes

    @staticmethod
    def _normalize_base_currency(value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("Base currency must be a 3-letter ISO currency code.")
        return normalized

    def shutdown(self) -> None:
        try:
            self.client.shutdown()
        except Exception:
            pass


def build_runtime(
    *,
    mock_mode: bool | None = None,
    cache_dir: str | Path | None = None,
    history_dir: str | Path | None = None,
    sample_data_dir: str | Path | None = None,
    include_desktop_session: bool = False,
) -> ApplicationRuntime:
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
    setup_logging()

    base_currency = os.getenv("BASE_CURRENCY", "EUR")
    auto_refresh = int(os.getenv("AUTO_REFRESH_SECONDS", "60") or 0)
    lookback = int(os.getenv("HIST_LOOKBACK_DAYS_DEFAULT", "252") or 252)
    quote_timeout = float(os.getenv("IB_SNAPSHOT_TIMEOUT_SECONDS", "2") or 2.0)
    market_data_mode = normalize_market_data_mode(os.getenv("IB_MARKET_DATA_MODE", "delayed"))

    if mock_mode is None:
        mock_env = os.getenv("MOCK_DATA")
        mock_mode = True if mock_env is None else mock_env.lower() == "true"

    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "1"))
    account = (os.getenv("IB_ACCOUNT", "") or "").strip() or None

    resolved_cache_dir = Path(cache_dir or os.getenv("CACHE_DIR", "cache"))
    resolved_history_dir = Path(history_dir or os.getenv("PORTFOLIO_HISTORY_DIR", "data"))
    resolved_sample_data_dir = Path(sample_data_dir or os.getenv("SAMPLE_DATA_DIR", "sample_data"))
    research_defaults = InstrumentDefaults(
        provider=os.getenv("RESEARCH_DEFAULT_PROVIDER", "research"),
        sec_type=os.getenv("RESEARCH_DEFAULT_SEC_TYPE", "STK"),
        exchange=os.getenv("RESEARCH_DEFAULT_EXCHANGE", "SMART"),
        currency=os.getenv("RESEARCH_DEFAULT_CURRENCY", "USD"),
    )
    benchmark_defaults = InstrumentDefaults(
        provider=os.getenv("BENCHMARK_DEFAULT_PROVIDER", "benchmark"),
        sec_type=os.getenv("BENCHMARK_DEFAULT_SEC_TYPE", "STK"),
        exchange=os.getenv("BENCHMARK_DEFAULT_EXCHANGE", "SMART"),
        currency=os.getenv("BENCHMARK_DEFAULT_CURRENCY", "USD"),
    )

    research_cache = ResearchHistoryCache()
    mock_service = MockDataService(base_path=resolved_sample_data_dir)
    client = IBKRClient(host, port, client_id, account, bool(mock_mode), mock_service)
    client.set_market_data_mode(market_data_mode)
    cache = CacheService(base_dir=resolved_cache_dir, ttl_hours=24)
    provider_capabilities = build_default_provider_capability_registry()
    market_data = MarketDataService(
        client.ib,
        cache,
        ib_runner=client.ib_runner,
        market_data_mode=market_data_mode,
    )
    fx_service = FXService(
        client.ib,
        cache=cache,
        market_data=market_data,
        ib_runner=client.ib_runner,
    )
    portfolio_history = PortfolioHistoryStore(base_dir=resolved_history_dir, mock=bool(mock_mode))
    saved_research_store = SavedResearchStore(base_dir=resolved_history_dir / "research")
    risk_free_service = RiskFreeRateService(cache=cache)

    portfolio_provider = PortfolioDataProvider(client, market_data, mock_service)
    research_provider = ResearchDataProvider(
        client,
        market_data,
        mock_service,
        None,
        base_currency,
        research_cache,
        research_defaults,
        benchmark_defaults,
    )

    portfolio_service = PortfolioService(
        client,
        market_data,
        fx_service,
        portfolio_history,
        data_provider=portfolio_provider,
        mock_service=mock_service,
        benchmark_defaults=benchmark_defaults,
    )
    research_service = ResearchService(research_provider, saved_store=saved_research_store)
    prediction_market_service = PredictionMarketService(
        adapters={
            "polymarket": PolymarketAdapter(cache),
            "kalshi": KalshiAdapter(cache),
        }
    )
    macro_service = MacroService(
        fred_adapter=FredMacroAdapter(cache),
        treasury_adapter=TreasuryCurveAdapter(cache),
        events_adapter=USMacroEventsAdapter(cache),
        fx_adapter=IBKRMacroFXAdapter(market_data),
        prediction_market_service=prediction_market_service,
    )
    commodities_service = CommoditiesService(provider=_build_commodities_provider(cache))
    maritime_service = MaritimeService(provider=_build_maritime_provider())
    crypto_service = CryptoService(
        market_adapter=CoinGeckoAdapter(cache),
        dex_adapter=GeckoTerminalAdapter(cache),
    )
    fundamentals_service = FundamentalsService(
        sec_adapter=SecFundamentalsAdapter(cache),
        valuation_adapter=IbkrValuationAdapter(
            research_provider=research_provider,
            market_data=market_data,
        ),
        store=FundamentalsResearchStore(base_dir=resolved_history_dir / "fundamentals"),
    )
    copilot_service = CopilotService(
        macro_service=macro_service,
        prediction_market_service=prediction_market_service,
        crypto_service=crypto_service,
        fundamentals_service=fundamentals_service,
        provider=_build_copilot_provider(),
    )
    risk_service = RiskService(
        client,
        market_data,
        mock_service,
        risk_free_service,
        benchmark_defaults=benchmark_defaults,
    )
    iv_service = IVService(client, market_data_mode)
    desktop = _build_desktop_state(research_provider) if include_desktop_session else None

    return ApplicationRuntime(
        base_currency=base_currency,
        auto_refresh_seconds=auto_refresh,
        default_lookback_days=lookback,
        quote_timeout_seconds=quote_timeout,
        market_data_mode=market_data_mode,
        mock_mode=bool(mock_mode),
        research_cache=research_cache,
        mock_service=mock_service,
        client=client,
        cache=cache,
        provider_capabilities=provider_capabilities,
        market_data=market_data,
        fx_service=fx_service,
        portfolio_history=portfolio_history,
        saved_research_store=saved_research_store,
        risk_free_service=risk_free_service,
        portfolio_provider=portfolio_provider,
        research_provider=research_provider,
        portfolio_service=portfolio_service,
        research_service=research_service,
        prediction_market_service=prediction_market_service,
        macro_service=macro_service,
        commodities_service=commodities_service,
        maritime_service=maritime_service,
        crypto_service=crypto_service,
        fundamentals_service=fundamentals_service,
        copilot_service=copilot_service,
        risk_service=risk_service,
        iv_service=iv_service,
        desktop=desktop,
    )


def build_desktop_runtime(
    *,
    mock_mode: bool | None = None,
    cache_dir: str | Path | None = None,
    history_dir: str | Path | None = None,
    sample_data_dir: str | Path | None = None,
) -> ApplicationRuntime:
    return build_runtime(
        mock_mode=mock_mode,
        cache_dir=cache_dir,
        history_dir=history_dir,
        sample_data_dir=sample_data_dir,
        include_desktop_session=True,
    )


@lru_cache(maxsize=1)
def get_runtime() -> ApplicationRuntime:
    return build_runtime()


def reset_runtime() -> None:
    if get_runtime.cache_info().currsize:
        runtime = get_runtime()
        runtime.shutdown()
    get_runtime.cache_clear()


def _build_desktop_state(research_provider: ResearchDataProvider) -> DesktopRuntimeState:
    from src.services.app_context import AppDataContext

    app_context = AppDataContext()
    research_provider.context = app_context
    return DesktopRuntimeState(app_context=app_context)


def _build_copilot_provider():
    provider = (os.getenv("GAMMA_COPILOT_PROVIDER", "openai") or "openai").strip().lower()
    if provider in {"disabled", "none", "off"}:
        return UnavailableCopilotProvider(message="Gamma Copilot is disabled by configuration.")
    if provider in {"mock", "demo", "offline"}:
        return MockCopilotProvider()
    if provider != "openai":
        return UnavailableCopilotProvider(message=f"Unsupported copilot provider: {provider}")

    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        return UnavailableCopilotProvider(
            message="Gamma Copilot is unavailable until OPENAI_API_KEY is configured."
        )

    # Stored responses are required for previous_response_id-based continuation.
    store_flag = (os.getenv("GAMMA_COPILOT_STORE_RESPONSES", "true") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return OpenAIResponsesCopilotProvider(
        api_key=api_key,
        model=(os.getenv("GAMMA_COPILOT_MODEL", "gpt-5.4") or "gpt-5.4").strip(),
        reasoning_effort=(os.getenv("GAMMA_COPILOT_REASONING_EFFORT", "medium") or "medium").strip(),
        api_url=(
            os.getenv("GAMMA_COPILOT_API_URL", "https://api.openai.com/v1/responses")
            or "https://api.openai.com/v1/responses"
        ).strip(),
        store_responses=store_flag,
    )


def _build_commodities_provider(cache: CacheService):
    provider = (os.getenv("COMMODITIES_PROVIDER", "sample") or "sample").strip().lower()
    sample_provider = SampleCommoditiesDataProvider()
    if provider in {"sample", "mock", "offline", "demo"}:
        return sample_provider
    if provider not in {"eia", "official", "eia_fred", "fred"}:
        return sample_provider

    fred_client = FredClient(cache=cache) if (os.getenv("FRED_API_KEY", "") or "").strip() else None
    return EiaCommoditiesDataProvider(
        api_key=os.getenv("EIA_API_KEY", ""),
        cache=cache,
        reference_provider=sample_provider,
        fred_client=fred_client,
        cache_seconds=int(os.getenv("COMMODITIES_CACHE_SECONDS", "21600") or 21600),
    )


def _build_maritime_provider():
    provider = (os.getenv("MARITIME_PROVIDER", "sample") or "sample").strip().lower()
    sample_provider = SampleMaritimeDataProvider()
    if provider not in {"aisstream", "aisstream_live", "live"}:
        return sample_provider

    try:
        bounding_boxes = parse_aisstream_bounding_boxes(os.getenv("AISSTREAM_BOUNDING_BOXES"))
    except ValueError:
        bounding_boxes = None

    message_types = [
        item.strip()
        for item in (os.getenv("AISSTREAM_MESSAGE_TYPES", "") or "").split(",")
        if item.strip()
    ] or None
    return AisstreamMaritimeDataProvider(
        api_key=os.getenv("AISSTREAM_API_KEY", ""),
        reference_provider=sample_provider,
        bounding_boxes=bounding_boxes,
        message_types=message_types,
        sample_seconds=float(os.getenv("AISSTREAM_SAMPLE_SECONDS", "6") or 6.0),
        max_messages=int(os.getenv("AISSTREAM_MAX_MESSAGES", "500") or 500),
        cache_seconds=int(os.getenv("AISSTREAM_CACHE_SECONDS", "30") or 30),
    )
