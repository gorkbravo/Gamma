"""Hypothetical forward tracking for ideas (Workstream 12, checkpoint I3a).

The canonical daily series of an idea is rebuilt from provider closes every
time it is read, so it has no holes when Gamma was closed:

* equities and ETFs come from research market data (Yahoo Finance, then IBKR
  when configured; the same read path as Strategy Lab and the ``equity_close``
  observable), crypto from CoinGecko daily closes;
* each tracking segment buys fixed quantities at the first close after its legs
  were frozen, with signed weights scaled to 100 % gross exposure, and is
  marked at every later close; nothing before the freeze is ever used;
* a session where a leg's market traded but the provider has no close is a
  gap, never an interpolation; a market that was closed while another leg's
  market traded carries its last close;
* net figures subtract the per-side cost of entering and of closing at the
  latest close (mark to liquidation), from the idea's cost model;
* return, drawdown, the benchmark comparison and costs are computed on this
  series only.

Nothing here can place, stage or route an order: the book is hypothetical and
labelled "Hypothetical, not executed" wherever it appears. Today's live P&L
from IBKR marks (the intraday layer) is a later slice (I3d) and never feeds
this series.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from src.models.handoff import HandoffEntity
from src.models.ideas import (
    DEFAULT_TRACKING_COST_BP,
    TRACKING_EXCHANGES,
    TRACKING_LABEL,
    Idea,
    IdeaCostModel,
    IdeaTracking,
    IdeaTrackedLeg,
    IdeaTrackingSegment,
    IdeaTrackingSnapshot,
    tracking_market,
    tracking_signature,
)
from src.models.provenance import ProvenanceRecord
from src.utils.time import now_utc

logger = logging.getLogger(__name__)

TRACKING_SOURCE_PROVIDER = "gamma_ideas"
TRACKING_ORIGIN = "idea_tracking.compute"
# Un cierre se da por definitivo 20 minutos después de la hora de cierre (subasta de cierre).
CLOSE_SETTLE = timedelta(minutes=20)
# CoinGecko fecha sus cierres diarios a las 00:00 UTC; se admite un pequeño margen.
CRYPTO_CLOSE_TOLERANCE = timedelta(minutes=5)
HISTORY_MARGIN_DAYS = 10
CRYPTO_HISTORY_MAX_DAYS = 365
# Un histórico que empieza más tarde que esto tras el inicio del segmento se avisa.
TRUNCATED_HISTORY_DAYS = 7
WARNINGS_MAX = 40
# Sesiones de mercado sin cierre del proveedor tras las que el registro se marca como detenido.
STALE_SESSIONS = 3
US_MARKET = ("America/New_York", 16, 0)
CRYPTO_ALIASES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}

METHODOLOGY = (
    "Hypothetical, not executed. Each segment buys fixed quantities at the first provider close after its legs "
    "were frozen, with signed weights scaled to 100% gross exposure, and is marked at every later close. Net "
    "figures subtract the per-side cost of entering and of closing at the latest close. Returns are in each "
    "instrument's own currency (no FX conversion). A session where a market traded but the provider has no "
    "close is a gap, never interpolated; a market closed while another leg's market traded keeps its last close. "
    "Segments chain: one exits at the same close the next one enters."
)

# Etiqueta, coste por lado y fundamento de cada clase, para la tabla de supuestos de la UI.
COST_CLASS_INFO: dict[str, dict[str, str]] = {
    "us_equity_liquid": {
        "label": "Liquid US equities and ETFs",
        "basis": "Commission ($0 at many US brokers, about 1-2 bp at IBKR Pro), SEC fee on sales and half a typical spread.",
    },
    "equity_other": {
        "label": "Other equities and ETFs",
        "basis": "Small caps, non-US listings, UCITS: about 5 bp commission plus a wider half spread. Buy-side stamp duty or FTT (20-50 bp) not included.",
    },
    "futures": {
        "label": "Futures",
        "basis": "Half a tick plus commission and exchange fees, as a share of notional; generous for index futures.",
    },
    "options": {
        "label": "Options",
        "basis": "Half the quoted bid-ask at the mark, from the chain; unavailable without a quote.",
    },
    "crypto_spot": {
        "label": "Spot crypto",
        "basis": "Entry-tier taker fee (0.50% at Coinbase Advanced EU/UK; higher at Kraken Pro and in the US) plus half the spread.",
    },
    "prediction_contract": {
        "label": "Prediction contracts",
        "basis": "Half the quoted spread plus the venue fee where the venue charges one, from the book.",
    },
    "non_tradable": {
        "label": "Not tradable",
        "basis": "Macro series and other observables are criteria, not legs; no cost.",
    },
}


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionClose:
    """One provider close: its session date, the instant it happened (naive UTC) and the price."""

    session: date
    close_at: datetime
    price: float


@dataclass(frozen=True)
class LegCloses:
    closes: tuple[SessionClose, ...] = ()
    provenance: ProvenanceRecord | None = None
    warnings: tuple[str, ...] = ()
    unavailable_reason: str | None = None

    @classmethod
    def unavailable(cls, reason: str, *, provenance: ProvenanceRecord | None = None, warnings: Sequence[str] = ()) -> "LegCloses":
        return cls(provenance=provenance, warnings=tuple(warnings), unavailable_reason=reason)


class TrackingPriceSource(Protocol):
    def leg_closes(self, leg: IdeaTrackedLeg, *, since: date, now: datetime) -> LegCloses: ...

    def benchmark_closes(self, symbol: str, *, since: date, now: datetime) -> LegCloses: ...


def _market_close_spec(market: str) -> tuple[str, int, int] | None:
    if market == "us":
        return US_MARKET
    for exchange, tz_name, hour, minute in TRACKING_EXCHANGES.values():
        if exchange == market:
            return tz_name, hour, minute
    return None


def market_close_at(market: str, session: date) -> datetime:
    """When ``session``'s close happened, in naive UTC.

    Crypto closes at the next UTC midnight. An ``unknown`` exchange is taken to
    close at the start of its own UTC day, so a session dated on or before the
    freeze day never counts as after it (conservative: never earlier knowledge).
    """
    midnight = datetime(session.year, session.month, session.day)
    if market == "crypto":
        return midnight + timedelta(days=1)
    spec = _market_close_spec(market)
    if spec is None:
        return midnight
    tz_name, hour, minute = spec
    local = datetime.combine(session, time(hour, minute), tzinfo=ZoneInfo(tz_name))
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def market_complete_at(market: str, session: date) -> datetime:
    """When ``session``'s close can be read as final."""
    if market == "crypto":
        return market_close_at(market, session)
    if _market_close_spec(market) is None:
        return datetime(session.year, session.month, session.day) + timedelta(days=1)
    return market_close_at(market, session) + CLOSE_SETTLE


