"""Workstream 12 - Ideas, checkpoint I3d: the TWS intraday layer.

Every test injects the clock, the daily closes and a fake IBKR client, so it
runs without network or Trader Workstation. What is checked:

* marks are recorded while TWS is connected, valued against the canonical
  daily series' entry prices and latest close, and labelled live, delayed or
  frozen as TWS served them;
* a stretch where TWS was disconnected, or Gamma was not running, is an
  explicit gap, never filled in;
* the canonical daily series is identical with and without marks;
* storage is bounded, IBKR requests are deduplicated and paced, and intraday
  criteria trigger only from fresh live or delayed marks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_criteria import ObservablePoint, ObservableReading, evaluate_criterion
from src.application.idea_evaluation import IdeaEvaluationScheduler
from src.application.idea_intraday import (
    CLOSED_MARK_SECONDS,
    INTRADAY_PASS_SECONDS,
    MARK_INSTRUMENTS_MAX,
    IdeaIntradayService,
    leg_market_open,
)
from src.application.idea_observables import ObservableRegistry
from src.application.idea_service import IdeaCreateRequest, IdeaPatchRequest, IdeaService
from src.application.idea_tracking import IdeaTrackingService, LegCloses, closes_from_series
from src.application.runtime import build_runtime
from src.models.handoff import HandoffEntity
from src.models.ideas import TRACKING_LABEL, IdeaCriterion, IdeaLeg, IdeaRiskEpisode, IdeaRiskSnapshot, ObservableRef
from src.models.provenance import ProvenanceRecord
from src.services.ibkr_marks import (
    BATCH_SIZE_WHILE_OPTIONS_STREAM,
    MD_DELAYED,
    MD_DELAYED_FROZEN,
    MD_FROZEN,
    MD_LIVE,
    IbkrMarkReader,
    LegMark,
    MarkBatch,
    best_price,
    mark_quality,
)
from src.services.idea_intraday_store import ROWS_PER_SESSION_MAX, SESSIONS_KEPT, IdeaIntradayStore
from src.services.idea_store import IdeaStore

# Semana del 9 al 13 de noviembre de 2026: NY abre 14:30 UTC y cierra 21:00 UTC.
MON, TUE, WED = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)
PRIOR = tuple(date(2026, 11, day) for day in (2, 3, 4, 5, 6))
AAPL = {**{day: 100.0 for day in PRIOR}, MON: 200.0, TUE: 202.0}
MSFT = {**{day: 50.0 for day in PRIOR}, MON: 400.0, TUE: 396.0}
SPY = {**{day: 300.0 for day in PRIOR}, MON: 500.0, TUE: 505.0}
TUE_OPEN = datetime(2026, 11, 10, 15, 0)  # martes 10:00 en Nueva York


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def set(self, moment: datetime) -> None:
        self.now = moment

    def __call__(self) -> datetime:
        return self.now


class _Prices:
    def __init__(self, closes=None, benchmark=None) -> None:
        self.closes = closes or {"AAPL": AAPL, "MSFT": MSFT}
        self.benchmark = benchmark or SPY

    def leg_closes(self, leg, *, since, now):
        series = self.closes.get(leg.entity.normalized_id.upper())
        if series is None:
            return LegCloses.unavailable("no closes")
        return LegCloses(
            closes=closes_from_series(series, leg.market),
            provenance=ProvenanceRecord(source_provider="fake_closes", retrieved_at=now, origin="tests.fake"),
        )

    def benchmark_closes(self, symbol, *, since, now):
        return LegCloses(closes=closes_from_series(self.benchmark, "us"))


@dataclass
class FakeMarks:
    """A fake IBKR mark source: connected or not, with fixed prices and data types."""

    connected_flag: bool = True
    prices: dict[str, float] = field(default_factory=lambda: {"AAPL": 204.0, "MSFT": 396.0})
    md_type: int = MD_LIVE
    price_field: str = "last"
    calls: list[list[str]] = field(default_factory=list)

    def connected(self) -> bool:
        return self.connected_flag

    def fetch(self, requests):
        self.calls.append([request.symbol for request in requests])
        batch = MarkBatch()
        for request in requests:
            price = self.prices.get(request.symbol)
            if price is None:
                batch.marks[request.key] = LegMark(key=request.key, price=None, reason=f"No price for {request.symbol}.")
                continue
            batch.marks[request.key] = LegMark(
                key=request.key,
                price=price,
                field=self.price_field,
                md_type=self.md_type,
                quality=mark_quality(self.md_type, self.price_field, request.market_open),
            )
        return batch


def _leg(symbol: str, weight: float | None = None, entity_type: str = "equity", native_id: str | None = None) -> IdeaLeg:
    return IdeaLeg(entity=HandoffEntity(entity_type=entity_type, label=symbol, normalized_id=symbol, native_id=native_id), weight=weight)


def _setup(tmp_path, *, marks: FakeMarks | None = None, legs=None, stance="long", activate_at=datetime(2026, 11, 9, 14, 0), now=TUE_OPEN):
    clock = _Clock(datetime(2026, 11, 6, 12, 0))
    store = IdeaStore(tmp_path / "ideas")
    service = IdeaService(store, clock=clock)
    idea = service.create_idea(
        IdeaCreateRequest(title="Pair", thesis="AAPL beats MSFT.", stance=stance, legs=tuple(legs or (_leg("AAPL", 1.0), _leg("MSFT", 1.0))))
    )
    clock.set(activate_at)
    service.activate(idea.idea_id)
    clock.set(now)
    tracker = IdeaTrackingService(service, _Prices(), clock=clock)
    intraday = IdeaIntradayService(
        service, tracker, IdeaIntradayStore(tmp_path / "ideas" / "intraday"), marks or FakeMarks(), clock=clock, run_id="run-a"
    )
    return clock, service, tracker, intraday, idea.idea_id


def _canonical(tracker, service, idea_id):
    payload = tracker.compute(idea_id, persist=False).to_dict()
    payload.pop("computed_at")
    return payload


# ---------------------------------------------------------------------------
# Recording and valuation
# ---------------------------------------------------------------------------


def test_marks_are_recorded_while_connected_and_valued_against_the_daily_series(tmp_path):
    clock, service, tracker, intraday, idea_id = _setup(tmp_path)
    before = _canonical(tracker, service, idea_id)

    result = intraday.record_pass()
    assert result.status == "recorded" and result.priced == 2

    stored = json.loads((tmp_path / "ideas" / "intraday" / idea_id / "2026-11-10.json").read_text(encoding="utf-8"))
    assert stored["label"] == TRACKING_LABEL and len(stored["rows"]) == 1
    row = stored["rows"][0]
    assert row["kind"] == "mark" and row["segment"] == 1 and row["cadence"] == INTRADAY_PASS_SECONDS
    assert row["legs"]["equity:AAPL"] == {"price": 204.0, "field": "last", "md_type": 1, "quality": "live"}

    view = intraday.view(service.get_idea(idea_id))
    assert view["available"] and view["label"] == TRACKING_LABEL and view["session"] == "2026-11-10"
    # La referencia es el último cierre canónico anterior al día de la marca (el lunes).
    assert view["reference"]["session"] == "2026-11-09"
    point = view["points"][0]
    weights, entry, bp = (0.5, 0.5), (200.0, 400.0), 0.0005
    relatives = (204.0 / entry[0], 396.0 / entry[1])
    gross = sum(w * (r - 1.0) for w, r in zip(weights, relatives))
    net = gross - sum(w * bp for w in weights) - sum(w * r * bp for w, r in zip(weights, relatives))
    reference = view["reference"]["net_return"]
    assert reference == pytest.approx(-0.001)  # costes de entrada y de salida al cierre del lunes
    assert point["net_return"] == pytest.approx(net)
    assert point["today_return"] == pytest.approx((1 + net) / (1 + reference) - 1)
    assert point["quality"] == "live" and point["state"] == "priced" and not point["gap"]
    assert view["summary"]["today_return"] == pytest.approx(point["today_return"])
    assert view["legs"][0]["reference_close"] == 200.0 and view["legs"][0]["move"] == pytest.approx(0.02)

    # La serie canónica no cambia con marcas grabadas: ni puntos nuevos ni valores distintos.
    after = _canonical(tracker, service, idea_id)
    assert after == before
    assert [point["session"] for point in after["points"]] == ["2026-11-09"]


def test_intraday_drawdown_tracks_the_fall_from_the_session_peak(tmp_path):
    marks = FakeMarks()
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    for minute, aapl in ((0, 210.0), (5, 214.0), (10, 206.0), (15, 209.0)):
        clock.set(TUE_OPEN + timedelta(minutes=minute))
        marks.prices = {"AAPL": aapl, "MSFT": 400.0}
        intraday.record_pass()
    view = intraday.view(service.get_idea(idea_id))
    values = [1 + point["net_return"] for point in view["points"]]
    peak = max(values[:2])
    assert view["summary"]["intraday_drawdown"] == pytest.approx(values[2] / peak - 1)
    assert view["summary"]["marks"] == 4
    # Solo el tramo entre la apertura (14:30 UTC) y la primera marca, sin huecos entre marcas.
    assert [(gap["start"], gap["end"], gap["kind"]) for gap in view["gaps"]] == [
        ("2026-11-10T14:30:00", "2026-11-10T15:00:00", "not_recorded")
    ]


def test_delayed_and_frozen_marks_are_labelled(tmp_path):
    marks = FakeMarks(md_type=MD_DELAYED)
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    intraday.record_pass()
    clock.set(datetime(2026, 11, 14, 12, 0))  # sábado: mercado de EE. UU. cerrado
    marks.md_type = MD_FROZEN
    intraday.record_pass()
    view = intraday.view(service.get_idea(idea_id), session=date(2026, 11, 10))
    assert view["points"][0]["quality"] == "delayed"
    saturday = intraday.view(service.get_idea(idea_id), session=date(2026, 11, 14))
    assert saturday["points"][0]["quality"] == "frozen"
    assert saturday["summary"]["qualities"] == ["frozen"]

    assert mark_quality(MD_LIVE, "last", True) == "live"
    assert mark_quality(MD_DELAYED, "last", True) == "delayed"
    assert mark_quality(MD_LIVE, "delayedLast", True) == "delayed"
    assert mark_quality(MD_FROZEN, "last", False) == "frozen"
    assert mark_quality(MD_LIVE, "last", False) == "frozen"  # mercado cerrado: nunca "live"
    assert mark_quality(MD_LIVE, "close", True) == "frozen"  # solo el cierre previo
    assert mark_quality(MD_DELAYED_FROZEN, "delayedLast", False) == "delayed_frozen"


def test_a_disconnection_and_a_restart_are_explicit_gaps(tmp_path):
    marks = FakeMarks()
    clock, service, tracker, intraday, idea_id = _setup(tmp_path, marks=marks)
    for minute in (0, 5):
        clock.set(TUE_OPEN + timedelta(minutes=minute))
        intraday.record_pass()
    marks.connected_flag = False
    for minute in (10, 15, 20):
        clock.set(TUE_OPEN + timedelta(minutes=minute))
        assert intraday.record_pass().status == "disconnected"
    marks.connected_flag = True
    clock.set(TUE_OPEN + timedelta(minutes=25))
    intraday.record_pass()

    stored = json.loads((tmp_path / "ideas" / "intraday" / idea_id / "2026-11-10.json").read_text(encoding="utf-8"))
    statuses = [row for row in stored["rows"] if row["kind"] == "status"]
    assert len(statuses) == 1  # una sola fila que se alarga mientras dura la desconexión
    assert statuses[0]["at"] == "2026-11-10T15:10:00" and statuses[0]["until"] == "2026-11-10T15:20:00"

    # Gamma se cierra a las 15:25 y vuelve a las 16:30 con otro run.
    restarted = IdeaIntradayService(service, tracker, intraday.store, marks, clock=clock, run_id="run-b")
    clock.set(datetime(2026, 11, 10, 16, 30))
    restarted.record_pass()
    clock.set(datetime(2026, 11, 10, 17, 30))  # sin marcas desde las 16:30, sesión aún abierta
    view = restarted.view(service.get_idea(idea_id))
    lead, *gaps = view["gaps"]
    assert (lead["start"], lead["end"], lead["kind"]) == ("2026-11-10T14:30:00", "2026-11-10T15:00:00", "not_recorded")
    assert [gap["kind"] for gap in gaps] == ["disconnected", "not_running", "not_recorded"]
    assert gaps[0]["start"] == "2026-11-10T15:05:00" and gaps[0]["end"] == "2026-11-10T15:25:00"
    assert "Trader Workstation disconnected" in gaps[0]["reason"]
    assert gaps[1]["start"] == "2026-11-10T15:25:00" and gaps[1]["end"] == "2026-11-10T16:30:00"
    assert gaps[2]["start"] == "2026-11-10T16:30:00" and gaps[2]["end"] is None
    # Los huecos no se rellenan: solo hay puntos donde hubo marca.
    assert [point["at"][11:16] for point in view["points"]] == ["15:00", "15:05", "15:25", "16:30"]
    assert view["summary"]["gaps"] == 4
    # Y la serie diaria sigue igual.
    assert [point["session"] for point in _canonical(tracker, service, idea_id)["points"]] == ["2026-11-09"]


def test_a_short_disconnection_is_a_gap_even_below_the_threshold(tmp_path):
    """Seen live on 2026-11-24: 10 minutes without TWS (one missed pass) left no gap and the line joined across it."""
    marks = FakeMarks()
    clock, service, _tracker, intraday, idea_id = _setup(tmp_path, marks=marks)
    for minute in (0, 5):
        clock.set(TUE_OPEN + timedelta(minutes=minute))
        intraday.record_pass()
    marks.connected_flag = False
    clock.set(TUE_OPEN + timedelta(minutes=10))
    assert intraday.record_pass().status == "disconnected"
    # Mientras sigue desconectado, el hueco ya se ve y queda abierto.
    clock.set(TUE_OPEN + timedelta(minutes=12))
    ongoing = intraday.view(service.get_idea(idea_id))["gaps"]
    assert (ongoing[-1]["start"], ongoing[-1]["end"], ongoing[-1]["kind"]) == ("2026-11-10T15:05:00", None, "disconnected")
    marks.connected_flag = True
    clock.set(TUE_OPEN + timedelta(minutes=15))
    intraday.record_pass()

    view = intraday.view(service.get_idea(idea_id))
    lead, *gaps = view["gaps"]
    assert lead["kind"] == "not_recorded"
    # Diez minutos entre marcas (por debajo de 2,5 veces la cadencia), pero una pasada no pudo marcar.
    assert [(gap["start"], gap["end"], gap["kind"]) for gap in gaps] == [("2026-11-10T15:05:00", "2026-11-10T15:15:00", "disconnected")]
    assert "Trader Workstation disconnected" in gaps[0]["reason"]
    # Sin filas de estado, un tramo igual de corto sigue sin ser hueco (tolerancia a la cadencia).
    clock.set(TUE_OPEN + timedelta(minutes=25))
    intraday.record_pass()
    assert len(intraday.view(service.get_idea(idea_id))["gaps"]) == 2


def test_a_gap_is_split_at_the_stretches_gamma_saw():
    from src.application.idea_intraday import _split_gap

    def status(kind, at, until, run="r1", reason="IBKR returned no price for Bitcoin within 5 s."):
        return {"kind": "status", "status": kind, "at": at, "until": until, "run": run, "reason": reason}

    at = lambda text: datetime.fromisoformat(f"2026-11-22T{text}")  # noqa: E731
    # Live check 2026-11-22: un hueco inicial de 18 h con dos tramos "skipped" al final no es todo "skipped".
    pieces = _split_gap(
        at("00:00:00"),
        at("18:32:42"),
        [status("skipped", "2026-11-22T18:23:51", "2026-11-22T18:28:55"), status("skipped", "2026-11-22T18:30:22", "2026-11-22T18:30:22", run="r2")],
        "not_recorded",
        "Not recorded.",
    )
    assert [(p[0].time().isoformat(), p[1].time().isoformat(), p[2]) for p in pieces] == [
        ("00:00:00", "18:23:51", "not_recorded"),
        ("18:23:51", "18:32:42", "skipped"),
    ]
    # Desconectado y después Gamma cerrado: dos tramos con su motivo.
    pieces = _split_gap(at("15:05:00"), at("16:30:00"), [status("disconnected", "2026-11-22T15:10:00", "2026-11-22T15:20:00", reason="Trader Workstation disconnected.")], "not_running", "Gamma was not running.")
    assert [(p[0].time().isoformat(), p[1].time().isoformat(), p[2]) for p in pieces] == [
        ("15:05:00", "15:20:00", "disconnected"),
        ("15:20:00", "16:30:00", "not_running"),
    ]
    # Sin filas de estado, el tramo entero conserva el motivo base.
    assert _split_gap(at("15:05:00"), at("16:30:00"), [], "not_running", "Gamma was not running.")[0][2] == "not_running"


def test_nothing_is_written_before_the_first_connection(tmp_path):
    marks = FakeMarks(connected_flag=False)
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    assert intraday.record_pass().status == "disconnected"
    assert intraday.store.sessions(idea_id) == []
    view = intraday.view(service.get_idea(idea_id))
    assert view["status"] == "no_marks" and not view["available"]
    assert "Trader Workstation is connected" in view["status_reason"]

    # Conectar hace la pasada debida en el acto, y desconectar también (marca el inicio del hueco).
    clock.set(TUE_OPEN + timedelta(seconds=30))
    assert not intraday.due()
    marks.connected_flag = True
    assert intraday.due()
    assert intraday.record_pass().status == "recorded"
    clock.set(TUE_OPEN + timedelta(seconds=60))
    assert not intraday.due()
    marks.connected_flag = False
    assert intraday.due()
    assert intraday.record_pass().status == "disconnected"
    assert [row["kind"] for row in intraday.store.load(idea_id, TUE_OPEN.date())["rows"]] == ["mark", "status"]
    # Mientras sigue desconectado, la siguiente pasada espera a la cadencia.
    assert not intraday.due()


def test_a_missing_mark_while_the_market_is_open_is_a_gap_and_a_closed_market_carries(tmp_path):
    marks = FakeMarks(prices={"AAPL": 204.0})  # IBKR no devuelve MSFT
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    intraday.record_pass()
    view = intraday.view(service.get_idea(idea_id))
    point = view["points"][0]
    assert point["gap"] and point["state"] == "gap" and point["net_return"] is None
    assert point["missing"] == ["MSFT"]
    assert view["legs"][1]["missing_reason"] == "No price for MSFT."

    # Libro con cripto y acción un sábado: la acción (mercado cerrado) usa su último cierre, sin hueco.
    legs = (_leg("BTC", None, "crypto", native_id="bitcoin"), _leg("AAPL"))
    marks2 = FakeMarks(prices={"BTC": 70_000.0})
    clock2, service2, _, intraday2, idea2 = _setup(tmp_path / "b", marks=marks2, legs=legs, now=datetime(2026, 11, 14, 12, 0))
    intraday2.tracking_service.prices.closes = {
        "AAPL": AAPL | {date(2026, 11, d): 205.0 for d in (11, 12, 13)},
        "BTC": {date(2026, 11, d): 60_000.0 + d for d in range(1, 14)},
    }
    result = intraday2.record_pass()
    assert result.status == "recorded" and sorted(marks2.calls[0]) == ["AAPL", "BTC"]
    weekend = intraday2.view(service2.get_idea(idea2))
    point = weekend["points"][0]
    assert not point["gap"] and point["carried"] == ["AAPL"] and point["net_return"] is not None
    aapl = next(leg for leg in weekend["legs"] if leg["label"] == "AAPL")
    assert aapl["carried"] and aapl["price"] == 205.0 and aapl["quality"] is None
    assert weekend["reference"]["session"] == "2026-11-13"


def test_closed_markets_are_marked_hourly_and_requests_are_deduplicated(tmp_path):
    marks = FakeMarks()
    clock, service, tracker, intraday, idea_id = _setup(tmp_path, marks=marks)
    second = service.create_idea(IdeaCreateRequest(title="AAPL long", thesis="x", stance="long", legs=(_leg("AAPL"),)))
    service.activate(second.idea_id)
    # En sesión, cada cinco minutos; AAPL se pide una vez para las dos ideas.
    assert intraday.due()
    intraday.record_pass()
    assert marks.calls == [["AAPL", "MSFT"]]
    clock.set(TUE_OPEN + timedelta(seconds=INTRADAY_PASS_SECONDS - 1))
    assert not intraday.due()
    clock.set(TUE_OPEN + timedelta(seconds=INTRADAY_PASS_SECONDS))
    assert intraday.due()
    # Un libro nuevo hace la pasada debida en el acto.
    clock.set(TUE_OPEN + timedelta(seconds=30))
    intraday.record_pass()
    service.update_idea(second.idea_id, IdeaPatchRequest(legs=(_leg("AAPL"), _leg("MSFT"))))
    assert intraday.due()
    # Con todos los mercados del libro cerrados (sábado), una marca congelada por hora.
    saturday = datetime(2026, 11, 14, 12, 0)
    clock.set(saturday)
    intraday.record_pass()
    clock.set(saturday + timedelta(minutes=10))
    assert not intraday.due()
    clock.set(saturday + timedelta(seconds=CLOSED_MARK_SECONDS))
    assert intraday.due()


def test_the_instrument_budget_caps_a_pass(tmp_path):
    symbols = [f"T{index:02d}" for index in range(MARK_INSTRUMENTS_MAX + 3)]
    marks = FakeMarks(prices={symbol: 10.0 for symbol in symbols})
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks, legs=(_leg("AAPL"),))
    for start in range(0, len(symbols), 9):
        idea = service.create_idea(IdeaCreateRequest(title=f"Basket {start}", thesis="x", stance="long", legs=tuple(_leg(s) for s in symbols[start : start + 9])))
        service.activate(idea.idea_id)
    intraday.record_pass()
    assert len(marks.calls[0]) == MARK_INSTRUMENTS_MAX


def test_demo_mode_records_nothing(tmp_path):
    clock, service, tracker, _, idea_id = _setup(tmp_path)
    demo = IdeaIntradayService(service, tracker, IdeaIntradayStore(tmp_path / "x"), FakeMarks(), clock=clock, mock_mode=True)
    assert not demo.due()
    assert demo.record_pass().status == "demo"
    assert demo.view(service.get_idea(idea_id))["status"] == "demo"


def test_a_segment_waiting_for_its_first_close_has_no_intraday_pnl(tmp_path):
    clock, service, _, intraday, idea_id = _setup(tmp_path, activate_at=datetime(2026, 11, 10, 14, 0))
    intraday.record_pass()
    view = intraday.view(service.get_idea(idea_id))
    assert view["points"][0]["state"] == "before_entry" and view["points"][0]["net_return"] is None
    assert any("first close" in item for item in view["warnings"])
    assert view["legs"][0]["price"] == 204.0


# ---------------------------------------------------------------------------
# Storage bounds
# ---------------------------------------------------------------------------


def test_the_store_is_bounded_and_survives_a_corrupt_file(tmp_path):
    store = IdeaIntradayStore(tmp_path)
    start = datetime(2026, 11, 10, 0, 0)
    for index in range(ROWS_PER_SESSION_MAX + 5):
        store.append_mark("idea1", start + timedelta(minutes=index), run_id="r", segment=1, cadence_seconds=60, legs={"k": {"price": 1.0}}, missing={})
    payload = store.load("idea1", start.date())
    assert len(payload["rows"]) == ROWS_PER_SESSION_MAX and payload["truncated"] is True
    for offset in range(SESSIONS_KEPT + 3):
        day = datetime(2026, 10, 1) + timedelta(days=offset)
        store.append_mark("idea2", day, run_id="r", segment=1, cadence_seconds=300, legs={"k": {"price": 1.0}}, missing={})
    assert len(store.sessions("idea2")) == SESSIONS_KEPT
    assert store.sessions("idea2")[0] == date(2026, 10, 13)
    path = tmp_path / "idea2" / "2026-10-13.json"
    path.write_text("{not json", encoding="utf-8")
    assert store.load("idea2", date(2026, 10, 13)) is None
    assert not path.exists() and any(item.name.endswith(".preserved") for item in path.parent.iterdir())
    with pytest.raises(ValueError):
        store.sessions("../escape")


# ---------------------------------------------------------------------------
# IBKR reader (fake TWS session)
# ---------------------------------------------------------------------------


class _Ticker:
    def __init__(self, **fields) -> None:
        self.marketDataType = fields.pop("marketDataType", 1)
        for name in ("last", "bid", "ask", "close", "delayedLast", "delayedBid", "delayedAsk", "delayedClose"):
            setattr(self, name, fields.get(name, float("nan")))


class _Event:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _FakeIB:
    """Records the data types requested and returns prepared tickers per (symbol, type)."""

    def __init__(self, tickers, errors=None) -> None:
        self.errorEvent = _Event()
        self.errors = errors or {}
        self.tickers = tickers
        self.types: list[int] = []
        self.requests: list[tuple[str, int, bool]] = []
        self.cancelled: list[str] = []
        self.wrapper = self

    def reqMarketDataType(self, value):
        self.types.append(value)

    def qualifyContracts(self, contract):
        contract.conId = 1000 + len(contract.symbol)
        return [contract]

    def reqMktData(self, contract, generic, snapshot, regulatory):
        current = self.types[-1]
        self.requests.append((contract.symbol, current, snapshot))
        error = self.errors.get((contract.symbol, current))
        if error is not None:
            self.errorEvent.emit(len(self.requests), error[0], error[1], contract)
        return self.tickers.get((contract.symbol, current), _Ticker(marketDataType=current))

    def endTicker(self, ticker, kind):
        pass

    def cancelMktData(self, contract):
        self.cancelled.append(contract.symbol)

    def sleep(self, seconds):
        pass


class _FakeClient:
    mock = False

    def __init__(self, ib, connected=True) -> None:
        self.ib = ib
        self.connected = connected
        self.market_data_mode = "auto"

    def is_connected(self):
        return self.connected

    def _run_ib(self, fn, timeout=None):
        return fn()


class _FakeIV:
    def __init__(self, running: bool) -> None:
        self.running = running

    def is_running(self):
        return self.running


def test_the_reader_falls_back_to_delayed_and_restores_the_default_type():
    from src.services.ibkr_marks import MarkRequest

    ib = _FakeIB(
        {
            ("AAPL", MD_LIVE): _Ticker(marketDataType=1, last=204.0),
            ("MSFT", MD_DELAYED): _Ticker(marketDataType=3, delayedLast=396.0),
            ("BTC", MD_LIVE): _Ticker(marketDataType=1, bid=70_000.0, ask=70_010.0),
        }
    )
    reader = IbkrMarkReader(_FakeClient(ib), market_data_mode="auto", timeout_seconds=0.01, sleep=lambda _s: None)
    batch = reader.fetch(
        [
            MarkRequest(key="equity:AAPL", label="AAPL", sec_type="STK", symbol="AAPL", market_open=True),
            MarkRequest(key="equity:MSFT", label="MSFT", sec_type="STK", symbol="MSFT", market_open=True),
            MarkRequest(key="crypto:BTC", label="BTC", sec_type="CRYPTO", symbol="BTC", market_open=True),
        ]
    )
    assert batch.marks["equity:AAPL"].quality == "live" and batch.marks["equity:AAPL"].price == 204.0
    assert batch.marks["equity:MSFT"].quality == "delayed" and batch.marks["equity:MSFT"].md_type == MD_DELAYED
    assert batch.marks["crypto:BTC"].field == "mid" and batch.marks["crypto:BTC"].price == pytest.approx(70_005.0)
    # Vivo primero, diferido solo para lo que faltó, y al final el tipo por defecto de la sesión.
    assert ib.types == [MD_LIVE, MD_DELAYED, MD_LIVE]
    assert ("MSFT", MD_DELAYED, True) in ib.requests and ("AAPL", MD_DELAYED, True) not in ib.requests
    # La cripto de IBKR no admite instantánea: se suscribe y se cancela.
    assert ("BTC", MD_LIVE, False) in ib.requests and ib.cancelled == ["BTC"]


def test_the_reader_asks_frozen_data_for_a_closed_market_and_respects_the_options_stream():
    from src.services.ibkr_marks import MarkRequest

    ib = _FakeIB({(f"S{i}", MD_FROZEN): _Ticker(marketDataType=2, last=10.0 + i) for i in range(6)})
    calls: list[int] = []
    client = _FakeClient(ib)
    original = client._run_ib

    def counting(fn, timeout=None):
        calls.append(1)
        return original(fn, timeout=timeout)

    client._run_ib = counting
    reader = IbkrMarkReader(client, iv_service=_FakeIV(True), market_data_mode="auto", timeout_seconds=0.01, sleep=lambda _s: None)
    requests = [MarkRequest(key=f"equity:S{i}", label=f"S{i}", sec_type="STK", symbol=f"S{i}", market_open=False) for i in range(6)]
    batch = reader.fetch(requests)
    assert all(mark.quality == "frozen" for mark in batch.marks.values())
    # Cada lote pide congelado y deja el tipo por defecto al terminar; nunca pide "live" con el mercado cerrado.
    assert ib.types == [MD_FROZEN, MD_LIVE, MD_FROZEN, MD_LIVE]
    assert {md_type for _symbol, md_type, _snapshot in ib.requests} == {MD_FROZEN}
    # Seis cualificaciones y dos lotes de cuatro como máximo mientras Options emite.
    snapshot_tasks = len(calls) - len(requests)
    assert snapshot_tasks == -(-len(requests) // BATCH_SIZE_WHILE_OPTIONS_STREAM)
    # Desconectado: nada se pide.
    client.connected = False
    assert reader.fetch(requests).unavailable_reason == "Trader Workstation is not connected."


class _CachingIB(_FakeIB):
    """Like ib_insync: one Ticker per contract object, kept between requests; ticks arrive on sleep."""

    def __init__(self, prices) -> None:
        super().__init__({})
        self.tickers = {}
        self.prices = prices
        self.pending: list[tuple[_Ticker, float]] = []

    def reqMktData(self, contract, generic, snapshot, regulatory):
        self.requests.append((contract.symbol, self.types[-1], snapshot))
        ticker = self.tickers.get(id(contract))
        if ticker is None:
            ticker = _Ticker(marketDataType=self.types[-1])
            self.tickers[id(contract)] = ticker
        # La respuesta de TWS llega después, durante la espera.
        self.pending.append((ticker, self.prices[contract.symbol]))
        return ticker

    def sleep(self, seconds):
        for ticker, price in self.pending:
            ticker.last = price
        self.pending.clear()


def test_a_new_pass_never_reads_the_previous_pass_price_from_the_cached_ticker():
    """Seen live on 2026-11-24: the second pass repeated the first pass's prices to the cent."""
    from src.services.ibkr_marks import MarkRequest

    ib = _CachingIB({"AAPL": 351.75})
    reader = IbkrMarkReader(_FakeClient(ib), market_data_mode="auto", timeout_seconds=0.05)
    request = MarkRequest(key="equity:AAPL", label="AAPL", sec_type="STK", symbol="AAPL", market_open=True)
    assert reader.fetch([request]).marks["equity:AAPL"].price == 351.75
    ib.prices["AAPL"] = 352.10
    # El contrato cualificado está en caché; el Ticker de la pasada anterior no debe responder por TWS.
    assert reader.fetch([request]).marks["equity:AAPL"].price == 352.10
    # Y no queda ningún Ticker guardado que crezca pasada tras pasada.
    assert ib.tickers == {}


