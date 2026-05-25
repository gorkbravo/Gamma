from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.api.schemas.research import ResearchAnalyzeResponseModel
from src.application.research_service import ResearchAnalysisRequest, ResearchService
from src.application.research_validation import ResearchValidationError
from src.models.app_mode import ResearchScopeType, SyntheticPosition
from src.models.instruments import build_instrument_id
from src.models.portfolio import PortfolioSnapshot, PositionItem


class _StubMarketData:
    def __init__(self, fx_history: pd.Series | None = None, fx_rate: float | None = None) -> None:
        self._fx_history = fx_history
        self._fx_rate = fx_rate

    def fetch_fx_history(self, base, quote, lookback_days):
        return self._fx_history

    def fetch_fx_rate(self, base, quote):
        return self._fx_rate


class _StubResearchProvider:
    def __init__(
        self,
        snapshot: PortfolioSnapshot | None,
        snapshot_warnings: list[str] | None = None,
        prices: dict[str, pd.Series] | None = None,
        missing: list[str] | None = None,
        benchmark_history: pd.Series | None = None,
        market_data: _StubMarketData | None = None,
        ohlcv: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._snapshot_warnings = snapshot_warnings or []
        self._prices = prices or {}
        self._missing = missing or []
        self._benchmark_history = benchmark_history
        self.market_data = market_data or _StubMarketData()
        self._ohlcv = ohlcv or {}

    def build_snapshot_for_scope(self, scope, primary_symbol="", synthetic_positions=None):
        return self._snapshot, list(self._snapshot_warnings)

    def load_prices(self, snapshot, lookback_days):
        return dict(self._prices), list(self._missing)

    def load_symbol_history(self, symbol, lookback_days):
        return self._benchmark_history

    def load_benchmark_history(self, symbol, lookback_days, *, base_currency=None, warnings=None):
        return self._benchmark_history

    def last_ohlcv_for_instrument(self, instrument_id: str):
        return self._ohlcv.get(instrument_id)


def _make_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2026, 3, 1),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem(
                "SPY",
                "STK",
                "USD",
                1.0,
                None,
                None,
                60.0,
                None,
                weight=0.6,
                base_market_value=60.0,
                instrument_id="SPY",
                display_symbol="SPY",
            ),
            PositionItem(
                "QQQ",
                "STK",
                "USD",
                1.0,
                None,
                None,
                40.0,
                None,
                weight=0.4,
                base_market_value=40.0,
                instrument_id="QQQ",
                display_symbol="QQQ",
            ),
        ],
        total_market_value=100.0,
        total_cash=0.0,
        net_liquidation=100.0,
    )


def test_research_service_returns_empty_result_when_snapshot_cannot_be_built():
    service = ResearchService(_StubResearchProvider(snapshot=None, snapshot_warnings=["History unavailable"]))

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SINGLE_TICKER,
            primary_symbol="SPY",
            benchmark_symbol="SPY",
        )
    )

    assert result.snapshot is None
    assert result.perf.empty
    assert result.weights.empty
    assert result.available_symbols == []
    assert result.missing_symbols == []
    assert result.benchmark_overlap_count == 0
    assert result.warnings == ["History unavailable"]


def test_research_service_computes_perf_and_benchmark_returns_for_scope():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    snapshot = _make_snapshot()
    prices = {
        "SPY": pd.Series([100.0, 101.0, 103.0, 102.0, 104.0], index=idx),
        "QQQ": pd.Series([200.0, 202.0, 201.0, 205.0, 207.0], index=idx),
    }
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 304.0, 305.0], index=idx)
    service = ResearchService(
        _StubResearchProvider(
            snapshot=snapshot,
            prices=prices,
            benchmark_history=benchmark_history,
        )
    )

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SINGLE_TICKER,
            primary_symbol="SPY",
            benchmark_symbol="IWM",
        )
    )

    assert result.snapshot is snapshot
    assert not result.perf.empty
    assert not result.weights.empty
    assert result.weights.index.tolist() == ["SPY", "QQQ"]
    assert result.primary_price.equals(prices[snapshot.positions[0].resolved_instrument_id()])
    assert not result.benchmark_returns.empty
    assert result.benchmark_symbol == "IWM"
    assert result.primary_symbol == "SPY"
    assert result.available_symbols == ["SPY", "QQQ"]
    assert result.missing_symbols == []
    assert result.benchmark_overlap_count == 4
    assert result.constituent_total_returns["SPY"] > 0
    assert result.constituent_annual_vol["QQQ"] is not None
    assert result.constituent_max_drawdown["SPY"] is not None
    assert result.warnings == []


