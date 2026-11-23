"""Workstream 12 - Ideas, checkpoint I4a: signals, validation and the trial ledger.

Every test injects the clock and the prices. Script runs come from the
deterministic E5 fixture runtime (``script_e5_fixtures``), which executes no
Python and spends no API credit; nothing here starts a real Script run.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from script_e5_fixtures import DATES, ParameterFixtureRuntime, e5_service
from src.api.main import create_app
from src.application import script_experiments
from src.application.idea_service import IdeaCreateRequest, IdeaPatchRequest, IdeaService, IdeaTrackingSettingsRequest
from src.application.idea_signals import IdeaSignalService, InstrumentMapping, SignalRequest, ValidationRequest
from src.application.idea_tracking import IdeaTrackingService
from src.application.runtime import build_runtime
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    IDEA_SCHEMA_VERSION,
    TRACKING_LABEL,
    Idea,
    IdeaLeg,
    IdeaTestSnapshot,
    IdeaTrackedLeg,
    IdeaValidationError,
    migrate_idea_v5_to_v6,
)
from src.models.research_script import ResearchScriptInputBundleRequest, ResearchScriptRunCreateRequest, ResearchScriptSweepAxis, ResearchScriptSweepCreateRequest
from src.services.idea_store import IdeaStore
from test_idea_tracking import AAPL, MSFT, SATURDAY_NOON, FakePrices, _Clock, _ids, _leg

MON_PM = datetime(2026, 11, 9, 14, 0)
TUE_PM = datetime(2026, 11, 10, 14, 0)
THU_PM = datetime(2026, 11, 12, 14, 0)
BP = 5.0 / 10_000.0  # coste por lado por defecto de la renta variable líquida de EE. UU.


def _rows(*items):
    return [dict(item) for item in items]


def _setup(tmp_path, *, script_service=None, research_service=None, activate=True):
    clock = _Clock(datetime(2026, 11, 6, 12, 0))
    service = IdeaService(IdeaStore(tmp_path / "ideas"), clock=clock, id_factory=_ids())
    idea = service.create_idea(
        IdeaCreateRequest(
            title="Big tech book",
            thesis="A quant book on AAPL and MSFT.",
            stance="long",
            legs=(_leg("AAPL", 1.0), _leg("MSFT", 1.0)),
        )
    )
    prices = FakePrices({"AAPL": AAPL, "MSFT": MSFT})
    signals = IdeaSignalService(
        service, script_service=script_service, research_service=research_service, prices=prices, clock=clock
    )
    tracker = IdeaTrackingService(service, prices, clock=_Clock(SATURDAY_NOON))
    if activate:
        clock.set(MON_PM)
        service.activate(idea.idea_id)
    return clock, service, signals, tracker, idea.idea_id


def _weights(rows, **kwargs):
    return SignalRequest(source="import", output_kind="weights", rows=rows, date_column="date", **kwargs)


# ---------------------------------------------------------------------------
# Signal-driven tracking
# ---------------------------------------------------------------------------


def test_a_weights_import_opens_a_segment_that_rebalances_by_turnover(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)
    idea = signals.attach(idea_id, _weights(_rows({"date": "2026-11-09", "AAPL": "0.6", "MSFT": "-0.2"})))

    signal = idea.current_signal
    assert signal is not None and signal.is_book and signal.as_of == date(2026, 11, 9)
    assert [(leg.entity.normalized_id, leg.weight) for leg in signal.legs] == [("AAPL", 0.6), ("MSFT", -0.2)]
    # Las patas siguen a la señal, y el segmento 2 congela el libro exacto (NAV, sin normalizar).
    assert [(leg.entity.normalized_id, leg.weight) for leg in idea.legs] == [("AAPL", 0.6), ("MSFT", -0.2)]
    first, second = idea.tracking.segments
    assert (first.end_reason, second.start_reason, second.signal_id, second.rebalance) == (
        "signal_changed", "signal_attached", signal.signal_id, True)
    assert [(leg.weight, leg.weight_source) for leg in second.legs] == [(0.6, "signal"), (-0.2, "signal")]
    kinds = [entry.kind for entry in idea.journal]
    assert "signal_attached" in kinds and kinds[-1] == "tracking_segment"
    assert idea.journal[-1].body.startswith(TRACKING_LABEL)

    result = tracker.compute(idea_id)
    s1, s2 = result.segments
    # S1 sale al cierre del martes y S2 entra en ese mismo cierre: nada antes de la señal.
    assert s1.exit_session == s2.entry_session == date(2026, 11, 10)
    assert s1.exit_rebalanced and s1.exit_cost == 0.0
    assert s1.net_return == pytest.approx(0.0 - 1.0 * BP)  # bruto 0 al martes; solo el coste de entrada
    # Rotación desde el libro derivado de S1 (AAPL 0,505 / MSFT 0,495) hasta 0,6 / -0,2.
    assert s2.rebalanced and s2.turnover == pytest.approx(0.79)
    assert s2.entry_cost == pytest.approx(0.79 * BP)
    gross = 0.6 * (210 / 202 - 1) - 0.2 * (380 / 396 - 1)
    exit_cost = (0.6 * 210 / 202 + 0.2 * 380 / 396) * BP
    assert s2.gross_return == pytest.approx(gross)
    assert s2.net_return == pytest.approx(gross - 0.79 * BP - exit_cost)
    assert result.net_return == pytest.approx((1 - BP) * (1 + gross - 0.79 * BP - exit_cost) - 1)
    view = result.to_dict()["segments"][1]
    assert view["rebalanced"] is True and view["signal_id"] == signal.signal_id


def test_changing_and_detaching_the_signal_each_open_a_new_segment(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)
    signals.attach(idea_id, _weights(_rows({"date": "2026-11-09", "AAPL": "0.5", "MSFT": "0.5"}), label="v1"))
    clock.set(THU_PM)
    idea = signals.attach(idea_id, _weights(_rows({"date": "2026-11-11", "AAPL": "0.5", "MSFT": "0.5"}), label="v2"))
    # Mismo libro, señal distinta: también abre segmento (y rebalancea sin rotación).
    assert [segment.start_reason for segment in idea.tracking.segments] == ["activated", "signal_attached", "signal_changed"]
    assert [signal.is_current for signal in idea.signals] == [False, True]
    result = tracker.compute(idea_id)
    assert result.segments[2].turnover == pytest.approx(
        abs(0.5 - 0.5 * (206 / 202) / (1 + 0.5 * (206 / 202 - 1) + 0.5 * (388 / 396 - 1)))
        + abs(0.5 - 0.5 * (388 / 396) / (1 + 0.5 * (206 / 202 - 1) + 0.5 * (388 / 396 - 1)))
    )
    with pytest.raises(IdeaValidationError, match="follow the attached signal"):
        service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    clock.set(datetime(2026, 11, 13, 14, 0))
    detached = signals.detach(idea_id)
    assert detached.current_signal is None and len(detached.signals) == 2
    last = detached.tracking.segments[-1]
    # Las patas conservan el último libro; sin señal vuelven a las reglas de I3a (cuota del bruto).
    assert last.start_reason == "signal_detached" and last.signal_id is None
    assert [leg.weight_source for leg in last.legs] == ["stated", "stated"]
    assert [leg.weight for leg in last.legs] == [0.5, 0.5]
    edited = service.update_idea(idea_id, IdeaPatchRequest(legs=(_leg("AAPL", 1.0),)))
    assert edited.tracking.segments[-1].start_reason == "legs_edited"


def test_a_returns_signal_is_validation_only_and_never_touches_tracking(tmp_path):
    from script_e5_fixtures import NoProvider
    from src.application.research_service import ResearchService
    from src.services.saved_research_store import SavedResearchStore

    owner = ResearchService(NoProvider(), SavedResearchStore(base_dir=tmp_path / "saved"))
    clock, service, signals, tracker, idea_id = _setup(tmp_path, research_service=owner)
    before = tracker.compute(idea_id).to_dict()
    clock.set(TUE_PM)
    rows = [{"date": (date(2026, 10, 1) + timedelta(days=offset)).isoformat(), "ret": f"{0.1 * ((-1) ** offset):.2f}%"} for offset in range(30)]
    idea = signals.attach(idea_id, SignalRequest(source="import", output_kind="returns", rows=rows, date_column="date", value_column="ret"))
    signal = idea.current_signal
    assert signal.output_kind == "returns" and not signal.is_book and signal.legs == ()
    assert signal.supplied is not None and signal.supplied.observations == 30
    assert "not rebuilt by Gamma" in signal.supplied.label
    assert signal.supplied.to_dict()["drives_tracking"] is False
    # Sin segmento nuevo, patas intactas y la serie canónica idéntica.
    assert [segment.start_reason for segment in idea.tracking.segments] == ["activated"]
    assert [leg.weight for leg in idea.legs] == [1.0, 1.0]
    after = tracker.compute(idea_id).to_dict()
    assert after["points"] == before["points"] and after["summary"] == before["summary"]


def test_rows_after_the_attach_day_are_refused(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)
    with pytest.raises(IdeaValidationError, match="never follows a schedule into the future"):
        signals.attach(idea_id, _weights(_rows(
            {"date": "2026-11-09", "AAPL": "0.5", "MSFT": "0.5"},
            {"date": "2026-11-20", "AAPL": "1", "MSFT": "0"},
        )))
    assert service.get_idea(idea_id).current_signal is None


def test_imports_use_the_strategy_lab_rules_and_refuse_a_ragged_last_row(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)
    idea = signals.attach(idea_id, _weights(_rows(
        {"date": "2026-11-05", "AAPL": "10%", "MSFT": "90%"},
        {"date": "not a date", "AAPL": "1", "MSFT": "1"},
        {"date": "2026-11-09", "AAPL": "70%", "MSFT": "30%"},
        {"date": "2026-11-09", "AAPL": "60%", "MSFT": "1,0%"},
    )))
    signal = idea.current_signal
    # Reglas de Strategy Lab: % se divide entre 100, la coma es separador de miles ("1,0%" es 10 %),
    # la fecha inválida se descarta y la fecha repetida conserva la última fila.
    assert [(leg.entity.normalized_id, round(leg.weight, 6)) for leg in signal.legs] == [("AAPL", 0.6), ("MSFT", 0.1)]
    assert any("invalid dates" in item for item in signal.warnings)
    assert any("duplicate dates" in item for item in signal.warnings)
    assert any("No out-of-sample validation" in item for item in signal.warnings)
    with pytest.raises(IdeaValidationError, match="no value on the latest row"):
        signals.attach(idea_id, _weights(_rows({"date": "2026-11-06", "AAPL": "0.5", "MSFT": "0.5"}, {"date": "2026-11-09", "AAPL": "0.4", "MSFT": ""})))
    with pytest.raises(IdeaValidationError, match="append % for percentages"):
        signals.attach(idea_id, _weights(_rows({"date": "2026-11-09", "AAPL": "60", "MSFT": "40"})))


def test_positions_are_valued_at_the_latest_final_close_and_held_as_gross_shares(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)  # el último cierre definitivo es el del lunes
    idea = signals.attach(idea_id, SignalRequest(
        source="import", output_kind="positions", date_column="date",
        rows=_rows({"date": "2026-11-09", "AAPL": "10", "MSFT": "-5"}),
    ))
    legs = idea.current_signal.legs
    assert [(leg.units, leg.price, leg.price_date) for leg in legs] == [(10.0, 200.0, date(2026, 11, 9)), (-5.0, 400.0, date(2026, 11, 9))]
    assert [leg.weight for leg in legs] == [pytest.approx(0.5), pytest.approx(-0.5)]


def test_crypto_columns_map_to_coingecko_ids(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    clock.set(TUE_PM)
    idea = signals.attach(idea_id, _weights(
        _rows({"date": "2026-11-09", "AAPL": "0.5", "BTC": "0.25"}),
        instruments={"BTC": InstrumentMapping(symbol="bitcoin", entity_type="crypto", label="Bitcoin")},
    ))
    btc = idea.current_signal.legs[1]
    assert (btc.entity.entity_type, btc.entity.native_id, btc.instrument_id) == ("crypto", "bitcoin", "BTC")
    assert idea.tracking.segments[-1].legs[1].market == "crypto"


# ---------------------------------------------------------------------------
# Trial ledger
# ---------------------------------------------------------------------------


def test_the_trial_count_never_goes_back_to_zero(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    first = _rows({"date": "2026-11-09", "AAPL": "0.5", "MSFT": "0.5"})
    second = _rows({"date": "2026-11-09", "AAPL": "0.7", "MSFT": "0.3"})
    clock.set(TUE_PM)
    assert signals.attach(idea_id, _weights(first)).current_signal.trial_count == 1
    assert signals.attach(idea_id, _weights(second)).current_signal.trial_count == 2
    signals.detach(idea_id)
    # Volver a adjuntar el mismo CSV no es una prueba nueva, pero tampoco borra las anteriores.
    again = signals.attach(idea_id, _weights(first))
    assert again.current_signal.trial_count == 2 and again.trial_count == 2
    assert [trial.kind for trial in again.trials] == ["import", "import"]
    # El almacén rechaza cualquier escritura que quite una prueba.
    with pytest.raises(IdeaValidationError, match="only grows"):
        service.store.update(idea_id, lambda current: replace(current, trials=current.trials[:1]))
    with pytest.raises(IdeaValidationError, match="cannot be removed"):
        service.store.update(idea_id, lambda current: replace(current, signals=current.signals[:-1]))


def test_a_backtest_with_new_weights_is_a_trial_and_its_snapshot_shows_the_count(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)

    def snapshot(weight: float) -> IdeaTestSnapshot:
        legs = (
            IdeaTrackedLeg(entity=_leg("AAPL").entity, weight=weight, asset_class="us_equity_liquid"),
            IdeaTrackedLeg(entity=_leg("MSFT").entity, weight=1 - weight, asset_class="us_equity_liquid"),
        )
        return IdeaTestSnapshot(snapshot_id=f"t{weight}", idea_id=idea_id, created_at=MON_PM, legs=legs, benchmark="SPY", lookback_days=756)

    assert service.add_test_snapshot(idea_id, snapshot(0.5)).tests[-1].trial_count == 1
    assert service.add_test_snapshot(idea_id, replace(snapshot(0.5), snapshot_id="again")).tests[-1].trial_count == 1
    idea = service.add_test_snapshot(idea_id, snapshot(0.7))
    assert idea.tests[-1].trial_count == 2 and "Trials recorded for this idea: 2 trials" in idea.journal[-1].body
    clock.set(TUE_PM)
    attached = signals.attach(idea_id, _weights(_rows({"date": "2026-11-09", "AAPL": "0.5", "MSFT": "0.5"})))
    assert attached.current_signal.trial_count == 3


def test_version_5_files_migrate_with_a_ledger_seeded_from_their_backtests(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path, activate=False)
    legs = (IdeaTrackedLeg(entity=_leg("AAPL").entity, weight=1.0, asset_class="us_equity_liquid"),)
    tests = [
        IdeaTestSnapshot(snapshot_id=name, idea_id=idea_id, created_at=MON_PM, legs=legs, benchmark="SPY", lookback_days=756).to_dict()
        for name in ("a", "b")
    ]
    payload = service.get_idea(idea_id).to_dict()
    for key in ("signals", "trials", "trials_lower_bound"):
        payload.pop(key)
    for item in tests:
        item.pop("trial_count")
        item.pop("trial_count_lower_bound")
    journal = payload["journal"]
    runs = [dict(journal[0], entry_id=f"run{index}", kind="test_refreshed", body="Ran a backtest.") for index in range(3)]
    payload.update(schema_version=5, tests=tests, journal=[*journal, *runs])
    for key in ("evidence", "journal", "criteria", "reviews", "tests", "risks"):
        payload[key] = [dict(item, schema_version=5) for item in payload[key]]

    migrated = migrate_idea_v5_to_v6(payload)
    migrated["schema_version"] = IDEA_SCHEMA_VERSION
    idea = Idea.from_dict(migrated)
    # Dos snapshots con los mismos pesos son una prueba; el diario registra tres ejecuciones, así que es una cota inferior.
    assert idea.trial_count == 1 and idea.trials[0].kind == "legs" and idea.trials_lower_bound is True
    assert idea.signals == () and idea.tests[0].trial_count is None

    # El almacén migra el fichero al leerlo.
    path = tmp_path / "ideas" / "items" / f"{idea_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    reloaded = IdeaStore(tmp_path / "ideas").require(idea_id)
    assert reloaded.schema_version == IDEA_SCHEMA_VERSION and reloaded.trials_lower_bound is True


# ---------------------------------------------------------------------------
# Costs per leg
# ---------------------------------------------------------------------------


def test_a_per_leg_cost_override_changes_net_figures_only(tmp_path):
    clock, service, signals, tracker, idea_id = _setup(tmp_path)
    before = tracker.compute(idea_id)
    idea = service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(leg_bp={"equity:AAPL": 25.0}))
    assert dict(idea.tracking.cost_model.leg_bp) == {"equity:AAPL": 25.0}
    assert idea.journal[-1].kind == "tracking_settings" and "cost of AAPL" in idea.journal[-1].body
    after = tracker.compute(idea_id)
    assert after.gross_return == pytest.approx(before.gross_return)
    assert after.net_return < before.net_return
    legs = after.to_dict()["segments"][0]["legs"]
    assert [(leg["cost_bp"], leg["cost_source"]) for leg in legs] == [(25.0, "leg"), (5.0, "class")]
    cleared = service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(leg_bp={"equity:AAPL": None}))
    assert dict(cleared.tracking.cost_model.leg_bp) == {} and "class default" in cleared.journal[-1].body
    with pytest.raises(IdeaValidationError, match="not a tracked leg"):
        service.update_tracking_settings(idea_id, IdeaTrackingSettingsRequest(leg_bp={"equity:NVDA": 3.0}))


# ---------------------------------------------------------------------------
# Script signals (deterministic E5 fixture, no API credit)
# ---------------------------------------------------------------------------


def _sweep(service, detail):
    snapshot = service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest()).snapshot_id
    sweep = script_experiments.create_sweep(service, detail.script.script_id, ResearchScriptSweepCreateRequest(
        revision_id=detail.script.canonical_revision_id, input_snapshot_id=snapshot,
        axes=[ResearchScriptSweepAxis("lookback", [5, 10, 20]), ResearchScriptSweepAxis("leverage", [1, 2])]))
    runs = [script_experiments.run_sweep_point(service, sweep.sweep_id, point.index) for point in sweep.points]
    return sweep, runs


SPY_MAP = {"research:asset": InstrumentMapping(symbol="SPY", entity_type="etf", label="SPDR S&P 500")}


def test_a_script_weights_signal_attaches_with_walk_forward_validation_and_every_trial(tmp_path):
    script_service, detail = e5_service(tmp_path)
    sweep, runs = _sweep(script_service, detail)
    plain = script_service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 7, "leverage": 1.0}))
    clock, service, signals, tracker, idea_id = _setup(tmp_path, script_service=script_service, research_service=script_service.research_service)
    clock.set(TUE_PM)
    idea = signals.attach(idea_id, SignalRequest(
        source="script", output_kind="weights", run_id=runs[0].run_id, instruments=SPY_MAP,
        validation=ValidationRequest(sweep_id=sweep.sweep_id, train_observations=60, test_observations=30),
    ))
    signal = idea.current_signal
    ref = signal.source_ref
    assert (ref["script_id"], ref["revision_id"], ref["run_id"], ref["parameters_sha256"]) == (
        detail.script.script_id, runs[0].revision_id, runs[0].run_id, runs[0].parameters_sha256)
    assert ref["revision_status"] not in {"staged", "rejected"} and ref["sweep_id"] == sweep.sweep_id
    # Libro: la última decisión del calendario (DATES[-1]), sin normalizar, con SPY como pata.
    assert signal.as_of == date.fromisoformat(DATES[-1])
    assert [(leg.entity.normalized_id, abs(leg.weight), leg.instrument_id) for leg in signal.legs] == [("SPY", 1.0, "research:asset")]
    # Seis puntos del barrido (todos ejecutados) más la ejecución suelta: siete pruebas, la propia incluida.
    assert signal.trial_count == 7 and idea.trial_count == 7
    assert sorted(trial.kind for trial in idea.trials) == ["script_run"] + ["sweep_point"] * 6
    validation = signal.validation
    assert validation is not None and validation.trials == 6 and validation.causality_verified
    assert all(fold.train_end < fold.test_start for fold in validation.folds)
    assert validation.target == "weight_book" and validation.cost_bps == 5.0 and validation.costs_included is True
    assert validation.out_of_sample["observations"] and validation.oos_curve
    assert "not a validation result" in validation.in_sample_label
    # El segmento de seguimiento sigue la señal.
    assert idea.tracking.segments[-1].signal_id == signal.signal_id
    assert plain.status == "completed"


def test_a_script_signal_outside_the_validated_sweep_says_so(tmp_path):
    script_service, detail = e5_service(tmp_path)
    sweep, _ = _sweep(script_service, detail)
    plain = script_service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 7, "leverage": 1.0}))
    clock, service, signals, tracker, idea_id = _setup(tmp_path, script_service=script_service, research_service=script_service.research_service)
    clock.set(TUE_PM)
    idea = signals.attach(idea_id, SignalRequest(
        source="script", output_kind="returns", run_id=plain.run_id, result_id="strategy",
        validation=ValidationRequest(sweep_id=sweep.sweep_id, train_observations=60, test_observations=30),
    ))
    signal = idea.current_signal
    assert signal.output_kind == "returns" and signal.supplied is not None and "Script run" in signal.supplied.label
    assert any("not a point of the validated sweep" in item for item in signal.warnings)
    assert signal.validation.target == "returns_result" and signal.validation.costs_included is None
    # Una señal de rendimientos no toca el seguimiento.
    assert [segment.start_reason for segment in idea.tracking.segments] == ["activated"]


def test_script_signals_need_an_executed_run_and_mapped_instruments(tmp_path):
    preview_service, preview_detail = e5_service(tmp_path / "preview", ParameterFixtureRuntime(executed=False))
    preview_run = preview_service.create_run(preview_detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 5, "leverage": 1.0}))
    clock, service, signals, tracker, idea_id = _setup(tmp_path, script_service=preview_service, research_service=preview_service.research_service)
    clock.set(TUE_PM)
    with pytest.raises(IdeaValidationError, match="safe previews are not calculations"):
        signals.attach(idea_id, SignalRequest(source="script", output_kind="weights", run_id=preview_run.run_id, instruments=SPY_MAP))

    script_service, detail = e5_service(tmp_path / "real")
    run = script_service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(parameters={"lookback": 5, "leverage": 1.0}))
    signals.script_service = script_service
    with pytest.raises(IdeaValidationError, match="needs a ticker or a CoinGecko id"):
        signals.attach(idea_id, SignalRequest(source="script", output_kind="weights", run_id=run.run_id))
    with pytest.raises(IdeaValidationError, match="positions come from an import"):
        signals.attach(idea_id, SignalRequest(source="script", output_kind="positions", run_id=run.run_id))
    assert service.get_idea(idea_id).trials == ()


# ---------------------------------------------------------------------------
# Routes against the demo runtime
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    with TestClient(create_app(runtime)) as client:
        client.runtime = runtime  # type: ignore[attr-defined]
        yield client


def test_signal_routes_attach_and_detach_an_import(demo_client):
    runtime = demo_client.runtime
    clock = _Clock(datetime(2026, 1, 12, 14, 0))
    runtime.idea_service._clock = clock
    runtime.idea_signals._clock = clock
    runtime.idea_tracking._clock = _Clock(datetime(2026, 1, 17, 12, 0))
    created = demo_client.post("/ideas", json={
        "title": "Imported book", "thesis": "A weights CSV drives this book.", "stance": "long",
        "legs": [{"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}}],
    }).json()
    idea_id = created["idea_id"]
    demo_client.post(f"/ideas/{idea_id}/activate")
    response = demo_client.post(f"/ideas/{idea_id}/signal", json={
        "source": "import", "output_kind": "weights", "date_column": "date",
        "rows": [{"date": "2026-01-09", "AAPL": "0.6", "MSFT": "0.3"}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == IDEA_SCHEMA_VERSION and body["trial_count"] == 1
    signal = body["signals"][-1]
    assert body["current_signal_id"] == signal["signal_id"] and signal["drives_tracking"] is True
    assert [leg["key"] for leg in signal["legs"]] == ["equity:AAPL", "equity:MSFT"]
    tracking = demo_client.get(f"/ideas/{idea_id}/tracking").json()
    assert tracking["segments"][-1]["signal_id"] == signal["signal_id"]
    assert tracking["segments"][-1]["legs"][0]["weight"] == 0.6
    refused = demo_client.post(f"/ideas/{idea_id}/signal", json={
        "source": "import", "output_kind": "weights", "date_column": "date", "rows": [{"date": "2026-02-09", "AAPL": "1"}],
    })
    assert refused.status_code == 422 and "future" in refused.json()["detail"]
    detached = demo_client.delete(f"/ideas/{idea_id}/signal")
    assert detached.status_code == 200 and detached.json()["current_signal_id"] is None
    assert detached.json()["trial_count"] == 1
    exported = demo_client.get(f"/ideas/{idea_id}/export?format=md").text
    assert "## Signal and validation" in exported and "Trials recorded for this idea: 1 trial" in exported
    assert demo_client.delete(f"/ideas/{idea_id}/signal").status_code == 422
