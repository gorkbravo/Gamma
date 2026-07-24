from __future__ import annotations

from types import SimpleNamespace
import sys

import pandas as pd

from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.models.provenance import FreshnessLabel
from src.services.data_providers import PortfolioDataProvider, ResearchDataProvider
from src.services.research_cache import ResearchHistoryCache
from src.services.research_market_data import (
    ResearchHistoryResult,
    YFinanceListedMarketHistoryProvider,
    contract_for_instrument,
)


class _NoopMarketData:
    def fetch_fx_history(self, base, quote, lookback_days):
        return None

    def fetch_fx_rate(self, base, quote):
        return None


class _NoopMockService:
    def load_history(self, symbol):
        return None


class _FakeHistoryProvider:
    def __init__(self, provider_id: str, source_label: str, histories: dict[str, pd.Series]) -> None:
        self.provider_id = provider_id
        self.source_label = source_label
        self.histories = histories

    def load_history(self, instrument: InstrumentReference, lookback_days: int) -> ResearchHistoryResult:
        symbol = instrument.normalized_symbol()
        series = self.histories.get(symbol)
        if series is None:
            return ResearchHistoryResult.unavailable(
                source_provider=self.provider_id,
                source_label=self.source_label,
                origin=f"{self.provider_id}.history",
                warning=f"{self.provider_id} unavailable for {symbol}",
            )
        return ResearchHistoryResult(
            series=series,
            source_provider=self.provider_id,
            source_label=self.source_label,
            origin=f"{self.provider_id}.history",
            freshness_label=FreshnessLabel.HISTORICAL,
        )


def _provider(*history_providers) -> ResearchDataProvider:
    return ResearchDataProvider(
        client=SimpleNamespace(mock=False),
        market_data=_NoopMarketData(),
        mock_service=_NoopMockService(),
        context=None,
        base_currency="USD",
        history_cache=ResearchHistoryCache(),
        instrument_defaults=InstrumentDefaults(provider="research", sec_type="STK", exchange="SMART", currency="USD"),
        benchmark_defaults=InstrumentDefaults(provider="benchmark", sec_type="STK", exchange="SMART", currency="USD"),
        history_providers=list(history_providers),
    )


def test_research_data_provider_falls_back_to_next_history_provider():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fallback_history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    provider = _provider(
        _FakeHistoryProvider("ibkr", "IBKR/TWS daily historical bars", {}),
        _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"AAPL": fallback_history}),
    )

    result = provider.load_instrument_history_result(InstrumentReference(symbol="AAPL"), 30)

    assert result.series is not None
    assert result.series.equals(fallback_history)
    assert result.source_provider == "yfinance"
    assert result.source_label == "Yahoo Finance/yfinance daily history"
    assert any("ibkr unavailable" in warning.lower() for warning in result.warnings)


def test_portfolio_data_provider_can_fall_back_to_public_history_provider():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fallback_history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    snapshot = PortfolioSnapshot(
        timestamp=pd.Timestamp("2026-01-06").to_pydatetime(),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem(
                symbol="AAPL",
                sec_type="STK",
                currency="USD",
                quantity=1.0,
                avg_cost=None,
                market_price=None,
                market_value=100.0,
                unrealized_pnl=None,
                base_market_value=100.0,
                instrument_id="portfolio:stk:aapl",
                display_symbol="AAPL",
            )
        ],
        net_liquidation=100.0,
    )
    provider = PortfolioDataProvider(
        client=SimpleNamespace(mock=False),
        market_data=_NoopMarketData(),
        mock_service=_NoopMockService(),
        history_providers=[
            _FakeHistoryProvider("ibkr", "IBKR/TWS daily historical bars", {}),
            _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"AAPL": fallback_history}),
        ],
    )

    prices, missing = provider.load_prices(snapshot, 30)

    assert missing == []
    assert prices["portfolio:stk:aapl"].equals(fallback_history)
    assert any("ibkr unavailable" in warning.lower() for warning in provider.drain_history_warnings())


def test_research_data_provider_preserves_history_source_metadata_from_cache():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    first_provider = _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"MSFT": history})
    provider = _provider(first_provider)

    first = provider.load_instrument_history_result(InstrumentReference(symbol="MSFT"), 30)
    first_provider.histories = {}
    second = provider.load_instrument_history_result(InstrumentReference(symbol="MSFT"), 30)

    assert first.source_provider == "yfinance"
    assert second.series is not None
    assert second.source_provider == "yfinance"
    assert second.source_label == "Yahoo Finance/yfinance daily history"
    assert second.warnings == []


def test_research_data_provider_reports_cached_history_source_in_summary():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    first_provider = _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"MSFT": history})
    provider = _provider(first_provider)

    provider.load_instrument_history_result(InstrumentReference(symbol="MSFT"), 30)
    provider.reset_history_tracking()
    first_provider.histories = {}
    provider.load_instrument_history_result(InstrumentReference(symbol="MSFT"), 30)

    summary = provider.history_source_summary()

    assert summary.source_provider == "yfinance"
    assert summary.source_label == "Yahoo Finance/yfinance daily history"