def test_research_analysis_response_preserves_primary_price_ohlcv_for_hero_chart():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    snapshot = _make_snapshot()
    prices = {
        "SPY": pd.Series([100.0, 101.0, 103.0, 102.0, 104.0], index=idx),
        "QQQ": pd.Series([200.0, 202.0, 201.0, 205.0, 207.0], index=idx),
    }
    ohlcv = pd.DataFrame(
        {
            "open": [99.0, 100.0, 101.5, 103.0, 102.5],
            "high": [101.0, 102.0, 104.0, 104.0, 105.0],
            "low": [98.0, 99.5, 101.0, 101.0, 102.0],
            "close": [100.0, 101.0, 103.0, 102.0, 104.0],
            "volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=idx,
    )
    service = ResearchService(
        _StubResearchProvider(
            snapshot=snapshot,
            prices=prices,
            benchmark_history=pd.Series([300.0, 301.0, 302.0, 304.0, 305.0], index=idx),
            ohlcv={"SPY": ohlcv},
        )
    )

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SINGLE_TICKER,
            primary_symbol="SPY",
            benchmark_symbol="IWM",
        )
    )
    response = ResearchAnalyzeResponseModel.from_service_result(result)

    assert response.primary_price_points[-1].value == 104.0
    assert response.primary_price_points[-1].open == 102.5
    assert response.primary_price_points[-1].high == 105.0
    assert response.primary_price_points[-1].low == 102.0
    assert response.primary_price_points[-1].close == 104.0
    assert response.primary_price_points[-1].volume == 1400.0


def test_research_service_preserves_synthetic_scope_weights_and_snapshot():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    snapshot = _make_snapshot()
    prices = {
        "SPY": pd.Series([100.0, 101.0, 103.0, 102.0, 104.0], index=idx),
        "QQQ": pd.Series([200.0, 202.0, 201.0, 205.0, 207.0], index=idx),
    }
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 304.0, 305.0], index=idx)
    service = ResearchService(
        _StubResearchProvider(
            snapshot=snapshot,
            prices=prices,
            benchmark_history=benchmark_history,
        )
    )

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
            primary_symbol="",
            synthetic_positions=[
                SyntheticPosition(symbol="SPY", weight=0.6),
                SyntheticPosition(symbol="QQQ", weight=0.4),
            ],
            benchmark_symbol="SPY",
        )
    )

    assert result.scope_type == ResearchScopeType.SYNTHETIC_PORTFOLIO
    assert result.primary_symbol is None
    assert result.snapshot is snapshot
    assert result.weights.index.tolist() == ["SPY", "QQQ"]
    assert result.weights["SPY"] == 0.6
    assert result.weights["QQQ"] == 0.4
    assert result.available_symbols == ["SPY", "QQQ"]
    assert result.benchmark_overlap_count == 4


def test_research_service_normalizes_mixed_currency_constituent_histories():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    snapshot = PortfolioSnapshot(
        timestamp=datetime(2026, 3, 1),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem(
                "USD_ASSET",
                "STK",
                "USD",
                1.0,
                None,
                None,
                50.0,
                None,
                weight=0.5,
                base_market_value=50.0,
                instrument_id="USD_ASSET",
                display_symbol="USD_ASSET",
            ),
            PositionItem(
                "EUR_ASSET",
                "STK",
                "EUR",
                1.0,
                None,
                None,
                50.0,
                None,
                weight=0.5,
                base_market_value=50.0,
                instrument_id="EUR_ASSET",
                display_symbol="EUR_ASSET",
            ),
        ],
        total_market_value=100.0,
        total_cash=0.0,
        net_liquidation=100.0,
    )
    prices = {
        "USD_ASSET": pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=idx),
        "EUR_ASSET": pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=idx),
    }
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 303.0, 304.0, 305.0], index=idx)
    fx_history = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5], index=idx)
    service = ResearchService(
        _StubResearchProvider(
            snapshot=snapshot,
            prices=prices,
            benchmark_history=benchmark_history,
            market_data=_StubMarketData(fx_history=fx_history),
        )
    )

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
            synthetic_positions=[
                SyntheticPosition(symbol="USD_ASSET", weight=0.5),
                SyntheticPosition(symbol="EUR_ASSET", weight=0.5, currency="EUR"),
            ],
            benchmark_symbol="SPY",
            lookback_days=252,
        )
    )

    expected_eur_returns = (prices["EUR_ASSET"] * fx_history).pct_change().dropna()
    expected = expected_eur_returns * 0.5

    pd.testing.assert_series_equal(result.perf, expected, check_names=False)
    assert result.constituent_total_returns["EUR_ASSET"] == pytest.approx(float((1.0 + expected_eur_returns).prod() - 1.0))
    assert not any("spot rate" in warning.lower() for warning in result.warnings)


