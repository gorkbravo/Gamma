from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from src.application.copilot_model_policy import (
    OPENAI_BASELINE_MODEL,
    CopilotModelPolicy,
    configured_provider_storage,
)
from src.application.copilot_service import CopilotService
from src.application.commodities_service import CommoditiesService
from src.application.crypto_service import CryptoService
from src.application.fundamentals_service import FundamentalsService
from src.application.iv_service import IVService
from src.application.macro_service import MacroService
from src.application.maritime_service import MaritimeService
from src.application.news_service import NewsService
from src.application.portfolio_service import PortfolioService
from src.application.prediction_market_service import PredictionMarketService
from src.application.provider_capability_registry import (
    ProviderCapabilityRegistry,
    build_default_provider_capability_registry,
)
from src.application.research_service import ResearchService
from src.application.research_script_service import ResearchScriptService
from src.application.risk_service import RiskService
from src.application.sitrep_service import SitrepService
from src.application.system_service import normalize_market_data_mode
from src.models.instruments import InstrumentDefaults
from src.models.commodities import (
    CommodityCoverageMetadata,
    CommodityInstrument,
    CommodityProviderSnapshot,
)
from src.models.maritime import MaritimeCoverageMetadata, MaritimeProviderSnapshot, MaritimeTrackSnippet
from src.models.news import NewsEventFeed
from src.models.provenance import FreshnessLabel
from src.services.cache import CacheService
from src.services.copilot_provider import UnavailableCopilotProvider
from src.services.copilot_store import CopilotStore
from src.services.commodities_adapters import (
    COMMODITY_INSTRUMENTS,
    EiaCommoditiesDataProvider,
    IBKR_FUTURES_ROOTS,
    IbkrCommoditiesDataProvider,
    SampleCommoditiesDataProvider,
)
from src.services.crypto_adapters import CoinGeckoAdapter, GeckoTerminalAdapter
from src.services.fundamentals_adapters import IbkrValuationAdapter, SecFundamentalsAdapter
from src.services.fundamentals_store import FundamentalsResearchStore
from src.services.fred import FredClient
from src.services.macro_adapters import (
    CensusTradePartnerAdapter,
    DBnomicsMacroAdapter,
    IBKRMacroFXAdapter,
    FredMacroAdapter,
    TreasuryCurveAdapter,
    USMacroEventsAdapter,
)
from src.services.maritime_adapters import (
    AisstreamMaritimeDataProvider,
    SampleMaritimeDataProvider,
    parse_aisstream_bounding_boxes,
)
from src.services.mock_copilot_provider import MockCopilotProvider
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
from src.services.openai_research_script_runtime import OpenAICodeInterpreterRuntime
from src.services.prediction_market_adapters import KalshiAdapter, PolymarketAdapter
from src.services.news_adapters import NewsEventProvider, RssNewsEventProvider, SampleNewsEventProvider
from src.services.data_providers import PortfolioDataProvider, ResearchDataProvider
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient, validate_portfolio_quote_timeout
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.research_market_data import (
    IbkrListedMarketHistoryProvider,
    ListedMarketHistoryProvider,
    MockListedMarketHistoryProvider,
    UnavailableListedMarketHistoryProvider,
    YFinanceListedMarketHistoryProvider,
)
from src.application.request_limits import MAX_RESEARCH_SCRIPT_RUN_DURATION_SECONDS
from src.services.research_script_runtime import MockResearchScriptRuntime, ResearchScriptRuntime
from src.services.research_script_store import ResearchScriptStore
from src.services.portfolio_history_store import PortfolioHistoryStore
from src.services.provider_usage import ProviderActivationCondition, ProviderUsageLedger, trace_provider
from src.services.research_cache import ResearchHistoryCache
from src.services.saved_research_store import SavedResearchStore
from src.services.prediction_research_store import PredictionResearchStore
from src.services.sitrep_follow_up_store import SitrepFollowUpStore
from src.services.risk_free_rate import RiskFreeRateService
from src.utils.time import now_utc
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
    provider_usage: ProviderUsageLedger
    market_data: MarketDataService
    fx_service: FXService
    portfolio_history: PortfolioHistoryStore
    saved_research_store: SavedResearchStore
    research_script_store: ResearchScriptStore
    research_script_runtime: ResearchScriptRuntime
    copilot_store: CopilotStore
    risk_free_service: RiskFreeRateService
    portfolio_provider: PortfolioDataProvider
    research_provider: ResearchDataProvider
    portfolio_service: PortfolioService
    research_service: ResearchService
    research_script_service: ResearchScriptService
    prediction_market_service: PredictionMarketService
    macro_service: MacroService
    commodities_service: CommoditiesService
    maritime_service: MaritimeService
    crypto_service: CryptoService
    fundamentals_service: FundamentalsService
    news_service: NewsService
    sitrep_service: SitrepService
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
        history_clear = self.portfolio_history.clear()
        notes.append(f"Base currency set to {normalized}.")
        if history_clear.archived:
            notes.append(
                "The previous local portfolio history was archived because stored snapshots "
                "are base-currency specific."
            )
        else:
            notes.append("No existing local portfolio history needed to be archived.")
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
    quote_timeout = validate_portfolio_quote_timeout(
        float(os.getenv("IB_SNAPSHOT_TIMEOUT_SECONDS", "2") or 2.0)
    )
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
    provider_usage = ProviderUsageLedger()
    _register_provider_activation_conditions(provider_usage, mock_mode=bool(mock_mode))
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
        sample_rates=(
            {
                ("EUR", "USD"): 1.10,
                ("USD", "EUR"): 1.0 / 1.10,
            }
            if mock_mode
            else None
        ),
    )
    portfolio_history = PortfolioHistoryStore(base_dir=resolved_history_dir, mock=bool(mock_mode))
    saved_research_store = SavedResearchStore(base_dir=resolved_history_dir / "research")
    research_script_store = ResearchScriptStore(base_dir=resolved_history_dir / "research_scripts")
    research_script_runtime = _build_research_script_runtime()
    copilot_store = CopilotStore(base_dir=resolved_history_dir / "copilot")
    risk_free_service = RiskFreeRateService(cache=cache)

    portfolio_provider = PortfolioDataProvider(
        client,
        market_data,
        mock_service,
        history_providers=_build_research_history_providers(
            client,
            market_data,
            mock_service,
            provider_usage,
            env_var="PORTFOLIO_RISK_HISTORY_PROVIDERS",
            live_default="ibkr,yfinance",
        ),
    )
    research_provider = ResearchDataProvider(
        client=client,
        market_data=market_data,
        mock_service=mock_service,
        context=None,
        base_currency=base_currency,
        history_cache=research_cache,
        instrument_defaults=research_defaults,
        benchmark_defaults=benchmark_defaults,
        history_providers=_build_research_history_providers(client, market_data, mock_service, provider_usage),
        history_provider_sets={
            "research_overview": _build_research_history_providers(
                client,
                market_data,
                mock_service,
                provider_usage,
                env_var="RESEARCH_MARKET_DATA_PROVIDERS",
                live_default="yfinance,ibkr",
            ),
            "sitrep": _build_research_history_providers(
                client,
                market_data,
                mock_service,
                provider_usage,
                env_var="SITREP_MARKET_DATA_PROVIDERS",
                live_default="yfinance",
            ),
        },
        history_cache_seconds_by_policy={
            "research_overview": int(os.getenv("RESEARCH_OVERVIEW_CACHE_SECONDS", "300") or 300),
            "sitrep": int(os.getenv("SITREP_MARKET_DATA_CACHE_SECONDS", "300") or 300),
        },
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
    research_script_service = ResearchScriptService(research_script_store, research_script_runtime)
    prediction_research_store = PredictionResearchStore(base_dir=resolved_history_dir / "prediction_markets")
    prediction_market_service = PredictionMarketService(
        adapters={
            "polymarket": trace_provider(PolymarketAdapter(cache), provider_usage, endpoint_prefix="prediction_markets"),
            "kalshi": trace_provider(KalshiAdapter(cache), provider_usage, endpoint_prefix="prediction_markets"),
        },
        research_store=prediction_research_store,
    )
    macro_service = MacroService(
        fred_adapter=trace_provider(FredMacroAdapter(cache), provider_usage, endpoint_prefix="macro"),
        treasury_adapter=trace_provider(TreasuryCurveAdapter(cache), provider_usage, endpoint_prefix="macro"),
        events_adapter=trace_provider(USMacroEventsAdapter(cache), provider_usage, endpoint_prefix="macro"),
        fx_adapter=trace_provider(IBKRMacroFXAdapter(market_data), provider_usage, endpoint_prefix="macro"),
        dbnomics_adapter=trace_provider(DBnomicsMacroAdapter(cache), provider_usage, endpoint_prefix="macro"),
        census_trade_adapter=trace_provider(
            CensusTradePartnerAdapter(cache, api_key=os.getenv("CENSUS_API_KEY", "")),
            provider_usage,
            endpoint_prefix="macro",
        ),
        prediction_market_service=prediction_market_service,
    )
    commodities_service = CommoditiesService(
        provider=trace_provider(
            _build_commodities_provider(cache, client, market_data, live_mode=not bool(mock_mode)),
            provider_usage,
            endpoint_prefix="commodities",
        )
    )
    maritime_service = MaritimeService(
        provider=trace_provider(
            _build_maritime_provider(live_mode=not bool(mock_mode)),
            provider_usage,
            endpoint_prefix="maritime",
        )
    )
    crypto_service = CryptoService(
        market_adapter=trace_provider(CoinGeckoAdapter(cache), provider_usage, endpoint_prefix="crypto"),
        dex_adapter=trace_provider(GeckoTerminalAdapter(cache), provider_usage, endpoint_prefix="crypto"),
    )
    fundamentals_service = FundamentalsService(
        sec_adapter=trace_provider(SecFundamentalsAdapter(cache), provider_usage, endpoint_prefix="fundamentals"),
        valuation_adapter=trace_provider(
            IbkrValuationAdapter(
                research_provider=research_provider,
                market_data=market_data,
            ),
            provider_usage,
            endpoint_prefix="fundamentals",
        ),
        store=FundamentalsResearchStore(base_dir=resolved_history_dir / "fundamentals"),
        treasury_adapter=macro_service.treasury_adapter,
    )
    news_service = NewsService(
        [
            trace_provider(provider, provider_usage, endpoint_prefix="news")
            for provider in _build_news_providers(live_mode=not bool(mock_mode))
        ]
    )
    sitrep_service = SitrepService(
        research_service=research_service,
        macro_service=macro_service,
        commodities_service=commodities_service,
        prediction_market_service=prediction_market_service,
        news_service=news_service,
        follow_up_store=SitrepFollowUpStore(base_dir=resolved_history_dir / "sitrep"),
    )
    risk_service = RiskService(
        client,
        market_data,
        mock_service,
        risk_free_service,
        benchmark_defaults=benchmark_defaults,
    )
    iv_service = IVService(client, market_data_mode)
    copilot_provider = trace_provider(
        _build_copilot_provider(allow_mock=bool(mock_mode)),
        provider_usage,
        endpoint_prefix="copilot",
    )
    copilot_model_policy = CopilotModelPolicy.from_environment(copilot_provider)
    copilot_service = CopilotService(
        macro_service=macro_service,
        prediction_market_service=prediction_market_service,
        crypto_service=crypto_service,
        fundamentals_service=fundamentals_service,
        risk_service=risk_service,
        iv_service=iv_service,
        portfolio_provider=portfolio_provider,
        research_provider=research_provider,
        research_service=research_service,
        research_script_service=research_script_service,
        commodities_service=commodities_service,
        maritime_service=maritime_service,
        news_service=news_service,
        sitrep_service=sitrep_service,
        provider=copilot_provider,
        model_policy=copilot_model_policy,
        store=copilot_store,
    )
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
        provider_usage=provider_usage,
        market_data=market_data,
        fx_service=fx_service,
        portfolio_history=portfolio_history,
        saved_research_store=saved_research_store,
        research_script_store=research_script_store,
        research_script_runtime=research_script_runtime,
        copilot_store=copilot_store,
        risk_free_service=risk_free_service,
        portfolio_provider=portfolio_provider,
        research_provider=research_provider,
        portfolio_service=portfolio_service,
        research_service=research_service,
        research_script_service=research_script_service,
        prediction_market_service=prediction_market_service,
        macro_service=macro_service,
        commodities_service=commodities_service,
        maritime_service=maritime_service,
        crypto_service=crypto_service,
        fundamentals_service=fundamentals_service,
        news_service=news_service,
        sitrep_service=sitrep_service,
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


def _build_copilot_provider(*, allow_mock: bool = True):
    provider = (os.getenv("GAMMA_COPILOT_PROVIDER", "openai") or "openai").strip().lower()
    if provider in {"disabled", "none", "off"}:
        return UnavailableCopilotProvider(
            message="Gamma Copilot is disabled by configuration.",
            provider_name="disabled",
            provider_id="disabled_copilot",
        )
    if provider in {"mock", "demo", "offline"}:
        if not allow_mock:
            return UnavailableCopilotProvider(
                message="Gamma Copilot mock/demo provider is disabled while Gamma is running in live mode.",
                provider_id="unavailable_copilot",
            )
        return MockCopilotProvider()
    if provider != "openai":
        return UnavailableCopilotProvider(
            message=f"Unsupported copilot provider: {provider}",
            provider_id="unavailable_copilot",
        )

    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        return UnavailableCopilotProvider(
            message="Gamma Copilot is unavailable until OPENAI_API_KEY is configured.",
            provider_id="unavailable_copilot",
        )

    storage_policy = configured_provider_storage()
    return OpenAIResponsesCopilotProvider(
        api_key=api_key,
        model=(os.getenv("GAMMA_COPILOT_MODEL", OPENAI_BASELINE_MODEL) or OPENAI_BASELINE_MODEL).strip(),
        reasoning_effort=(os.getenv("GAMMA_COPILOT_REASONING_EFFORT", "medium") or "medium").strip(),
        api_url=(
            os.getenv("GAMMA_COPILOT_API_URL", "https://api.openai.com/v1/responses")
            or "https://api.openai.com/v1/responses"
        ).strip(),
        store_responses=storage_policy.effective == "enabled",
    )


def _build_research_script_runtime() -> ResearchScriptRuntime:
    configured = (os.getenv("GAMMA_RESEARCH_SCRIPT_RUNTIME", "mock") or "mock").strip().lower()
    if configured in {"mock", "demo", "offline", "disabled", "none", "off"}:
        return MockResearchScriptRuntime()
    if configured != "openai":
        # Unsupported runtime values never broaden authority; the deterministic
        # mock remains the safe local development path.
        return MockResearchScriptRuntime()
    configured_model = (
        os.getenv("GAMMA_RESEARCH_SCRIPT_MODEL")
        or os.getenv("GAMMA_COPILOT_MODEL")
        or OPENAI_BASELINE_MODEL
    )
    return OpenAICodeInterpreterRuntime(
        api_key=(os.getenv("OPENAI_API_KEY", "") or "").strip() or None,
        model=str(configured_model).strip(),
        configured_runtime=configured,
        max_duration_seconds=MAX_RESEARCH_SCRIPT_RUN_DURATION_SECONDS,
    )


def _register_provider_activation_conditions(
    provider_usage: ProviderUsageLedger,
    *,
    mock_mode: bool,
) -> None:
    maritime_provider = (os.getenv("MARITIME_PROVIDER", "sample") or "sample").strip().lower()
    provider_usage.register_activation_condition(
        ProviderActivationCondition(
            provider_id="aisstream",
            display_name="AISstream live AIS",
            expected_when="Sealanes live map has a viewport subscription at zoom >= 4.",
            configured=maritime_provider in {"aisstream", "aisstream_live", "live"}
            and bool((os.getenv("AISSTREAM_API_KEY", "") or "").strip()),
            active=False,
            idle_status="idle_by_design",
            idle_reason="AISstream calls are geofenced and zoom-gated to avoid unnecessary provider traffic.",
            action_label="Open Sealanes and zoom past level 4 to subscribe.",
        )
    )
    copilot_provider = (os.getenv("GAMMA_COPILOT_PROVIDER", "openai") or "openai").strip().lower()
    openai_selected = copilot_provider == "openai"
    openai_configured = bool((os.getenv("OPENAI_API_KEY", "") or "").strip())
    provider_usage.register_activation_condition(
        ProviderActivationCondition(
            provider_id="openai_copilot",
            display_name="OpenAI Copilot",
            expected_when="Copilot research card, follow-up, or synthesis request is submitted.",
            configured=openai_configured if openai_selected else True,
            active=False,
            idle_status="not_requested" if openai_selected else "idle_by_design",
            idle_reason=(
                "No OpenAI Copilot request has been made in this backend session."
                if openai_selected
                else f"OpenAI Copilot is not selected; GAMMA_COPILOT_PROVIDER={copilot_provider}."
            ),
            action_label="Ask Copilot for a grounded research card.",
        )
    )
    if copilot_provider in {"mock", "demo", "offline"}:
        provider_usage.register_activation_condition(
            ProviderActivationCondition(
                provider_id="mock_copilot",
                display_name="Mock Copilot",
                expected_when="Copilot is requested while the explicit mock/demo provider is selected.",
                configured=mock_mode,
                active=False,
                idle_status="not_requested" if mock_mode else "idle_by_design",
                idle_reason=(
                    "No mock Copilot request has been made in this backend session."
                    if mock_mode
                    else "Mock Copilot is disabled in live mode."
                ),
                action_label="Ask Copilot while Gamma is running in mock mode.",
            )
        )
    elif copilot_provider in {"disabled", "none", "off"}:
        provider_usage.register_activation_condition(
            ProviderActivationCondition(
                provider_id="disabled_copilot",
                display_name="Disabled Copilot",
                expected_when="A Copilot request is submitted while Copilot is explicitly disabled.",
                configured=True,
                active=False,
                idle_status="idle_by_design",
                idle_reason="Copilot is intentionally disabled by configuration.",
                action_label="Set GAMMA_COPILOT_PROVIDER to openai or mock to enable Copilot.",
            )
        )
    elif not openai_selected or not openai_configured:
        provider_usage.register_activation_condition(
            ProviderActivationCondition(
                provider_id="unavailable_copilot",
                display_name="Unavailable Copilot",
                expected_when="A Copilot request is submitted without a usable configured provider.",
                configured=False,
                active=False,
                idle_status="not_requested",
                idle_reason="No usable Copilot provider is configured.",
                action_label="Configure GAMMA_COPILOT_PROVIDER and its required credentials.",
            )
        )
    provider_usage.register_activation_condition(
        ProviderActivationCondition(
            provider_id="yfinance",
            display_name="Yahoo Finance / yfinance",
            expected_when="SITREP or Research Overview listed-market boards are loaded with yfinance policy.",
            configured=not mock_mode,
            active=False,
            idle_status="not_requested",
            idle_reason="Research/SITREP listed-market boards have not requested yfinance in this backend session.",
            action_label="Open SITREP or Research Overview.",
        )
    )
    provider_usage.register_activation_condition(
        ProviderActivationCondition(
            provider_id="ibkr",
            display_name="IBKR / TWS market data",
            expected_when="Portfolio, IV, Risk, FX, Fundamentals valuation, or IBKR-backed commodities request broker data.",
            configured=not mock_mode,
            active=False,
            idle_status="not_requested",
            idle_reason="No broker-backed provider request has been made in this backend session.",
            action_label="Connect TWS and open a broker-backed workspace.",
        )
    )
    commodities_provider = (os.getenv("COMMODITIES_PROVIDER", "sample") or "sample").strip().lower()
    provider_usage.register_activation_condition(
        ProviderActivationCondition(
            provider_id="eia",
            display_name="EIA commodities",
            expected_when="Commodities workspace is loaded with EIA/FRED official-provider configuration.",
            configured=commodities_provider in {"eia", "official", "eia_fred", "fred", "ibkr_eia"}
            and bool((os.getenv("EIA_API_KEY", "") or "").strip()),
            active=False,
            idle_status="not_requested",
            idle_reason="No EIA-backed commodities request has been made in this backend session.",
            action_label="Configure EIA_API_KEY and open Commodities.",
        )
    )


def _build_research_history_providers(
    client: IBKRClient,
    market_data: MarketDataService,
    mock_service: MockDataService,
    provider_usage: ProviderUsageLedger,
    *,
    env_var: str = "RESEARCH_MARKET_DATA_PROVIDERS",
    live_default: str = "yfinance,ibkr",
) -> list[ListedMarketHistoryProvider]:
    configured = (os.getenv(env_var, "") or "").strip().lower()
    if configured:
        provider_ids = [item.strip() for item in configured.split(",") if item.strip()]
    elif client.mock:
        provider_ids = ["mock"]
    else:
        provider_ids = [item.strip() for item in live_default.split(",") if item.strip()]

    providers: list[ListedMarketHistoryProvider] = []
    for provider_id in provider_ids:
        if provider_id in {"mock", "sample", "offline", "demo"}:
            if client.mock:
                providers.append(
                    trace_provider(
                        MockListedMarketHistoryProvider(mock_service),
                        provider_usage,
                        endpoint_prefix="research_history",
                    )
                )
            else:
                providers.append(
                    trace_provider(
                        UnavailableListedMarketHistoryProvider(
                            provider_id=provider_id,
                            source_label=f"{provider_id} listed-market history",
                            warning=(
                                f"Configured listed-market provider '{provider_id}' is disabled while Gamma is running "
                                "in live mode."
                            ),
                        ),
                        provider_usage,
                        endpoint_prefix="research_history",
                    )
                )
        elif provider_id in {"ibkr", "tws"}:
            providers.append(
                trace_provider(
                    IbkrListedMarketHistoryProvider(market_data),
                    provider_usage,
                    endpoint_prefix="research_history",
                )
            )
        elif provider_id in {"yfinance", "yahoo", "yahoo_finance"}:
            providers.append(
                trace_provider(
                    YFinanceListedMarketHistoryProvider(
                        timeout_seconds=float(os.getenv("YFINANCE_TIMEOUT_SECONDS", "10") or 10.0),
                        max_retries=int(os.getenv("YFINANCE_MAX_RETRIES", "2") or 2),
                        base_backoff_seconds=float(os.getenv("YFINANCE_BACKOFF_SECONDS", "0.25") or 0.25),
                        max_backoff_seconds=float(os.getenv("YFINANCE_MAX_BACKOFF_SECONDS", "2") or 2.0),
                        circuit_rate_limit_threshold=int(os.getenv("YFINANCE_CIRCUIT_THRESHOLD", "3") or 3),
                        circuit_cooldown_seconds=float(os.getenv("YFINANCE_CIRCUIT_COOLDOWN_SECONDS", "30") or 30.0),
                    ),
                    provider_usage,
                    endpoint_prefix="research_history",
                )
            )
        elif provider_id in {"akshare", "ak_share"}:
            providers.append(
                trace_provider(
                    UnavailableListedMarketHistoryProvider(
                        provider_id="akshare",
                        source_label="AKShare listed-market history (planned optional adapter)",
                        warning=(
                            "AKShare is recognized as a planned China/Asia coverage hook, but no Gamma adapter is active yet"
                        ),
                    ),
                    provider_usage,
                    endpoint_prefix="research_history",
                )
            )
        else:
            providers.append(
                trace_provider(
                    UnavailableListedMarketHistoryProvider(
                        provider_id=provider_id,
                        source_label=f"{provider_id} listed-market history",
                        warning=f"Configured listed-market provider '{provider_id}' is not supported by this Gamma build",
                    ),
                    provider_usage,
                    endpoint_prefix="research_history",
                )
            )
    fallback = MockListedMarketHistoryProvider(mock_service) if client.mock else IbkrListedMarketHistoryProvider(market_data)
    return providers or [trace_provider(fallback, provider_usage, endpoint_prefix="research_history")]


def _build_commodities_provider(
    cache: CacheService,
    client: IBKRClient,
    market_data: MarketDataService,
    *,
    live_mode: bool = False,
):
    provider = (os.getenv("COMMODITIES_PROVIDER", "sample") or "sample").strip().lower()
    sample_provider = SampleCommoditiesDataProvider()
    live_reference_provider = LiveCommoditiesReferenceProvider()
    unavailable_live_provider = UnavailableCommoditiesDataProvider(
        warning=(
            "No live commodities provider is configured. Set COMMODITIES_PROVIDER=ibkr with TWS connectivity "
            "or COMMODITIES_PROVIDER=eia with EIA_API_KEY/FRED_API_KEY for live-mode commodities coverage."
        )
    )
    if provider in {"sample", "mock", "offline", "demo"}:
        if live_mode:
            return UnavailableCommoditiesDataProvider(
                warning=(
                    f"COMMODITIES_PROVIDER={provider} is disabled while Gamma is running in live mode; "
                    "sample commodities data was not loaded."
                )
            )
        return sample_provider

    fred_client = FredClient(cache=cache) if (os.getenv("FRED_API_KEY", "") or "").strip() else None
    eia_provider = None
    if (os.getenv("EIA_API_KEY", "") or "").strip():
        eia_provider = EiaCommoditiesDataProvider(
            api_key=os.getenv("EIA_API_KEY", ""),
            cache=cache,
            reference_provider=live_reference_provider if live_mode else sample_provider,
            fred_client=fred_client,
            cache_seconds=int(os.getenv("COMMODITIES_CACHE_SECONDS", "21600") or 21600),
        )

    if provider in {"ibkr", "tws", "ibkr_eia", "ibkr_futures"}:
        return IbkrCommoditiesDataProvider(
            client=client,
            market_data=market_data,
            cache=cache,
            reference_provider=eia_provider or (live_reference_provider if live_mode else sample_provider),
            startup_instrument_ids=_parse_env_list("IBKR_COMMODITIES_STARTUP_ENABLED", "wti"),
            breadth_instrument_ids=_parse_env_list("IBKR_COMMODITIES_BREADTH_ENABLED", "__enabled__"),
            on_demand_enabled=_parse_bool_env("IBKR_COMMODITIES_ON_DEMAND", True),
            selected_cache_seconds=int(os.getenv("IBKR_COMMODITIES_SELECTED_CACHE_SECONDS", "300") or 300),
            contract_cache_seconds=int(os.getenv("IBKR_COMMODITIES_CONTRACT_CACHE_SECONDS", "21600") or 21600),
            contract_depth=int(os.getenv("IBKR_COMMODITIES_CONTRACT_DEPTH", "12") or 12),
            breadth_contract_depth=int(os.getenv("IBKR_COMMODITIES_BREADTH_CONTRACT_DEPTH", "2") or 2),
            history_days=int(os.getenv("IBKR_COMMODITIES_HISTORY_DAYS", "120") or 120),
            quote_timeout_seconds=float(
                os.getenv("IBKR_COMMODITIES_QUOTE_TIMEOUT_SECONDS", os.getenv("IB_SNAPSHOT_TIMEOUT_SECONDS", "2"))
                or 2.0
            ),
            contract_details_timeout_seconds=float(
                os.getenv("IBKR_COMMODITIES_CONTRACT_TIMEOUT_SECONDS", "12") or 12.0
            ),
            quote_batch_size=int(os.getenv("IBKR_COMMODITIES_QUOTE_BATCH_SIZE", "8") or 8),
        )

    if provider not in {"eia", "official", "eia_fred", "fred"}:
        if live_mode:
            return UnavailableCommoditiesDataProvider(
                warning=(
                    f"Unsupported COMMODITIES_PROVIDER={provider!r}; no commodities sample fallback is loaded "
                    "in live mode."
                )
            )
        return sample_provider

    if live_mode and not (os.getenv("EIA_API_KEY", "") or "").strip():
        return unavailable_live_provider

    return EiaCommoditiesDataProvider(
        api_key=os.getenv("EIA_API_KEY", ""),
        cache=cache,
        reference_provider=live_reference_provider if live_mode else sample_provider,
        fred_client=fred_client,
        cache_seconds=int(os.getenv("COMMODITIES_CACHE_SECONDS", "21600") or 21600),
    )


def _parse_env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _build_maritime_provider(*, live_mode: bool = False):
    provider = (os.getenv("MARITIME_PROVIDER", "sample") or "sample").strip().lower()
    sample_provider = SampleMaritimeDataProvider()
    if provider not in {"aisstream", "aisstream_live", "live"}:
        if live_mode:
            return UnavailableMaritimeDataProvider(
                warning=(
                    f"MARITIME_PROVIDER={provider} is disabled while Gamma is running in live mode; "
                    "sample maritime data was not loaded."
                )
            )
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
        reference_provider=UnavailableMaritimeDataProvider(
            warning="AISstream reference definitions are unavailable until live provider configuration supplies them."
        )
        if live_mode
        else sample_provider,
        bounding_boxes=bounding_boxes,
        message_types=message_types,
        sample_seconds=float(os.getenv("AISSTREAM_SAMPLE_SECONDS", "6") or 6.0),
        max_messages=int(os.getenv("AISSTREAM_MAX_MESSAGES", "500") or 500),
        cache_seconds=int(os.getenv("AISSTREAM_CACHE_SECONDS", "30") or 30),
    )


