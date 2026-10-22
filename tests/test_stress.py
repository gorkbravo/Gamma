"""Escenarios de estrés medidos: replay histórico de episodios y regímenes de volatilidad."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.analytics.stress import (
    HISTORICAL_STRESS_EPISODES,
    StressEpisode,
    replay_episode,
    volatility_regimes,
)
from src.api.main import create_app
from src.application.risk_service import RiskService, RiskStressReplayRequest
from src.application.runtime import build_runtime
from src.models.portfolio import PortfolioSnapshot, PositionItem
from src.models.research_lab import ResearchBookRiskLeg

EPISODE = StressEpisode("test", "Test episode", date(2024, 3, 4), date(2024, 3, 8), "Monday to Friday.")


def _prices(values, start="2024-03-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# ── Episodios ────────────────────────────────────────────────────────────


def test_episodes_are_well_formed_and_chronological():
    ids = [episode.episode_id for episode in HISTORICAL_STRESS_EPISODES]
    assert len(ids) == len(set(ids))
    assert all(episode.start < episode.end for episode in HISTORICAL_STRESS_EPISODES)
    assert [episode.start for episode in HISTORICAL_STRESS_EPISODES] == sorted(
        episode.start for episode in HISTORICAL_STRESS_EPISODES
    )
    covid = next(episode for episode in HISTORICAL_STRESS_EPISODES if episode.episode_id == "covid_2020")
    assert (covid.start, covid.end) == (date(2020, 2, 19), date(2020, 3, 23))


def test_episode_library_includes_labelled_commodity_episodes():
    # GUA-20261021-9: un libro de crudo no tenía ningún episodio propio de materias primas.
    by_id = {episode.episode_id: episode for episode in HISTORICAL_STRESS_EPISODES}
    oil = by_id["oil_crash_2020"]
    energy = by_id["energy_shock_2022"]
    assert (oil.start, oil.end) == (date(2020, 3, 5), date(2020, 4, 21))
    assert (energy.start, energy.end) == (date(2022, 2, 23), date(2022, 3, 8))
    assert {oil.kind, energy.kind} == {"commodity"}
    assert oil.anchor == energy.anchor == "Brent front-month settlement"
    assert by_id["covid_2020"].kind == "equity"
    assert all(episode.kind in {"equity", "commodity"} for episode in HISTORICAL_STRESS_EPISODES)


# ── Replay ───────────────────────────────────────────────────────────────


def test_replay_buys_and_holds_current_weights_through_the_episode():
    # Sesiones 1, 4-8 y 11 de marzo; el episodio va del lunes 4 (A=100, B=50) al viernes 8 (A=82, B=55).
    prices = {
        "A": _prices([100, 100, 90, 85, 80, 82, 80]),
        "B": _prices([50, 50, 51, 53, 54, 55, 55]),
    }
    weights = pd.Series({"A": 0.6, "B": -0.4})
    bench = _prices([400, 400, 390, 380, 370, 372, 360])

    result = replay_episode(prices, weights, EPISODE, portfolio_value=1000.0, benchmark_prices=bench)

    legs = {leg.key: leg for leg in result.legs}
    assert result.status == "full"
    assert legs["A"].episode_return == pytest.approx(82 / 100 - 1)
    assert legs["B"].episode_return == pytest.approx(55 / 50 - 1)
    expected = 0.6 * (82 / 100 - 1) + -0.4 * (55 / 50 - 1)
    assert result.book_return == pytest.approx(expected)
    assert result.book_pnl == pytest.approx(expected * 1000.0)
    assert result.benchmark_return == pytest.approx(372 / 400 - 1)
    assert result.active_return == pytest.approx(expected - (372 / 400 - 1))
    assert sum(leg.contribution_share for leg in result.legs) == pytest.approx(1.0)
    assert result.max_drawdown is not None and result.max_drawdown <= result.book_return + 1e-12
    assert result.worst_day_date is not None and result.worst_day_return < 0


def test_replay_uses_the_last_close_before_a_weekend_start():
    episode = StressEpisode("weekend", "Weekend start", date(2024, 3, 9), date(2024, 3, 12), "Saturday start.")
    prices = {"A": _prices([100, 100, 100, 100, 100, 100, 100, 90, 81], start="2024-03-01")}
    result = replay_episode(prices, pd.Series({"A": 1.0}), episode, portfolio_value=100.0)
    leg = result.legs[0]
    assert leg.start_price_date == date(2024, 3, 8)
    assert leg.end_price_date == date(2024, 3, 12)
    # El martes 12 cotiza a 90 (la serie llega a 81 el miércoles 13, fuera del episodio).
    assert result.book_return == pytest.approx(90 / 100 - 1)


def test_replay_treats_missing_positions_as_flat_and_reports_coverage():
    prices = {"A": _prices([100, 100, 90, 85, 80, 82, 80])}
    weights = pd.Series({"A": 0.7, "NEW": 0.3})
    late = {"A": prices["A"], "NEW": _prices([10, 11], start="2024-03-07")}

    result = replay_episode(late, weights, EPISODE, portfolio_value=100.0)

    legs = {leg.key: leg for leg in result.legs}
    assert result.status == "partial"
    assert legs["NEW"].status == "missing"
    assert "starts 2024-03-07" in legs["NEW"].note
    assert result.book_return == pytest.approx(0.7 * (82 / 100 - 1))
    assert result.covered_gross_weight == pytest.approx(0.7)
    assert "treated as flat" in result.note


def test_replay_withholds_the_book_result_when_coverage_is_too_thin():
    prices = {"A": _prices([100, 100, 90, 85, 80, 82, 80])}
    result = replay_episode(prices, pd.Series({"A": 0.2, "B": 0.8}), EPISODE, portfolio_value=100.0)
    assert result.status == "unavailable"
    assert result.book_return is None and result.max_drawdown is None
    assert "20%" in result.note


# ── Regímenes ────────────────────────────────────────────────────────────


def test_volatility_regimes_separate_calm_and_stressed_days():
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2025-01-01", periods=240)
    bench_vol = np.r_[np.full(120, 0.005), np.full(120, 0.025)]
    bench = pd.Series(rng.normal(0, 1, 240) * bench_vol, index=idx)
    portfolio = 0.8 * bench + pd.Series(rng.normal(0, 0.002, 240), index=idx)

    analysis = volatility_regimes(portfolio, bench, 0.95)

    assert analysis.status == "available"
    calm, stressed = analysis.regimes
    assert (calm.regime, stressed.regime) == ("calm", "stressed")
    assert calm.observation_count + stressed.observation_count == analysis.observation_count
    assert stressed.annual_vol > calm.annual_vol
    assert stressed.historical_cvar > calm.historical_cvar
    assert stressed.benchmark_correlation > 0.9


def test_volatility_regimes_explain_when_history_is_too_short():
    idx = pd.bdate_range("2025-01-01", periods=40)
    returns = pd.Series(np.linspace(-0.01, 0.01, 40), index=idx)
    analysis = volatility_regimes(returns, returns, 0.95)
    assert analysis.status == "unavailable"
    assert "at least 40 days" in analysis.note


# ── Servicio y API ───────────────────────────────────────────────────────


class _Provider:
    def __init__(self, prices_by_id):
        self.prices_by_id = prices_by_id
        self.lookbacks: list[int] = []

    def load_prices(self, snapshot, lookback_days, progress_cb=None):
        self.lookbacks.append(lookback_days)
        prices, missing = {}, []
        for position in snapshot.positions:
            key = position.resolved_instrument_id()
            series = self.prices_by_id.get(position.symbol)
            if series is None:
                missing.append(position.symbol)
            else:
                prices[key] = series
        return prices, missing


class _MarketData:
    def fetch_history(self, contract, lookback_days):
        return None


class _Client:
    mock = False


def _service():
    return RiskService(client=_Client(), market_data=_MarketData(), mock_service=None, risk_free_service=None)


def test_service_replays_a_research_book_and_flags_non_listed_legs():
    covid = next(episode for episode in HISTORICAL_STRESS_EPISODES if episode.episode_id == "covid_2020")
    idx = pd.bdate_range("2020-02-03", "2020-04-03")
    falling = pd.Series(np.linspace(100, 60, len(idx)), index=idx)
    provider = _Provider({"AAPL": falling, "SPY": falling * 3})
    legs = [
        ResearchBookRiskLeg(leg_id="1:strategy_portfolio_leg:equity:AAPL:2024-01-01:2025-01-01",
                            label="AAPL", symbol="AAPL", instrument_id="aapl", weight=0.8),
        ResearchBookRiskLeg(leg_id="2:strategy_portfolio_leg:prediction_contract:PM-1:2024-01-01:2025-01-01",
                            label="Election contract", symbol="PM-1", instrument_id="pm", weight=0.2),
    ]
    snapshot = PortfolioSnapshot(timestamp=datetime(2026, 10, 20), base_currency="USD", account_summary={},
                                 positions=[], net_liquidation=100000.0, total_market_value=100000.0, total_cash=0.0)

    result = _service().compute_stress_replay(
        RiskStressReplayRequest(snapshot=snapshot, benchmark_symbol="SPY", base_currency="USD",
                                source_scope="research_book", research_book_legs=legs,
                                episodes=(covid,), as_of=date(2026, 10, 20)),
        data_provider=provider,
    )

    episode = result.episodes[0]
    legs_by_symbol = {result.leg_metadata[leg.key]["symbol"]: leg for leg in episode.legs}
    assert episode.status == "partial"
    assert legs_by_symbol["AAPL"].status == "covered"
    assert legs_by_symbol["PM-1"].status == "missing"
    assert "prediction_contract" in legs_by_symbol["PM-1"].note
    assert episode.benchmark_return == pytest.approx(legs_by_symbol["AAPL"].episode_return)
    assert provider.lookbacks and max(provider.lookbacks) > 1500


def _commodity_book_leg(start: str, end: str, *, daily: float = -0.01) -> ResearchBookRiskLeg:
    from src.models.research_lab import ResearchObjectReturnPoint

    index = pd.bdate_range(start, end)
    return ResearchBookRiskLeg(
        leg_id=f"1:strategy_portfolio_leg:commodity:BRENT:{start}:{end}",
        label="Brent Crude Oil spot proxy return stream",
        symbol="BRENT",
        instrument_id="brent",
        weight=1.0,
        return_points=[ResearchObjectReturnPoint(timestamp=stamp.isoformat(), value=daily) for stamp in index],
    )


def _empty_book_snapshot():
    return PortfolioSnapshot(timestamp=datetime(2026, 10, 21), base_currency="USD", account_summary={},
                             positions=[], net_liquidation=100000.0, total_market_value=100000.0, total_cash=0.0)


def test_commodity_book_leg_replays_an_episode_with_its_own_history():
    oil = next(episode for episode in HISTORICAL_STRESS_EPISODES if episode.episode_id == "oil_crash_2020")
    leg = _commodity_book_leg("2020-01-02", "2020-06-30")
    result = _service().compute_stress_replay(
        RiskStressReplayRequest(snapshot=_empty_book_snapshot(), benchmark_symbol="SPY", base_currency="USD",
                                source_scope="research_book", research_book_legs=[leg],
                                episodes=(oil,), as_of=date(2026, 10, 21)),
        data_provider=_Provider({}),
    )

    episode = result.episodes[0]
    assert episode.status == "full"
    assert episode.legs[0].status == "covered"
    # Rendimiento propio del tramo (−1 % diario), sin proxy: (0,99)^n − 1 entre el 5 de marzo y el 21 de abril.
    sessions = len(pd.bdate_range("2020-03-06", "2020-04-21"))
    assert episode.book_return == pytest.approx(0.99 ** sessions - 1)
    assert result.coverage_summary is None


def test_stress_replay_summarises_a_book_without_history_for_any_episode():
    leg = _commodity_book_leg("2025-10-22", "2026-10-14")
    result = _service().compute_stress_replay(
        RiskStressReplayRequest(snapshot=_empty_book_snapshot(), benchmark_symbol="SPY", base_currency="USD",
                                source_scope="research_book", research_book_legs=[leg],
                                as_of=date(2026, 10, 21)),
        data_provider=_Provider({}),
    )

    assert all(episode.status == "unavailable" for episode in result.episodes)
    assert (result.history_start, result.history_end) == (date(2025, 10, 22), date(2026, 10, 14))
    assert result.coverage_summary.startswith(
        "No stress episode is covered: the book's price history runs 2025-10-22 to 2026-10-14"
    )
    assert "No proxy history is substituted" in result.coverage_summary
    assert f"the {len(HISTORICAL_STRESS_EPISODES)} episodes run from 2007-10-09" in result.coverage_summary


def test_stress_replay_endpoint_and_regimes_in_risk_compute(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data",
                            sample_data_dir="sample_data")
    try:
        client = TestClient(create_app(runtime))
        snapshot = client.get("/portfolio/snapshot").json()
        replay = client.post("/risk/stress-replay", json={"snapshot": snapshot, "benchmark_symbol": "SPY"})
        assert replay.status_code == 200, replay.text
        body = replay.json()
        assert [episode["episode_id"] for episode in body["episodes"]] == [
            episode.episode_id for episode in HISTORICAL_STRESS_EPISODES
        ]
        assert body["method"].startswith("Current weights are held")
        assert all(episode["status"] in {"full", "partial", "unavailable"} for episode in body["episodes"])
        assert {episode["kind"] for episode in body["episodes"]} == {"equity", "commodity"}
        assert "coverage_summary" in body and "history_start" in body

        risk = client.post("/risk/compute", json={"snapshot": snapshot, "include_monte_carlo": False}).json()
        assert "regime_analysis" in risk
        assert risk["regime_analysis"]["status"] in {"available", "unavailable"}
    finally:
        runtime.shutdown()