def test_research_service_rejects_duplicate_synthetic_symbols():
    service = ResearchService(_StubResearchProvider(snapshot=_make_snapshot()))

    with pytest.raises(ResearchValidationError) as exc_info:
        service.analyze(
            ResearchAnalysisRequest(
                scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
                synthetic_positions=[
                    SyntheticPosition(symbol="SPY", weight=0.6),
                    SyntheticPosition(symbol="SPY", weight=0.4),
                ],
            )
        )

    assert "Duplicate symbol in synthetic portfolio: SPY" in exc_info.value.errors


def test_research_service_rejects_non_positive_synthetic_weights():
    service = ResearchService(_StubResearchProvider(snapshot=_make_snapshot()))

    with pytest.raises(ResearchValidationError) as exc_info:
        service.analyze(
            ResearchAnalysisRequest(
                scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
                synthetic_positions=[SyntheticPosition(symbol="SPY", weight=0.0)],
            )
        )

    assert "Synthetic weight must be positive for SPY" in exc_info.value.errors


def test_research_service_keeps_distinct_instruments_with_same_display_symbol_separate():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    spy_us_id = build_instrument_id(
        provider="research",
        provider_id="spy-us",
        symbol="SPY",
        sec_type="STK",
        exchange="SMART",
        currency="USD",
    )
    spy_eu_id = build_instrument_id(
        provider="research",
        provider_id="spy-eu",
        symbol="SPY",
        sec_type="STK",
        exchange="AEB",
        currency="EUR",
    )
    snapshot = PortfolioSnapshot(
        timestamp=datetime(2026, 3, 1),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem(
                "SPY",
                "STK",
                "USD",
                1.0,
                None,
                None,
                55.0,
                None,
                weight=0.55,
                base_market_value=55.0,
                instrument_id=spy_us_id,
                display_symbol="SPY",
                exchange="SMART",
                provider="research",
                provider_id="spy-us",
            ),
            PositionItem(
                "SPY",
                "STK",
                "EUR",
                1.0,
                None,
                None,
                45.0,
                None,
                weight=0.45,
                base_market_value=45.0,
                instrument_id=spy_eu_id,
                display_symbol="SPY",
                exchange="AEB",
                provider="research",
                provider_id="spy-eu",
            ),
        ],
        total_market_value=100.0,
        total_cash=0.0,
        net_liquidation=100.0,
    )
    service = ResearchService(
        _StubResearchProvider(
            snapshot=snapshot,
            prices={
                spy_us_id: pd.Series([100.0, 101.0, 102.0, 101.5, 103.0], index=idx),
                spy_eu_id: pd.Series([80.0, 80.5, 81.0, 82.0, 82.5], index=idx),
            },
            benchmark_history=pd.Series([300.0, 301.0, 302.0, 304.0, 305.0], index=idx),
        )
    )

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SYNTHETIC_PORTFOLIO,
            synthetic_positions=[
                SyntheticPosition(
                    symbol="SPY",
                    weight=0.55,
                    instrument_id=spy_us_id,
                    provider="research",
                    provider_id="spy-us",
                    exchange="SMART",
                    currency="USD",
                ),
                SyntheticPosition(
                    symbol="SPY",
                    weight=0.45,
                    instrument_id=spy_eu_id,
                    provider="research",
                    provider_id="spy-eu",
                    exchange="AEB",
                    currency="EUR",
                ),
            ],
            benchmark_symbol="SPY",
        )
    )

    assert result.weights.index.tolist() == [spy_us_id, spy_eu_id]
    assert result.weights.iloc[0] == pytest.approx(0.55)
    assert result.weights.iloc[1] == pytest.approx(0.45)
    assert result.available_symbols == ["SPY", "SPY"]
    assert set(result.constituent_total_returns.index) == {spy_us_id, spy_eu_id}
