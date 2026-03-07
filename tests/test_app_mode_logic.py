from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from src.models.app_mode import AppMode, ResearchScopeType, SyntheticPosition
from src.models.portfolio import PortfolioSnapshot
from src.services.app_context import AppDataContext
from src.services.data_providers import (
    PortfolioDataProvider,
    ResearchDataProvider,
    select_data_provider,
    should_auto_follow_research_symbol,
)
from src.ui.tabs.research_overview_tab import ResearchOverviewTab
from src.ui.tabs.risk_tab import RiskTab


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


def _make_providers(ctx: AppDataContext):
    client = _StubClient()
    market = _StubMarketData()
    mock = _StubMockService()
    portfolio_provider = PortfolioDataProvider(client, market, mock)  # type: ignore[arg-type]
    research_provider = ResearchDataProvider(client, market, mock, ctx, "USD")  # type: ignore[arg-type]
    return portfolio_provider, research_provider


def test_mode_switch_changes_provider_selection():
    ctx = AppDataContext()
    portfolio_provider, research_provider = _make_providers(ctx)

    selected = select_data_provider(ctx, portfolio_provider, research_provider)
    assert selected is portfolio_provider

    ctx.set_app_mode(AppMode.RESEARCH)
    selected = select_data_provider(ctx, portfolio_provider, research_provider)
    assert selected is research_provider

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
    provider = ResearchDataProvider(client, market, mock, ctx, "USD")  # type: ignore[arg-type]

    provider.load_symbol_history("SPY", 126)
    provider.load_symbol_history("SPY", 252)
    provider.load_symbol_history("SPY", 126)

    assert market.calls == [126, 252]


def test_risk_tab_keeps_portfolio_snapshot_across_research_mode_switch():
    ctx = AppDataContext()
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
    tab = SimpleNamespace(app_context=ctx, portfolio_snapshot=None)

    RiskTab.set_portfolio_snapshot(tab, portfolio_snapshot)
    assert RiskTab._active_snapshot(tab) is portfolio_snapshot

    ctx.set_app_mode(AppMode.RESEARCH)
    ctx.set_research_snapshot(research_snapshot)
    assert RiskTab._active_snapshot(tab) is research_snapshot

    ctx.set_app_mode(AppMode.PORTFOLIO)
    assert RiskTab._active_snapshot(tab) is portfolio_snapshot


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