def test_a_contract_without_a_data_subscription_is_named_and_not_asked_again_for_an_hour():
    from src.services.ibkr_marks import MarkRequest

    not_subscribed = (354, "Requested market data is not subscribed.")
    ib = _FakeIB(
        {("AAPL", MD_DELAYED): _Ticker(marketDataType=3, last=204.0)},
        errors={("BTC", MD_LIVE): not_subscribed, ("BTC", MD_DELAYED): not_subscribed, ("AAPL", MD_LIVE): not_subscribed},
    )
    reader = IbkrMarkReader(_FakeClient(ib), market_data_mode="auto", timeout_seconds=0.01, sleep=lambda _s: None)
    requests = [
        MarkRequest(key="crypto:BTC", label="Bitcoin", sec_type="CRYPTO", symbol="BTC", market_open=True),
        MarkRequest(key="equity:AAPL", label="AAPL", sec_type="STK", symbol="AAPL", market_open=True),
    ]
    first = reader.fetch(requests)
    assert first.marks["crypto:BTC"].price is None
    assert first.marks["crypto:BTC"].reason == "IBKR error 354: Requested market data is not subscribed."
    # AAPL falló en vivo pero tiene datos diferidos: tiene marca y no queda en espera.
    assert first.marks["equity:AAPL"].quality == "delayed"
    # TWS ya cerró la petición rechazada: no se cancela (evita el error 300).
    assert ib.cancelled == []
    ib.requests.clear()
    second = reader.fetch(requests)
    assert [symbol for symbol, _type, _snapshot in ib.requests] == ["AAPL", "AAPL"]
    assert second.marks["crypto:BTC"].reason.startswith("IBKR error 354")
    assert ib.errorEvent.handlers == []


