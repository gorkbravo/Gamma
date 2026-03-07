from __future__ import annotations

from datetime import datetime
from types import MethodType, SimpleNamespace

import pandas as pd

from src.analytics.var import parametric_var
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.ui.tabs.overview_tab import OverviewTab
from src.ui.tabs.risk_tab import BenchmarkMetricsResult, RiskComputeRequest, RiskTab


class _StubClient:
    mock = True


class _StubMarketData:
    def __init__(self, fx_history: pd.Series | None = None, fx_rate: float | None = None) -> None:
        self._fx_history = fx_history
        self._fx_rate = fx_rate

    def drain_errors(self):
        return []

    def fetch_fx_history(self, base, quote, lookback_days):
        return self._fx_history

    def fetch_fx_rate(self, base, quote):
        return self._fx_rate


class _StubMockService:
    def load_history(self, symbol):
        return None


class _StubFXService:
    def __init__(self, rate: float | None = None) -> None:
        self._rate = rate

    def get_rate(self, base, quote):
        return self._rate


def _make_snapshot(positions, net_liq=100.0):
    return PortfolioSnapshot(
        timestamp=datetime(2026, 2, 22),
        base_currency="USD",
        account_summary={},
        positions=positions,
        net_liquidation=net_liq,
        total_market_value=net_liq,
        total_cash=0.0,
    )


def _make_tab(price_map, market_data=None):
    tab = SimpleNamespace()
    tab.client = _StubClient()
    tab.market_data = market_data or _StubMarketData()
    tab.mock_service = _StubMockService()
    tab.risk_free_service = None
    tab.base_currency = "USD"
    tab._load_prices = MethodType(lambda self, snapshot, lookback_days, progress_cb=None: (price_map, []), tab)
    tab._beta_corr_alpha = MethodType(
        lambda self, **kwargs: BenchmarkMetricsResult(overlap_count=int(len(kwargs["port_ret"]))), tab
    )
    tab._ensure_cash_returns = MethodType(RiskTab._ensure_cash_returns, tab)
    tab._weights_for_symbols = MethodType(RiskTab._weights_for_symbols, tab)
    tab._concentration_metrics = RiskTab._concentration_metrics
    return tab


def test_compute_worker_aligns_covariance_to_weight_order():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 99, 100, 102, 103], index=idx),
        "B": pd.Series([50, 51, 52, 50, 49, 50], index=idx),
    }
    # Deliberately reverse snapshot order vs price/covariance column order.
    snapshot = _make_snapshot(
        [
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=80.0),
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=20.0),
        ],
        net_liq=100.0,
    )
    request = RiskComputeRequest(
        request_id=1,
        snapshot=snapshot,
        alpha=0.95,
        lookback_days=252,
        horizon_days=1,
        beta_window=63,
        benchmark_symbol="SPY",
        base_currency="USD",
    )
    tab = _make_tab(prices)

    _, results, _, returns_df, contrib, weights, _, component_var = RiskTab._compute_worker(tab, request)

    expected_weights = weights.reindex(["A", "B"])
    expected_cov = returns_df[["A", "B"]].cov().values
    expected_param_var_r = parametric_var(expected_weights.values, expected_cov, 0.95)

    assert results.covered_portfolio_value == 100.0
    assert results.parametric_var is not None
    assert expected_param_var_r is not None
    assert abs((results.parametric_var / results.covered_portfolio_value) - expected_param_var_r) < 1e-12
    assert abs(component_var.sum() - results.parametric_var) < 1e-10
    assert set(contrib.index) == {"A", "B"}


def test_compute_worker_excludes_missing_base_value_without_crashing_and_reports_coverage():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 100, 102, 101, 103], index=idx),
        "B": pd.Series([50, 52, 51, 53, 54, 55], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=80.0),
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=None),
        ],
        net_liq=100.0,
    )
    request = RiskComputeRequest(
        request_id=2,
        snapshot=snapshot,
        alpha=0.95,
        lookback_days=252,
        horizon_days=1,
        beta_window=63,
        benchmark_symbol="SPY",
        base_currency="USD",
    )
    tab = _make_tab(prices)

    _, results, *_ = RiskTab._compute_worker(tab, request)

    assert results.excluded_assets.get("B") == "Missing base market value"
    assert results.risk_coverage_ratio is not None
    assert abs(results.risk_coverage_ratio - 0.8) < 1e-12
    assert results.historical_var is not None
    assert results.historical_var_total_estimate is not None
    assert abs(results.historical_var_total_estimate - (results.historical_var / 0.8)) < 1e-9


def test_convert_benchmark_to_base_does_not_backfill_fx_history():
    px_idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fx_idx = px_idx[2:]
    px = pd.Series([100.0, 101.0, 102.0, 103.0], index=px_idx)
    fx = pd.Series([0.9, 0.91], index=fx_idx)

    tab = SimpleNamespace()
    tab.market_data = _StubMarketData(fx_history=fx, fx_rate=None)

    converted, warnings = RiskTab._convert_benchmark_to_base(tab, px, "USD", "EUR", 252)

    assert warnings == []
    assert converted is not None
    assert list(converted.index) == list(fx_idx)


def test_convert_benchmark_to_base_spot_fallback_warns():
    px_idx = pd.date_range("2026-01-02", periods=3, freq="B")
    px = pd.Series([100.0, 101.0, 102.0], index=px_idx)
    tab = SimpleNamespace()
    tab.market_data = _StubMarketData(fx_history=None, fx_rate=0.9)

    converted, warnings = RiskTab._convert_benchmark_to_base(tab, px, "USD", "EUR", 252)

    assert converted is not None
    assert len(warnings) == 1
    assert "spot" in warnings[0].lower()


def test_overview_convert_series_to_base_does_not_backfill_fx_history():
    px_idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fx_idx = px_idx[2:]
    px = pd.Series([100.0, 101.0, 102.0, 103.0], index=px_idx)
    fx = pd.Series([0.9, 0.91], index=fx_idx)

    tab = SimpleNamespace()
    tab.market_data = _StubMarketData(fx_history=fx, fx_rate=None)
    tab.fx_service = _StubFXService(rate=None)
    warnings: list[str] = []

    converted = OverviewTab._convert_series_to_base(tab, px, "USD", "EUR", 252, warnings)

    assert warnings == []
    assert converted is not None
    assert list(converted.index) == list(fx_idx)
