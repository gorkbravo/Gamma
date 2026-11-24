"""The intraday layer of an idea's hypothetical record (Workstream 12, checkpoint I3d).

While Gamma runs and Trader Workstation is connected, the evaluation scheduler
asks this service to record one IBKR mark per leg of every open tracking
segment: every five minutes while a leg's market is open, once an hour while
every market of the book is closed (those marks are labelled frozen). Marks
are stored locally per idea and per UTC session day (``IdeaIntradayStore``).

The layer feeds three things only: today's live P&L, the intraday drawdown and
intraday criterion triggers (``equity_close`` and ``crypto_price`` read the
latest fresh mark). It never replaces or rewrites the canonical daily series:
``compute_tracking`` reads provider closes and nothing from here, and the
marks are valued against that series' entry prices and latest close.

Absence stays visible: a stretch where Gamma ran but TWS was disconnected or
IBKR did not answer is stored as a status row; a stretch with no row at all is
time Gamma was not running. Both are shown as explicit gaps, never filled in.
Read-only throughout: no orders, no account data.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.application.idea_tracking import (
    LegCloses,
    SegmentResult,
    TrackingComputation,
    _coingecko_id,
    market_close_at,
)
from src.models.ideas import TRACKING_LABEL, Idea, IdeaTrackedLeg
from src.services.ibkr_marks import LegMark, MarkBatch, MarkRequest, ibkr_crypto_symbol
from src.services.idea_intraday_store import IdeaIntradayStore
from src.utils.time import now_utc

logger = logging.getLogger(__name__)

# Cadencia: la de la pasada intradía de criterios mientras algún mercado del libro está abierto.
INTRADAY_PASS_SECONDS = 300
# Con todos los mercados del libro cerrados basta una marca congelada por hora.
CLOSED_MARK_SECONDS = 3600
# Un intervalo sin marca mayor que 2,5 veces la cadencia prometida es un hueco.
GAP_FACTOR = 2.5
# Un criterio intradía solo usa una marca viva o diferida de menos de 12,5 minutos.
FRESH_MARK_SECONDS = int(INTRADAY_PASS_SECONDS * GAP_FACTOR)
# Presupuesto IBKR por pasada: instrumentos distintos, deduplicados entre ideas.
MARK_INSTRUMENTS_MAX = 24
QUALITY_ORDER = {"live": 0, "delayed": 1, "frozen": 2, "delayed_frozen": 3}
TRIGGER_QUALITIES = ("live", "delayed")
_NEW_YORK = ZoneInfo("America/New_York")
INTRADAY_SOURCE = "IBKR/TWS market-data snapshots"
INTRADAY_ORIGIN = "ibkr.reqMktData(snapshot)"

INTRADAY_METHODOLOGY = (
    "Hypothetical, not executed. While Trader Workstation is connected and Gamma runs, Gamma records one IBKR "
    "mark per leg of the open segment every 5 minutes while a leg's market is open (hourly, labelled frozen, "
    "while every market is closed). Each mark values the segment's book against its entry prices from the "
    "canonical daily series, with the same costs; today's return is measured from the latest daily close "
    "before the mark's day. Delayed and frozen quotes are labelled. Stretches where Gamma or TWS was closed "
    "are gaps, never filled in. The intraday layer never changes the canonical daily series."
)


# ---------------------------------------------------------------------------
# Mercados
# ---------------------------------------------------------------------------


def leg_market_open(market: str, at: datetime) -> bool | None:
    """Whether a leg's market is in its regular session at ``at`` (naive UTC).

    Crypto always trades. US listings trade 09:30-16:00 New York time on
    weekdays (no holiday calendar). ``None``: Gamma does not know the hours.
    """
    if market == "crypto":
        return True
    if market == "us":
        local = at.replace(tzinfo=timezone.utc).astimezone(_NEW_YORK)
        if local.weekday() >= 5:
            return False
        return time(9, 30) <= local.time() < time(16, 0)
    return None


def _session_window(market: str, day: date) -> tuple[datetime, datetime] | None:
    """The regular session of ``market`` on UTC day ``day``, in naive UTC."""
    if market == "crypto":
        start = datetime(day.year, day.month, day.day)
        return start, start + timedelta(days=1)
    if market == "us":
        if day.weekday() >= 5:
            return None
        open_local = datetime.combine(day, time(9, 30), tzinfo=_NEW_YORK)
        close_local = datetime.combine(day, time(16, 0), tzinfo=_NEW_YORK)
        return (
            open_local.astimezone(timezone.utc).replace(tzinfo=None),
            close_local.astimezone(timezone.utc).replace(tzinfo=None),
        )
    return None


def mark_request_for(leg: IdeaTrackedLeg, at: datetime) -> tuple[MarkRequest | None, str | None]:
    """How IBKR knows a leg, or why this build cannot mark it."""
    entity_type = str(leg.entity.entity_type).strip().lower()
    label = leg.entity.label
    if entity_type in {"equity", "etf"}:
        if leg.market != "us":
            return None, f"{label}: only US listings are mapped to IBKR contracts in this build."
        symbol = str(leg.entity.normalized_id).strip().upper()
        return MarkRequest(key=leg.key, label=label, sec_type="STK", symbol=symbol, market_open=leg_market_open("us", at)), None
    if entity_type == "crypto":
        symbol = ibkr_crypto_symbol(_coingecko_id(leg.entity)) or ibkr_crypto_symbol(str(leg.entity.normalized_id))
        if symbol is None:
            return None, f"{label}: IBKR crypto covers BTC, ETH, LTC and BCH only."
        return MarkRequest(key=leg.key, label=label, sec_type="CRYPTO", symbol=symbol, market_open=True), None
    return None, f"{label}: {entity_type.replace('_', ' ')} legs have no IBKR mark in this build."


class MarkSource(Protocol):
    def connected(self) -> bool: ...

    def fetch(self, requests: Sequence[MarkRequest]) -> MarkBatch: ...


@dataclass(frozen=True)
class IntradayQuote:
    """The latest recorded mark of one instrument, for intraday criteria."""

    at: datetime
    price: float
    quality: str
    price_field: str | None
    label: str


@dataclass(frozen=True)
class _Target:
    idea_id: str
    segment: int
    started_at: datetime
    legs: tuple[IdeaTrackedLeg, ...]


@dataclass
class IntradayPassResult:
    at: datetime
    status: str  # recorded | disconnected | skipped | idle | demo
    ideas: int = 0
    instruments: int = 0
    priced: int = 0
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


class IdeaIntradayService:
    """Records the marks (scheduler) and serves the intraday view (routes)."""

    def __init__(
        self,
        idea_service: Any,
        tracking_service: Any,
        store: IdeaIntradayStore,
        marks: MarkSource | None,
        *,
        clock: Callable[[], datetime] = now_utc,
        mock_mode: bool = False,
        run_id: str | None = None,
    ) -> None:
        self.idea_service = idea_service
        self.tracking_service = tracking_service
        self.store = store
        self.marks = marks
        self.mock_mode = bool(mock_mode)
        self._clock = clock
        self.run_id = run_id or uuid4().hex[:12]
        self._last_pass_at: datetime | None = None
        self._last_markets: frozenset[str] = frozenset()
        self._last_signature: tuple = ()
        self._ever_connected = False
        self._latest: dict[tuple[str, str], IntradayQuote] = {}
        # Última marca congelada de cada pata con el mercado cerrado: se pide una vez por hora.
        self._closed_cache: dict[str, tuple[datetime, LegMark]] = {}
        self.last_pass: IntradayPassResult | None = None

    # -- grabación ---------------------------------------------------------------

    def tws_connected(self) -> bool:
        if self.mock_mode or self.marks is None:
            return False
        try:
            return bool(self.marks.connected())
        except Exception:  # noqa: BLE001
            return False

    def cadence_seconds(self, now: datetime, markets: frozenset[str] | None = None) -> int:
        markets = self._last_markets if markets is None else markets
        if any(leg_market_open(market, now) is not False for market in markets):
            return INTRADAY_PASS_SECONDS
        return CLOSED_MARK_SECONDS

    def _signature(self) -> tuple:
        rows = []
        for summary in self.idea_service.store.list_summaries():
            tracking = summary.tracking or {}
            if summary.status == "active" and tracking.get("open"):
                rows.append((summary.idea_id, tracking.get("segments")))
        return tuple(sorted(rows))

    def due(self, now: datetime | None = None) -> bool:
        """A pass is due at the cadence, or at once when the tracked books changed."""
        if self.mock_mode or self.marks is None:
            return False
        moment = now or self._clock()
        if self._last_pass_at is None:
            return True
        if self._signature() != self._last_signature:
            return True
        # Un cambio de estado de TWS se registra en el acto: la primera marca al conectar,
        # y el inicio exacto del hueco al desconectar.
        last_status = self.last_pass.status if self.last_pass is not None else None
        connected = self.tws_connected()
        if (last_status == "disconnected" and connected) or (last_status in {"recorded", "skipped"} and not connected):
            return True
        return (moment - self._last_pass_at).total_seconds() >= self.cadence_seconds(moment)

    def _targets(self) -> list[_Target]:
        targets = []
        for summary in self.idea_service.store.list_summaries():
            tracking = summary.tracking or {}
            if summary.status != "active" or not tracking.get("open"):
                continue
            idea = self.idea_service.store.get(summary.idea_id)
            segment = idea.tracking.open_segment if idea is not None and idea.tracking is not None else None
            if segment is None or segment.untracked_reason:
                continue
            targets.append(_Target(idea.idea_id, segment.number, segment.started_at, segment.legs))
        return targets

    def record_pass(self) -> IntradayPassResult:
        """One pass: one IBKR snapshot per distinct leg, written to each idea's session file."""
        now = self._clock()
        self._last_pass_at = now
        self._last_signature = self._signature()
        if self.mock_mode or self.marks is None:
            result = IntradayPassResult(at=now, status="demo", reason="Demo mode records no IBKR marks.")
            self.last_pass = result
            return result
        targets = self._targets()
        markets = frozenset(leg.market for target in targets for leg in target.legs)
        self._last_markets = markets
        cadence = self.cadence_seconds(now, markets)
        if not targets:
            result = IntradayPassResult(at=now, status="idle", reason="No active idea has an open tracked segment.")
            self.last_pass = result
            return result
        if not self.tws_connected():
            reason = "Trader Workstation disconnected."
            # Antes de la primera conexión no hay capa intradía que interrumpir; después, cada pasada lo deja escrito.
            if self._ever_connected:
                for target in targets:
                    self._note(target.idea_id, now, "disconnected", reason, cadence)
            result = IntradayPassResult(at=now, status="disconnected", ideas=len(targets), reason=reason)
            self.last_pass = result
            return result
        self._ever_connected = True
        requests: dict[str, MarkRequest] = {}
        unsupported: dict[str, str] = {}
        for target in targets:
            for leg in target.legs:
                request, reason = mark_request_for(leg, now)
                if request is None:
                    unsupported[leg.key] = str(reason)
                else:
                    requests.setdefault(leg.key, request)
        # Una pata con su mercado cerrado no cambia de precio: entre pasadas horarias se reutiliza su marca.
        reused: dict[str, tuple[datetime, LegMark]] = {}
        for key in list(requests):
            cached = self._closed_cache.get(key)
            if requests[key].market_open is False and cached is not None and (now - cached[0]).total_seconds() < CLOSED_MARK_SECONDS:
                reused[key] = cached
                del requests[key]
        keys = sorted(requests)
        for key in keys[MARK_INSTRUMENTS_MAX:]:
            unsupported[key] = f"Over the per-pass IBKR budget of {MARK_INSTRUMENTS_MAX} instruments."
        wanted = [requests[key] for key in keys[:MARK_INSTRUMENTS_MAX]]
        batch = self.marks.fetch(wanted) if wanted else MarkBatch()
        if batch.unavailable_reason:
            for target in targets:
                self._note(target.idea_id, now, "skipped", batch.unavailable_reason, cadence)
            result = IntradayPassResult(at=now, status="skipped", ideas=len(targets), instruments=len(wanted), reason=batch.unavailable_reason)
            self.last_pass = result
            return result
        for key in keys[:MARK_INSTRUMENTS_MAX]:
            mark = batch.marks.get(key)
            if mark is not None and mark.ok and requests[key].market_open is False:
                self._closed_cache[key] = (now, mark)
        for target in targets:
            # Una idea cuyas patas solo tienen marcas reutilizadas no gana fila: su cadencia es horaria.
            if all(leg.key in reused for leg in target.legs):
                continue
            idea_cadence = self.cadence_seconds(now, frozenset(leg.market for leg in target.legs))
            legs: dict[str, dict[str, Any]] = {}
            missing: dict[str, str] = {}
            for leg in target.legs:
                if leg.key in reused:
                    marked_at, mark = reused[leg.key]
                    legs[leg.key] = {
                        "price": mark.price,
                        "field": mark.field,
                        "md_type": mark.md_type,
                        "quality": mark.quality,
                        "marked_at": marked_at.replace(microsecond=0).isoformat(),
                    }
                    continue
                mark = batch.marks.get(leg.key)
                if mark is not None and mark.ok:
                    legs[leg.key] = {"price": mark.price, "field": mark.field, "md_type": mark.md_type, "quality": mark.quality}
                else:
                    missing[leg.key] = (mark.reason if mark is not None else None) or unsupported.get(leg.key) or "No IBKR mark."
            if not legs:
                self._note(target.idea_id, now, "skipped", next(iter(missing.values()), "No IBKR mark."), idea_cadence)
                continue
            try:
                self.store.append_mark(
                    target.idea_id, now, run_id=self.run_id, segment=target.segment, cadence_seconds=idea_cadence, legs=legs, missing=missing
                )
            except Exception:  # noqa: BLE001 - un fichero que no se escribe no detiene la pasada
                logger.exception("Could not store the intraday marks of idea %s", target.idea_id)
        self._remember(targets, batch, now)
        result = IntradayPassResult(
            at=now,
            status="recorded",
            ideas=len(targets),
            instruments=len(wanted),
            priced=sum(1 for mark in batch.marks.values() if mark.ok),
            warnings=list(batch.warnings),
        )
        self.last_pass = result
        return result

    def _note(self, idea_id: str, now: datetime, status: str, reason: str, cadence: int) -> None:
        try:
            self.store.note_status(idea_id, now, run_id=self.run_id, status=status, reason=reason, cadence_seconds=cadence)
        except Exception:  # noqa: BLE001
            logger.exception("Could not store the intraday status of idea %s", idea_id)

    def _remember(self, targets: Sequence[_Target], batch: MarkBatch, now: datetime) -> None:
        for target in targets:
            for leg in target.legs:
                mark = batch.marks.get(leg.key)
                if mark is None or not mark.ok or mark.quality is None:
                    continue
                quote = IntradayQuote(at=now, price=float(mark.price), quality=mark.quality, price_field=mark.field, label=leg.entity.label)
                entity_type = str(leg.entity.entity_type).strip().lower()
                if entity_type in {"equity", "etf"}:
                    self._latest[("equity", str(leg.entity.normalized_id).strip().upper())] = quote
                elif entity_type == "crypto":
                    self._latest[("crypto", _coingecko_id(leg.entity))] = quote
                    self._latest[("crypto", str(leg.entity.normalized_id).strip().lower())] = quote

    def latest_quote(self, observable_id: str, params: Mapping[str, str], *, now: datetime | None = None) -> IntradayQuote | None:
        """The latest fresh live or delayed mark for an observable; frozen marks never trigger criteria."""
        if observable_id == "equity_close":
            key = ("equity", str(params.get("symbol") or "").strip().upper())
        elif observable_id == "crypto_price":
            key = ("crypto", str(params.get("token_id") or "").strip().lower())
        else:
            return None
        quote = self._latest.get(key)
        if quote is None or quote.quality not in TRIGGER_QUALITIES:
            return None
        moment = now or self._clock()
        if (moment - quote.at).total_seconds() > FRESH_MARK_SECONDS:
            return None
        return quote

    # -- lectura -----------------------------------------------------------------

    def view(self, idea: Idea, *, session: date | None = None) -> dict[str, Any]:
        """Rebuild the canonical series (not persisted) and value the session's marks against it."""
        tracking = idea.tracking
        if tracking is None or not tracking.segments:
            return self.empty_view("not_tracked", "The intraday layer starts once the idea tracks a book.")
        result, prices = self.tracking_service.compute_with_prices(idea, persist=False)
        return self.view_for(idea, result, prices, session=session)

    def empty_view(self, status: str, reason: str, *, sessions: Sequence[date] = ()) -> dict[str, Any]:
        return {
            **_view_header(),
            "available": False,
            "status": status,
            "status_reason": reason,
            "tws_connected": self.tws_connected(),
            "session": None,
            "sessions": [day.isoformat() for day in sessions],
            "reference": None,
            "summary": _empty_summary(),
            "points": [],
            "gaps": [],
            "legs": [],
            "warnings": [],
        }

    def view_for(
        self,
        idea: Idea,
        result: TrackingComputation,
        prices: Mapping[str, LegCloses],
        *,
        session: date | None = None,
    ) -> dict[str, Any]:
        now = self._clock()
        sessions = self.store.sessions(idea.idea_id)
        if self.mock_mode:
            return self.empty_view("demo", "Demo mode: the intraday layer records IBKR marks only in live mode with Trader Workstation.", sessions=sessions)
        if idea.tracking is None or not idea.tracking.segments:
            return self.empty_view("not_tracked", "The intraday layer starts once the idea tracks a book.", sessions=sessions)
        chosen = session or (sessions[0] if sessions else None)
        payload = self.store.load(idea.idea_id, chosen) if chosen else None
        if payload is None or not payload.get("rows"):
            reason = (
                "No IBKR marks yet. Gamma records them every 5 minutes while Trader Workstation is connected."
                if idea.tracking.open_segment is not None
                else "No IBKR marks were recorded for this idea."
            )
            view = self.empty_view("no_marks", reason, sessions=sessions)
            view["session"] = chosen.isoformat() if chosen else None
            return view
        return compute_intraday(
            idea,
            chosen,
            payload,
            result,
            prices,
            now=now,
            run_id=self.run_id,
            tws_connected=self.tws_connected(),
            sessions=sessions,
        )