def test_closed_market_legs_are_asked_hourly_while_crypto_keeps_the_five_minute_cadence(tmp_path):
    saturday = datetime(2026, 11, 14, 12, 0)
    marks = FakeMarks(prices={"AAPL": 205.5, "MSFT": 398.0, "BTC": 70_000.0})
    clock, service, _, intraday, pair_id = _setup(tmp_path, marks=marks, now=saturday)
    crypto = service.create_idea(
        IdeaCreateRequest(title="BTC and AAPL", thesis="x", stance="long", legs=(_leg("BTC", None, "crypto", native_id="bitcoin"), _leg("AAPL")))
    )
    service.activate(crypto.idea_id)
    intraday.record_pass()
    assert sorted(marks.calls[-1]) == ["AAPL", "BTC", "MSFT"]
    clock.set(saturday + timedelta(minutes=5))
    assert intraday.due()  # el mercado cripto está abierto: cadencia de cinco minutos
    intraday.record_pass()
    assert marks.calls[-1] == ["BTC"]  # AAPL y MSFT (cerrados) no se vuelven a pedir
    pair_rows = intraday.store.load(pair_id, saturday.date())["rows"]
    assert len(pair_rows) == 1 and pair_rows[0]["cadence"] == CLOSED_MARK_SECONDS
    crypto_rows = intraday.store.load(crypto.idea_id, saturday.date())["rows"]
    assert len(crypto_rows) == 2 and crypto_rows[1]["cadence"] == INTRADAY_PASS_SECONDS
    assert crypto_rows[1]["legs"]["equity:AAPL"]["marked_at"] == "2026-11-14T12:00:00"
    assert "marked_at" not in crypto_rows[1]["legs"]["crypto:BTC"]
    clock.set(saturday + timedelta(hours=1))
    intraday.record_pass()
    assert sorted(marks.calls[-1]) == ["AAPL", "BTC", "MSFT"]
    assert len(intraday.store.load(pair_id, saturday.date())["rows"]) == 2
    # Las filas horarias del par no son huecos.
    assert intraday.view(service.get_idea(pair_id), session=saturday.date())["gaps"] == []


