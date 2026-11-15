"""Workstream 12 - Ideas, checkpoint I2: criteria, observables, evaluation and notifications."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_criteria import ObservablePoint, ObservableReading, describe_criterion, evaluate_criterion
from src.application.idea_evaluation import (
    IdeaEvaluationScheduler,
    IdeaEvaluationService,
    cadences_for_trigger,
    last_daily_close_session,
)
from src.application.idea_observables import ObservableRegistry
from src.application.idea_service import IdeaCreateRequest, IdeaCriterionRequest, IdeaPatchRequest, IdeaService
from src.application.runtime import build_runtime
from src.models.ideas import (
    IDEA_SCHEMA_VERSION,
    CriterionEvaluation,
    IdeaCriterion,
    IdeaLifecycleError,
    IdeaValidationError,
    ObservableRef,
)
from src.models.provenance import ProvenanceRecord
from src.services.idea_explanations import EXPLANATIONS, list_explanations
from src.services.idea_store import IdeaStore

T0 = datetime(2026, 11, 10, 9, 0)
XOM = ObservableRef("equity_close", {"symbol": "XOM"}, "XOM close")


class _Clock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now

    def jump(self, delta: timedelta) -> None:
        self.now = self.now + delta


def _ids(prefix: str = "id"):
    counter = iter(range(1, 100_000))
    return lambda: f"{prefix}{next(counter):05d}"


def _closes(*pairs: tuple[int, float], month: int = 11) -> tuple[ObservablePoint, ...]:
    return tuple(ObservablePoint(at=datetime(2026, month, day), value=value) for day, value in pairs)


class FakeRegistry:
    """Registry stand-in: returns scripted readings and counts reads."""

    def __init__(self, readings: dict[str, ObservableReading] | None = None, *, tws: bool = False) -> None:
        self.readings = readings or {}
        self.tws = tws
        self.reads: list[str] = []
        self.fail: set[str] = set()

    def read(self, ref, *, now, intraday=False):
        self.reads.append(ref.key)
        if ref.observable_id in self.fail:
            raise RuntimeError("provider timed out")
        return self.readings.get(ref.observable_id, ObservableReading.unavailable("No reading scripted."))

    def change_unit(self, ref):
        return "percent"

    def format_value(self, ref, value):
        return "N/A" if value is None else f"{value:.2f}"

    def intraday_capable(self, observable_id):
        return observable_id == "option_atm_iv"

    def tws_connected(self):
        return self.tws

    def validate(self, ref, *, condition, cadence):
        return ref

    def describe(self, ref, *, condition, threshold, window):
        return describe_criterion(observable_label=ref.label, condition=condition, threshold=threshold, window=window)


def _setup(tmp_path, registry: FakeRegistry | None = None):
    clock = _Clock()
    store = IdeaStore(tmp_path / "ideas")
    registry = registry or FakeRegistry()
    service = IdeaService(store, clock=clock, id_factory=_ids("s"), criteria_registry=registry)
    evaluation = IdeaEvaluationService(store, registry, clock=clock, id_factory=_ids("e"))
    return clock, store, registry, service, evaluation


def _active_idea(service: IdeaService, title: str = "XOM holds its dividend"):
    idea = service.create_idea(IdeaCreateRequest(title=title, thesis="Cash returns hold up into Q1.", stance="long"))
    return service.activate(idea.idea_id)


def _criterion(kind="invalidate", condition="below", threshold=100.0, window=None, cadence="daily_close", ref=XOM, label=None):
    return IdeaCriterionRequest(
        kind=kind, observable=ref, condition=condition, threshold=threshold, window=window, cadence=cadence, label=label
    )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_criterion_model_enforces_rule_shape_and_round_trips():
    base = dict(criterion_id="c1", idea_id="i1", kind="invalidate", label="XOM below 100", observable=XOM)
    with pytest.raises(IdeaValidationError, match="threshold"):
        IdeaCriterion(**base, condition="below")
    with pytest.raises(IdeaValidationError, match="window"):
        IdeaCriterion(**base, condition="change_over_window", threshold=-5)
    with pytest.raises(IdeaValidationError, match="cannot be zero"):
        IdeaCriterion(**base, condition="change_over_window", threshold=0, window="1m")
    with pytest.raises(IdeaValidationError, match="takes no threshold"):
        IdeaCriterion(**base, condition="date_reached", threshold=3)
    with pytest.raises(IdeaValidationError, match="acknowledged"):
        IdeaCriterion(**base, condition="below", threshold=100, acknowledged_at=T0)
    with pytest.raises(IdeaValidationError, match="reason"):
        CriterionEvaluation(state="unavailable", evaluated_at=T0)

    evaluation = CriterionEvaluation(state="triggered", evaluated_at=T0, value=98.0, first_met_at=datetime(2026, 11, 9))
    criterion = IdeaCriterion(
        **base, condition="below", threshold=100, last_evaluation=evaluation, trigger_evaluation=evaluation, triggered_at=T0
    )
    assert criterion.state == "triggered" and criterion.needs_acknowledgement
    payload = json.loads(json.dumps(criterion.to_dict()))
    restored = IdeaCriterion.from_dict(payload)
    assert restored.to_dict() == criterion.to_dict()
    assert ObservableRef("Equity_Close", {"symbol": " XOM ", "empty": ""}).params == {"symbol": "XOM"}
    assert IdeaCriterion(**base, condition="below", threshold=100).state == "pending"


def test_v1_idea_files_migrate_to_v2_with_empty_criteria(tmp_path):
    base = tmp_path / "ideas"
    _, store, _, service, _ = _setup(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Legacy idea"))
    path = base / "items" / f"{idea.idea_id}.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("criteria")
    for entry in legacy["journal"]:
        entry["schema_version"] = 1
    path.write_text(json.dumps(legacy), encoding="utf-8")
    (base / "index.json").unlink()

    reopened = IdeaStore(base)
    migrated = reopened.require(idea.idea_id)
    assert migrated.schema_version == IDEA_SCHEMA_VERSION == 2
    assert migrated.criteria == ()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 2 and on_disk["criteria"] == []
    assert all(entry["schema_version"] == 2 for entry in on_disk["journal"])
    assert any(item.action == "migrated" for item in reopened.storage_warnings())


# ---------------------------------------------------------------------------
# Pure evaluation
# ---------------------------------------------------------------------------


def _rule(condition="below", threshold=100.0, window=None, armed=T0):
    return IdeaCriterion(
        criterion_id="c1",
        idea_id="i1",
        kind="invalidate",
        label="rule",
        observable=XOM,
        condition=condition,
        threshold=threshold,
        window=window,
        armed_at=armed,
    )


def test_level_rule_finds_the_first_close_after_arming_while_away():
    reading = ObservableReading(history=_closes((6, 97), (7, 104), (10, 103), (11, 99), (12, 101), (13, 102)))
    result = evaluate_criterion(_rule(), reading, armed_from=T0, now=datetime(2026, 11, 15, 9))
    # The 6 Nov close was below 100 but before the rule existed: it cannot count.
    assert result.state == "triggered"
    assert result.first_met_at == datetime(2026, 11, 11)
    assert result.value == 102 and result.as_of == datetime(2026, 11, 13)

    holding = evaluate_criterion(_rule(threshold=95), reading, armed_from=T0, now=datetime(2026, 11, 15, 9))
    assert holding.state == "holding" and holding.first_met_at is None


def test_crossing_rules_need_a_crossing_not_a_level():
    already_above = ObservableReading(history=_closes((9, 110), (10, 111), (11, 112)))
    rule = _rule(condition="crosses_above", threshold=105)
    assert evaluate_criterion(rule, already_above, armed_from=T0, now=T0 + timedelta(days=3)).state == "holding"

    crossing = ObservableReading(history=_closes((9, 104), (10, 104.5), (11, 106)))
    result = evaluate_criterion(rule, crossing, armed_from=T0, now=T0 + timedelta(days=3))
    assert result.state == "triggered" and result.first_met_at == datetime(2026, 11, 11) and result.reference_value == 104.5

    single = ObservableReading(value=106, as_of=T0)
    lonely = evaluate_criterion(rule, single, armed_from=T0, now=T0)
    assert lonely.state == "unavailable" and "two observations" in lonely.reason


def test_change_over_window_uses_the_last_observation_before_the_window():
    history = _closes((1, 100), (3, 99), (10, 95), (11, 93.5), (12, 94), month=11)
    rule = _rule(condition="change_over_window", threshold=-5, window="5d", armed=datetime(2026, 11, 9))
    result = evaluate_criterion(rule, ObservableReading(history=history), armed_from=rule.armed_at, now=datetime(2026, 11, 13))
    # 11 Nov: reference is the 3 Nov close (last on or before 6 Nov): 93.5 / 99 - 1 = -5.56%.
    assert result.state == "triggered" and result.first_met_at == datetime(2026, 11, 11)
    assert result.reference_value == 99 and result.change == pytest.approx(-5.5555, rel=1e-3)

    rising = _rule(condition="change_over_window", threshold=10, window="5d", armed=datetime(2026, 11, 9))
    holding = evaluate_criterion(rising, ObservableReading(history=history), armed_from=rising.armed_at, now=datetime(2026, 11, 13))
    assert holding.state == "holding" and holding.change is not None

    short = _rule(condition="change_over_window", threshold=-5, window="1y", armed=datetime(2026, 11, 9))
    too_short = evaluate_criterion(short, ObservableReading(history=history), armed_from=short.armed_at, now=datetime(2026, 11, 13))
    assert too_short.state == "unavailable" and "too short" in too_short.reason


def test_unavailable_and_stale_are_never_holding():
    missing = evaluate_criterion(_rule(), ObservableReading.unavailable("Needs Trader Workstation."), armed_from=T0, now=T0)
    assert missing.state == "unavailable" and missing.reason == "Needs Trader Workstation." and missing.value is None

    old = ObservableReading(history=_closes((12, 104)), stale_reason="The latest close is old.")
    stale = evaluate_criterion(_rule(), old, armed_from=T0, now=datetime(2026, 11, 30))
    assert stale.state == "stale" and stale.reason == "The latest close is old."
    # A stale close that met the condition is still a fact.
    old_met = ObservableReading(history=_closes((12, 96)), stale_reason="The latest close is old.")
    assert evaluate_criterion(_rule(), old_met, armed_from=T0, now=datetime(2026, 11, 30)).state == "triggered"


def test_date_and_event_conditions():
    target = ObservableReading(event_time=datetime(2026, 11, 20))
    date_rule = replace(_rule(condition="date_reached", threshold=None), observable=ObservableRef("calendar_date", {"date": "2026-11-20"}))
    before = evaluate_criterion(date_rule, target, armed_from=T0, now=datetime(2026, 11, 18))
    assert before.state == "holding" and before.value == 2 and before.value_display == "In 2 days"
    after = evaluate_criterion(date_rule, target, armed_from=T0, now=datetime(2026, 11, 21))
    assert after.state == "triggered" and after.first_met_at == datetime(2026, 11, 20)

    event_rule = replace(
        _rule(condition="event_occurs", threshold=None),
        observable=ObservableRef("prediction_probability", {"market_id": "kalshi:FED"}),
    )
    open_market = ObservableReading(value=40, as_of=T0, event_released=False, event_time=datetime(2026, 12, 1))
    assert evaluate_criterion(event_rule, open_market, armed_from=T0, now=T0).state == "holding"
    resolved = ObservableReading(value=100, as_of=T0, event_released=True, event_time=datetime(2026, 11, 12))
    occurred = evaluate_criterion(event_rule, resolved, armed_from=T0, now=datetime(2026, 11, 13))
    assert occurred.state == "triggered" and occurred.first_met_at == datetime(2026, 11, 12)


def test_generated_labels_read_as_plain_language():
    assert describe_criterion(observable_label="XOM close", condition="below", threshold=100, window=None) == "XOM close below 100"
    assert (
        describe_criterion(observable_label="Brent", condition="change_over_window", threshold=-10, window="1m")
        == "Brent falls 10% over 1 month"
    )
    assert (
        describe_criterion(observable_label="Fed cut odds", condition="change_over_window", threshold=15, window="5d", change_unit="points")
        == "Fed cut odds rises 15 pts over 5 days"
    )
    assert describe_criterion(observable_label="CPI release", condition="date_reached", threshold=None, window=None) == "CPI release reached"


# ---------------------------------------------------------------------------
# Service: criteria are journaled edits
# ---------------------------------------------------------------------------


def test_criteria_changes_are_journaled_and_rule_edits_re_arm(tmp_path):
    clock, store, registry, service, evaluation = _setup(tmp_path)
    idea = _active_idea(service)
    idea, criterion = service.add_criterion(idea.idea_id, _criterion(label=None))
    assert criterion.label == "XOM close below 100" and criterion.state == "pending"
    assert idea.journal[-1].kind == "criterion_added" and "XOM close below 100" in idea.journal[-1].body

    registry.readings["equity_close"] = ObservableReading(history=_closes((10, 99.5)))
    idea = evaluation.evaluate_idea(idea.idea_id)
    triggered = idea.criterion(criterion.criterion_id)
    assert triggered.state == "triggered" and triggered.trigger_evaluation.value == 99.5

    renamed = service.update_criterion(idea.idea_id, criterion.criterion_id, _criterion(label="Dividend cover breaks"))
    kept = renamed.criterion(criterion.criterion_id)
    assert kept.label == "Dividend cover breaks" and kept.state == "triggered", "a label edit keeps the trigger"

    edited = service.update_criterion(idea.idea_id, criterion.criterion_id, _criterion(threshold=90.0, label="XOM below 90"))
    rearmed = edited.criterion(criterion.criterion_id)
    assert rearmed.state == "pending" and rearmed.triggered_at is None and rearmed.armed_at > criterion.armed_at
    assert edited.journal[-1].kind == "criterion_edited" and "re-armed" in edited.journal[-1].body
    assert "earlier trigger" in edited.journal[-1].body

    removed = service.remove_criterion(idea.idea_id, criterion.criterion_id)
    assert removed.criteria == () and removed.journal[-1].kind == "criterion_removed"
    assert len(removed.journal) > len(edited.journal)

    archived = service.archive(idea.idea_id)
    with pytest.raises(IdeaLifecycleError):
        service.add_criterion(archived.idea_id, _criterion())


# ---------------------------------------------------------------------------
# Evaluation service
# ---------------------------------------------------------------------------


def test_only_active_ideas_evaluate_and_triggers_reach_notifications(tmp_path):
    registry = FakeRegistry({"equity_close": ObservableReading(history=_closes((10, 99), (11, 101)))})
    clock, store, registry, service, evaluation = _setup(tmp_path, registry)
    draft = service.create_idea(IdeaCreateRequest(title="Draft idea"))
    service.add_criterion(draft.idea_id, _criterion())
    active = _active_idea(service)
    active, criterion = service.add_criterion(active.idea_id, _criterion())

    result = evaluation.evaluate_all(trigger="startup")
    assert result.ideas_evaluated == 1 and len(result.new_triggers) == 1
    assert store.require(draft.idea_id).criteria[0].state == "pending", "drafts are not evaluated"
    updated = store.require(active.idea_id)
    fired = updated.criterion(criterion.criterion_id)
    assert fired.state == "triggered" and fired.trigger_evaluation.first_met_at == datetime(2026, 11, 10)
    trigger_body = updated.journal[-1].body
    assert updated.journal[-1].kind == "criterion_triggered"
    # The journal names the close that met the rule, not just the latest one.
    assert "at 99.00" in trigger_body and "latest 101.00" in trigger_body

    notes = evaluation.notifications()
    assert [item.kind for item in notes] == ["criterion_triggered"]
    assert notes[0].label == "XOM close below 100" and notes[0].first_met_at == datetime(2026, 11, 10)
    assert notes[0].value_display == "99.00"
    summary = next(item for item in store.list_summaries() if item.idea_id == active.idea_id)
    assert summary.unacknowledged_triggers == 1 and summary.criteria_counts["triggered"] == 1

    # A later pass keeps the trigger latched even if the value recovers.
    registry.readings["equity_close"] = ObservableReading(history=_closes((12, 105)))
    evaluation.evaluate_all(trigger="daily_close")
    again = store.require(active.idea_id).criterion(criterion.criterion_id)
    assert again.state == "triggered" and again.last_evaluation.state == "holding"
    assert sum(1 for entry in store.require(active.idea_id).journal if entry.kind == "criterion_triggered") == 1

    acknowledged = evaluation.acknowledge(active.idea_id, criterion.criterion_id)
    assert acknowledged.journal[-1].kind == "criterion_acknowledged"
    assert evaluation.notifications() == []


def test_one_pass_reads_each_observable_once_and_failures_become_unavailable(tmp_path):
    registry = FakeRegistry({"equity_close": ObservableReading(history=_closes((10, 120)))})
    clock, store, registry, service, evaluation = _setup(tmp_path, registry)
    for title in ("First idea", "Second idea"):
        idea = _active_idea(service, title)
        service.add_criterion(idea.idea_id, _criterion())
    evaluation.evaluate_all(trigger="manual")
    assert registry.reads.count(XOM.key) == 1

    registry.fail.add("equity_close")
    evaluation.evaluate_all(trigger="manual")
    states = {item.criteria[0].last_evaluation.state for item in (store.require(s.idea_id) for s in store.list_summaries())}
    assert states == {"unavailable"}
    reasons = {store.require(s.idea_id).criteria[0].last_evaluation.reason for s in store.list_summaries()}
    assert reasons == {"The source failed: provider timed out"}


def test_cadences_open_trigger_and_intraday_fallback(tmp_path):
    registry = FakeRegistry(
        {
            "equity_close": ObservableReading(history=_closes((10, 120))),
            "option_atm_iv": ObservableReading(value=21.0, as_of=T0),
        }
    )
    clock, store, registry, service, evaluation = _setup(tmp_path, registry)
    idea = _active_idea(service)
    _, daily = service.add_criterion(idea.idea_id, _criterion(cadence="daily_close"))
    iv_ref = ObservableRef("option_atm_iv", {"symbol": "SPY"}, "SPY ATM IV")
    _, intraday = service.add_criterion(
        idea.idea_id, _criterion(kind="confirm", condition="above", threshold=30, cadence="intraday", ref=iv_ref)
    )
    evaluation.evaluate_all(trigger="manual")
    stored = store.require(idea.idea_id)
    note = stored.criterion(intraday.criterion_id).last_evaluation
    assert note.effective_cadence == "daily_close" and "Trader Workstation" in note.cadence_note

    registry.reads.clear()
    evaluation.evaluate_idea(idea.idea_id, trigger="open")
    assert registry.reads == [], "on open evaluates only on_open (and never-evaluated) criteria"

    registry.tws = True
    evaluation.evaluate_all(trigger="intraday")
    assert registry.reads == [iv_ref.key + ""] or registry.reads == [iv_ref.key]
    assert store.require(idea.idea_id).criterion(intraday.criterion_id).last_evaluation.effective_cadence == "intraday"
    assert cadences_for_trigger("startup") is None and cadences_for_trigger("open") == {"on_open"}


def test_a_rule_edited_during_a_read_keeps_its_new_state(tmp_path):
    clock, store, registry, service, evaluation = _setup(tmp_path)
    idea = _active_idea(service)
    idea, criterion = service.add_criterion(idea.idea_id, _criterion())

    def slow_read(ref, *, now, intraday=False):
        service.update_criterion(idea.idea_id, criterion.criterion_id, _criterion(threshold=80.0))
        return ObservableReading(history=_closes((10, 70)))

    registry.read = slow_read
    evaluation.evaluate_idea(idea.idea_id)
    current = store.require(idea.idea_id).criterion(criterion.criterion_id)
    assert current.threshold == 80.0 and current.state == "pending" and current.triggered_at is None


def test_reviews_due_reach_notifications(tmp_path):
    clock, store, registry, service, evaluation = _setup(tmp_path)
    idea = _active_idea(service)
    from src.models.ideas import IdeaHorizon

    service.update_idea(idea.idea_id, IdeaPatchRequest(horizon=IdeaHorizon(review_date=date(2026, 11, 9))))
    notes = evaluation.notifications()
    assert len(notes) == 1 and notes[0].kind == "review_due" and notes[0].days_overdue == 1


def test_scheduler_runs_start_daily_close_and_intraday_passes(tmp_path):
    # 2026-11-13 is a Friday; 21:30 UTC is 16:30 in New York (after the close pass time).
    assert last_daily_close_session(datetime(2026, 11, 13, 21, 30)) == date(2026, 11, 13)
    assert last_daily_close_session(datetime(2026, 11, 13, 20, 0)) == date(2026, 11, 12)
    assert last_daily_close_session(datetime(2026, 11, 15, 12, 0)) == date(2026, 11, 13), "weekends roll back"

    passes: list[str] = []
    service = SimpleNamespace(
        evaluate_all=lambda trigger: passes.append(trigger) or SimpleNamespace(trigger=trigger),
        has_intraday_criteria=lambda: True,
        registry=SimpleNamespace(tws_connected=lambda: False),
    )
    clock = _Clock(datetime(2026, 11, 13, 20, 0))
    scheduler = IdeaEvaluationScheduler(service, clock=clock)
    scheduler.run_startup()
    scheduler.tick()
    assert passes == ["startup"]
    clock.jump(timedelta(hours=2))
    scheduler.tick()
    assert passes == ["startup", "daily_close"]
    scheduler.tick()
    assert passes == ["startup", "daily_close"], "one daily pass per session"
    service.registry = SimpleNamespace(tws_connected=lambda: True)
    scheduler.tick()
    assert passes[-1] == "intraday"


# ---------------------------------------------------------------------------
# Registry (validation and dependencies, no network)
# ---------------------------------------------------------------------------


def test_registry_orders_validates_and_states_dependencies():
    client = SimpleNamespace(is_connected=lambda: False)
    iv = SimpleNamespace(is_running=lambda: True, active_symbol=lambda: "QQQ", latest_snapshot=lambda: None)
    registry = ObservableRegistry(client=client, iv_service=iv, research_provider=object(), env=lambda key: None)
    ids = [item.observable_id for item in registry.definitions()]
    assert ids.index("equity_close") < ids.index("option_atm_iv"), "no-TWS observables come first"
    rows = {row["observable_id"]: row for row in registry.describe_all()}
    assert rows["option_atm_iv"]["available"] is False and "Trader Workstation" in rows["option_atm_iv"]["unavailable_reason"]
    assert rows["macro_series"]["unavailable_reason"] == "Needs FRED_API_KEY in Settings."

    reading = registry.read(ObservableRef("option_atm_iv", {"symbol": "SPY"}), now=T0)
    assert reading.is_unavailable and "Trader Workstation" in reading.unavailable_reason

    connected = ObservableRegistry(client=SimpleNamespace(is_connected=lambda: True), iv_service=iv, env=lambda key: None)
    busy = connected.read(connected.validate(ObservableRef("option_skew", {"symbol": "spy"}), condition="above", cadence="intraday"), now=T0)
    assert "streaming QQQ" in busy.unavailable_reason, "a live Options surface is never interrupted"

    with pytest.raises(IdeaValidationError, match="supports above, below"):
        connected.validate(ObservableRef("option_atm_iv", {"symbol": "SPY"}), condition="crosses_above", cadence=None)
    with pytest.raises(IdeaValidationError, match="kalshi"):
        connected.validate(ObservableRef("prediction_probability", {"market_id": "nope"}), condition="above", cadence=None)
    with pytest.raises(IdeaValidationError, match="does not take"):
        connected.validate(ObservableRef("equity_close", {"symbol": "XOM", "venue": "x"}), condition="above", cadence=None)
    normalized = connected.validate(ObservableRef("equity_close", {"symbol": " xom "}), condition="below", cadence="daily_close")
    assert normalized.params == {"symbol": "XOM"} and normalized.label == "XOM close"
    assert connected.describe(normalized, condition="below", threshold=100, window=None) == "XOM close below 100.00"


def test_every_observable_condition_and_state_has_an_explanation():
    registry = ObservableRegistry(env=lambda key: None)
    keys = set(EXPLANATIONS)
    for definition in registry.definitions():
        assert f"observable.{definition.observable_id}" in keys
        for condition in definition.conditions:
            assert f"condition.{condition}" in keys
    for state in ("pending", "holding", "triggered", "unavailable", "stale"):
        assert f"state.{state}" in keys
    for entry in list_explanations():
        assert entry.measures and entry.computed and set(entry.why) == {"long", "short", "relative", "event", "neutral"}
        assert "buy" not in entry.measures.lower() and "sell" not in entry.measures.lower()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def test_routes_manage_criteria_evaluate_and_notify(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "history")
    client = TestClient(create_app(runtime=runtime, session_token="test-token"))
    headers = {"X-Gamma-Session": "test-token"}

    registry_payload = client.get("/ideas/observables", headers=headers).json()
    assert registry_payload["items"][0]["observable_id"] == "equity_close"
    assert any(item["observable_id"] == "calendar_date" for item in registry_payload["items"])

    preview = client.post(
        "/ideas/observables/preview",
        json={"observable": {"observable_id": "calendar_date", "params": {"date": "2026-11-01"}}},
        headers=headers,
    ).json()
    assert preview["available"] is True and preview["event_time"].startswith("2026-11-01")

    idea = client.post("/ideas", json={"title": "Deadline idea", "thesis": "It plays out by November."}, headers=headers).json()
    idea_id = idea["idea_id"]
    draft_add = client.post(
        f"/ideas/{idea_id}/criteria",
        json={"kind": "review", "observable": {"observable_id": "calendar_date", "params": {"date": "2026-11-01"}}, "condition": "date_reached"},
        headers=headers,
    )
    assert draft_add.status_code == 200
    body = draft_add.json()
    assert body["criterion"]["state"] == "pending", "a draft does not evaluate"
    assert body["criterion"]["label"] == "2026-11-01 reached"
    assert body["idea"]["schema_version"] == 2

    bad = client.post(
        f"/ideas/{idea_id}/criteria",
        json={"kind": "review", "observable": {"observable_id": "calendar_date", "params": {"date": "2026-11-01"}}, "condition": "above", "threshold": 1},
        headers=headers,
    )
    assert bad.status_code == 422

    activated = client.post(f"/ideas/{idea_id}/activate", headers=headers).json()
    criterion = activated["criteria"][0]
    assert criterion["state"] == "triggered" and criterion["trigger_evaluation"]["provenance"]["source_provider"] == "gamma_clock"

    notes = client.get("/ideas/notifications", headers=headers).json()
    assert notes["triggered"] == 1 and notes["items"][0]["idea_title"] == "Deadline idea"
    assert "only while Gamma runs" in notes["limitation"]

    board = client.get("/ideas", headers=headers).json()
    assert board["items"][0]["unacknowledged_triggers"] == 1 and board["items"][0]["criteria_counts"]["triggered"] == 1

    ack = client.post(f"/ideas/{idea_id}/criteria/{criterion['criterion_id']}/acknowledge", headers=headers).json()
    assert ack["criteria"][0]["acknowledged_at"] is not None
    assert client.get("/ideas/notifications", headers=headers).json()["items"] == []

    edited = client.patch(
        f"/ideas/{idea_id}/criteria/{criterion['criterion_id']}",
        json={"kind": "review", "observable": {"observable_id": "calendar_date", "params": {"date": "2099-01-01"}}, "condition": "date_reached"},
        headers=headers,
    ).json()
    assert edited["criteria"][0]["state"] == "holding", "an edited rule on an active idea is evaluated at once"

    evaluated = client.post(f"/ideas/{idea_id}/evaluate", headers=headers).json()
    assert evaluated["criteria"][0]["last_evaluation"]["value_display"].startswith("In ")
    assert client.post("/ideas/evaluate", headers=headers).json()["ideas_evaluated"] == 1

    explanations = client.get("/ideas/explanations", headers=headers).json()
    assert any(item["key"] == "observable.calendar_date" for item in explanations["items"])

    removed = client.delete(f"/ideas/{idea_id}/criteria/{criterion['criterion_id']}", headers=headers).json()
    assert removed["criteria"] == []
    kinds = [entry["kind"] for entry in removed["journal"]]
    assert kinds.count("criterion_triggered") == 1 and "criterion_acknowledged" in kinds and kinds[-1] == "criterion_removed"

    exported = client.get(f"/ideas/{idea_id}/export?format=md", headers=headers).text
    assert "## Criteria" in exported
