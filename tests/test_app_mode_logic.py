from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from src.application.runtime import build_desktop_runtime, build_runtime
from src.models.app_mode import AppMode, ResearchScopeType, SyntheticPosition
from src.models.instruments import InstrumentDefaults
from src.models.portfolio import PortfolioSnapshot
from src.services.app_context import AppDataContext
from src.application.workspace_service import can_forward_research_to_iv, resolve_active_snapshot, resolve_followed_symbol
from src.services.data_providers import (
    PortfolioDataProvider,
    ResearchDataProvider,
    select_data_provider,
    select_data_provider_for_mode,
    should_auto_follow_research_symbol,
)
from src.services.research_cache import ResearchHistoryCache
from src.ui.tabs.research_overview_tab import ResearchOverviewTab


@dataclass
class _StubClient:
    mock: bool = True


class _StubMarketData:
    pass


class _StubMockService:
    def load_history(self, symbol):
        return None


class _HistoryMarketData:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def fetch_history(self, contract, lookback_days):
        self.calls.append(int(lookback_days))
        idx = pd.date_range("2026-01-02", periods=4, freq="B")
        return pd.Series([100.0, 101.0, 102.0, 103.0], index=idx)


class _ContractHistoryMarketData:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str, str]] = []

    def fetch_history(self, contract, lookback_days):
        self.calls.append(
            (
                str(contract.symbol),
                str(contract.secType),
                str(contract.exchange),
                str(contract.currency),
                str(getattr(contract, "primaryExchange", "") or ""),
            )
        )
        idx = pd.date_range("2026-01-02", periods=4, freq="B")
        base = 100.0 if str(contract.exchange) == "SMART" else 200.0
        return pd.Series([base, base + 1.0, base + 2.0, base + 3.0], index=idx)


def _make_providers(ctx: AppDataContext):
    client = _StubClient()
    market = _StubMarketData()
    mock = _StubMockService()
    portfolio_provider = PortfolioDataProvider(client, market, mock)  # type: ignore[arg-type]
    research_provider = ResearchDataProvider(
        client,
        market,
        mock,
        ctx,
        "USD",
        ResearchHistoryCache(),
    )  # type: ignore[arg-type]
    return portfolio_provider, research_provider


def test_mode_switch_changes_provider_selection():
    ctx = AppDataContext()
    portfolio_provider, research_provider = _make_providers(ctx)

    selected = select_data_provider(ctx, portfolio_provider, research_provider)
    assert selected is portfolio_provider
    assert select_data_provider_for_mode(AppMode.PORTFOLIO, portfolio_provider, research_provider) is portfolio_provider

    ctx.set_app_mode(AppMode.RESEARCH)
    selected = select_data_provider(ctx, portfolio_provider, research_provider)
    assert selected is research_provider
    assert select_data_provider_for_mode(AppMode.RESEARCH, portfolio_provider, research_provider) is research_provider

    ctx.set_app_mode(AppMode.PORTFOLIO)
    selected = select_data_provider(ctx, portfolio_provider, research_provider)
    assert selected is portfolio_provider


def test_research_scope_validation():
    invalid_single = AppDataContext.validate_scope(ResearchScopeType.SINGLE_TICKER, "", [])
    assert not invalid_single.valid
    assert any("Ticker is required" in err for err in invalid_single.errors)

    invalid_synth = AppDataContext.validate_scope(
        ResearchScopeType.SYNTHETIC_PORTFOLIO,
        "",
        [SyntheticPosition("SPY", 0.0)],
    )
    assert not invalid_synth.valid
    assert any("positive" in err.lower() for err in invalid_synth.errors)

    valid_synth = AppDataContext.validate_scope(
        ResearchScopeType.SYNTHETIC_PORTFOLIO,
        "",
        [SyntheticPosition("SPY", 0.6), SyntheticPosition("QQQ", 0.4)],
    )
    assert valid_synth.valid
    assert valid_synth.errors == []


def test_iv_auto_follow_decision_logic():
    assert should_auto_follow_research_symbol(AppMode.RESEARCH, ResearchScopeType.SINGLE_TICKER, True)
    assert not should_auto_follow_research_symbol(AppMode.RESEARCH, ResearchScopeType.SINGLE_TICKER, False)
    assert not should_auto_follow_research_symbol(AppMode.RESEARCH, ResearchScopeType.SYNTHETIC_PORTFOLIO, True)
    assert not should_auto_follow_research_symbol(AppMode.PORTFOLIO, ResearchScopeType.SINGLE_TICKER, True)


def test_research_to_iv_forwarding_requires_single_ticker_scope():
    assert can_forward_research_to_iv(ResearchScopeType.SINGLE_TICKER)
    assert not can_forward_research_to_iv(ResearchScopeType.SYNTHETIC_PORTFOLIO)
    assert not can_forward_research_to_iv(ResearchScopeType.NONE)


