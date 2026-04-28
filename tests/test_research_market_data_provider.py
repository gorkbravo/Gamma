from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.provenance import FreshnessLabel
from src.services.data_providers import ResearchDataProvider
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