def _build_news_providers(*, live_mode: bool = False) -> list[NewsEventProvider]:
    configured = (os.getenv("NEWS_PROVIDER", "sample") or "sample").strip().lower()
    provider_ids = [item.strip() for item in configured.split(",") if item.strip()]
    providers: list[NewsEventProvider] = []
    for provider_id in provider_ids:
        if provider_id in {"rss", "rss_news", "rss_news_feeds"}:
            providers.append(
                RssNewsEventProvider(
                    timeout_seconds=float(os.getenv("RSS_NEWS_TIMEOUT_SECONDS", "6") or 6.0),
                )
            )
        elif provider_id in {"sample", "mock", "offline", "demo", "sample_news"}:
            if live_mode:
                providers.append(
                    UnavailableNewsEventProvider(
                        provider_id=provider_id,
                        warning=(
                            f"NEWS_PROVIDER={provider_id} is disabled while Gamma is running in live mode; "
                            "sample news items were not loaded."
                        ),
                    )
                )
            else:
                providers.append(SampleNewsEventProvider())
    if providers:
        return providers
    if live_mode:
        return [
            UnavailableNewsEventProvider(
                warning="No live news provider is configured. Set NEWS_PROVIDER=rss for live-mode RSS coverage."
            )
        ]
    return [SampleNewsEventProvider()]