def test_research_provider_build_snapshot_by_scope():
    ctx = AppDataContext()
    _, research_provider = _make_providers(ctx)

    ctx.set_research_scope(ResearchScopeType.SINGLE_TICKER, primary_symbol="AAPL")
    single_snapshot, warnings = research_provider.build_snapshot()
    assert warnings == []
    assert single_snapshot is not None
    assert [p.symbol for p in single_snapshot.positions] == ["AAPL"]

    ctx.set_research_scope(
        ResearchScopeType.SYNTHETIC_PORTFOLIO,
        synthetic_positions=[SyntheticPosition("SPY", 0.75), SyntheticPosition("QQQ", 0.25)],
    )
    synth_snapshot, warnings = research_provider.build_snapshot()
    assert warnings == []
    assert synth_snapshot is not None
    assert len(synth_snapshot.positions) == 2
    assert abs(sum(float(p.base_market_value or 0.0) for p in synth_snapshot.positions) - 100.0) < 1e-9


def test_research_provider_symbol_cache_respects_requested_lookback():
    ctx = AppDataContext()
    client = _StubClient(mock=False)
    market = _HistoryMarketData()
    mock = _StubMockService()
    provider = ResearchDataProvider(
        client,
        market,
        mock,
        ctx,
        "USD",
        ResearchHistoryCache(),
    )  # type: ignore[arg-type]

    provider.load_symbol_history("SPY", 126)
    provider.load_symbol_history("SPY", 252)
    provider.load_symbol_history("SPY", 126)

    assert market.calls == [126, 252]


def test_research_provider_uses_configurable_instrument_defaults():
    ctx = AppDataContext()
    client = _StubClient(mock=False)
    market = _ContractHistoryMarketData()
    mock = _StubMockService()
    provider = ResearchDataProvider(
        client,
        market,
        mock,
        ctx,
        "USD",
        ResearchHistoryCache(),
        instrument_defaults=InstrumentDefaults(
            provider="research",
            sec_type="CRYPTO",
            exchange="PAXOS",
            currency="USD",
        ),
    )  # type: ignore[arg-type]

    snapshot, warnings = provider.build_snapshot_for_scope(ResearchScopeType.SINGLE_TICKER, primary_symbol="BTC")
    assert warnings == []
    assert snapshot is not None
    assert snapshot.positions[0].sec_type == "CRYPTO"
    assert snapshot.positions[0].exchange == "PAXOS"
    provider.load_symbol_history("BTC", 126)

    assert market.calls == [("BTC", "CRYPTO", "PAXOS", "USD", "")]


def test_research_provider_uses_separate_benchmark_defaults():
    ctx = AppDataContext()
    client = _StubClient(mock=False)
    market = _ContractHistoryMarketData()
    mock = _StubMockService()
    provider = ResearchDataProvider(
        client,
        market,
        mock,
        ctx,
        "USD",
        ResearchHistoryCache(),
        instrument_defaults=InstrumentDefaults(
            provider="research",
            sec_type="CRYPTO",
            exchange="PAXOS",
            currency="USD",
        ),
        benchmark_defaults=InstrumentDefaults(
            provider="benchmark",
            sec_type="IND",
            exchange="CBOE",
            currency="USD",
        ),
    )  # type: ignore[arg-type]

    provider.load_symbol_history("BTC", 126)
    provider.load_benchmark_history("VIX", 126)

    assert market.calls == [
        ("BTC", "CRYPTO", "PAXOS", "USD", ""),
        ("VIX", "IND", "CBOE", "USD", ""),
    ]


def test_research_provider_keeps_distinct_same_symbol_histories_separate():
    ctx = AppDataContext()
    client = _StubClient(mock=False)
    market = _ContractHistoryMarketData()
    mock = _StubMockService()
    provider = ResearchDataProvider(
        client,
        market,
        mock,
        ctx,
        "USD",
        ResearchHistoryCache(),
    )  # type: ignore[arg-type]

    snapshot, warnings = provider.build_snapshot_for_scope(
        ResearchScopeType.SYNTHETIC_PORTFOLIO,
        synthetic_positions=[
            SyntheticPosition(
                symbol="SPY",
                weight=0.6,
                provider="research",
                provider_id="spy-us",
                exchange="SMART",
                currency="USD",
            ),
            SyntheticPosition(
                symbol="SPY",
                weight=0.4,
                provider="research",
                provider_id="spy-eu",
                exchange="AEB",
                currency="EUR",
            ),
        ],
    )

    assert warnings == []
    assert snapshot is not None

    prices, missing = provider.load_prices(snapshot, 126)

    assert missing == []
    assert len(prices) == 2
    assert set(prices) == {position.resolved_instrument_id() for position in snapshot.positions}
    assert market.calls == [
        ("SPY", "STK", "SMART", "USD", ""),
        ("SPY", "STK", "AEB", "EUR", ""),
    ]
    assert not prices[snapshot.positions[0].resolved_instrument_id()].equals(
        prices[snapshot.positions[1].resolved_instrument_id()]
    )