# ---------------------------------------------------------------------------
# Valoración (pura: filas, serie canónica y reloj son entradas)
# ---------------------------------------------------------------------------


def _view_header() -> dict[str, Any]:
    return {
        "label": TRACKING_LABEL,
        "methodology": INTRADAY_METHODOLOGY,
        "cadence_seconds": INTRADAY_PASS_SECONDS,
        "closed_cadence_seconds": CLOSED_MARK_SECONDS,
        "source_provider": INTRADAY_SOURCE,
        "origin": INTRADAY_ORIGIN,
        "transformation_note": "IBKR marks valued against the canonical daily series' entry prices and latest close; stored per idea and session day.",
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "as_of": None,
        "today_return": None,
        "net_return": None,
        "intraday_drawdown": None,
        "quality": None,
        "marks": 0,
        "gaps": 0,
        "segment": None,
    }


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _worst_quality(qualities: Sequence[str]) -> str | None:
    known = [item for item in qualities if item in QUALITY_ORDER]
    return max(known, key=lambda item: QUALITY_ORDER[item]) if known else None


def _close_before(data: LegCloses | None, at: datetime) -> float | None:
    if data is None or not data.closes:
        return None
    earlier = [close for close in data.closes if close.close_at <= at]
    return earlier[-1].price if earlier else None