def market_horizon(market: str, now: datetime) -> date:
    """The latest session date whose close is final at ``now``."""
    day = now.date() + timedelta(days=1)
    for _ in range(5):
        if market_complete_at(market, day) <= now:
            return day
        day -= timedelta(days=1)
    return day


def _session_date(value: Any) -> date | None:
    """A daily bar's own session date (the local date the provider gave, ignoring its zone)."""
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


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _naive_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def closes_from_series(series: Any, market: str) -> tuple[SessionClose, ...]:
    """Daily closes indexed by session date (a pandas Series or a mapping)."""
    rows: dict[date, SessionClose] = {}
    items = series.items() if hasattr(series, "items") else []
    for index, value in items:
        session = _session_date(index)
        price = _finite_positive(value)
        if session is None or price is None:
            continue
        rows[session] = SessionClose(session=session, close_at=market_close_at(market, session), price=price)
    return tuple(rows[key] for key in sorted(rows))


def closes_from_instants(points: Sequence[tuple[Any, Any]]) -> tuple[SessionClose, ...]:
    """Crypto daily closes from (instant, price) pairs; only points at a UTC midnight count.

    CoinGecko's daily history stamps each close at 00:00 UTC (the close of the
    previous UTC day) and appends the current price; that last point is not a
    close and is dropped.
    """
    rows: dict[date, SessionClose] = {}
    for instant, value in points:
        moment = _naive_utc(instant)
        price = _finite_positive(value)
        if moment is None or price is None:
            continue
        midnight = datetime(moment.year, moment.month, moment.day)
        if moment - midnight > CRYPTO_CLOSE_TOLERANCE:
            continue
        session = (midnight - timedelta(days=1)).date()
        rows[session] = SessionClose(session=session, close_at=midnight, price=price)
    return tuple(rows[key] for key in sorted(rows))