def test_best_price_never_uses_the_prior_session_close():
    assert best_price(_Ticker(last=10.0, close=9.0)) == (10.0, "last")
    assert best_price(_Ticker(bid=9.0, ask=11.0, close=9.5)) == (10.0, "mid")
    assert best_price(_Ticker(delayedLast=9.8, delayedClose=9.5)) == (9.8, "delayedLast")
    # Live check 2026-11-22 (domingo): el "close" diferido de TWS era el del jueves, no el del viernes.
    assert best_price(_Ticker(close=9.5)) == (None, None)
    assert best_price(_Ticker(delayedClose=9.5)) == (None, None)
    assert best_price(_Ticker()) == (None, None)


def test_a_ticker_with_only_the_prior_close_has_no_mark_and_says_why(tmp_path):
    from src.services.ibkr_marks import MarkRequest

    ib = _FakeIB({("AAPL", MD_DELAYED_FROZEN): _Ticker(marketDataType=4, close=349.21)})
    reader = IbkrMarkReader(_FakeClient(ib), market_data_mode="delayed", timeout_seconds=0.01, sleep=lambda _s: None)
    batch = reader.fetch([MarkRequest(key="equity:AAPL", label="AAPL", sec_type="STK", symbol="AAPL", market_open=False)])
    mark = batch.marks["equity:AAPL"]
    assert mark.price is None and "prior session's close" in mark.reason
    # En el libro, la pata (mercado cerrado) usa entonces su último cierre canónico, sin hueco.
    marks = FakeMarks(prices={"MSFT": 396.0})
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks, now=datetime(2026, 11, 14, 12, 0))
    intraday.record_pass()
    point = intraday.view(service.get_idea(idea_id))["points"][0]
    assert point["carried"] == ["AAPL"] and not point["gap"]


