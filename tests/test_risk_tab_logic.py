from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.analytics.var import parametric_var
from src.application.portfolio_service import PortfolioPerformanceRequest, PortfolioService
from src.application.risk_service import RiskComputeRequest, RiskService
from src.models.instruments import InstrumentDefaults
from src.models.portfolio import PortfolioSnapshot, PositionItem


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
    def __init__(self, histories=None) -> None:
        self._histories = dict(histories or {})

    def load_history(self, symbol):
        return self._histories.get(symbol)


class _StubFXService:
    def __init__(self, rate: float | None = None) -> None:
        self._rate = rate

    def get_rate(self, base, quote):
        return self._rate


class _StubHistoryStore:
    def append_snapshot(self, *args, **kwargs) -> None:
        return None

    def load_series(self, *args, **kwargs) -> pd.DataFrame:
        return pd.DataFrame()

    def clear(self) -> None:
        return None


class _PriceProvider:
    def __init__(self, price_map) -> None:
        self.price_map = dict(price_map)

    def load_prices(self, snapshot, lookback_days, progress_cb=None):
        symbols = list(self.price_map.keys())
        if progress_cb is not None:
            total = len(symbols)
            for index, symbol in enumerate(symbols, start=1):
                progress_cb(index, total, symbol)
        return dict(self.price_map), []


def _make_snapshot(positions, net_liq=100.0):
    for position in positions:
        if position.instrument_id is None:
            position.instrument_id = position.symbol
        if position.display_symbol is None:
            position.display_symbol = position.symbol
    return PortfolioSnapshot(
        timestamp=datetime(2026, 2, 22),
        base_currency="USD",
        account_summary={},
        positions=positions,
        net_liquidation=net_liq,
        total_market_value=net_liq,
        total_cash=0.0,
    )


def _make_risk_service(market_data=None, mock_service=None, benchmark_defaults=None):
    return RiskService(
        client=_StubClient(),
        market_data=market_data or _StubMarketData(),
        mock_service=mock_service or _StubMockService(),
        risk_free_service=None,
        benchmark_defaults=benchmark_defaults,
    )


def _make_portfolio_service(market_data=None, fx_service=None, data_provider=None, mock_service=None, benchmark_defaults=None):
    return PortfolioService(
        client=_StubClient(),
        market_data=market_data or _StubMarketData(),
        fx_service=fx_service or _StubFXService(),
        history_store=_StubHistoryStore(),
        data_provider=data_provider,
        mock_service=mock_service or _StubMockService(),
        benchmark_defaults=benchmark_defaults,
    )


def _compute_payload(prices, snapshot, **overrides):
    service = _make_risk_service()
    request = RiskComputeRequest(
        snapshot=snapshot,
        alpha=overrides.get("alpha", 0.95),
        lookback_days=overrides.get("lookback_days", 252),
        horizon_days=overrides.get("horizon_days", 1),
        mc_horizon_days=overrides.get("mc_horizon_days", 10),
        mc_simulation_model=overrides.get("mc_simulation_model", "Gaussian"),
        mc_num_simulations=overrides.get("mc_num_simulations", 2000),
        beta_window=overrides.get("beta_window", 63),
        benchmark_symbol=overrides.get("benchmark_symbol", "SPY"),
        base_currency=overrides.get("base_currency", "USD"),
        recommended_min_obs=overrides.get("recommended_min_obs", 60),
    )
    return service.compute(request, data_provider=_PriceProvider(prices))


def test_compute_aligns_covariance_to_weight_order():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 99, 100, 102, 103], index=idx),
        "B": pd.Series([50, 51, 52, 50, 49, 50], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=80.0),
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=20.0),
        ],
        net_liq=100.0,
    )

    payload = _compute_payload(prices, snapshot)
    results = payload.results
    returns_df = payload.returns_df
    contrib = payload.contributions
    weights = payload.weights
    component_var = payload.component_var

    expected_weights = weights.reindex(["A", "B"])
    expected_cov = returns_df[["A", "B"]].cov().values
    expected_param_var_r = parametric_var(expected_weights.values, expected_cov, 0.95)

    assert results.covered_portfolio_value == 100.0
    assert results.parametric_var is not None
    assert expected_param_var_r is not None
    assert abs((results.parametric_var / results.covered_portfolio_value) - expected_param_var_r) < 1e-12
    assert abs(component_var.sum() - results.parametric_var) < 1e-10
    assert set(contrib.index) == {"A", "B"}


