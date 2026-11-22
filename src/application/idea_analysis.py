"""Test and risk snapshots for ideas (Workstream 12, checkpoint I3c).

A snapshot is recomputed only when the user asks. It runs the idea's current
legs, with the same signed shares of gross exposure as tracking, through the
services the other tabs already use:

* **Test:** a Strategy Lab portfolio composition (``ResearchService.
  compose_strategy_lab_portfolio``): equity curve, returns, volatility,
  Sharpe, drawdown, benchmark and per-leg contributions. It is in-sample and
  carries no costs, and the snapshot says so.
* **Risk:** the Risk service on that research book (``source_scope =
  "research_book"``): historical and parametric 1-day VaR, expected
  shortfall, volatility, beta, plus a replay of the book through documented
  stress episodes, with the worst one named.

Each snapshot keeps its legs, window, benchmark, source ids, provenance and
warnings, and is frozen with its date; it is marked stale when the legs change
or after a few days. Nothing here can place, stage or route an order.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.models.ideas import (
    DEFAULT_TRACKING_BENCHMARK,
    Idea,
    IdeaRiskEpisode,
    IdeaRiskSnapshot,
    IdeaSourceUnavailableError,
    IdeaTestSnapshot,
    IdeaTrackedLeg,
    IdeaValidationError,
    freeze_tracking_legs,
)
from src.models.provenance import ProvenanceRecord
from src.utils.time import now_utc

TEST_LOOKBACK_DAYS = 756
TEST_MIN_OBSERVATIONS = 60
RISK_LOOKBACK_DAYS = 252
RISK_ALPHA = 0.95
RISK_NOTIONAL = 100_000.0
ANALYSIS_ORIGIN = "idea_analysis"
# Avisos genéricos de Strategy Lab que no dicen nada de los datos; el snapshot ya muestra los pesos.
_BOILERPLATE_PREFIXES = (
    "Strategy Lab portfolio compositions are read-only",
    "Strategy Lab compositions are read-only",
    "Portfolio leg weights are signed exposures",
)


def _data_warnings(items: Any) -> list[str]:
    return [str(item) for item in (items or []) if not str(item).startswith(_BOILERPLATE_PREFIXES)]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _day(value: Any) -> date | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _curve(series: Any) -> list[tuple[str, float]]:
    points: list[tuple[str, float]] = []
    if series is None:
        return points
    for index, value in series.items():
        day = _day(index)
        number = _finite(value)
        if day is not None and number is not None:
            points.append((day.isoformat(), number))
    return points


def _total(series: Any) -> float | None:
    clean = [value for _, value in _curve(series)]
    if len(clean) < 2 or clean[0] == 0:
        return None
    return clean[-1] / clean[0] - 1.0


class IdeaAnalysisService:
    """Runs test and risk snapshots of an idea's legs on request."""

    def __init__(
        self,
        idea_service: Any,
        *,
        research_service_factory: Callable[[], Any],
        risk_service: Any,
        research_provider: Any,
        crypto_prices: Any = None,
        clock: Callable[[], datetime] = now_utc,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self.idea_service = idea_service
        self._research_service = research_service_factory
        self.risk_service = risk_service
        self.research_provider = research_provider
        self.crypto_prices = crypto_prices
        self._clock = clock
        self._new_id = id_factory

    # -- public ---------------------------------------------------------------

    def run_test(self, idea_id: str) -> Idea:
        idea = self.idea_service.get_idea(idea_id)
        legs = self._legs(idea, "tested")
        now = self._clock()
        composition = self._compose(idea, legs, lookback_days=TEST_LOOKBACK_DAYS, now=now)
        metrics = composition.metrics
        benchmark_total = _total(composition.benchmark_equity_curve)
        total = _finite(metrics.total_return)
        snapshot = IdeaTestSnapshot(
            snapshot_id=self._new_id(),
            idea_id=idea.idea_id,
            created_at=now,
            legs=legs,
            benchmark=self._benchmark(idea),
            lookback_days=TEST_LOOKBACK_DAYS,
            window_start=_day(metrics.start_date),
            window_end=_day(metrics.end_date),
            observations=int(metrics.observation_count or 0),
            source_ids={"composition": composition.name, "origin": str(composition.origin or "")},
            provenance=self._provenance(composition, now),
            warnings=tuple(_data_warnings(composition.warnings)),
            metrics={
                "total_return": total,
                "annual_return": metrics.annual_return,
                "annual_volatility": metrics.annual_volatility,
                "sharpe_ratio": metrics.sharpe_ratio,
                "sortino_ratio": metrics.sortino_ratio,
                "max_drawdown": metrics.max_drawdown,
                "benchmark_total_return": benchmark_total,
                "excess_total_return": None if total is None or benchmark_total is None else total - benchmark_total,
                "benchmark_beta": metrics.benchmark_beta,
                "benchmark_correlation": metrics.benchmark_correlation,
            },
            leg_contributions=dict(composition.leg_contributions or {}),
            equity_curve=tuple(_curve(composition.equity_curve)),
            benchmark_curve=tuple(_curve(composition.benchmark_equity_curve)),
        )
        return self.idea_service.add_test_snapshot(idea.idea_id, snapshot)

    def run_risk(self, idea_id: str) -> Idea:
        from src.application.risk_service import RiskComputeRequest, RiskStressReplayRequest
        from src.models.portfolio import PortfolioSnapshot

        idea = self.idea_service.get_idea(idea_id)
        legs = self._legs(idea, "risk-checked")
        now = self._clock()
        benchmark = self._benchmark(idea)
        composition = self._compose(idea, legs, lookback_days=TEST_LOOKBACK_DAYS, now=now)
        book = PortfolioSnapshot(
            timestamp=now,
            base_currency="USD",
            account_summary={},
            positions=[],
            total_market_value=RISK_NOTIONAL,
            total_cash=0.0,
            net_liquidation=RISK_NOTIONAL,
            source_provider="gamma_ideas",
            retrieved_at=now,
            origin=ANALYSIS_ORIGIN,
            freshness_label="derived",
            transformation_note="Notional research book for the idea's legs; risk is reported as a share of the book.",
        )
        payload = self._call_source("Risk", lambda: self.risk_service.compute(
            RiskComputeRequest(
                snapshot=book,
                alpha=RISK_ALPHA,
                lookback_days=RISK_LOOKBACK_DAYS,
                horizon_days=1,
                mc_horizon_days=10,
                mc_simulation_model="Gaussian",
                mc_num_simulations=2000,
                beta_window=126,
                benchmark_symbol=benchmark,
                base_currency="USD",
                include_monte_carlo=False,
                source_scope="research_book",
                source_label=f"Idea: {idea.title}",
                source_object_id=idea.idea_id,
                source_origin=ANALYSIS_ORIGIN,
                research_book_returns=composition.returns,
                research_book_benchmark_returns=composition.benchmark_returns,
                research_book_legs=list(composition.risk_legs or []),
            ),
            data_provider=self.research_provider,
        ))
        results = payload.results
        value = float(results.portfolio_value or RISK_NOTIONAL) or RISK_NOTIONAL

        def share(amount: Any) -> float | None:
            number = _finite(amount)
            return None if number is None else number / value

        warnings = _data_warnings(composition.warnings)
        episodes: list[IdeaRiskEpisode] = []
        try:
            replay = self.risk_service.compute_stress_replay(
                RiskStressReplayRequest(
                    snapshot=book,
                    benchmark_symbol=benchmark,
                    base_currency="USD",
                    source_scope="research_book",
                    research_book_legs=list(composition.risk_legs or []),
                    as_of=now.date(),
                ),
                data_provider=self.research_provider,
            )
            warnings.extend(getattr(replay, "warnings", []) or [])
            for item in replay.episodes:
                episodes.append(
                    IdeaRiskEpisode(
                        episode_id=item.episode.episode_id,
                        label=item.episode.label,
                        start=item.episode.start,
                        end=item.episode.end,
                        status=item.status,
                        book_return=item.book_return,
                        benchmark_return=item.benchmark_return,
                        max_drawdown=item.max_drawdown,
                        coverage=(
                            float(item.covered_gross_weight) / float(item.gross_weight)
                            if getattr(item, "gross_weight", 0)
                            else None
                        ),
                    )
                )
        except Exception as exc:  # noqa: BLE001 - la réplica es opcional; el VaR se guarda igual
            warnings.append(f"The stress replay did not run: {exc}")
        risk_returns = payload.portfolio_returns
        window = [day for day in (_day(index) for index in getattr(risk_returns, "index", [])) if day is not None]
        snapshot = IdeaRiskSnapshot(
            snapshot_id=self._new_id(),
            idea_id=idea.idea_id,
            created_at=now,
            legs=legs,
            benchmark=benchmark,
            lookback_days=RISK_LOOKBACK_DAYS,
            window_start=min(window) if window else None,
            window_end=max(window) if window else None,
            observations=len(window),
            source_ids={"composition": composition.name, "risk_scope": "research_book"},
            provenance=ProvenanceRecord(
                source_provider=str(composition.source_provider or "research"),
                retrieved_at=now,
                origin="idea_analysis.run_risk",
                transformation_note=(
                    f"Risk service on the idea's research book ({int(RISK_ALPHA * 100)}% one-day historical and parametric VaR, "
                    "expected shortfall, no Monte Carlo); stress episodes replay the same signed weights."
                ),
            ),
            warnings=tuple(dict.fromkeys([*warnings, *_data_warnings(getattr(payload, "warnings", None))])),
            alpha=RISK_ALPHA,
            horizon_days=1,
            metrics={
                "historical_var": share(results.historical_var),
                "historical_es": share(results.historical_cvar),
                "parametric_var": share(results.parametric_var),
                "daily_volatility": results.daily_vol,
                "annual_volatility": results.annual_vol,
                "max_drawdown": results.max_drawdown,
                "beta": results.beta,
                "correlation": results.correlation,
            },
            episodes=tuple(episodes),
        )
        return self.idea_service.add_risk_snapshot(idea.idea_id, snapshot)

    # -- helpers --------------------------------------------------------------

    def _legs(self, idea: Idea, verb: str) -> tuple[IdeaTrackedLeg, ...]:
        if not idea.legs:
            raise IdeaValidationError(f"Add legs with signed weights before the idea can be {verb}.")
        legs, untracked = freeze_tracking_legs(idea.legs, idea.stance)
        if untracked:
            raise IdeaValidationError(f"The legs cannot be {verb}: {untracked}")
        return legs

    @staticmethod
    def _benchmark(idea: Idea) -> str:
        return idea.tracking.benchmark if idea.tracking is not None else DEFAULT_TRACKING_BENCHMARK

    def _compose(self, idea: Idea, legs: tuple[IdeaTrackedLeg, ...], *, lookback_days: int, now: datetime) -> Any:
        from src.application.research_validation import ResearchValidationError
        from src.models.research_lab import (
            ResearchObjectReturnPoint,
            StrategyLabPortfolioCompositionRequest,
            StrategyLabPortfolioLeg,
        )

        portfolio_legs = []
        for leg in legs:
            entity_type = str(leg.entity.entity_type).strip().lower()
            label = leg.entity.label
            if entity_type == "crypto":
                points = self._crypto_points(leg, lookback_days=lookback_days, now=now)
                portfolio_legs.append(
                    StrategyLabPortfolioLeg(label=label, asset_class="crypto", identifier=leg.entity.normalized_id, weight=float(leg.weight or 0.0), value_kind="level", return_points=points)
                )
            else:
                portfolio_legs.append(
                    StrategyLabPortfolioLeg(label=label, asset_class=entity_type, identifier=leg.entity.normalized_id.upper(), weight=float(leg.weight or 0.0))
                )
        try:
            return self._research_service().compose_strategy_lab_portfolio(
                StrategyLabPortfolioCompositionRequest(
                    name=f"Idea: {idea.title}"[:120],
                    legs=portfolio_legs,
                    benchmark_symbol=self._benchmark(idea),
                    lookback_days=lookback_days,
                    min_observations=TEST_MIN_OBSERVATIONS,
                )
            )
        except ResearchValidationError as exc:
            errors = getattr(exc, "errors", None) or [str(exc)]
            raise IdeaValidationError("Strategy Lab could not compose the legs: " + "; ".join(str(item) for item in errors)) from exc
        except IdeaValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - un fallo del proveedor se nombra, no es un 500
            raise IdeaSourceUnavailableError(f"Strategy Lab could not read the prices: {exc}") from exc

    @staticmethod
    def _call_source(name: str, action: Callable[[], Any]) -> Any:
        try:
            return action()
        except IdeaValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IdeaSourceUnavailableError(f"{name} failed: {exc}") from exc

    def _crypto_points(self, leg: IdeaTrackedLeg, *, lookback_days: int, now: datetime) -> list[Any]:
        from src.models.research_lab import ResearchObjectReturnPoint

        if self.crypto_prices is None:
            raise IdeaValidationError(f"{leg.entity.label}: crypto history is not available.")
        closes = self._call_source(
            "CoinGecko", lambda: self.crypto_prices.leg_closes(leg, since=now.date() - timedelta(days=lookback_days), now=now)
        )
        if closes.unavailable_reason or not closes.closes:
            raise IdeaValidationError(f"{leg.entity.label}: {closes.unavailable_reason or 'no daily closes'}")
        return [ResearchObjectReturnPoint(timestamp=close.session.isoformat(), value=close.price) for close in closes.closes]

    @staticmethod
    def _provenance(composition: Any, now: datetime) -> ProvenanceRecord:
        retrieved = getattr(composition, "retrieved_at", None) or now
        if getattr(retrieved, "tzinfo", None) is not None:
            retrieved = retrieved.replace(tzinfo=None)
        return ProvenanceRecord(
            source_provider=str(getattr(composition, "source_provider", None) or "research"),
            retrieved_at=retrieved,
            origin=str(getattr(composition, "origin", None) or "research_service.strategy_lab"),
            transformation_note=getattr(composition, "transformation_note", None),
        )


__all__ = ["IdeaAnalysisService", "RISK_ALPHA", "TEST_LOOKBACK_DAYS"]