def test_market_hours():
    assert leg_market_open("us", TUE_OPEN) is True
    assert leg_market_open("us", datetime(2026, 11, 10, 21, 5)) is False
    assert leg_market_open("us", datetime(2026, 11, 14, 15, 0)) is False
    assert leg_market_open("crypto", datetime(2026, 11, 14, 15, 0)) is True
    assert leg_market_open("lse", TUE_OPEN) is None


# ---------------------------------------------------------------------------
# Intraday criteria
# ---------------------------------------------------------------------------


class _Research:
    def load_instrument_history_result(self, reference, lookback, max_age_seconds=None):
        import pandas as pd

        class _Result:
            series = pd.Series({pd.Timestamp(day): value for day, value in AAPL.items()})
            warnings = []
            source_label = "fake"
            source_provider = "fake"
            retrieved_at = TUE_OPEN
            origin = "tests"
            transformation_note = None
            freshness_label = "historical"

        return _Result()


class _Client:
    def is_connected(self):
        return True


def test_an_intraday_criterion_triggers_from_a_fresh_mark_and_never_from_a_frozen_one(tmp_path):
    marks = FakeMarks(prices={"AAPL": 210.0, "MSFT": 396.0})
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    registry = ObservableRegistry(research_provider=_Research(), client=_Client(), clock=clock)
    registry.intraday_quotes = intraday.latest_quote
    ref = registry.validate(ObservableRef(observable_id="equity_close", params={"symbol": "AAPL"}), condition="above", cadence="intraday")
    assert registry.intraday_capable("equity_close") and registry.intraday_capable("crypto_price")

    # Sin marca: la lectura es la diaria y dice por qué.
    plain = registry.read(ref, now=clock(), intraday=True)
    assert plain.intraday_from is None and "No fresh IBKR mark for AAPL" in plain.intraday_note

    intraday.record_pass()
    reading = registry.read(ref, now=clock(), intraday=True)
    assert reading.value == 210.0 and reading.intraday_from == TUE_OPEN
    assert reading.history[-1] == ObservablePoint(at=TUE_OPEN, value=210.0)
    assert reading.provenance.source_provider == "IBKR/TWS (live)"
    criterion = IdeaCriterion(
        criterion_id="c1", idea_id=idea_id, kind="invalidate", label="AAPL above 205", observable=ref, condition="above",
        threshold=205.0, cadence="intraday", created_at=TUE_OPEN - timedelta(hours=2), armed_at=TUE_OPEN - timedelta(hours=1),
    )
    evaluation = evaluate_criterion(criterion, reading, armed_from=criterion.armed_at, now=clock(), effective_cadence="intraday")
    assert evaluation.state == "triggered" and evaluation.first_met_at == TUE_OPEN

    # Una marca anterior al armado no cuenta (regla de instante, no de día).
    late = IdeaCriterion(**{**criterion.__dict__, "armed_at": TUE_OPEN + timedelta(minutes=1)})
    assert evaluate_criterion(late, reading, armed_from=late.armed_at, now=clock(), effective_cadence="intraday").state != "triggered"

    # Marca caducada o congelada: no se usa.
    clock.set(TUE_OPEN + timedelta(minutes=20))
    assert intraday.latest_quote("equity_close", {"symbol": "AAPL"}) is None
    marks.md_type = MD_FROZEN
    clock.set(datetime(2026, 11, 14, 12, 0))
    intraday.record_pass()
    assert intraday.latest_quote("equity_close", {"symbol": "AAPL"}) is None