def test_portfolio_service_compute_performance_normalizes_mixed_currency_histories():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "USD_ASSET": pd.Series([100.0, 101.0, 102.0, 103.0, 104.0, 105.0], index=idx),
        "EUR_ASSET": pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=idx),
    }
    fx_history = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5], index=idx)
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 303.0, 304.0, 305.0], index=idx)
    snapshot = _make_snapshot(
        [
            PositionItem("USD_ASSET", "STK", "USD", 1, None, None, None, None, base_market_value=50.0),
            PositionItem("EUR_ASSET", "STK", "EUR", 1, None, None, None, None, base_market_value=50.0),
        ],
        net_liq=100.0,
    )
    service = _make_portfolio_service(
        market_data=_StubMarketData(fx_history=fx_history),
        fx_service=_StubFXService(rate=1.5),
        data_provider=_PriceProvider(prices),
        mock_service=_StubMockService({"SPY": benchmark_history}),
    )

    result = service.compute_performance(
        PortfolioPerformanceRequest(
            snapshot=snapshot,
            benchmark_symbol="SPY",
            lookback_days=252,
        )
    )

    eur_returns = (prices["EUR_ASSET"] * fx_history).pct_change().dropna()
    usd_returns = prices["USD_ASSET"].pct_change().dropna()
    expected = (usd_returns * 0.5) + (eur_returns * 0.5)

    pd.testing.assert_index_equal(result.portfolio_returns.index, expected.index)
    pd.testing.assert_series_equal(result.portfolio_returns, expected, check_names=False)
    assert not any("spot rate" in warning.lower() for warning in result.warnings)


def test_compute_excludes_missing_base_value_without_crashing_and_reports_coverage():
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

    results = _compute_payload(prices, snapshot).results

    assert results.excluded_assets.get("B") == "Missing base market value"
    assert results.covered_risk_basis_value == 80.0
    assert results.risk_basis_value == 100.0
    assert results.risk_coverage_ratio is not None
    assert abs(results.risk_coverage_ratio - 0.8) < 1e-12
    assert results.historical_var is not None
    assert results.historical_var_total_estimate is not None
    assert abs(results.historical_var_total_estimate - (results.historical_var / 0.8)) < 1e-9
    assert results.monte_carlo_var is not None
    assert results.monte_carlo_var_total_estimate is not None
    assert abs(results.monte_carlo_var_total_estimate - (results.monte_carlo_var / 0.8)) < 1e-9


def test_compute_uses_base_currency_normalized_returns_for_mixed_currency_book():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "USD_ASSET": pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=idx),
        "EUR_ASSET": pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=idx),
    }
    fx_history = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4, 1.5], index=idx)
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 303.0, 304.0, 305.0], index=idx)
    snapshot = _make_snapshot(
        [
            PositionItem("USD_ASSET", "STK", "USD", 1, None, None, None, None, base_market_value=50.0),
            PositionItem("EUR_ASSET", "STK", "EUR", 1, None, None, None, None, base_market_value=50.0),
        ],
        net_liq=100.0,
    )
    service = _make_risk_service(
        market_data=_StubMarketData(fx_history=fx_history),
        mock_service=_StubMockService({"SPY": benchmark_history}),
    )
    request = RiskComputeRequest(
        snapshot=snapshot,
        alpha=0.95,
        lookback_days=252,
        horizon_days=1,
        mc_horizon_days=10,
        mc_simulation_model="Gaussian",
        mc_num_simulations=1000,
        beta_window=3,
        benchmark_symbol="SPY",
        base_currency="USD",
        recommended_min_obs=3,
    )

    payload = service.compute(request, data_provider=_PriceProvider(prices))

    expected_eur_returns = (prices["EUR_ASSET"] * fx_history).pct_change().dropna()
    pd.testing.assert_series_equal(payload.returns_df["EUR_ASSET"], expected_eur_returns, check_names=False)
    assert payload.results.daily_vol is not None
    assert payload.results.daily_vol > 0
    assert payload.portfolio_returns.abs().sum() > 0