def _entry_instant(result: SegmentResult) -> datetime | None:
    if result.entry_session is None:
        return None
    return max(market_close_at(leg.market, result.entry_session) for leg in result.legs)


def compute_intraday(
    idea: Idea,
    session: date,
    payload: Mapping[str, Any],
    result: TrackingComputation,
    prices: Mapping[str, LegCloses],
    *,
    now: datetime,
    run_id: str,
    tws_connected: bool,
    sessions: Sequence[date] = (),
) -> dict[str, Any]:
    rows = sorted(
        (row for row in payload.get("rows") or [] if _parse(row.get("at")) is not None),
        key=lambda row: _parse(row["at"]),
    )
    marks = [row for row in rows if row.get("kind") == "mark"]
    statuses = [row for row in rows if row.get("kind") == "status"]
    by_number = {item.segment.number: item for item in result.segments}
    labels = {leg.key: leg.entity.label for segment in (idea.tracking.segments if idea.tracking else ()) for leg in segment.legs}
    warnings: list[str] = []
    # Factor encadenado antes de cada segmento, como en la serie canónica.
    factors: dict[int, float] = {}
    factor = 1.0
    for item in result.segments:
        factors[item.segment.number] = factor
        if item.priced and item.net_return is not None:
            factor *= 1.0 + float(item.net_return)
    canonical = [point for point in result.points if not point.gap and point.net_return is not None]
    reference = next((point for point in reversed(canonical) if point.session < session), None)
    reference_value = 1.0 + float(reference.net_return) if reference is not None else None

    points: list[dict[str, Any]] = []
    peak = reference_value
    max_dd: float | None = None
    latest_legs: list[dict[str, Any]] = []
    for row in marks:
        at = _parse(row["at"])
        number = int(row.get("segment") or 0)
        segment = by_number.get(number)
        row_legs = row.get("legs") or {}
        row_missing = row.get("missing") or {}
        quality = _worst_quality([str((value or {}).get("quality") or "") for value in row_legs.values()])
        point: dict[str, Any] = {
            "at": at.isoformat(),
            "segment": number,
            "net_return": None,
            "gross_return": None,
            "today_return": None,
            "drawdown": None,
            "quality": quality,
            "gap": False,
            "state": "priced",
            "missing": [],
            "carried": [],
        }
        leg_rows: list[dict[str, Any]] = []
        if segment is None or not segment.priced or not segment.legs or any(leg.entry_price is None for leg in segment.legs):
            point["state"] = "before_entry"
        elif (_entry_instant(segment) or at) > at:
            point["state"] = "before_entry"
        if point["state"] == "priced" and segment is not None:
            gross = 0.0
            exit_cost = 0.0
            entry_cost = 0.0
            ok = True
            for leg in segment.legs:
                weight = float(leg.weight or 0.0)
                bp = float(leg.cost_bp or 0.0) / 10_000.0
                entry_cost += abs(weight) * bp
                mark = row_legs.get(leg.key)
                reference_close = _close_before(prices.get(leg.key), at)
                price = None
                carried = False
                if mark and mark.get("price"):
                    price = float(mark["price"])
                elif leg_market_open(leg.market, at) is False and reference_close is not None:
                    price = reference_close
                    carried = True
                    point["carried"].append(leg.label)
                else:
                    ok = False
                    point["missing"].append(leg.label)
                leg_rows.append(
                    {
                        "key": leg.key,
                        "label": leg.label,
                        "price": price,
                        "field": (mark or {}).get("field"),
                        "md_type": (mark or {}).get("md_type"),
                        "quality": (mark or {}).get("quality") if not carried else None,
                        "carried": carried,
                        "reference_close": reference_close,
                        "move": (price / reference_close - 1.0) if price is not None and reference_close else None,
                        "missing_reason": None if price is not None else str(row_missing.get(leg.key) or "No IBKR mark."),
                    }
                )
                if price is not None and leg.entry_price:
                    relative = price / float(leg.entry_price)
                    gross += weight * (relative - 1.0)
                    exit_cost += abs(weight) * relative * bp
            if ok:
                net = gross - entry_cost - exit_cost
                chained = factors.get(number, 1.0) * (1.0 + net) - 1.0
                value = 1.0 + chained
                point["gross_return"] = factors.get(number, 1.0) * (1.0 + gross) - 1.0
                point["net_return"] = chained
                if reference_value is not None:
                    point["today_return"] = value / reference_value - 1.0
                    peak = value if peak is None else max(peak, value)
                    drawdown = value / peak - 1.0 if peak > 0 else 0.0
                    point["drawdown"] = drawdown
                    max_dd = drawdown if max_dd is None else min(max_dd, drawdown)
            else:
                point["gap"] = True
                point["state"] = "gap"
        else:
            leg_rows = [
                {
                    "key": key,
                    "label": labels.get(key, key),
                    "price": (value or {}).get("price"),
                    "field": (value or {}).get("field"),
                    "md_type": (value or {}).get("md_type"),
                    "quality": (value or {}).get("quality"),
                    "carried": False,
                    "reference_close": _close_before(prices.get(key), at),
                    "move": None,
                    "missing_reason": None,
                }
                for key, value in row_legs.items()
            ] + [
                {"key": key, "label": labels.get(key, key), "price": None, "field": None, "md_type": None, "quality": None, "carried": False, "reference_close": None, "move": None, "missing_reason": str(reason)}
                for key, reason in row_missing.items()
            ]
        points.append(point)
        latest_legs = leg_rows

    gaps = _gaps(idea, session, marks, statuses, now=now, run_id=run_id)
    if any(point["state"] == "before_entry" for point in points):
        warnings.append("Marks before the segment's first close have no P&L: the book enters at that close.")
    if payload.get("truncated"):
        warnings.append("This session reached the stored mark limit; later marks were not kept.")
    priced = [point for point in points if point["net_return"] is not None]
    last = priced[-1] if priced else None
    qualities = sorted({point["quality"] for point in points if point["quality"]}, key=lambda item: QUALITY_ORDER.get(item, 9))
    status = "recording" if tws_connected and session == now.date() else "idle"
    status_reason = None
    if not tws_connected:
        status_reason = "Trader Workstation is not connected; the layer records only while it is."
    return {
        **_view_header(),
        "available": True,
        "status": status,
        "status_reason": status_reason,
        "tws_connected": tws_connected,
        "session": session.isoformat(),
        "sessions": [day.isoformat() for day in sessions],
        "reference": (
            {"session": reference.session.isoformat(), "net_return": reference.net_return} if reference is not None else None
        ),
        "summary": {
            "as_of": last["at"] if last else (points[-1]["at"] if points else None),
            "today_return": last["today_return"] if last else None,
            "net_return": last["net_return"] if last else None,
            "intraday_drawdown": max_dd,
            "quality": last["quality"] if last else (points[-1]["quality"] if points else None),
            "qualities": qualities,
            "marks": len(points),
            "gaps": len(gaps),
            "segment": last["segment"] if last else (points[-1]["segment"] if points else None),
        },
        "points": points,
        "gaps": gaps,
        "legs": latest_legs,
        "warnings": warnings,
    }