def test_the_evaluation_service_says_when_an_intraday_rule_falls_back_to_the_close(tmp_path):
    from src.application.idea_evaluation import IdeaEvaluationService
    from src.application.idea_service import IdeaCriterionRequest

    marks = FakeMarks(prices={"AAPL": 210.0, "MSFT": 396.0})
    clock, service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    registry = ObservableRegistry(research_provider=_Research(), client=_Client(), clock=clock)
    registry.intraday_quotes = intraday.latest_quote
    service.criteria_registry = registry
    _, criterion = service.add_criterion(
        idea_id,
        IdeaCriterionRequest(
            kind="invalidate",
            observable=ObservableRef(observable_id="equity_close", params={"symbol": "AAPL"}),
            condition="above",
            threshold=205.0,
            cadence="intraday",
        ),
    )
    evaluation = IdeaEvaluationService(service.store, registry, clock=clock)
    evaluation.evaluate_all(trigger="intraday")
    first = service.get_idea(idea_id).criterion(criterion.criterion_id).last_evaluation
    assert first.effective_cadence == "daily_close" and "No fresh IBKR mark for AAPL" in first.cadence_note
    assert first.state != "triggered"  # los cierres diarios (202) no superan 205

    clock.set(TUE_OPEN + timedelta(minutes=1))
    intraday.record_pass()
    evaluation.evaluate_all(trigger="intraday")
    second = service.get_idea(idea_id).criterion(criterion.criterion_id)
    assert second.last_evaluation.effective_cadence == "intraday"
    assert second.last_evaluation.state == "triggered" and second.trigger_evaluation.met_value == 210.0
    assert second.trigger_evaluation.provenance.source_provider == "IBKR/TWS (live)"
    # La marca no toca la serie diaria de la idea.
    assert all(point.session <= TUE for point in intraday.tracking_service.compute(idea_id, persist=False).points)


