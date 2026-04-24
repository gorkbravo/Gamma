from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.api.schemas.research import ResearchOverviewResponseModel
from src.application.research_service import ResearchService
from src.models.instruments import InstrumentDefaults, InstrumentReference
from src.models.provenance import FreshnessLabel
from src.models.research_overview import ResearchOverviewRequest
from src.services.data_providers import ResearchDataProvider
from src.services.research_cache import ResearchHistoryCache
from src.services.research_market_data import ResearchHistoryResult


class _OverviewProvider:
    def __init__(self, histories: dict[str, pd.Series]) -> None:
        self.histories = histories
        self.client = SimpleNamespace(mock=True)
        self.base_currency = "USD"
        self.instrument_defaults = InstrumentDefaults(
            provider="research",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        )

    def load_instrument_history(self, instrument, lookback_days):
        return self.histories.get(instrument.normalized_symbol())

    def load_benchmark_history(self, symbol, lookback_days, *, base_currency=None, warnings=None):
        return self.histories.get(str(symbol or "").strip().upper())


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


def _research_data_provider(*history_providers) -> ResearchDataProvider:
    return ResearchDataProvider(
        client=SimpleNamespace(mock=False),
        market_data=_NoopMarketData(),
        mock_service=_NoopMockService(),
        context=None,
        base_currency="USD",
        history_cache=ResearchHistoryCache(),
        instrument_defaults=InstrumentDefaults(
            provider="research",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        ),
        benchmark_defaults=InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="USD",
        ),
        history_providers=list(history_providers),
    )


def test_research_overview_builds_nodes_rankings_and_provenance():
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    service = ResearchService(
        _OverviewProvider(
            {
                "AAPL": pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=idx),
                "MSFT": pd.Series([100, 101, 103, 106, 110, 112, 116, 120], index=idx),
                "SAP": pd.Series([100, 99, 98, 97, 98, 99, 98, 97], index=idx),
            }
        )
    )

    result = service.overview(
        ResearchOverviewRequest(
            universe_id="sample_equities",
            timeframe="1M",
            benchmark_symbol="AAPL",
        )
    )

    assert result.universe_id == "sample_equities"
    assert result.timeframe == "1M"
    assert result.coverage.instrument_count == 3
    assert result.coverage.priced_count == 3
    assert result.coverage.coverage_ratio == 1
    assert result.coverage.thin_history_symbols == ["AAPL", "MSFT", "SAP"]
    assert result.coverage.history_source_label == "Mock sample-data daily history"
    assert result.metadata_source_label == "Local sample/watchlist metadata"
    assert result.coverage.benchmark_available is True
    assert result.source_provider == "mock"
    assert result.freshness_label.value == "mocked"
    assert "not a complete market map" in " ".join(result.warnings)
    assert result.sort_options[0].sort_id == "market_cap_desc"

    instrument_nodes = [node for node in result.nodes if node.level == "instrument"]
    group_nodes = [node for node in result.nodes if node.level == "group"]
    assert {node.symbol for node in instrument_nodes} == {"AAPL", "MSFT", "SAP"}
    assert {node.label for node in group_nodes} == {"US Mega-Cap Tech", "International Software"}
    assert result.rankings.leaders[0].symbol == "MSFT"
    assert result.rankings.laggards[0].symbol == "SAP"
    assert result.rankings.highest_beta
    assert all(node.origin.startswith("research_service.overview") for node in result.nodes)

    response = ResearchOverviewResponseModel.from_domain(result)
    assert response.nodes[0].freshness_label == "mocked"
    assert response.coverage.benchmark_symbol == "AAPL"
    assert response.coverage.thin_history_symbols == ["AAPL", "MSFT", "SAP"]
    assert response.history_source_label == "Mock sample-data daily history"
    assert response.sort_options[0].sort_id == "market_cap_desc"
    assert response.transformation_note is not None


def test_research_overview_global_indices_uses_cash_index_universe():
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    service = ResearchService(
        _OverviewProvider(
            {
                "^GSPC": pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=idx),
                "^GDAXI": pd.Series([100, 100, 101, 101, 102, 103, 103, 104], index=idx),
                "^N225": pd.Series([100, 99, 100, 101, 101, 102, 103, 104], index=idx),
            }
        )
    )

    result = service.overview(
        ResearchOverviewRequest(
            universe_id="global_indices",
            timeframe="1M",
            benchmark_symbol="SPY",
        )
    )

    instrument_nodes = [node for node in result.nodes if node.level == "instrument"]

    assert result.universe_id == "global_indices"
    assert result.universe_label == "Global Indices"
    assert result.coverage.instrument_count == 12
    assert result.coverage.priced_count == 3
    assert result.coverage.coverage_label == "Curated global cash-index board, provider-dependent coverage"
    assert result.metadata_source_label == "Curated Gamma global cash-index symbol list"
    assert {node.symbol for node in instrument_nodes} >= {"^GSPC", "^GDAXI", "^N225"}
    assert {node.group for node in instrument_nodes} >= {"US", "Germany", "Japan"}
    assert any("direct public index symbols" in warning for warning in result.warnings)


def test_research_overview_labels_partial_coverage_without_failing():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    service = ResearchService(
        _OverviewProvider(
            {
                "AAPL": pd.Series([100, 99, 101, 102, 104], index=idx),
                "MSFT": pd.Series([100, 101, 100, 102, 103], index=idx),
            }
        )
    )

    result = service.overview(
        ResearchOverviewRequest(
            universe_id="unknown",
            timeframe="bad",
            benchmark_symbol="SPY",
        )
    )

    assert result.universe_id == "broad_us_market"
    assert result.timeframe == "DoD"
    assert result.coverage.priced_count == 2
    assert result.coverage.missing_count == 78
    assert result.coverage.coverage_label == "Static large-cap US seed, partial coverage"
    assert result.metadata_source_label == "Static S&P 500-derived proxy metadata"
    assert "NVDA" in result.coverage.missing_symbols
    assert result.coverage.benchmark_available is False
    assert any("Unknown Research Overview universe" in warning for warning in result.warnings)
    assert any("Unknown Research Overview timeframe" in warning for warning in result.warnings)
    assert any("Coverage is partial" in warning for warning in result.warnings)


def test_research_overview_reports_mixed_history_provider_sources():
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    provider = _research_data_provider(
        _FakeHistoryProvider(
            "yfinance",
            "Yahoo Finance/yfinance daily history",
            {
                "AAPL": pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=idx),
                "MSFT": pd.Series([100, 101, 103, 106, 110, 112, 116, 120], index=idx),
            },
        ),
        _FakeHistoryProvider(
            "ibkr",
            "IBKR/TWS daily historical bars",
            {
                "SAP": pd.Series([100, 99, 98, 97, 98, 99, 98, 97], index=idx),
            },
        ),
    )
    service = ResearchService(provider)

    result = service.overview(
        ResearchOverviewRequest(
            universe_id="sample_equities",
            timeframe="1M",
            benchmark_symbol="AAPL",
            provider_policy="research_overview",
        )
    )

    instrument_sources = {node.symbol: node.source_provider for node in result.nodes if node.level == "instrument"}

    assert instrument_sources == {"AAPL": "yfinance", "MSFT": "yfinance", "SAP": "ibkr"}
    assert result.source_provider == "mixed"
    assert result.history_source_label.startswith("Mixed listed-market history providers")
    assert any("more than one listed-market history provider" in warning for warning in result.warnings)
