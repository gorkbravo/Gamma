from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.application.research_service import ResearchAnalysisRequest, ResearchService
from src.models.app_mode import ResearchScopeType
from src.models.portfolio import PortfolioSnapshot, PositionItem


class _StubResearchProvider:
    def __init__(
        self,
        snapshot: PortfolioSnapshot | None,
        snapshot_warnings: list[str] | None = None,
        prices: dict[str, pd.Series] | None = None,
        missing: list[str] | None = None,
        benchmark_history: pd.Series | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._snapshot_warnings = snapshot_warnings or []
        self._prices = prices or {}
        self._missing = missing or []
        self._benchmark_history = benchmark_history

    def build_snapshot_for_scope(self, scope, primary_symbol="", synthetic_positions=None):
        return self._snapshot, list(self._snapshot_warnings)

    def load_prices(self, snapshot, lookback_days):
        return dict(self._prices), list(self._missing)

    def load_symbol_history(self, symbol, lookback_days):
        return self._benchmark_history


def _make_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=datetime(2026, 3, 1),
        base_currency="USD",
        account_summary={},
        positions=[
            PositionItem("SPY", "STK", "USD", 1.0, None, None, 60.0, None, weight=0.6, base_market_value=60.0),
            PositionItem("QQQ", "STK", "USD", 1.0, None, None, 40.0, None, weight=0.4, base_market_value=40.0),
        ],
        total_market_value=100.0,
        total_cash=0.0,
        net_liquidation=100.0,
    )


def test_research_service_returns_empty_result_when_snapshot_cannot_be_built():
    service = ResearchService(_StubResearchProvider(snapshot=None, snapshot_warnings=["Ticker is required"]))

    result = service.analyze(
        ResearchAnalysisRequest(
            scope_type=ResearchScopeType.SINGLE_TICKER,
            primary_symbol="",
            benchmark_symbol="SPY",
        )
    )

    assert result.snapshot is None
    assert result.perf.empty
    assert result.weights.empty
    assert result.warnings == ["Ticker is required"]


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
    assert result.primary_price.equals(prices["SPY"])
    assert not result.benchmark_returns.empty
    assert result.benchmark_symbol == "IWM"
    assert result.warnings == []