def test_portfolio_service_warns_when_position_history_uses_spot_fx_fallback():
    idx = pd.date_range("2026-01-02", periods=4, freq="B")
    prices = {
        "EUR_ASSET": pd.Series([100.0, 101.0, 102.0, 103.0], index=idx),
    }
    benchmark_history = pd.Series([300.0, 301.0, 302.0, 303.0], index=idx)
    snapshot = _make_snapshot(
        [
            PositionItem("EUR_ASSET", "STK", "EUR", 1, None, None, None, None, base_market_value=100.0),
        ],
        net_liq=100.0,
    )
    service = _make_portfolio_service(
        market_data=_StubMarketData(fx_history=None, fx_rate=1.2),
        fx_service=_StubFXService(rate=1.2),
        data_provider=_PriceProvider(prices),
        mock_service=_StubMockService({"SPY": benchmark_history}),
    )

    result = service.compute_performance(
        PortfolioPerformanceRequest(
            snapshot=snapshot,
            benchmark_symbol="SPY",
            lookback_days=252,
        )
    )

    assert any("spot rate" in warning.lower() for warning in result.warnings)


def test_compute_caps_coverage_ratio_on_margined_live_like_book():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 100, 102, 103, 104], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=120.0),
            PositionItem("CASH_USD", "CASH", "USD", -20, None, 1.0, -20.0, 0.0, base_market_value=-20.0),
        ],
        net_liq=100.0,
    )

    results = _compute_payload(prices, snapshot).results

    assert results.covered_portfolio_value == 100.0
    assert results.covered_risk_basis_value == 120.0
    assert results.risk_basis_value == 120.0
    assert results.risk_coverage_ratio == 1.0
    assert results.historical_var_total_estimate == results.historical_var


def test_compute_treats_fully_covered_cash_heavy_book_as_fully_covered():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 100, 102, 103, 104], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("CASH_USD", "CASH", "USD", 80, None, 1.0, 80.0, 0.0, base_market_value=80.0),
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=20.0),
        ],
        net_liq=100.0,
    )

    results = _compute_payload(prices, snapshot).results

    assert results.covered_portfolio_value == 100.0
    assert results.covered_risk_basis_value == 20.0
    assert results.risk_basis_value == 20.0
    assert results.risk_coverage_ratio == 1.0
    assert results.historical_var_total_estimate == results.historical_var


def test_convert_benchmark_to_base_does_not_backfill_fx_history():
    px_idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fx_idx = px_idx[2:]
    px = pd.Series([100.0, 101.0, 102.0, 103.0], index=px_idx)
    fx = pd.Series([0.9, 0.91], index=fx_idx)

    service = _make_risk_service(_StubMarketData(fx_history=fx, fx_rate=None))
    converted, warnings = service._convert_benchmark_to_base(px, "USD", "EUR", 252)

    assert warnings == []
    assert converted is not None
    assert list(converted.index) == list(fx_idx)


def test_convert_benchmark_to_base_spot_fallback_warns():
    px_idx = pd.date_range("2026-01-02", periods=3, freq="B")
    px = pd.Series([100.0, 101.0, 102.0], index=px_idx)

    service = _make_risk_service(_StubMarketData(fx_history=None, fx_rate=0.9))
    converted, warnings = service._convert_benchmark_to_base(px, "USD", "EUR", 252)

    assert converted is not None
    assert len(warnings) == 1
    assert "spot" in warnings[0].lower()


def test_portfolio_benchmark_conversion_uses_resolved_non_usd_currency():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    snapshot = _make_snapshot([], net_liq=100.0)
    benchmark_history = pd.Series([200.0, 202.0, 204.0, 203.0, 205.0], index=idx)
    fx_history = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4], index=idx)
    service = _make_portfolio_service(
        market_data=_StubMarketData(fx_history=fx_history),
        fx_service=_StubFXService(rate=None),
        mock_service=_StubMockService({"VGK": benchmark_history}),
        benchmark_defaults=InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="EUR",
        ),
    )

    cumulative, source, warnings = service.build_benchmark(snapshot, "VGK", 252, idx[1:])

    expected = (benchmark_history * fx_history).pct_change().dropna()
    expected = (1.0 + expected).cumprod()
    expected = expected / float(expected.iloc[0])
    expected = expected.reindex(idx[1:]).ffill().fillna(1.0)

    assert source == "history_VGK"
    assert warnings == []
    pd.testing.assert_series_equal(cumulative, expected, check_names=False)