class ProviderTrackingPrices:
    """Reads closes through the services the runtime already composes (read-only)."""

    def __init__(self, *, research_provider: Any = None, crypto_service: Any = None) -> None:
        self.research_provider = research_provider
        self.crypto_service = crypto_service

    def leg_closes(self, leg: IdeaTrackedLeg, *, since: date, now: datetime) -> LegCloses:
        entity_type = str(leg.entity.entity_type).strip().lower()
        if entity_type in {"equity", "etf"}:
            return self._equity(str(leg.entity.normalized_id).strip().upper(), leg.market, since=since, now=now)
        if entity_type == "crypto":
            return self._crypto(_coingecko_id(leg.entity), since=since, now=now)
        return LegCloses.unavailable(f"{entity_type.replace('_', ' ')} legs have no price source in this build.")

    def benchmark_closes(self, symbol: str, *, since: date, now: datetime) -> LegCloses:
        market = tracking_market(HandoffEntity(entity_type="etf", label=symbol, normalized_id=symbol))
        return self._equity(symbol, market, since=since, now=now)

    def _equity(self, symbol: str, market: str, *, since: date, now: datetime) -> LegCloses:
        if self.research_provider is None:
            return LegCloses.unavailable("Research market data is not running.")
        from src.models.instruments import InstrumentReference

        lookback = max(30, (now.date() - since).days + HISTORY_MARGIN_DAYS)
        result = self.research_provider.load_instrument_history_result(
            InstrumentReference(symbol=symbol), lookback, max_age_seconds=1800
        )
        warnings = [str(item) for item in (result.warnings or []) if str(item or "").strip()]
        provenance = ProvenanceRecord(
            source_provider=str(result.source_label or result.source_provider or "unknown"),
            retrieved_at=_naive_utc(result.retrieved_at) or now,
            origin=str(result.origin or "research_market_data.history"),
            transformation_note=result.transformation_note,
        )
        series = result.series
        if series is None or len(series) == 0:
            reason = warnings[0] if warnings else f"No configured history provider returned closes for {symbol}."
            return LegCloses.unavailable(reason, provenance=provenance, warnings=warnings[1:])
        label = str(getattr(result.freshness_label, "value", result.freshness_label) or "")
        if label == "mocked":
            warnings.insert(0, f"{symbol}: demo sample history, not market data.")
        closes = closes_from_series(series, market)
        if not closes:
            return LegCloses.unavailable(f"The closes for {symbol} had no usable values.", provenance=provenance)
        return LegCloses(closes=closes, provenance=provenance, warnings=tuple(warnings))

    def _crypto(self, token_id: str, *, since: date, now: datetime) -> LegCloses:
        if self.crypto_service is None:
            return LegCloses.unavailable("The crypto service is not running.")
        needed = (now.date() - since).days + HISTORY_MARGIN_DAYS
        # Más de 90 días devuelve cierres diarios; menos, puntos horarios.
        days = min(CRYPTO_HISTORY_MAX_DAYS, max(91, needed))
        rows = self.crypto_service.get_price_history(token_id, days=days) or []
        if not rows:
            return LegCloses.unavailable(f"CoinGecko returned no prices for {token_id}; use its CoinGecko id, e.g. bitcoin.")
        latest = rows[-1]
        provenance = ProvenanceRecord(
            source_provider=str(getattr(latest, "source_provider", "") or "coingecko"),
            retrieved_at=_naive_utc(getattr(latest, "retrieved_at", None)) or now,
            origin=str(getattr(latest, "origin", "") or "crypto_service.get_price_history"),
            transformation_note="Daily closes stamped at 00:00 UTC; the current price is not a close and is dropped.",
        )
        closes = closes_from_instants([(row.timestamp, row.price) for row in rows])
        warnings: list[str] = []
        if needed > CRYPTO_HISTORY_MAX_DAYS:
            warnings.append(f"CoinGecko serves {CRYPTO_HISTORY_MAX_DAYS} days of daily closes; older sessions of {token_id} are missing.")
        if not closes:
            return LegCloses.unavailable(f"CoinGecko returned no daily closes for {token_id}.", provenance=provenance)
        return LegCloses(closes=closes, provenance=provenance, warnings=tuple(warnings))


def _coingecko_id(entity: HandoffEntity) -> str:
    metadata = entity.metadata or {}
    explicit = metadata.get("coingecko_id") or metadata.get("token_id") or entity.native_id
    if explicit:
        return str(explicit).strip().lower()
    symbol = str(entity.normalized_id).strip().upper()
    return CRYPTO_ALIASES.get(symbol, symbol.lower())


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentPoint:
    session: date
    gross_return: float | None
    net_return: float | None
    benchmark_return: float | None
    gap: bool = False
    missing: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()


@dataclass(frozen=True)
class SegmentLegView:
    key: str
    label: str
    entity_type: str
    normalized_id: str
    stated_weight: float | None
    weight: float | None
    weight_source: str
    asset_class: str
    detected_class: str
    cost_bp: float | None
    market: str
    entry_price: float | None = None
    last_price: float | None = None


@dataclass(frozen=True)
class SegmentResult:
    segment: IdeaTrackingSegment
    status: str  # untracked | unavailable | waiting | never_entered | tracking | exiting | closed
    reason: str | None
    legs: tuple[SegmentLegView, ...]
    points: tuple[SegmentPoint, ...] = ()
    entry_session: date | None = None
    exit_session: date | None = None
    entry_cost: float | None = None
    exit_cost: float | None = None
    gross_return: float | None = None
    net_return: float | None = None
    benchmark_return: float | None = None
    max_drawdown: float | None = None
    sessions: int = 0
    gaps: int = 0
    last_session: date | None = None

    @property
    def priced(self) -> bool:
        return self.status in {"tracking", "exiting", "closed"}

    def to_dict(self) -> dict[str, Any]:
        segment = self.segment
        excess = None
        if self.net_return is not None and self.benchmark_return is not None:
            excess = self.net_return - self.benchmark_return
        return {
            "segment_id": segment.segment_id,
            "number": segment.number,
            "status": self.status,
            "reason": self.reason,
            "started_at": segment.started_at.isoformat(),
            "start_reason": segment.start_reason,
            "start_note": segment.start_note,
            "ended_at": segment.ended_at.isoformat() if segment.ended_at else None,
            "end_reason": segment.end_reason,
            "stance": segment.stance,
            "entry_session": self.entry_session.isoformat() if self.entry_session else None,
            "exit_session": self.exit_session.isoformat() if self.exit_session else None,
            "last_session": self.last_session.isoformat() if self.last_session else None,
            "sessions": self.sessions,
            "gaps": self.gaps,
            "gross_return": self.gross_return,
            "net_return": self.net_return,
            "entry_cost": self.entry_cost,
            "exit_cost": self.exit_cost,
            "cost": None if self.entry_cost is None else self.entry_cost + (self.exit_cost or 0.0),
            "benchmark_return": self.benchmark_return,
            "excess_return": excess,
            "max_drawdown": self.max_drawdown,
            "legs": [
                {
                    "key": leg.key,
                    "label": leg.label,
                    "entity_type": leg.entity_type,
                    "normalized_id": leg.normalized_id,
                    "stated_weight": leg.stated_weight,
                    "weight": leg.weight,
                    "weight_source": leg.weight_source,
                    "asset_class": leg.asset_class,
                    "detected_class": leg.detected_class,
                    "cost_bp": leg.cost_bp,
                    "market": leg.market,
                    "entry_price": leg.entry_price,
                    "last_price": leg.last_price,
                }
                for leg in self.legs
            ],
        }


