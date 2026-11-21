"""Workstream 12 - Ideas, checkpoint I3a: hypothetical forward tracking.

Every test injects the clock and the prices, so it runs without network or
Trader Workstation. The fake price source returns closes from before the
activation and after "now" on purpose: the series must use neither.
"""

from __future__ import annotations

import json
from dataclasses import replace
import math
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_service import (
    IdeaCreateRequest,
    IdeaPatchRequest,
    IdeaService,
    IdeaTrackingSettingsRequest,
)
from src.application.idea_tracking import (
    IdeaTrackingService,
    LegCloses,
    closes_from_instants,
    closes_from_series,
    compute_tracking,
    market_close_at,
    market_horizon,
)
from src.application.runtime import build_runtime
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    DEFAULT_TRACKING_COST_BP,
    IDEA_SCHEMA_VERSION,
    TRACKING_LABEL,
    IdeaLeg,
    IdeaTracking,
    IdeaValidationError,
    freeze_tracking_legs,
)
from src.models.provenance import ProvenanceRecord
from src.services.idea_store import IdeaStore

# Semana del 9 al 13 de noviembre de 2026 (EE. UU. ya en horario de invierno: cierre 21:00 UTC).
MON, TUE, WED, THU, FRI = (date(2026, 11, day) for day in (9, 10, 11, 12, 13))
WEEK = (MON, TUE, WED, THU, FRI)
PRIOR = tuple(date(2026, 11, day) for day in (2, 3, 4, 5, 6))
NEXT = tuple(date(2026, 11, day) for day in (16, 17))
SATURDAY_NOON = datetime(2026, 11, 14, 12, 0)

AAPL = {**{day: 100.0 for day in PRIOR}, MON: 200.0, TUE: 202.0, WED: 204.0, THU: 206.0, FRI: 210.0, **{day: 999.0 for day in NEXT}}
MSFT = {**{day: 50.0 for day in PRIOR}, MON: 400.0, TUE: 396.0, WED: 392.0, THU: 388.0, FRI: 380.0, **{day: 1.0 for day in NEXT}}
SPY = {**{day: 300.0 for day in PRIOR}, MON: 500.0, TUE: 505.0, WED: 510.0, THU: 500.0, FRI: 515.0, **{day: 1.0 for day in NEXT}}