class _ResearchWithTodaysBar(_Research):
    """Like Yahoo during the session: today's bar carries the latest price, above the threshold."""

    def load_instrument_history_result(self, reference, lookback, max_age_seconds=None):
        import pandas as pd

        result = super().load_instrument_history_result(reference, lookback, max_age_seconds)
        result.series = pd.Series({**{pd.Timestamp(day): value for day, value in AAPL.items()}, pd.Timestamp(TUE): 209.0})
        return result


def test_todays_provisional_bar_never_triggers_a_close_rule_and_the_mark_does(tmp_path):
    """Seen live on 2026-11-24: a rule armed mid-session triggered from Yahoo's in-progress bar, not a mark."""
    marks = FakeMarks(prices={"AAPL": 210.0, "MSFT": 396.0})
    clock, _service, _, intraday, idea_id = _setup(tmp_path, marks=marks)
    registry = ObservableRegistry(research_provider=_ResearchWithTodaysBar(), client=_Client(), clock=clock)
    registry.intraday_quotes = intraday.latest_quote
    ref = registry.validate(ObservableRef(observable_id="equity_close", params={"symbol": "AAPL"}), condition="above", cadence="intraday")
    criterion = IdeaCriterion(
        criterion_id="c1", idea_id=idea_id, kind="confirm", label="AAPL above 205", observable=ref, condition="above",
        threshold=205.0, cadence="intraday", created_at=TUE_OPEN, armed_at=TUE_OPEN, baseline_as_of=datetime(2026, 11, 9), baseline_for=TUE_OPEN,
    )

    # En sesión, sin marca: la barra de hoy (209) no es un cierre; el último cierre definitivo es el del lunes.
    daily = registry.read(ref, now=clock(), intraday=True)
    assert daily.value == 200.0 and daily.as_of == datetime(2026, 11, 9)
    assert any("2026-11-10 bar is not a close yet" in warning for warning in daily.warnings)
    assert evaluate_criterion(criterion, daily, armed_from=criterion.armed_at, now=clock(), effective_cadence="intraday").state != "triggered"

    # Una marca en vivo posterior al armado sí dispara, y queda como la observación que lo cumplió.
    clock.set(TUE_OPEN + timedelta(minutes=5))
    intraday.record_pass()
    reading = registry.read(ref, now=clock(), intraday=True)
    evaluation = evaluate_criterion(criterion, reading, armed_from=criterion.armed_at, now=clock(), effective_cadence="intraday")
    assert evaluation.state == "triggered"
    assert evaluation.first_met_at == TUE_OPEN + timedelta(minutes=5) and evaluation.met_value == 210.0

    # Tras el cierre (16:20 en Nueva York) la barra del martes ya es un cierre.
    after = registry.read(ref, now=datetime(2026, 11, 10, 21, 25), intraday=False)
    assert after.value == 209.0 and after.as_of == datetime(2026, 11, 10)


