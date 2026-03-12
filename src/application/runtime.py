from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from src.application.iv_service import IVService
from src.application.portfolio_service import PortfolioService
from src.application.research_service import ResearchService
from src.application.risk_service import RiskService
from src.application.system_service import normalize_market_data_mode
from src.services.app_context import AppDataContext
from src.services.cache import CacheService
from src.services.data_providers import PortfolioDataProvider, ResearchDataProvider
from src.services.fx import FXService
from src.services.ibkr_client import IBKRClient
from src.services.market_data import MarketDataService
from src.services.mock_data import MockDataService
from src.services.portfolio_history_store import PortfolioHistoryStore
from src.services.research_cache import ResearchHistoryCache
from src.services.risk_free_rate import RiskFreeRateService
from src.utils.logging_config import setup_logging


@dataclass
class ApplicationRuntime:
    base_currency: str
    auto_refresh_seconds: int
    default_lookback_days: int
    quote_timeout_seconds: float
    market_data_mode: str
    mock_mode: bool
    app_context: AppDataContext
    research_cache: ResearchHistoryCache
    mock_service: MockDataService
    client: IBKRClient
    cache: CacheService
    market_data: MarketDataService
    fx_service: FXService
    portfolio_history: PortfolioHistoryStore
    risk_free_service: RiskFreeRateService
    portfolio_provider: PortfolioDataProvider
    research_provider: ResearchDataProvider
    portfolio_service: PortfolioService
    research_service: ResearchService
    risk_service: RiskService
    iv_service: IVService

    def set_market_data_mode(self, value: str | None) -> str:
        normalized = normalize_market_data_mode(value)
        self.market_data_mode = normalized
        self.market_data.set_market_data_mode(normalized)
        self.client.set_market_data_mode(normalized)
        self.iv_service.set_market_data_mode(normalized)
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
) -> ApplicationRuntime:
    load_dotenv()
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

    app_context = AppDataContext()
    research_cache = ResearchHistoryCache()
    mock_service = MockDataService(base_path=resolved_sample_data_dir)
    client = IBKRClient(host, port, client_id, account, bool(mock_mode), mock_service)
    client.set_market_data_mode(market_data_mode)
    cache = CacheService(base_dir=resolved_cache_dir, ttl_hours=24)
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
    risk_free_service = RiskFreeRateService(cache=cache)

    portfolio_provider = PortfolioDataProvider(client, market_data, mock_service)
    research_provider = ResearchDataProvider(
        client,
        market_data,
        mock_service,
        app_context,
        base_currency,
        research_cache,
    )

    portfolio_service = PortfolioService(
        client,
        market_data,
        fx_service,
        portfolio_history,
        data_provider=portfolio_provider,
        mock_service=mock_service,
    )
    research_service = ResearchService(research_provider)
    risk_service = RiskService(client, market_data, mock_service, risk_free_service)
    iv_service = IVService(client, market_data_mode)

    return ApplicationRuntime(
        base_currency=base_currency,
        auto_refresh_seconds=auto_refresh,
        default_lookback_days=lookback,
        quote_timeout_seconds=quote_timeout,
        market_data_mode=market_data_mode,
        mock_mode=bool(mock_mode),
        app_context=app_context,
        research_cache=research_cache,
        mock_service=mock_service,
        client=client,
        cache=cache,
        market_data=market_data,
        fx_service=fx_service,
        portfolio_history=portfolio_history,
        risk_free_service=risk_free_service,
        portfolio_provider=portfolio_provider,
        research_provider=research_provider,
        portfolio_service=portfolio_service,
        research_service=research_service,
        risk_service=risk_service,
        iv_service=iv_service,
    )


@lru_cache(maxsize=1)
def get_runtime() -> ApplicationRuntime:
    return build_runtime()


def reset_runtime() -> None:
    if get_runtime.cache_info().currsize:
        runtime = get_runtime()
        runtime.shutdown()
    get_runtime.cache_clear()