def _status_kind(row: Mapping[str, Any]) -> str:
    return "disconnected" if row.get("status") == "disconnected" else "skipped"


def _split_gap(
    start: datetime,
    end: datetime,
    statuses: Sequence[Mapping[str, Any]],
    base_kind: str,
    base_reason: str,
) -> list[tuple[datetime, datetime, str, str]]:
    """Split a stretch without marks at the status stretches inside it.

    A status row says what Gamma saw while it ran (TWS disconnected, IBKR did
    not answer) from ``at`` to ``until``; the rest of the stretch keeps the
    base reason (Gamma not running, or nothing recorded). Slivers shorter than
    the gap threshold are absorbed by their neighbour, and equal neighbours merge.
    """
    tolerance = timedelta(seconds=GAP_FACTOR * INTRADAY_PASS_SECONDS)
    inside = sorted(
        (row for row in statuses if (_parse(row.get("until")) or _parse(row["at"])) >= start and _parse(row["at"]) <= end),
        key=lambda row: _parse(row["at"]),
    )
    pieces: list[tuple[datetime, datetime, str, str]] = []
    cursor = start
    for index, row in enumerate(inside):
        at = max(_parse(row["at"]), start)
        until = min(_parse(row.get("until")) or at, end)
        piece_start = cursor
        if at - cursor > tolerance:
            pieces.append((cursor, at, base_kind, base_reason))
            piece_start = at
        boundary = min(_parse(inside[index + 1]["at"]), end) if index + 1 < len(inside) else end
        piece_end = boundary if boundary - until <= tolerance else until
        pieces.append((piece_start, max(piece_end, piece_start), _status_kind(row), str(row.get("reason") or "No mark.")))
        cursor = max(piece_end, piece_start)
    if not pieces or end - cursor > tolerance:
        pieces.append((cursor, end, base_kind, base_reason))
    elif cursor < end:
        last = pieces[-1]
        pieces[-1] = (last[0], end, last[2], last[3])
    merged: list[tuple[datetime, datetime, str, str]] = []
    for piece in pieces:
        if merged and merged[-1][2:] == piece[2:]:
            merged[-1] = (merged[-1][0], piece[1], piece[2], piece[3])
        else:
            merged.append(piece)
    return merged