class LiveCommoditiesReferenceProvider:
    provider_id = "live_commodities_reference"
    provider_label = "Live Commodities Reference Universe"

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
        del force_refresh
        del selected_instrument_id
        retrieved_at = now_utc().replace(microsecond=0)
        instruments = [
            CommodityInstrument(
                instrument_id=config.instrument_id,
                symbol=config.symbol,
                name=config.name,
                family=config.family,
                subgroup=config.subgroup,
                quote_unit=config.quote_unit,
                currency="USD",
                exchange=config.exchange,
                front_symbol=config.front_symbol,
                provider_symbols={"ibkr": config.front_symbol or ""},
                aliases=[config.name.lower(), config.symbol.lower()],
                description=f"{config.name} read-only commodity research instrument.",
                source_provider="gamma",
                retrieved_at=retrieved_at,
                origin="gamma.live_commodities_reference.instruments",
                transformation_note="Static Gamma instrument metadata used to request live commodities providers.",
            )
            for config in COMMODITY_INSTRUMENTS
        ]
        coverage = CommodityCoverageMetadata(
            coverage_status="unavailable",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="unavailable",
            instruments=[instrument.instrument_id for instrument in instruments],
            regions=["US", "Global"],
            as_of=retrieved_at,
            caveats=["Reference universe only; no commodity prices, curves, inventories, or events are included."],
            supports_prices=False,
            supports_curves=False,
            supports_inventories=False,
            supports_events=False,
            source_provider="gamma",
            retrieved_at=retrieved_at,
            origin="gamma.live_commodities_reference.coverage",
            transformation_note="Gamma returned provider-neutral instrument metadata without sample market data.",
        )
        return CommodityProviderSnapshot(
            coverage=coverage,
            instruments=instruments,
            warnings=["Live commodities reference metadata loaded without sample market data."],
            source_provider="gamma",
            retrieved_at=retrieved_at,
            origin="gamma.live_commodities_reference.snapshot",
            transformation_note="No sample commodity records are included in live-mode reference metadata.",
        )