def test_backend_runtime_omits_desktop_session_state(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        assert runtime.desktop is None
        assert runtime.app_context is None
        assert runtime.research_provider.context is None
    finally:
        runtime.shutdown()


def test_desktop_runtime_attaches_desktop_session_state(tmp_path):
    runtime = build_desktop_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        assert runtime.desktop is not None
        assert runtime.app_context is not None
        assert runtime.research_provider.context is runtime.app_context
    finally:
        runtime.shutdown()


def test_live_runtime_does_not_load_sample_or_mock_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    monkeypatch.setenv("MARITIME_PROVIDER", "sample")
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    monkeypatch.setenv("GAMMA_COPILOT_PROVIDER", "mock")
    monkeypatch.setenv("RESEARCH_MARKET_DATA_PROVIDERS", "mock")
    monkeypatch.setenv("SITREP_MARKET_DATA_PROVIDERS", "mock")

    runtime = build_runtime(
        mock_mode=False,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        commodities = runtime.commodities_service.get_workspace()
        assert commodities.coverage.coverage_status == "unavailable"
        assert commodities.instruments == []
        assert commodities.price_histories == []
        assert commodities.coverage.source_provider == "unavailable"

        maritime = runtime.maritime_service.get_workspace()
        assert maritime.coverage.coverage_status == "unavailable"
        assert maritime.vessels == []
        assert maritime.positions == []
        assert maritime.coverage.source_provider == "unavailable"

        news = runtime.news_service.latest()
        assert news.items == []
        assert news.source_provider == "unavailable"
        assert news.freshness_label.value == "unavailable"

        assert runtime.copilot_service.provider.provider_name == "unconfigured"

        history = runtime.research_provider.load_symbol_history("SPY", 5)
        warnings = runtime.research_provider.drain_history_warnings()
        assert history is None
        assert any("disabled while Gamma is running in live mode" in warning for warning in warnings)
    finally:
        runtime.shutdown()


def test_research_history_cache_survives_workspace_scope_reset():
    ctx = AppDataContext()
    client = _StubClient(mock=False)
    market = _HistoryMarketData()
    mock = _StubMockService()
    cache = ResearchHistoryCache()
    provider = ResearchDataProvider(client, market, mock, ctx, "USD", cache)  # type: ignore[arg-type]

    provider.load_symbol_history("SPY", 126)
    ctx.clear_research_state()
    provider.load_symbol_history("SPY", 126)

    assert market.calls == [126]
    assert cache.symbols() == ["SPY"]


def test_active_snapshot_keeps_portfolio_snapshot_across_research_mode_switch():
    portfolio_snapshot = PortfolioSnapshot(
        timestamp=datetime(2026, 3, 1),
        base_currency="USD",
        account_summary={},
        positions=[],
        net_liquidation=1000.0,
    )
    research_snapshot = PortfolioSnapshot(
        timestamp=datetime(2026, 3, 2),
        base_currency="USD",
        account_summary={},
        positions=[],
        net_liquidation=200.0,
    )
    assert resolve_active_snapshot(AppMode.PORTFOLIO, portfolio_snapshot, None) is portfolio_snapshot
    assert resolve_active_snapshot(AppMode.RESEARCH, portfolio_snapshot, research_snapshot) is research_snapshot
    assert resolve_active_snapshot(AppMode.PORTFOLIO, portfolio_snapshot, research_snapshot) is portfolio_snapshot


def test_resolve_followed_symbol_respects_toggle_and_current_value():
    assert resolve_followed_symbol("AAPL", "SPY", True) == "AAPL"
    assert resolve_followed_symbol("AAPL", "AAPL", True) is None
    assert resolve_followed_symbol("AAPL", "SPY", False) is None
    assert resolve_followed_symbol("", "SPY", True) is None


def test_research_overview_effective_positions_uses_weight_concentration():
    weights = pd.Series({"SPY": 0.5, "QQQ": 0.5})
    assert abs(ResearchOverviewTab._effective_positions(weights) - 2.0) < 1e-12


def test_research_overview_beta_corr_aligns_series():
    idx = pd.date_range("2026-01-02", periods=5, freq="B")
    perf = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005], index=idx)
    benchmark = pd.Series([0.008, 0.01, -0.012, 0.013, 0.004], index=idx)

    beta, corr = ResearchOverviewTab._beta_corr(perf, benchmark)

    assert beta is not None
    assert corr is not None
    assert corr > 0.9


def test_research_overview_slice_series_respects_timeframe():
    idx = pd.date_range("2026-01-01", periods=400, freq="D")
    series = pd.Series(range(len(idx)), index=idx, dtype=float)

    sliced = ResearchOverviewTab._slice_series(SimpleNamespace(), series, "1M")

    assert not sliced.empty
    assert sliced.index.min() >= idx.max() - pd.Timedelta(days=30)
    assert sliced.index.max() == idx.max()