def test_the_scheduler_records_marks_before_the_intraday_criteria_pass():
    order: list[str] = []

    class _Intraday:
        def due(self, now):
            return True

        def record_pass(self):
            order.append("marks")

    class _Registry:
        def tws_connected(self):
            return True

    class _Service:
        registry = _Registry()

        def evaluate_all(self, *, trigger):
            order.append(trigger)

        def has_intraday_criteria(self):
            return True

    clock = _Clock(TUE_OPEN)
    scheduler = IdeaEvaluationScheduler(_Service(), clock=clock, intraday=_Intraday())
    scheduler.last_daily_session = MON
    scheduler.tick()
    assert order == ["marks", "intraday"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    with TestClient(create_app(runtime)) as test_client:
        test_client.runtime = runtime  # type: ignore[attr-defined]
        yield test_client


def test_routes_serve_the_intraday_layer_beside_the_daily_series(demo_client):
    runtime = demo_client.runtime
    service_clock = _Clock(datetime(2026, 1, 12, 14, 0))
    runtime.idea_service._clock = service_clock
    created = demo_client.post(
        "/ideas",
        json={
            "title": "AAPL over MSFT",
            "thesis": "Apple holds up better.",
            "stance": "relative",
            "legs": [
                {"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1},
                {"entity": {"entity_type": "equity", "label": "Microsoft", "normalized_id": "MSFT"}, "weight": -1},
            ],
        },
    ).json()
    idea_id = created["idea_id"]
    demo_client.post(f"/ideas/{idea_id}/activate")
    now = _Clock(datetime(2026, 1, 14, 16, 0))  # miércoles 14 de enero, sesión abierta
    runtime.idea_tracking._clock = now

    # En demo la capa intradía lo dice y no graba.
    body = demo_client.get(f"/ideas/{idea_id}/tracking").json()
    assert body["intraday"]["status"] == "demo" and body["intraday"]["label"] == TRACKING_LABEL
    daily_before = [point["session"] for point in body["points"]]

    # Con una fuente IBKR falsa (como en vivo), la capa graba y se sirve junto a la serie diaria.
    marks = FakeMarks(prices={"AAPL": 999.0, "MSFT": 1.0})
    live = IdeaIntradayService(runtime.idea_service, runtime.idea_tracking, runtime.idea_intraday.store, marks, clock=now, run_id="t")
    runtime.idea_intraday = live
    assert live.record_pass().status == "recorded"
    body = demo_client.get(f"/ideas/{idea_id}/tracking").json()
    assert body["intraday"]["status"] == "recording" and body["intraday"]["available"]
    assert body["intraday"]["points"][0]["quality"] == "live"
    assert [point["session"] for point in body["points"]] == daily_before  # la serie diaria no cambia
    detail = demo_client.get(f"/ideas/{idea_id}/tracking/intraday", params={"session": "2026-01-14"})
    assert detail.status_code == 200 and detail.json()["session"] == "2026-01-14"
    assert detail.json()["summary"]["marks"] == 1
    assert demo_client.get(f"/ideas/{idea_id}/tracking/intraday", params={"session": "2026-01-13"}).json()["status"] == "no_marks"
    assert demo_client.get("/ideas/missing/tracking/intraday").status_code == 404


# ---------------------------------------------------------------------------
# Live-check regression (2026-11-21): the worst replayed episode
# ---------------------------------------------------------------------------


def test_the_worst_episode_is_a_full_replay_and_a_partial_one_says_its_coverage():
    def episode(episode_id, status, book, coverage):
        return IdeaRiskEpisode(episode_id=episode_id, label=episode_id, start=date(2022, 1, 3), end=date(2022, 10, 12), status=status, book_return=book, coverage=coverage)

    from src.models.ideas import IdeaTrackedLeg

    leg = IdeaTrackedLeg(entity=HandoffEntity(entity_type="equity", label="AAPL", normalized_id="AAPL"), weight=1.0, asset_class="us_equity_liquid")
    base = dict(snapshot_id="s", idea_id="i", created_at=TUE_OPEN, legs=(leg,), benchmark="SPY", lookback_days=252)
    mixed = IdeaRiskSnapshot(**base, episodes=(episode("rates_2022", "partial", -0.36, 0.5), episode("tariffs_2025", "full", -0.12, 1.0)))
    assert mixed.worst_episode.episode_id == "tariffs_2025"
    only_partial = IdeaRiskSnapshot(**base, episodes=(episode("rates_2022", "partial", -0.36, 0.5),))
    assert only_partial.worst_episode.episode_id == "rates_2022"
    assert only_partial.to_dict()["episodes"][0]["coverage"] == 0.5
    assert IdeaRiskEpisode.from_dict(only_partial.to_dict()["episodes"][0]).coverage == 0.5