class UnavailableCommoditiesDataProvider:
    provider_id = "unavailable_commodities"
    provider_label = "Unavailable Commodities Provider"

    def __init__(self, *, warning: str) -> None:
        self.warning = warning

    def get_snapshot(
        self,
        *,
        force_refresh: bool = False,
        selected_instrument_id: str | None = None,
    ) -> CommodityProviderSnapshot:
        del force_refresh
        del selected_instrument_id
        retrieved_at = now_utc().replace(microsecond=0)
        coverage = CommodityCoverageMetadata(
            coverage_status="unavailable",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="unavailable",
            as_of=retrieved_at,
            caveats=[self.warning],
            credential_env_vars=["COMMODITIES_PROVIDER", "EIA_API_KEY", "FRED_API_KEY", "IBKR_COMMODITIES_ENABLED"],
            supports_prices=False,
            supports_curves=False,
            supports_inventories=False,
            supports_events=False,
            source_provider="unavailable",
            retrieved_at=retrieved_at,
            origin="gamma.commodities.unavailable",
            transformation_note="Gamma returned no commodities records because sample data is disabled in live mode.",
        )
        return CommodityProviderSnapshot(
            coverage=coverage,
            warnings=[self.warning],
            source_provider="unavailable",
            retrieved_at=retrieved_at,
            origin="gamma.commodities.unavailable",
            transformation_note="No mock or sample commodities data was loaded.",
        )