def _gaps(
    idea: Idea,
    session: date,
    marks: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    run_id: str,
) -> list[dict[str, Any]]:
    """Explicit gaps: stretches of the session without marks, with why (when Gamma knows)."""
    gaps: list[dict[str, Any]] = []

    def add_pieces(pieces: Sequence[tuple[datetime, datetime, str, str]], *, open_ended: bool = False) -> None:
        for index, (start, end, kind, reason) in enumerate(pieces):
            last_piece = index == len(pieces) - 1
            gaps.append(
                {
                    "start": start.isoformat(),
                    "end": None if open_ended and last_piece else end.isoformat(),
                    "kind": kind,
                    "reason": reason,
                }
            )

    segments = idea.tracking.segments if idea.tracking else ()
    markets = sorted({leg.market for segment in segments for leg in segment.legs})
    windows = [window for window in (_session_window(market, session) for market in markets) if window]
    open_start = min((window[0] for window in windows), default=None)
    open_end = max((window[1] for window in windows), default=None)
    started = max((segment.started_at for segment in segments if segment.started_at.date() <= session), default=None)
    lead_from = None
    if open_start is not None:
        lead_from = max(open_start, started) if started is not None else open_start
    day_end = datetime(session.year, session.month, session.day) + timedelta(days=1)
    horizon = min(now, open_end if open_end is not None else day_end, day_end)
    ongoing = session == now.date() and (open_end is None or now < open_end)
    not_before = "Not recorded before the first mark (Gamma or Trader Workstation was closed)."
    not_since = "No mark since then." if ongoing else "No mark since then (Gamma or Trader Workstation was closed)."

    if not marks:
        if not statuses:
            return gaps
        first_status = _parse(statuses[0]["at"])
        start = min(lead_from, first_status) if lead_from is not None else first_status
        end = max(horizon, max(_parse(row.get("until")) or _parse(row["at"]) for row in statuses))
        add_pieces(_split_gap(start, end, statuses, "not_recorded", not_before), open_ended=ongoing)
        return gaps

    def missed(start: datetime, end: datetime) -> bool:
        # Una fila de estado dentro del tramo dice que una pasada debida no pudo marcar: es un hueco
        # aunque el tramo sea más corto que el umbral (visto en vivo: 10 minutos sin TWS se perdían).
        return any(start < _parse(row["at"]) < end for row in statuses)

    first = marks[0]
    first_at = _parse(first["at"])
    first_cadence = int(first.get("cadence") or INTRADAY_PASS_SECONDS)
    if lead_from is not None and (
        first_at - lead_from > timedelta(seconds=GAP_FACTOR * first_cadence) or missed(lead_from - timedelta(microseconds=1), first_at)
    ):
        add_pieces(_split_gap(lead_from, first_at, statuses, "not_recorded", not_before))
    for previous, current in zip(marks, marks[1:]):
        start = _parse(previous["at"])
        end = _parse(current["at"])
        cadence = int(previous.get("cadence") or INTRADAY_PASS_SECONDS)
        if end - start > timedelta(seconds=GAP_FACTOR * cadence) or missed(start, end):
            restarted = previous.get("run") and current.get("run") and previous.get("run") != current.get("run")
            base = ("not_running", "Gamma was not running.") if restarted else (
                "not_recorded",
                "No mark was recorded (Gamma or Trader Workstation was closed).",
            )
            add_pieces(_split_gap(start, end, statuses, *base))
    last = marks[-1]
    last_at = _parse(last["at"])
    last_cadence = int(last.get("cadence") or INTRADAY_PASS_SECONDS)
    if horizon - last_at > timedelta(seconds=GAP_FACTOR * last_cadence) or missed(last_at, horizon + timedelta(microseconds=1)):
        add_pieces(_split_gap(last_at, horizon, statuses, "not_recorded", not_since), open_ended=ongoing)
    return gaps


__all__ = [
    "CLOSED_MARK_SECONDS",
    "FRESH_MARK_SECONDS",
    "GAP_FACTOR",
    "INTRADAY_METHODOLOGY",
    "INTRADAY_PASS_SECONDS",
    "IdeaIntradayService",
    "IntradayPassResult",
    "IntradayQuote",
    "MARK_INSTRUMENTS_MAX",
    "compute_intraday",
    "leg_market_open",
    "mark_request_for",
]