class _Clock:
    """A settable clock; each read advances one second so journal times stay ordered."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def set(self, moment: datetime) -> None:
        self.now = moment

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


class FakePrices:
    """In-memory closes keyed by symbol; records every call."""

    def __init__(self, closes: dict[str, dict[date, float]], benchmark: dict[date, float] | None = None) -> None:
        self.closes = closes
        self.benchmark = benchmark if benchmark is not None else SPY
        self.calls: list[tuple[str, date, datetime]] = []

    def _closes(self, symbol: str, market: str) -> LegCloses:
        series = self.closes.get(symbol)
        if series is None:
            return LegCloses.unavailable(f"No fake closes for {symbol}.")
        return LegCloses(
            closes=closes_from_series(series, market),
            provenance=ProvenanceRecord(source_provider="fake_closes", retrieved_at=SATURDAY_NOON, origin="tests.fake"),
        )

    def leg_closes(self, leg, *, since, now):
        self.calls.append((leg.key, since, now))
        if leg.market == "crypto":
            series = self.closes.get(leg.entity.normalized_id.upper())
            if series is None:
                return LegCloses.unavailable("no crypto closes")
            instants = [(datetime(day.year, day.month, day.day) + timedelta(days=1), price) for day, price in series.items()]
            return LegCloses(closes=closes_from_instants(instants))
        return self._closes(leg.entity.normalized_id.upper(), leg.market)

    def benchmark_closes(self, symbol, *, since, now):
        self.calls.append((f"benchmark:{symbol}", since, now))
        if self.benchmark is None:
            return LegCloses.unavailable("no benchmark")
        return LegCloses(closes=closes_from_series(self.benchmark, "us"))


def _ids():
    counter = iter(range(1, 10_000))
    return lambda: f"id{next(counter):04d}"


def _leg(symbol: str, weight: float | None = None, entity_type: str = "equity") -> IdeaLeg:
    return IdeaLeg(
        entity=HandoffEntity(entity_type=entity_type, label=f"{symbol} Corp", normalized_id=symbol),
        weight=weight,
    )


def _setup(tmp_path, closes=None, benchmark=None, *, legs=None, stance="long", activate_at=datetime(2026, 11, 9, 14, 0)):
    clock = _Clock(datetime(2026, 11, 6, 12, 0))
    store = IdeaStore(tmp_path / "ideas")
    service = IdeaService(store, clock=clock, id_factory=_ids())
    idea = service.create_idea(
        IdeaCreateRequest(
            title="Big tech pair",
            thesis="AAPL outruns MSFT into year end.",
            stance=stance,
            legs=tuple(legs if legs is not None else (_leg("AAPL", 1.0), _leg("MSFT", 1.0))),
        )
    )
    prices = FakePrices(closes if closes is not None else {"AAPL": AAPL, "MSFT": MSFT}, benchmark)
    tracking_clock = _Clock(SATURDAY_NOON)
    tracker = IdeaTrackingService(service, prices, clock=tracking_clock)
    if activate_at is not None:
        clock.set(activate_at)
        service.activate(idea.idea_id)
    return clock, service, tracker, tracking_clock, prices, idea.idea_id


# ---------------------------------------------------------------------------
# Acceptance: five trading days, no backfill, no TWS
# ---------------------------------------------------------------------------


def test_a_legs_idea_tracks_five_trading_days_without_backfill_or_tws(tmp_path):
    _, service, tracker, _, prices, idea_id = _setup(tmp_path)
    idea = service.get_idea(idea_id)
    segment = idea.tracking.open_segment
    assert segment.number == 1 and segment.start_reason == "activated"
    assert [leg.weight for leg in segment.legs] == [0.5, 0.5], "weights are shares of gross exposure"

    result = tracker.compute(idea_id)

    assert result.status == "tracking"
    assert [point.session for point in result.points] == list(WEEK)
    assert result.sessions == 5 and result.gaps == 0
    assert result.first_session == MON and result.as_of == FRI
    seg = result.segments[0]
    # Entra al cierre del lunes (posterior a la activación), nunca a un precio anterior.
    assert [leg.entry_price for leg in seg.legs] == [AAPL[MON], MSFT[MON]]
    assert all(point.session >= MON for point in result.points), "nothing before activation is added"
    assert all(point.session <= FRI for point in result.points), "nothing after now is used"
    gross = 0.5 * (AAPL[FRI] / AAPL[MON] - 1) + 0.5 * (MSFT[FRI] / MSFT[MON] - 1)
    assert result.gross_return == pytest.approx(gross)
    assert result.benchmark_return == pytest.approx(SPY[FRI] / SPY[MON] - 1)
    # Sin TWS: solo la fuente inyectada (proveedores de lectura), ningún cliente IBKR.
    assert {key for key, _, _ in prices.calls} == {"equity:AAPL", "equity:MSFT", "benchmark:SPY"}

    stored = service.get_idea(idea_id).tracking.snapshot
    assert stored is not None and stored.as_of == FRI and stored.sessions == 5
    assert stored.net_return == pytest.approx(result.net_return)
    row = next(item for item in service.store.list_summaries() if item.idea_id == idea_id)
    assert row.tracking["snapshot"]["net_return"] == pytest.approx(result.net_return)
    assert row.tracking["label"] == TRACKING_LABEL


def test_activation_after_the_close_enters_at_the_next_session(tmp_path):
    # 21:10 UTC del lunes es posterior al cierre de las 16:00 en Nueva York: el lunes ya se conocía.
    _, _, tracker, _, _, idea_id = _setup(tmp_path, activate_at=datetime(2026, 11, 9, 21, 10))
    result = tracker.compute(idea_id)
    assert result.segments[0].entry_session == TUE
    assert [point.session for point in result.points] == [TUE, WED, THU, FRI]


def test_tracking_waits_for_the_first_close_and_shows_it(tmp_path):
    _, _, tracker, tracking_clock, _, idea_id = _setup(tmp_path)
    tracking_clock.set(datetime(2026, 11, 9, 18, 0))
    result = tracker.compute(idea_id)
    assert result.status == "waiting" and not result.points
    assert "first close after 2026-11-09 14:00 UTC" in (result.status_reason or "")
    # 20 minutos tras el cierre el lunes ya es definitivo.
    tracking_clock.set(datetime(2026, 11, 9, 21, 25))
    assert [point.session for point in tracker.compute(idea_id).points] == [MON]


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


def test_a_leg_edit_closes_the_segment_and_opens_a_new_one(tmp_path):
    clock, service, tracker, _, _, idea_id = _setup(tmp_path)
    clock.set(datetime(2026, 11, 11, 15, 0))  # miércoles por la mañana en Nueva York
    edited = service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0), _leg("MSFT", -1.0))))

    first, second = edited.tracking.segments
    assert first.end_reason == "legs_edited" and first.ended_at is not None
    assert second.is_open and second.start_reason == "legs_edited" and second.number == 2
    assert [leg.weight for leg in second.legs] == [0.5, -0.5]
    assert second.start_note == "Legs edited: AAPL Corp +1; MSFT Corp +1 → AAPL Corp +1; MSFT Corp -1"
    entry = edited.journal[-1]
    assert entry.kind == "tracking_segment" and TRACKING_LABEL in entry.body
    assert entry.details["closed_segment"] == 1 and entry.details["opened_segment"] == 2

    result = tracker.compute(idea_id)
    seg1, seg2 = result.segments
    assert (seg1.status, seg1.entry_session, seg1.exit_session) == ("closed", MON, WED)
    assert (seg2.status, seg2.entry_session) == ("tracking", WED)
    assert [point.session for point in result.points] == list(WEEK)
    assert [point.segment for point in result.points] == [1, 1, 2, 2, 2]
    chained = (1 + seg1.net_return) * (1 + seg2.net_return) - 1
    assert result.net_return == pytest.approx(chained)
    # El segundo libro está corto en MSFT: gana cuando MSFT cae.
    assert seg2.gross_return == pytest.approx(0.5 * (AAPL[FRI] / AAPL[WED] - 1) - 0.5 * (MSFT[FRI] / MSFT[WED] - 1))


def test_renames_and_scaled_weights_keep_the_segment(tmp_path):
    clock, service, _, _, _, idea_id = _setup(tmp_path)
    clock.set(datetime(2026, 11, 10, 15, 0))
    renamed = IdeaLeg(entity=HandoffEntity(entity_type="equity", label="Apple", normalized_id="AAPL"), weight=2.0)
    updated = service.update_idea(idea_id, IdeaPatchRequest(legs=(renamed, _leg("MSFT", 2.0)), title="Renamed"))
    assert len(updated.tracking.segments) == 1, "same book: (2, 2) is (1, 1) scaled"
    assert updated.journal[-1].kind == "edited"


def test_an_edit_before_the_first_close_never_enters(tmp_path):
    clock, service, tracker, _, _, idea_id = _setup(tmp_path)
    clock.set(datetime(2026, 11, 9, 18, 0))  # antes del cierre del lunes
    service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    result = tracker.compute(idea_id)
    assert result.segments[0].status == "never_entered"
    assert result.segments[1].entry_session == MON
    assert result.gross_return == pytest.approx(AAPL[FRI] / AAPL[MON] - 1)


def test_archive_stops_tracking_and_restore_opens_a_new_segment(tmp_path):
    clock, service, tracker, _, _, idea_id = _setup(tmp_path)
    clock.set(datetime(2026, 11, 10, 22, 0))  # martes, después del cierre
    archived = service.archive(idea_id)
    assert archived.tracking.open_segment is None
    assert archived.tracking.segments[0].end_reason == "archived"
    stopped = tracker.compute(idea_id)
    assert stopped.status == "stopped"
    assert stopped.segments[0].exit_session == WED, "the book exits at the first close after the archive"
    assert [point.session for point in stopped.points] == [MON, TUE, WED]

    clock.set(datetime(2026, 11, 12, 14, 0))
    restored = service.restore(idea_id)
    assert restored.tracking.segments[-1].start_reason == "restored"
    result = tracker.compute(idea_id)
    assert [point.segment for point in result.points] == [1, 1, 1, 2, 2]
    assert result.segments[1].entry_session == THU


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------


def test_a_missing_close_stays_a_gap_and_is_never_interpolated(tmp_path):
    msft = {day: price for day, price in MSFT.items() if day != THU}
    _, _, tracker, _, _, idea_id = _setup(tmp_path, closes={"AAPL": AAPL, "MSFT": msft})
    result = tracker.compute(idea_id)
    thursday = next(point for point in result.points if point.session == THU)
    assert thursday.gap and thursday.net_return is None and thursday.missing == ("MSFT Corp",)
    assert result.gaps == 1 and result.sessions == 4
    assert any("no close for MSFT Corp on 2026-11-12" in item and "not interpolated" in item for item in result.warnings)
    friday = next(point for point in result.points if point.session == FRI)
    # El viernes se valora con los precios de entrada, no con un jueves inventado.
    assert friday.gross_return == pytest.approx(0.5 * (AAPL[FRI] / AAPL[MON] - 1) + 0.5 * (MSFT[FRI] / MSFT[MON] - 1))


def test_a_session_where_no_market_traded_is_not_a_gap(tmp_path):
    def holiday(series):
        return {day: price for day, price in series.items() if day != WED}

    _, _, tracker, _, _, idea_id = _setup(
        tmp_path, closes={"AAPL": holiday(AAPL), "MSFT": holiday(MSFT)}, benchmark=holiday(SPY)
    )
    result = tracker.compute(idea_id)
    assert [point.session for point in result.points] == [MON, TUE, THU, FRI]
    assert result.gaps == 0


def test_crypto_trades_every_day_and_equities_keep_their_close_on_weekends(tmp_path):
    days = [date(2026, 11, 9) + timedelta(days=offset) for offset in range(8)]  # lunes a lunes
    btc = {day: 90_000.0 + 1_000 * index for index, day in enumerate(days) if day != date(2026, 11, 15)}
    legs = (_leg("AAPL", 1.0), _leg("BTC", 1.0, entity_type="crypto"))
    _, _, tracker, tracking_clock, _, idea_id = _setup(tmp_path, closes={"AAPL": AAPL, "BTC": btc}, legs=legs)
    tracking_clock.set(datetime(2026, 11, 17, 12, 0))
    result = tracker.compute(idea_id)
    by_day = {point.session: point for point in result.points}
    # El sábado cotiza BTC; AAPL conserva el cierre del viernes (mercado cerrado, no hueco).
    assert not by_day[date(2026, 11, 14)].gap
    saturday = date(2026, 11, 14)
    expected = 0.5 * (AAPL[FRI] / AAPL[MON] - 1) + 0.5 * (btc[saturday] / btc[MON] - 1)
    assert by_day[saturday].gross_return == pytest.approx(expected)
    # El domingo falta el cierre de BTC: hueco.
    assert by_day[date(2026, 11, 15)].gap and by_day[date(2026, 11, 15)].missing == ("BTC Corp",)
    assert result.segments[0].legs[1].market == "crypto"
    assert result.segments[0].legs[1].asset_class == "crypto_spot"


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------


def test_costs_are_applied_per_side_and_shown_next_to_returns(tmp_path):
    _, service, tracker, _, _, idea_id = _setup(tmp_path)
    result = tracker.compute(idea_id)
    seg = result.segments[0]
    bp = DEFAULT_TRACKING_COST_BP["us_equity_liquid"] / 10_000
    assert bp > 0, "never zero by default"
    rel_a, rel_m = AAPL[FRI] / AAPL[MON], MSFT[FRI] / MSFT[MON]
    entry_cost = 0.5 * bp + 0.5 * bp
    exit_cost = 0.5 * rel_a * bp + 0.5 * rel_m * bp
    assert seg.entry_cost == pytest.approx(entry_cost)
    assert seg.exit_cost == pytest.approx(exit_cost)
    assert result.net_return == pytest.approx(result.gross_return - entry_cost - exit_cost)
    payload = result.to_dict()
    assert payload["label"] == TRACKING_LABEL
    assert payload["summary"]["cost_drag"] == pytest.approx(entry_cost + exit_cost)
    assert [leg["cost_bp"] for leg in payload["segments"][0]["legs"]] == [5.0, 5.0]

    gross_before = result.gross_return
    updated = service.update_tracking_settings(
        idea_id,
        IdeaTrackingSettingsRequest(per_side_bp={"us_equity_liquid": 20.0}, leg_classes={"equity:MSFT": "equity_other"}),
    )
    assert updated.journal[-1].kind == "tracking_settings"
    assert "20 bp" in updated.journal[-1].body and "gross record is unchanged" in updated.journal[-1].body
    assert updated.tracking.snapshot is None, "a headline computed with old assumptions is dropped"
    after = tracker.compute(idea_id)
    assert after.gross_return == pytest.approx(gross_before), "costs never change the gross record"
    bp_a, bp_m = 20.0 / 10_000, DEFAULT_TRACKING_COST_BP["equity_other"] / 10_000
    expected = gross_before - (0.5 * bp_a + 0.5 * bp_m) - (0.5 * rel_a * bp_a + 0.5 * rel_m * bp_m)
    assert after.net_return == pytest.approx(expected)
    assert [leg.asset_class for leg in after.segments[0].legs] == ["us_equity_liquid", "equity_other"]

    with pytest.raises(IdeaValidationError):
        service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(per_side_bp={"us_equity_liquid": -1}))
    with pytest.raises(IdeaValidationError):
        service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(leg_classes={"equity:MSFT": "options"}))
    with pytest.raises(IdeaValidationError):
        service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(leg_classes={"equity:XOM": "futures"}))


def test_asset_classes_follow_the_listing():
    frozen, reason = freeze_tracking_legs(
        (_leg("SPY", 1), _leg("SAP.DE", 1), _leg("BRK.B", 1), _leg("ETH", 1, entity_type="crypto")), "long"
    )
    assert reason is None
    assert [leg.asset_class for leg in frozen] == ["us_equity_liquid", "equity_other", "us_equity_liquid", "crypto_spot"]
    assert [leg.market for leg in frozen] == ["us", "xetra", "us", "crypto"]


# ---------------------------------------------------------------------------
# What cannot be tracked
# ---------------------------------------------------------------------------


def test_untrackable_legs_and_weights_are_states_with_a_reason(tmp_path):
    legs = (_leg("AAPL", 1.0), _leg("BRENT", -1.0, entity_type="commodity"))
    _, service, tracker, _, _, idea_id = _setup(tmp_path, legs=legs, stance="relative")
    result = tracker.compute(idea_id)
    assert result.status == "unavailable" and not result.points
    assert "commodity legs have no price source" in (result.status_reason or "")
    assert service.get_idea(idea_id).tracking.open_segment.untracked_reason

    _, reason = freeze_tracking_legs((_leg("AAPL"), _leg("MSFT")), "relative")
    assert reason and "signed weight" in reason
    _, mixed = freeze_tracking_legs((_leg("AAPL", 1.0), _leg("MSFT")), "long")
    assert mixed and "every leg" in mixed
    frozen, short = freeze_tracking_legs((_leg("AAPL"), _leg("MSFT")), "short")
    assert short is None and [leg.weight for leg in frozen] == [-0.5, -0.5]
    assert {leg.weight_source for leg in frozen} == {"stance"}


def test_a_failing_price_source_is_unavailable_not_an_error(tmp_path):
    _, _, tracker, _, _, idea_id = _setup(tmp_path, closes={"AAPL": AAPL})
    result = tracker.compute(idea_id)
    assert result.status == "unavailable"
    assert "MSFT Corp: No fake closes for MSFT." in (result.status_reason or "")


def test_a_draft_or_legless_idea_has_no_tracking(tmp_path):
    _, service, tracker, _, _, idea_id = _setup(tmp_path, activate_at=None)
    assert service.get_idea(idea_id).tracking is None
    assert tracker.compute(idea_id).status == "not_started"
    assert compute_tracking("x", IdeaTracking(), {}, None, now=SATURDAY_NOON).status == "not_started"


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


def test_close_instants_follow_each_market_and_daylight_saving():
    assert market_close_at("us", date(2026, 7, 1)) == datetime(2026, 7, 1, 20, 0)  # EDT
    assert market_close_at("us", date(2026, 11, 9)) == datetime(2026, 11, 9, 21, 0)  # EST
    assert market_close_at("xetra", date(2026, 11, 9)) == datetime(2026, 11, 9, 16, 30)
    assert market_close_at("tse", date(2026, 11, 9)) == datetime(2026, 11, 9, 6, 25)
    assert market_close_at("crypto", date(2026, 11, 9)) == datetime(2026, 11, 10)
    # Mercado desconocido: el cierre se toma al inicio de su día UTC (nunca antes de conocerlo).
    assert market_close_at("unknown", date(2026, 11, 9)) == datetime(2026, 11, 9)
    assert market_horizon("us", datetime(2026, 11, 9, 21, 10)) == date(2026, 11, 8)
    assert market_horizon("us", datetime(2026, 11, 9, 21, 25)) == date(2026, 11, 9)


def test_crypto_closes_drop_the_current_price_point():
    points = [
        (datetime(2026, 11, 10, 0, 0), 100.0),
        (datetime(2026, 11, 11, 0, 0), 101.0),
        (datetime(2026, 11, 11, 13, 37), 105.0),  # precio actual, no un cierre
    ]
    closes = closes_from_instants(points)
    assert [(item.session, item.price) for item in closes] == [(date(2026, 11, 9), 100.0), (date(2026, 11, 10), 101.0)]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def _as_v2(payload: dict) -> dict:
    legacy = json.loads(json.dumps(payload))
    legacy["schema_version"] = 2
    legacy.pop("tracking", None)
    for key in ("evidence", "journal", "criteria"):
        for item in legacy.get(key) or []:
            item["schema_version"] = 2
    legacy["journal"] = [entry for entry in legacy["journal"] if not entry["kind"].startswith("tracking_")]
    return legacy


def test_v2_active_ideas_migrate_with_a_segment_from_their_last_freeze(tmp_path):
    clock, service, _, _, _, idea_id = _setup(tmp_path)
    clock.set(datetime(2026, 11, 10, 15, 0))
    service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    draft = service.create_idea(IdeaCreateRequest(title="Draft", legs=(_leg("SPY", 1.0),)))
    base = tmp_path / "ideas"
    for current_id in (idea_id, draft.idea_id):
        path = base / "items" / f"{current_id}.json"
        path.write_text(json.dumps(_as_v2(json.loads(path.read_text(encoding="utf-8")))), encoding="utf-8")
    (base / "index.json").unlink()

    store = IdeaStore(base)
    migrated = store.require(idea_id)
    assert migrated.schema_version == IDEA_SCHEMA_VERSION
    (segment,) = migrated.tracking.segments
    assert segment.start_reason == "migrated" and segment.is_open
    # Patas sin cambios desde la última edición (martes 15:00): el registro empieza ahí, no antes.
    assert segment.started_at == datetime(2026, 11, 10, 15, 0, 1)
    assert "nothing earlier is added" in segment.start_note
    assert [leg.entity.normalized_id for leg in segment.legs] == ["AAPL"]
    assert store.require(draft.idea_id).tracking is None
    assert any(item.action == "migrated" for item in store.storage_warnings())


# ---------------------------------------------------------------------------
# Routes against the demo runtime (sample closes, no TWS)
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    with TestClient(create_app(runtime)) as test_client:
        test_client.runtime = runtime  # type: ignore[attr-defined]
        yield test_client


def test_tracking_routes_rebuild_the_series_from_demo_closes(demo_client):
    runtime = demo_client.runtime
    assert runtime.idea_observables.tws_connected() is False
    service_clock = _Clock(datetime(2026, 1, 12, 14, 0))  # lunes 12 de enero, antes de la apertura
    runtime.idea_service._clock = service_clock
    runtime.idea_tracking._clock = _Clock(datetime(2026, 1, 17, 12, 0))  # sábado

    created = demo_client.post(
        "/ideas",
        json={
            "title": "AAPL over MSFT",
            "thesis": "Apple holds up better than Microsoft into earnings.",
            "stance": "relative",
            "legs": [
                {"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1},
                {"entity": {"entity_type": "equity", "label": "Microsoft", "normalized_id": "MSFT"}, "weight": -1},
            ],
        },
    )
    assert created.status_code == 200
    idea_id = created.json()["idea_id"]
    assert demo_client.get(f"/ideas/{idea_id}/tracking").json()["status"] == "not_started"
    activated = demo_client.post(f"/ideas/{idea_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["tracking"]["segments"][0]["legs"][1]["weight"] == -0.5

    response = demo_client.get(f"/ideas/{idea_id}/tracking")
    assert response.status_code == 200
    body = response.json()
    assert body["label"] == TRACKING_LABEL and body["status"] == "tracking"
    sessions = [point["session"] for point in body["points"]]
    assert sessions == ["2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]
    assert body["summary"]["sessions"] == 5 and body["summary"]["gaps"] == 0
    assert body["summary"]["cost_drag"] > 0
    assert body["benchmark"]["symbol"] == "SPY" and body["benchmark"]["available"]
    assert any("demo sample history" in item for item in body["warnings"])
    assert {row["source_provider"] for row in body["provenance"]} == {"Mock sample-data daily history"}
    assert all(math.isfinite(point["net_return"]) for point in body["points"])

    board = demo_client.get("/ideas").json()
    row = next(item for item in board["items"] if item["idea_id"] == idea_id)
    assert row["tracking"]["snapshot"]["net_return"] == pytest.approx(body["summary"]["net_return"])
    assert row["tracking"]["snapshot"]["as_of"] == "2026-01-16"

    patched = demo_client.patch(f"/ideas/{idea_id}/tracking", json={"per_side_bp": {"us_equity_liquid": 25}})
    assert patched.status_code == 200
    assert patched.json()["summary"]["gross_return"] == pytest.approx(body["summary"]["gross_return"])
    assert patched.json()["summary"]["net_return"] < body["summary"]["net_return"]
    bad = demo_client.patch(f"/ideas/{idea_id}/tracking", json={"per_side_bp": {"us_equity_liquid": 900}})
    assert bad.status_code == 422

    markdown = demo_client.get(f"/ideas/{idea_id}/export?format=md").text
    assert f"## Tracking — {TRACKING_LABEL}" in markdown and "Gamma placed no orders" in markdown
    assert "| 1 |" in markdown and "25 bp" in markdown
    exported = json.loads(demo_client.get(f"/ideas/{idea_id}/export?format=json").text)
    assert exported["format_version"] == 3 and exported["tracking_label"] == TRACKING_LABEL
    assert exported["tracking_series"]["label"] == TRACKING_LABEL
    assert len(exported["tracking_series"]["points"]) == 5
    assert demo_client.get("/ideas/missing/tracking").status_code == 404


# ---------------------------------------------------------------------------
# Regressions from the stack review (2026-11-21)
# ---------------------------------------------------------------------------


def test_a_v2_file_that_cannot_migrate_is_quarantined_not_fatal(tmp_path):
    clock, service, _, _, _, idea_id = _setup(tmp_path)
    good = service.create_idea(IdeaCreateRequest(title="Untouched", thesis="x"))
    base = tmp_path / "ideas"
    path = base / "items" / f"{idea_id}.json"
    legacy = _as_v2(json.loads(path.read_text(encoding="utf-8")))
    legacy["legs"][0]["weight"] = 500  # fuera de rango: IdeaLeg lo rechaza al migrar
    path.write_text(json.dumps(legacy), encoding="utf-8")
    (base / "index.json").unlink()

    store = IdeaStore(base)  # no debe lanzar
    assert store.get(idea_id) is None and store.get(good.idea_id) is not None
    assert list((base / "quarantine").glob(f"{idea_id}.json.migration-failed-v2.*.preserved"))
    assert any("could not be migrated" in item.message for item in store.storage_warnings())


def test_a_slow_rebuild_never_overwrites_the_headline_of_a_changed_record(tmp_path):
    clock, service, tracker, _, prices, idea_id = _setup(tmp_path)
    original = prices.leg_closes
    edited = {"done": False}

    def edit_while_reading(leg, *, since, now):
        if not edited["done"]:
            edited["done"] = True
            clock.set(datetime(2026, 11, 13, 15, 0))
            service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
        return original(leg, since=since, now=now)

    prices.leg_closes = edit_while_reading
    tracker.compute(idea_id)
    stored = service.get_idea(idea_id).tracking
    assert len(stored.segments) == 2 and stored.snapshot is None, "the headline of the old book is dropped"
    prices.leg_closes = original
    tracker.compute(idea_id)
    assert service.get_idea(idea_id).tracking.snapshot is not None


def test_consecutive_segments_never_hold_two_books_at_once(tmp_path):
    msft = {day: price for day, price in MSFT.items() if day != WED}
    clock, service, tracker, _, _, idea_id = _setup(tmp_path, closes={"AAPL": AAPL, "MSFT": msft})
    clock.set(datetime(2026, 11, 11, 15, 0))  # miércoles: se quita MSFT, que no cierra ese día
    service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    result = tracker.compute(idea_id)
    first, second = result.segments
    assert first.exit_session == THU, "the old book can only exit when MSFT prices again"
    assert second.entry_session == THU, "the new book is bought at the close where the old one is sold"
    sessions = [point.session for point in result.points]
    assert len(sessions) == len(set(sessions))
    assert result.net_return == pytest.approx((1 + first.net_return) * (1 + second.net_return) - 1)


def test_a_segment_waits_while_the_previous_one_cannot_exit(tmp_path):
    msft = {day: price for day, price in MSFT.items() if day <= TUE}
    clock, service, tracker, _, _, idea_id = _setup(tmp_path, closes={"AAPL": AAPL, "MSFT": msft})
    clock.set(datetime(2026, 11, 11, 15, 0))
    service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    result = tracker.compute(idea_id)
    assert result.segments[0].status == "exiting"
    assert result.segments[1].status == "waiting"
    assert "Enters at the close where segment 1 exits" in (result.segments[1].reason or "")


def test_a_provider_that_stops_is_named_not_shown_as_current(tmp_path):
    def until_wednesday(series):
        return {day: price for day, price in series.items() if day <= WED}

    _, service, tracker, tracking_clock, _, idea_id = _setup(
        tmp_path, closes={"AAPL": until_wednesday(AAPL), "MSFT": until_wednesday(MSFT)}
    )
    tracking_clock.set(datetime(2026, 11, 20, 12, 0))  # viernes siguiente: cinco sesiones sin cierre
    result = tracker.compute(idea_id)
    assert result.stale_since == WED and result.as_of == WED
    assert "no close since 2026-11-11" in (result.status_reason or "")
    assert any("No close from the provider for AAPL Corp since 2026-11-11" in item for item in result.warnings)
    assert service.get_idea(idea_id).tracking.snapshot.stale_since == WED
    tracking_clock.set(datetime(2026, 11, 14, 12, 0))
    assert tracker.compute(idea_id).stale_since is None, "two quiet sessions are not stale yet"


def test_an_unchanged_headline_is_not_rewritten(tmp_path):
    _, service, tracker, _, _, idea_id = _setup(tmp_path)
    tracker.compute(idea_id)
    path = tmp_path / "ideas" / "items" / f"{idea_id}.json"
    before = (path.stat().st_mtime_ns, (tmp_path / "ideas" / "index.json").stat().st_mtime_ns)
    tracker.compute(idea_id)
    assert (path.stat().st_mtime_ns, (tmp_path / "ideas" / "index.json").stat().st_mtime_ns) == before


def test_a_non_leg_edit_never_opens_a_segment(tmp_path):
    clock, service, _, _, _, idea_id = _setup(tmp_path)
    service.store.update(idea_id, lambda idea: replace(idea, tracking=None))
    clock.set(datetime(2026, 11, 12, 15, 0))
    edited = service.update_idea(idea_id, IdeaPatchRequest(title="Renamed pair"))
    assert edited.tracking is None and edited.journal[-1].kind == "edited"
    added = service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    assert added.tracking.segments[-1].start_reason == "legs_added"