def test_risk_benchmark_conversion_uses_resolved_non_usd_currency():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    benchmark_history = pd.Series([200.0, 202.0, 204.0, 203.0, 205.0], index=idx)
    fx_history = pd.Series([1.0, 1.1, 1.2, 1.3, 1.4], index=idx)
    service = _make_risk_service(
        market_data=_StubMarketData(fx_history=fx_history),
        mock_service=_StubMockService({"VGK": benchmark_history}),
        benchmark_defaults=InstrumentDefaults(
            provider="benchmark",
            sec_type="STK",
            exchange="SMART",
            currency="EUR",
        ),
    )

    returns, warnings = service._load_benchmark_returns(252, "USD", "VGK")

    expected = (benchmark_history * fx_history).pct_change().dropna()

    assert warnings == []
    assert returns is not None
    pd.testing.assert_series_equal(returns, expected, check_names=False)


def test_portfolio_service_convert_series_to_base_does_not_backfill_fx_history():
    px_idx = pd.date_range("2026-01-02", periods=4, freq="B")
    fx_idx = px_idx[2:]
    px = pd.Series([100.0, 101.0, 102.0, 103.0], index=px_idx)
    fx = pd.Series([0.9, 0.91], index=fx_idx)

    warnings: list[str] = []
    service = _make_portfolio_service(
        market_data=_StubMarketData(fx_history=fx, fx_rate=None),
        fx_service=_StubFXService(rate=None),
    )
    converted = service.convert_series_to_base(px, "USD", "EUR", 252, warnings)

    assert warnings == []
    assert converted is not None
    assert list(converted.index) == list(fx_idx)


def test_compute_populates_monte_carlo_for_valid_long_only_portfolio():
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    prices = {
        "A": pd.Series([100, 101, 102, 101, 103, 104, 105, 107], index=idx),
        "B": pd.Series([50, 50.5, 51, 50.8, 51.5, 52.2, 52.8, 53.1], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=60.0),
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=40.0),
        ],
        net_liq=100.0,
    )

    results = _compute_payload(
        prices,
        snapshot,
        horizon_days=10,
        mc_horizon_days=21,
        mc_simulation_model="Bootstrap",
        mc_num_simulations=1000,
    ).results

    assert results.monte_carlo_model == "Bootstrap"
    assert results.monte_carlo_horizon_days == 21
    assert results.monte_carlo_num_simulations == 1000
    assert results.monte_carlo_var is not None
    assert results.monte_carlo_cvar is not None
    assert results.monte_carlo_terminal_returns is not None
    assert results.monte_carlo_fan_percentiles is not None
    assert results.monte_carlo_sample_paths is not None
    assert results.monte_carlo_fan_percentiles.shape[0] == 22
    assert results.monte_carlo_sample_paths.shape[0] == 22


def test_compute_skips_monte_carlo_for_negative_weight_portfolio():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 99, 101, 102, 100, 103], index=idx),
        "B": pd.Series([50, 51, 50.5, 50.8, 51.2, 51.5], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=120.0),
            PositionItem("B", "STK", "USD", -1, None, None, None, None, base_market_value=-20.0),
        ],
        net_liq=100.0,
    )

    results = _compute_payload(
        prices,
        snapshot,
        horizon_days=10,
        mc_horizon_days=10,
        mc_simulation_model="Gaussian",
        mc_num_simulations=2000,
    ).results

    assert results.monte_carlo_var is None
    assert results.monte_carlo_cvar is None
    assert results.monte_carlo_fan_percentiles is None
    assert any("Monte Carlo VaR unavailable" in warning for warning in results.warnings)