class UnavailableMaritimeDataProvider:
    provider_id = "unavailable_maritime"
    provider_label = "Unavailable Maritime Provider"

    def __init__(self, *, warning: str) -> None:
        self.warning = warning

    def get_snapshot(self, *, force_refresh: bool = False) -> MaritimeProviderSnapshot:
        del force_refresh
        retrieved_at = now_utc()
        coverage = MaritimeCoverageMetadata(
            coverage_status="unavailable",
            provider_id=self.provider_id,
            provider_label=self.provider_label,
            freshness_label="unavailable",
            as_of=retrieved_at,
            caveats=[self.warning],
            credential_env_vars=["MARITIME_PROVIDER", "AISSTREAM_API_KEY", "AISSTREAM_BOUNDING_BOXES"],
            supports_live=False,
            supports_historical=False,
            source_provider="unavailable",
            retrieved_at=retrieved_at,
            origin="gamma.maritime.unavailable",
            transformation_note="Gamma returned no maritime records because sample data is disabled in live mode.",
        )
        return MaritimeProviderSnapshot(
            coverage=coverage,
            warnings=[self.warning],
            source_provider="unavailable",
            retrieved_at=retrieved_at,
            origin="gamma.maritime.unavailable",
            transformation_note="No mock or sample maritime data was loaded.",
        )

    def get_track(self, vessel_id: str, *, force_refresh: bool = False) -> MaritimeTrackSnippet | None:
        del vessel_id
        del force_refresh
        return None


class UnavailableNewsEventProvider:
    source_name = "Unavailable news provider"

    def __init__(self, *, warning: str, provider_id: str = "unavailable_news") -> None:
        self.provider_id = provider_id
        self.warning = warning

    def latest(self, *, limit: int = 25) -> NewsEventFeed:
        del limit
        return NewsEventFeed(
            items=[],
            source_provider="unavailable",
            retrieved_at=now_utc(),
            origin="gamma.news.unavailable",
            freshness_label=FreshnessLabel.UNAVAILABLE,
            warnings=[self.warning],
            transformation_note="Gamma returned no news/event records because sample data is disabled in live mode.",
        )