@dataclass(frozen=True)
class TrackingPoint:
    """One session of the chained record across segments (a gap has no values)."""

    session: date
    segment: int
    net_return: float | None
    gross_return: float | None
    benchmark_return: float | None
    drawdown: float | None
    gap: bool = False
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.isoformat(),
            "segment": self.segment,
            "net_return": self.net_return,
            "gross_return": self.gross_return,
            "benchmark_return": self.benchmark_return,
            "drawdown": self.drawdown,
            "gap": self.gap,
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class TrackingComputation:
    idea_id: str
    status: str
    status_reason: str | None
    computed_at: datetime
    benchmark: str
    benchmark_available: bool
    benchmark_reason: str | None
    cost_model: IdeaCostModel
    segments: tuple[SegmentResult, ...] = ()
    points: tuple[TrackingPoint, ...] = ()
    net_return: float | None = None
    gross_return: float | None = None
    benchmark_return: float | None = None
    max_drawdown: float | None = None
    sessions: int = 0
    gaps: int = 0
    partial: bool = False
    stale_since: date | None = None
    first_session: date | None = None
    as_of: date | None = None
    warnings: tuple[str, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()

    @property
    def final(self) -> bool:
        """No open segment and no exit still waiting for its close: the figures will not change."""
        return bool(self.segments) and all(
            not result.segment.is_open and result.status not in {"exiting", "waiting"} for result in self.segments
        )

    def snapshot(self) -> IdeaTrackingSnapshot:
        return IdeaTrackingSnapshot(
            status=self.status,
            computed_at=self.computed_at,
            as_of=self.as_of,
            net_return=self.net_return,
            gross_return=self.gross_return,
            benchmark_return=self.benchmark_return,
            benchmark=self.benchmark,
            sessions=self.sessions,
            gaps=self.gaps,
            partial=self.partial,
            final=self.final,
            stale_since=self.stale_since,
        )

    def to_dict(self) -> dict[str, Any]:
        excess = None
        if self.net_return is not None and self.benchmark_return is not None:
            excess = self.net_return - self.benchmark_return
        cost_drag = None
        if self.net_return is not None and self.gross_return is not None:
            cost_drag = self.gross_return - self.net_return
        return {
            "idea_id": self.idea_id,
            "label": TRACKING_LABEL,
            "status": self.status,
            "status_reason": self.status_reason,
            "methodology": METHODOLOGY,
            "summary": {
                "net_return": self.net_return,
                "gross_return": self.gross_return,
                "cost_drag": cost_drag,
                "benchmark_return": self.benchmark_return,
                "excess_return": excess,
                "max_drawdown": self.max_drawdown,
                "sessions": self.sessions,
                "gaps": self.gaps,
                "partial": self.partial,
                "final": self.final,
                "stale_since": self.stale_since.isoformat() if self.stale_since else None,
                "first_session": self.first_session.isoformat() if self.first_session else None,
                "as_of": self.as_of.isoformat() if self.as_of else None,
            },
            "benchmark": {
                "symbol": self.benchmark,
                "available": self.benchmark_available,
                "reason": self.benchmark_reason,
            },
            "cost_model": cost_model_view(self.cost_model),
            "segments": [segment.to_dict() for segment in self.segments],
            "points": [point.to_dict() for point in self.points],
            "warnings": list(self.warnings),
            "provenance": [dict(item) for item in self.provenance],
            "computed_at": self.computed_at.isoformat(),
            "source_provider": TRACKING_SOURCE_PROVIDER,
            "origin": TRACKING_ORIGIN,
            "transformation_note": "Rebuilt from provider daily closes on every read; nothing before a segment's freeze is used.",
        }


def cost_model_view(cost_model: IdeaCostModel) -> dict[str, Any]:
    classes = []
    for asset_class, info in COST_CLASS_INFO.items():
        bp = cost_model.bp_for(asset_class)
        default = DEFAULT_TRACKING_COST_BP.get(asset_class)
        classes.append(
            {
                "asset_class": asset_class,
                "label": info["label"],
                "basis": info["basis"],
                "per_side_bp": bp,
                "default_bp": default,
                "editable": asset_class in cost_model.per_side_bp,
                "source": "stated" if asset_class in cost_model.per_side_bp else ("none" if asset_class == "non_tradable" else "quote"),
                "edited": default is not None and bp is not None and bp != default,
            }
        )
    return {
        "classes": classes,
        "leg_classes": dict(cost_model.leg_classes),
        "updated_at": cost_model.updated_at.isoformat() if cost_model.updated_at else None,
        "edited": cost_model.edited,
    }


# ---------------------------------------------------------------------------
# Computation (pure: prices and the clock are inputs)
# ---------------------------------------------------------------------------


def compute_tracking(
    idea_id: str,
    tracking: IdeaTracking | None,
    prices: Mapping[str, LegCloses],
    benchmark: LegCloses | None,
    *,
    now: datetime,
) -> TrackingComputation:
    """Rebuild the canonical daily series of every segment and chain them."""
    if tracking is None or not tracking.segments:
        return TrackingComputation(
            idea_id=idea_id,
            status="not_started",
            status_reason="Tracking starts when an idea with legs is activated.",
            computed_at=now,
            benchmark=(tracking.benchmark if tracking else "SPY"),
            benchmark_available=False,
            benchmark_reason=None,
            cost_model=tracking.cost_model if tracking else IdeaCostModel(),
        )
    warnings: list[str] = []
    bench_ok = benchmark is not None and benchmark.unavailable_reason is None and bool(benchmark.closes)
    bench_reason = None
    if not bench_ok:
        bench_reason = (benchmark.unavailable_reason if benchmark else None) or f"No closes for {tracking.benchmark}."
    bench_market = tracking_market(HandoffEntity(entity_type="etf", label=tracking.benchmark, normalized_id=tracking.benchmark))
    results: list[SegmentResult] = []
    held: SegmentResult | None = None
    for segment in tracking.segments:
        # Un libro se compra al cierre en que se vende el anterior: nunca hay dos libros a la vez.
        not_before = held.exit_session if held is not None and held.status == "closed" else None
        blocked_by = held.segment.number if held is not None and held.status == "exiting" else None
        result = _compute_segment(
            segment,
            tracking.cost_model,
            prices,
            benchmark if bench_ok else None,
            bench_market,
            now=now,
            warnings=warnings,
            not_before=not_before,
            blocked_by=blocked_by,
        )
        results.append(result)
        if result.priced:
            held = result
    stale_since = _stale_since(results, prices, now=now, warnings=warnings)
    points, chained = _chain(results)
    priced_points = [point for point in points if not point.gap]
    # Parcial: hubo un periodo con libro que no se pudo valorar. Un segmento que nunca entró no tuvo libro.
    partial = any(result.status in {"untracked", "unavailable"} for result in results[:-1]) or (
        results[-1].status in {"untracked", "unavailable"} and any(result.priced for result in results[:-1])
    )
    status, reason = _overall_status(results)
    if stale_since is not None and status in {"tracking", "waiting"}:
        reason = f"The provider has no close since {stale_since.isoformat()}; the record stops there and is not filled in."
    # El motivo de un segmento sin libro va en su fila (y en el estado), no repetido como aviso.
    provenance = _provenance_rows(tracking, prices, benchmark)
    for data in prices.values():
        warnings.extend(data.warnings)
    if benchmark is not None:
        warnings.extend(benchmark.warnings)
    if bench_reason and any(result.priced for result in results):
        warnings.append(f"Benchmark {tracking.benchmark} unavailable: {bench_reason}")
    deduped = list(dict.fromkeys(item for item in warnings if item))
    if len(deduped) > WARNINGS_MAX:
        extra = len(deduped) - WARNINGS_MAX
        deduped = deduped[:WARNINGS_MAX] + [f"…and {extra} more warnings."]
    return TrackingComputation(
        idea_id=idea_id,
        status=status,
        status_reason=reason,
        computed_at=now,
        benchmark=tracking.benchmark,
        benchmark_available=bench_ok,
        benchmark_reason=bench_reason,
        cost_model=tracking.cost_model,
        segments=tuple(results),
        points=tuple(points),
        net_return=chained["net"],
        gross_return=chained["gross"],
        benchmark_return=chained["benchmark"],
        max_drawdown=chained["max_drawdown"],
        sessions=len(priced_points),
        gaps=sum(1 for point in points if point.gap),
        partial=partial,
        stale_since=stale_since,
        first_session=next((result.entry_session for result in results if result.entry_session), None),
        as_of=priced_points[-1].session if priced_points else None,
        warnings=tuple(deduped),
        provenance=tuple(provenance),
    )


def _leg_views(segment: IdeaTrackingSegment, cost_model: IdeaCostModel) -> tuple[SegmentLegView, ...]:
    views = []
    for leg in segment.legs:
        asset_class = cost_model.class_for(leg)
        views.append(
            SegmentLegView(
                key=leg.key,
                label=leg.entity.label,
                entity_type=leg.entity.entity_type,
                normalized_id=leg.entity.normalized_id,
                stated_weight=leg.stated_weight,
                weight=leg.weight,
                weight_source=leg.weight_source,
                asset_class=asset_class,
                detected_class=leg.asset_class,
                cost_bp=cost_model.bp_for(asset_class),
                market=leg.market,
            )
        )
    return tuple(views)


def _compute_segment(
    segment: IdeaTrackingSegment,
    cost_model: IdeaCostModel,
    prices: Mapping[str, LegCloses],
    benchmark: LegCloses | None,
    bench_market: str,
    *,
    now: datetime,
    warnings: list[str],
    not_before: date | None = None,
    blocked_by: int | None = None,
) -> SegmentResult:
    views = _leg_views(segment, cost_model)
    if segment.untracked_reason:
        return SegmentResult(segment=segment, status="untracked", reason=segment.untracked_reason, legs=views)
    legs = segment.legs
    problems = []
    for leg in legs:
        data = prices.get(leg.key)
        if data is None or data.unavailable_reason or not data.closes:
            problems.append(f"{leg.entity.label}: {(data.unavailable_reason if data else None) or 'no closes'}")
    if problems:
        return SegmentResult(segment=segment, status="unavailable", reason="; ".join(problems), legs=views)
    costs = [cost_model.bp_for(view.asset_class) for view in views]
    if any(value is None for value in costs):
        return SegmentResult(
            segment=segment,
            status="unavailable",
            reason="A leg's cost class takes its cost from a live quote, which daily tracking does not read.",
            legs=views,
        )
    if blocked_by is not None:
        if segment.ended_at is not None:
            return SegmentResult(
                segment=segment,
                status="never_entered",
                reason=f"The legs changed again before segment {blocked_by} exited; this one held nothing.",
                legs=views,
            )
        return SegmentResult(
            segment=segment,
            status="waiting",
            reason=f"Enters at the close where segment {blocked_by} exits; that close is not in yet.",
            legs=views,
        )
    horizon = min(market_horizon(leg.market, now) for leg in legs)
    by_leg: list[dict[date, SessionClose]] = []
    for leg in legs:
        rows = {close.session: close for close in prices[leg.key].closes if close.session <= horizon}
        by_leg.append(rows)
        first = min(rows) if rows else None
        if first is not None and first > segment.started_at.date() + timedelta(days=TRUNCATED_HISTORY_DAYS):
            warnings.append(
                f"{leg.entity.label}: the provider history starts on {first.isoformat()}, after segment "
                f"{segment.number} began; its entry may be later than the true next close."
            )
    bench_rows = {close.session: close for close in benchmark.closes if close.session <= horizon} if benchmark else {}
    start_day = segment.started_at.date() - timedelta(days=1)
    calendars: dict[str, set[date]] = {}
    for leg, rows in zip(legs, by_leg):
        calendar = calendars.setdefault(leg.market, set())
        if leg.market == "crypto":
            day = start_day
            while day <= horizon:
                calendar.add(day)
                day += timedelta(days=1)
        else:
            calendar.update(day for day in rows if day >= start_day)
    if bench_market in calendars and bench_market != "crypto":
        calendars[bench_market].update(day for day in bench_rows if day >= start_day)
    candidates = sorted(set().union(*calendars.values()))

    def all_after(day: date, instant: datetime) -> bool:
        return all(day in rows and rows[day].close_at > instant for rows in by_leg)

    entry = next(
        (day for day in candidates if (not_before is None or day >= not_before) and all_after(day, segment.started_at)),
        None,
    )
    pre_entry_missing = [
        (day, [leg.entity.label for leg, rows in zip(legs, by_leg) if day not in rows and day in calendars[leg.market]])
        for day in candidates
        if (entry is None or day < entry)
        and any(rows.get(day) and rows[day].close_at > segment.started_at for rows in by_leg)
    ]
    for day, labels in pre_entry_missing:
        if labels:
            warnings.append(
                f"Segment {segment.number}: no close for {', '.join(labels)} on {day.isoformat()}; the entry waited for the next session with every price."
            )
    if entry is None:
        if segment.ended_at is not None:
            return SegmentResult(
                segment=segment,
                status="never_entered",
                reason="The legs changed again before this segment's first close; it held nothing.",
                legs=views,
            )
        return SegmentResult(
            segment=segment,
            status="waiting",
            reason=(
                f"Waiting for the first close after {segment.started_at.strftime('%Y-%m-%d %H:%M')} UTC "
                "with a price for every leg."
            ),
            legs=views,
        )
    exit_day = None
    if segment.ended_at is not None:
        exit_day = next((day for day in candidates if day >= entry and all_after(day, segment.ended_at)), None)
        if exit_day == entry:
            return SegmentResult(
                segment=segment,
                status="never_entered",
                reason="The legs changed again before this segment's first close; it held nothing.",
                legs=views,
                entry_session=entry,
            )
    last_day = exit_day or candidates[-1]
    marks = [day for day in candidates if entry <= day <= last_day]
    weights = [float(leg.weight or 0.0) for leg in legs]
    bps = [float(value or 0.0) / 10_000.0 for value in costs]
    entry_prices = [rows[entry].price for rows in by_leg]
    entry_cost = sum(abs(weight) * bp for weight, bp in zip(weights, bps))
    bench_entry = _bench_mark(bench_rows, entry, calendars.get(bench_market)) if benchmark else None
    points: list[SegmentPoint] = []
    last_prices: list[float] = list(entry_prices)
    peak = 1.0
    max_dd = 0.0
    last_exit_cost: float | None = None
    for day in marks:
        missing: list[str] = []
        carried: list[str] = []
        current: list[float] = []
        for index, (leg, rows) in enumerate(zip(legs, by_leg)):
            close = rows.get(day)
            if close is not None:
                last_prices[index] = close.price
                current.append(close.price)
            elif day not in calendars[leg.market]:
                carried.append(leg.entity.label)
                current.append(last_prices[index])
            else:
                missing.append(leg.entity.label)
                current.append(float("nan"))
        bench_value = None
        if bench_entry is not None:
            mark = _bench_mark(bench_rows, day, calendars.get(bench_market))
            bench_value = None if mark is None else mark / bench_entry - 1.0
        if missing:
            warnings.append(
                f"Segment {segment.number}: no close for {', '.join(missing)} on {day.isoformat()}; the session is a gap, not interpolated."
            )
            points.append(SegmentPoint(session=day, gross_return=None, net_return=None, benchmark_return=bench_value, gap=True, missing=tuple(missing), carried=tuple(carried)))
            continue
        relatives = [price / start for price, start in zip(current, entry_prices)]
        gross = sum(weight * (relative - 1.0) for weight, relative in zip(weights, relatives))
        exit_cost = sum(abs(weight) * relative * bp for weight, relative, bp in zip(weights, relatives, bps))
        net = gross - entry_cost - exit_cost
        last_exit_cost = exit_cost
        value = 1.0 + net
        peak = max(peak, value)
        max_dd = min(max_dd, value / peak - 1.0 if peak > 0 else 0.0)
        points.append(SegmentPoint(session=day, gross_return=gross, net_return=net, benchmark_return=bench_value, carried=tuple(carried)))
    priced = [point for point in points if not point.gap]
    final = priced[-1] if priced else None
    status = "tracking" if segment.ended_at is None else ("closed" if exit_day is not None else "exiting")
    reason = None
    if status == "exiting":
        reason = "The legs changed; this segment exits at the next close after the change."
    views_with_prices = tuple(
        SegmentLegView(**{**view.__dict__, "entry_price": entry_prices[index], "last_price": last_prices[index]})
        for index, view in enumerate(views)
    )
    return SegmentResult(
        segment=segment,
        status=status,
        reason=reason,
        legs=views_with_prices,
        points=tuple(points),
        entry_session=entry,
        exit_session=exit_day,
        entry_cost=entry_cost,
        exit_cost=last_exit_cost,
        gross_return=final.gross_return if final else None,
        net_return=final.net_return if final else None,
        benchmark_return=final.benchmark_return if final else None,
        max_drawdown=max_dd if priced else None,
        sessions=len(priced),
        gaps=len(points) - len(priced),
        last_session=final.session if final else None,
    )


def _sessions_behind(market: str, latest: date, horizon: date) -> int:
    """Sessions of ``market`` after ``latest`` up to ``horizon`` (weekdays; every day for crypto)."""
    count = 0
    day = latest + timedelta(days=1)
    while day <= horizon:
        if market == "crypto" or day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def _stale_since(
    results: Sequence[SegmentResult], prices: Mapping[str, LegCloses], *, now: datetime, warnings: list[str]
) -> date | None:
    """The oldest last close among legs that still need prices, once it lags the market.

    Only open, waiting and exiting segments need new closes. A provider that
    stopped answering leaves the record where it was, never filled in; this
    names it instead of letting the record look current.
    """
    oldest: date | None = None
    seen: set[str] = set()
    for result in results:
        if result.status not in {"tracking", "waiting", "exiting"}:
            continue
        for leg in result.segment.legs:
            if leg.key in seen:
                continue
            seen.add(leg.key)
            data = prices.get(leg.key)
            if data is None or not data.closes:
                continue
            latest = max(close.session for close in data.closes)
            if _sessions_behind(leg.market, latest, market_horizon(leg.market, now)) > STALE_SESSIONS:
                warnings.append(
                    f"No close from the provider for {leg.entity.label} since {latest.isoformat()}; "
                    "the record stops there and is not filled in."
                )
                oldest = latest if oldest is None else min(oldest, latest)
    return oldest


def _bench_mark(rows: Mapping[date, SessionClose], day: date, calendar: set[date] | None) -> float | None:
    """The benchmark close on ``day``; its last close when its market did not trade that day."""
    close = rows.get(day)
    if close is not None:
        return close.price
    if calendar is not None and day in calendar:
        return None
    earlier = [key for key in rows if key <= day]
    return rows[max(earlier)].price if earlier else None


def _chain(results: Sequence[SegmentResult]) -> tuple[list[TrackingPoint], dict[str, float | None]]:
    """Chain segment returns: one exits at the close where the next enters."""
    by_session: dict[date, TrackingPoint] = {}
    net_factor = 1.0
    gross_factor = 1.0
    bench_factor = 1.0
    bench_known = True
    last_net = last_gross = last_bench = None
    any_points = False
    for result in results:
        if not result.priced:
            continue
        final_net = final_gross = final_bench = None
        for point in result.points:
            if point.gap:
                by_session[point.session] = TrackingPoint(
                    session=point.session,
                    segment=result.segment.number,
                    net_return=None,
                    gross_return=None,
                    benchmark_return=None,
                    drawdown=None,
                    gap=True,
                    missing=point.missing,
                )
                continue
            net = net_factor * (1.0 + float(point.net_return or 0.0)) - 1.0
            gross = gross_factor * (1.0 + float(point.gross_return or 0.0)) - 1.0
            bench = None
            if point.benchmark_return is not None and bench_known:
                bench = bench_factor * (1.0 + point.benchmark_return) - 1.0
            by_session[point.session] = TrackingPoint(
                session=point.session,
                segment=result.segment.number,
                net_return=net,
                gross_return=gross,
                benchmark_return=bench,
                drawdown=None,
            )
            final_net, final_gross, final_bench = point.net_return, point.gross_return, point.benchmark_return
            any_points = True
            last_net, last_gross, last_bench = net, gross, bench
        if final_net is not None:
            net_factor *= 1.0 + float(final_net)
            gross_factor *= 1.0 + float(final_gross or 0.0)
            if final_bench is None:
                bench_known = False
            else:
                bench_factor *= 1.0 + final_bench
    ordered = [by_session[key] for key in sorted(by_session)]
    peak = 1.0
    max_dd: float | None = 0.0 if any_points else None
    chained: list[TrackingPoint] = []
    for point in ordered:
        if point.gap or point.net_return is None:
            chained.append(point)
            continue
        value = 1.0 + point.net_return
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak > 0 else 0.0
        max_dd = min(max_dd or 0.0, drawdown)
        chained.append(TrackingPoint(**{**point.__dict__, "drawdown": drawdown}))
    return chained, {
        "net": last_net,
        "gross": last_gross,
        "benchmark": last_bench,
        "max_drawdown": max_dd,
    }


def _overall_status(results: Sequence[SegmentResult]) -> tuple[str, str | None]:
    last = results[-1]
    if last.segment.is_open:
        if last.status == "tracking":
            return "tracking", None
        if last.status == "waiting":
            return "waiting", last.reason
        return "unavailable", last.reason
    if any(result.priced for result in results):
        reasons = {"archived": "The idea is archived", "legs_removed": "The legs were removed", "closed": "The idea is closed"}
        text = reasons.get(last.segment.end_reason or "", "No segment is open")
        return "stopped", f"{text}; tracking stopped at the exit close."
    return "stopped", "No segment is open and none was priced."


def _provenance_rows(
    tracking: IdeaTracking, prices: Mapping[str, LegCloses], benchmark: LegCloses | None
) -> list[dict[str, Any]]:
    labels = {leg.key: leg.entity.label for segment in tracking.segments for leg in segment.legs}
    rows = []
    for key, data in prices.items():
        record = data.provenance
        rows.append(
            {
                "key": key,
                "label": labels.get(key, key),
                "role": "leg",
                "source_provider": record.source_provider if record else None,
                "retrieved_at": record.retrieved_at.isoformat() if record else None,
                "origin": record.origin if record else None,
                "transformation_note": record.transformation_note if record else None,
                "available": data.unavailable_reason is None,
            }
        )
    if benchmark is not None:
        record = benchmark.provenance
        rows.append(
            {
                "key": f"benchmark:{tracking.benchmark}",
                "label": tracking.benchmark,
                "role": "benchmark",
                "source_provider": record.source_provider if record else None,
                "retrieved_at": record.retrieved_at.isoformat() if record else None,
                "origin": record.origin if record else None,
                "transformation_note": record.transformation_note if record else None,
                "available": benchmark.unavailable_reason is None,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IdeaTrackingService:
    """Rebuilds an idea's canonical series and keeps the Board headline current."""

    def __init__(self, idea_service: Any, prices: TrackingPriceSource, *, clock: Callable[[], datetime] = now_utc) -> None:
        self.idea_service = idea_service
        self.prices = prices
        self._clock = clock

    def compute(self, idea_id: str, *, persist: bool = True) -> TrackingComputation:
        return self.compute_for(self.idea_service.get_idea(idea_id), persist=persist)

    def compute_for(self, idea: Idea, *, persist: bool = True) -> TrackingComputation:
        now = self._clock()
        tracking = idea.tracking
        if tracking is None or not tracking.segments:
            return compute_tracking(idea.idea_id, tracking, {}, None, now=now)
        since = min(segment.started_at for segment in tracking.segments).date() - timedelta(days=7)
        prices: dict[str, LegCloses] = {}
        for segment in tracking.segments:
            if segment.untracked_reason:
                continue
            for leg in segment.legs:
                if leg.key in prices:
                    continue
                try:
                    prices[leg.key] = self.prices.leg_closes(leg, since=since, now=now)
                except Exception as exc:  # noqa: BLE001 - un fallo del proveedor es un estado, no un error
                    prices[leg.key] = LegCloses.unavailable(f"The price source failed: {exc}")
        benchmark: LegCloses | None
        try:
            benchmark = self.prices.benchmark_closes(tracking.benchmark, since=since, now=now)
        except Exception as exc:  # noqa: BLE001
            benchmark = LegCloses.unavailable(f"The benchmark source failed: {exc}")
        result = compute_tracking(idea.idea_id, tracking, prices, benchmark, now=now)
        if persist:
            try:
                self.idea_service.store_tracking_snapshot(idea.idea_id, result.snapshot(), basis=tracking_signature(tracking))
            except Exception:  # noqa: BLE001 - la idea pudo borrarse durante la lectura
                logger.info("Could not store the tracking snapshot of idea %s", idea.idea_id, exc_info=True)
        return result

    def refresh_all(self) -> int:
        """Recompute tracked ideas (start-up and daily-close passes).

        Active ideas always; a closed or archived idea until its record is
        final, so the exit close after a close or an archive is picked up.
        """
        refreshed = 0
        for summary in self.idea_service.store.list_summaries():
            if not summary.tracking:
                continue
            snapshot = summary.tracking.get("snapshot") or {}
            if summary.status != "active" and snapshot.get("final"):
                continue
            try:
                self.compute(summary.idea_id)
                refreshed += 1
            except Exception:  # noqa: BLE001 - una idea mala no detiene la pasada
                logger.exception("Tracking refresh failed for idea %s", summary.idea_id)
        return refreshed


__all__ = [
    "COST_CLASS_INFO",
    "LegCloses",
    "METHODOLOGY",
    "IdeaTrackingService",
    "ProviderTrackingPrices",
    "SessionClose",
    "TrackingComputation",
    "closes_from_instants",
    "closes_from_series",
    "compute_tracking",
    "cost_model_view",
    "market_close_at",
    "market_horizon",
]