def test_compute_allows_offsetting_cash_balances_in_live_like_snapshot():
    idx = pd.date_range("2026-01-02", periods=7, freq="B")
    prices = {
        "A": pd.Series([100, 101, 102, 103, 102, 104, 105], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("CASH_USD", "CASH", "USD", 10, None, 1.0, 10.0, 0.0, base_market_value=10.0, weight=0.1),
            PositionItem("CASH_EUR", "CASH", "EUR", -10, None, 1.0, -10.0, 0.0, base_market_value=-10.0, weight=-0.1),
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=100.0, weight=1.0),
        ],
        net_liq=100.0,
    )

    results = _compute_payload(
        prices,
        snapshot,
        mc_horizon_days=10,
        mc_num_simulations=1000,
    ).results

    assert results.monte_carlo_var is not None
    assert results.monte_carlo_fan_percentiles is not None
    assert not any("risky gross exposure exceeds" in warning for warning in results.warnings)


def test_compute_builds_efficient_frontier_from_covered_risky_history():
    idx = pd.date_range("2026-01-02", periods=12, freq="B")
    prices = {
        "A": pd.Series([100, 101, 102, 103, 104, 103, 105, 106, 107, 108, 109, 111], index=idx),
        "B": pd.Series([50, 50.2, 50.8, 50.5, 51.0, 51.8, 52.0, 52.5, 53.0, 52.8, 53.5, 54.0], index=idx),
        "C": pd.Series([30, 30.5, 30.2, 30.8, 31.2, 31.0, 31.8, 32.1, 31.9, 32.4, 32.8, 33.0], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=50.0),
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=30.0),
            PositionItem("C", "STK", "USD", 1, None, None, None, None, base_market_value=20.0),
        ],
        net_liq=100.0,
    )

    payload = _compute_payload(prices, snapshot, recommended_min_obs=3)
    labels = {point.label for point in payload.frontier_points}

    assert {"Current", "Min Vol", "Max Sharpe", "Risk Parity"}.issubset(labels)
    assert any(point.kind == "frontier" for point in payload.frontier_points)
    current = next(point for point in payload.frontier_points if point.label == "Current")
    assert abs(sum(weight.weight for weight in current.weights) - 1.0) < 1e-9
    assert current.annual_vol > 0
    assert not any("Efficient frontier unavailable" in warning for warning in payload.results.warnings)


def test_compute_exposes_position_correlation_matrix():
    idx = pd.date_range("2026-01-02", periods=8, freq="B")
    prices = {
        "A": pd.Series([100, 101, 102, 101, 103, 104, 105, 106], index=idx),
        "B": pd.Series([50, 50.5, 50.9, 50.7, 51.1, 51.8, 52.0, 52.5], index=idx),
        "CASH_USD": pd.Series([1, 1, 1, 1, 1, 1, 1, 1], index=idx),
    }
    snapshot = _make_snapshot(
        [
            PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=50.0),
            PositionItem("B", "STK", "USD", 1, None, None, None, None, base_market_value=40.0),
            PositionItem("CASH_USD", "CASH", "USD", 10, None, 1.0, 10.0, 0.0, base_market_value=10.0),
        ],
        net_liq=100.0,
    )

    payload = _compute_payload(prices, snapshot, recommended_min_obs=3)

    assert list(payload.correlation_matrix.columns) == ["A", "B"]
    assert payload.correlation_matrix.loc["A", "B"] is not None
    assert "CASH_USD" not in payload.correlation_matrix.columns


def test_compute_explains_frontier_unavailable_for_single_covered_asset():
    idx = pd.date_range("2026-01-02", periods=6, freq="B")
    prices = {
        "A": pd.Series([100, 101, 102, 103, 104, 105], index=idx),
    }
    snapshot = _make_snapshot(
        [PositionItem("A", "STK", "USD", 1, None, None, None, None, base_market_value=100.0)],
        net_liq=100.0,
    )

    payload = _compute_payload(prices, snapshot, recommended_min_obs=3)

    assert payload.frontier_points == []
    warning = next(warning for warning in payload.results.warnings if "Efficient frontier unavailable" in warning)
    assert "eligible 1" in warning
    assert "snapshot risky 1" in warning