def test_research_data_provider_uses_policy_specific_provider_chain_and_cache():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    yfinance_history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    ibkr_history = pd.Series([200.0, 201.0, 202.0, 203.0], index=idx)
    provider = _provider(_FakeHistoryProvider("ibkr", "IBKR/TWS daily historical bars", {"AAPL": ibkr_history}))
    provider.history_provider_sets = {
        "sitrep": [
            _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"AAPL": yfinance_history})
        ]
    }

    sitrep = provider.load_instrument_history_result(
        InstrumentReference(symbol="AAPL"),
        30,
        provider_policy="sitrep",
    )
    default = provider.load_instrument_history_result(InstrumentReference(symbol="AAPL"), 30)

    assert sitrep.source_provider == "yfinance"
    assert sitrep.series is not None
    assert sitrep.series.equals(yfinance_history)
    assert default.source_provider == "ibkr"
    assert default.series is not None
    assert default.series.equals(ibkr_history)


def test_ibkr_contract_normalizes_us_class_share_separator_without_changing_display_symbol():
    instrument = InstrumentReference(
        symbol="BRK-B",
        display_symbol="BRK-B",
        sec_type="STK",
        exchange="SMART",
        primary_exchange="NYSE",
        currency="USD",
    )

    contract = contract_for_instrument(instrument)

    assert contract.symbol == "BRK B"
    assert contract.secType == "STK"
    assert contract.exchange == "SMART"
    assert contract.primaryExchange == "NYSE"
    assert instrument.normalized_display_symbol() == "BRK-B"


def test_yfinance_provider_keeps_dash_class_share_symbol():
    instrument = InstrumentReference(symbol="BRK-B", sec_type="STK", exchange="SMART", currency="USD")

    assert YFinanceListedMarketHistoryProvider._provider_symbol(instrument) == "BRK-B"


def _yfinance_frame() -> pd.DataFrame:
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    return pd.DataFrame({"Open": [99, 100, 101, 102], "High": [101, 102, 103, 104],
                         "Low": [98, 99, 100, 101], "Close": [100, 101, 102, 103],
                         "Volume": [1000, 1001, 1002, 1003]}, index=idx)


def test_yfinance_rate_limit_retries_with_bounded_backoff(monkeypatch):
    calls = 0
    sleeps: list[float] = []

    def download(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("HTTP Error 429: Too Many Requests")
        return _yfinance_frame()

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    provider = YFinanceListedMarketHistoryProvider(
        max_retries=2,
        base_backoff_seconds=0.2,
        max_backoff_seconds=0.5,
        sleep=sleeps.append,
        jitter=lambda _low, _high: 0.0,
    )
    result = provider.load_history(InstrumentReference(symbol="AAPL"), 30)

    assert calls == 2
    assert sleeps == [0.2]
    assert result.series is not None
    assert any("rate limit" in warning.lower() and "retry" in warning.lower() for warning in result.warnings)


def test_yfinance_circuit_opens_and_skips_followup_requests(monkeypatch):
    calls = 0
    now = [100.0]

    def download(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    provider = YFinanceListedMarketHistoryProvider(
        max_retries=5,
        circuit_rate_limit_threshold=2,
        circuit_cooldown_seconds=30,
        sleep=lambda _delay: None,
        monotonic=lambda: now[0],
        jitter=lambda _low, _high: 0.0,
    )
    first = provider.load_history(InstrumentReference(symbol="AAPL"), 30)
    second = provider.load_history(InstrumentReference(symbol="MSFT"), 30)

    assert calls == 2
    assert first.series is None and second.series is None
    assert any("circuit" in warning.lower() for warning in first.warnings)
    assert any("request skipped" in warning.lower() for warning in second.warnings)


def test_research_provider_uses_stale_cache_after_provider_failure():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    history = pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)
    source = _FakeHistoryProvider("yfinance", "Yahoo Finance/yfinance daily history", {"AAPL": history})
    provider = _provider(source)
    provider.load_instrument_history_result(InstrumentReference(symbol="AAPL"), 30)
    source.histories = {}

    fallback = provider.load_instrument_history_result(
        InstrumentReference(symbol="AAPL"), 30, bypass_cache=True
    )

    assert fallback.series is not None and fallback.series.equals(history)
    assert fallback.freshness_label == FreshnessLabel.STALE
    assert any("preserving stale cached" in warning.lower() for warning in fallback.warnings)


def test_research_history_cache_refresh_replaces_overlapping_older_values():
    cache = ResearchHistoryCache()
    idx = pd.date_range("2026-01-02", periods=3, freq="B")
    cache.set("AAPL", pd.Series([100.0, 101.0, 102.0], index=idx), 30)
    cache.set("AAPL", pd.Series([101.5, 102.5, 103.5], index=idx), 30)

    refreshed = cache.get("AAPL", 30)

    assert refreshed is not None
    assert refreshed.tolist() == [101.5, 102.5, 103.5]
