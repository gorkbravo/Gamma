"""Workstream 12 - Ideas, checkpoint I3b: close with a review, reopen, Review mode statistics.

The clock and the prices are injected, so nothing here reads the network or
Trader Workstation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_service import (
    IdeaCloseRequest,
    IdeaCreateRequest,
    IdeaCriterionRequest,
    IdeaEvidenceCreateRequest,
    IdeaService,
    build_review_statistics,
)
from src.application.idea_tracking import IdeaTrackingService, LegCloses, closes_from_series
from src.application.runtime import build_runtime
from src.models.handoff import HandoffEntity
from src.models.ideas import (
    IDEA_SCHEMA_VERSION,
    CriterionEvaluation,
    Idea,
    IdeaLeg,
    IdeaLifecycleError,
    IdeaValidationError,
    ObservableRef,
)
from src.services.idea_store import IdeaStore

MON, TUE, WED, THU, FRI = (date(2026, 11, day) for day in (9, 10, 11, 12, 13))
NEXT_MON, NEXT_TUE = date(2026, 11, 16), date(2026, 11, 17)
WEEK = (MON, TUE, WED, THU, FRI, NEXT_MON, NEXT_TUE)
UP = dict(zip(WEEK, (100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0)))
DOWN = dict(zip(WEEK, (100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0)))
FLAT = dict(zip(WEEK, (300.0,) * 7))


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def set(self, moment: datetime) -> None:
        self.now = moment

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


class FakePrices:
    def __init__(self, closes):
        self.closes = closes

    def leg_closes(self, leg, *, since, now):
        series = self.closes.get(leg.entity.normalized_id.upper())
        if series is None:
            return LegCloses.unavailable("no closes")
        return LegCloses(closes=closes_from_series(series, leg.market))

    def benchmark_closes(self, symbol, *, since, now):
        return LegCloses(closes=closes_from_series(FLAT, "us"))


def _ids():
    counter = iter(range(1, 10_000))
    return lambda: f"id{next(counter):04d}"


def _leg(symbol: str, weight: float | None = 1.0) -> IdeaLeg:
    return IdeaLeg(entity=HandoffEntity(entity_type="equity", label=symbol, normalized_id=symbol), weight=weight)


class _Env:
    def __init__(self, tmp_path):
        self.clock = _Clock(datetime(2026, 11, 6, 12, 0))
        self.store = IdeaStore(tmp_path / "ideas")
        self.service = IdeaService(self.store, clock=self.clock, id_factory=_ids())
        self.tracking_clock = _Clock(datetime(2026, 11, 18, 12, 0))
        self.tracker = IdeaTrackingService(self.service, FakePrices({"UP": UP, "DOWN": DOWN}), clock=self.tracking_clock)

    def active_idea(self, symbol: str, *, at=datetime(2026, 11, 9, 14, 0), title: str | None = None) -> str:
        idea = self.service.create_idea(
            IdeaCreateRequest(title=title or f"Long {symbol}", thesis=f"{symbol} keeps going.", stance="long", legs=(_leg(symbol),))
        )
        self.clock.set(at)
        self.service.activate(idea.idea_id)
        return idea.idea_id

    def close(self, idea_id: str, *, at: datetime, outcome: str = "confirmed", **extra) -> Idea:
        self.clock.set(at)
        self.tracking_clock.set(at)
        realized = self.tracker.compute(idea_id, persist=False).snapshot()
        return self.service.close(idea_id, IdeaCloseRequest(outcome=outcome, lesson=extra.pop("lesson", "Stated exits work."), realized=realized, **extra))


# ---------------------------------------------------------------------------
# Close requires a review
# ---------------------------------------------------------------------------


def test_closing_requires_a_review_and_an_active_idea(tmp_path):
    env = _Env(tmp_path)
    draft = env.service.create_idea(IdeaCreateRequest(title="Draft"))
    with pytest.raises(IdeaLifecycleError, match="Only an active idea"):
        env.service.close(draft.idea_id, IdeaCloseRequest(outcome="confirmed", lesson="Too early."))
    idea_id = env.active_idea("UP")
    with pytest.raises(IdeaValidationError, match="write the lesson"):
        env.service.close(idea_id, IdeaCloseRequest(outcome="confirmed", lesson="  "))
    with pytest.raises(IdeaValidationError, match="Choose an outcome"):
        env.service.close(idea_id, IdeaCloseRequest(outcome="won", lesson="Stated exits work."))
    assert env.service.get_idea(idea_id).status == "active"
    # El propio modelo rechaza una idea cerrada sin la revisión de su cierre.
    with pytest.raises(IdeaValidationError, match="needs the review"):
        replace(env.service.get_idea(idea_id), status="closed", closed_at=datetime(2026, 11, 12))


def test_close_freezes_the_review_and_stops_tracking_at_the_exit_close(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    _, pin = env.service.pin_evidence(
        idea_id, IdeaEvidenceCreateRequest(kind="note", stance="supports", title="Orders keep rising", captured_values={"text": "x"})
    )
    closed = env.close(
        idea_id,
        at=datetime(2026, 11, 12, 15, 0),  # jueves por la mañana en Nueva York
        expected="",
        realized_note="Momentum held.",
        evidence_verdicts={pin.evidence_id: "held"},
    )
    review = closed.current_review
    assert closed.status == "closed" and closed.closed_at == review.closed_at
    assert review.outcome == "confirmed" and review.lesson == "Stated exits work."
    assert review.expected == "UP keeps going.", "a blank expectation defaults to the thesis"
    assert review.opened_at == datetime(2026, 11, 9, 14, 0, 1)
    assert review.holding_days == pytest.approx((review.closed_at - review.opened_at).total_seconds() / 86_400)
    assert [(item.title, item.stance, item.verdict) for item in review.evidence_verdicts] == [("Orders keep rising", "supports", "held")]
    # Lo realizado al cerrar: el registro hasta el miércoles (el cierre del jueves aún no existía).
    assert review.realized is not None and review.realized.as_of == WED and review.realized.status == "tracking"
    status_entry = next(entry for entry in reversed(closed.journal) if entry.kind == "status_changed")
    assert status_entry.details["outcome"] == "confirmed" and "Lesson: Stated exits work." in status_entry.body
    segment = closed.tracking.segments[-1]
    assert segment.end_reason == "closed" and closed.tracking.open_segment is None

    env.tracking_clock.set(datetime(2026, 11, 18, 12, 0))
    after = env.tracker.compute(idea_id)
    assert after.status == "stopped" and after.final
    # Sale al primer cierre posterior al cierre de la idea (jueves) y nada después.
    assert after.segments[0].exit_session == THU
    assert [point.session for point in after.points] == [MON, TUE, WED, THU]
    assert env.service.get_idea(idea_id).tracking.snapshot.final is True


def test_unknown_or_blank_verdicts(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    with pytest.raises(IdeaValidationError, match="not pinned"):
        env.close(idea_id, at=datetime(2026, 11, 12, 15, 0), evidence_verdicts={"nope": "held"})
    closed = env.close(idea_id, at=datetime(2026, 11, 12, 15, 0), evidence_verdicts={})
    assert closed.current_review.evidence_verdicts == ()


# ---------------------------------------------------------------------------
# Reopen, archive, restore
# ---------------------------------------------------------------------------


def test_reopen_keeps_the_review_and_opens_a_new_segment(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    first = env.close(idea_id, at=datetime(2026, 11, 10, 15, 0), outcome="abandoned", lesson="Exited too early.")
    first_review = first.current_review.to_dict()
    env.clock.set(datetime(2026, 11, 12, 14, 0))
    reopened = env.service.reopen(idea_id)
    assert reopened.status == "active" and reopened.closed_at is None
    assert reopened.current_review is None and reopened.latest_review.to_dict() == first_review
    assert reopened.tracking.segments[-1].start_reason == "reopened"
    assert "stays in the record" in next(e for e in reversed(reopened.journal) if e.kind == "status_changed").body
    with pytest.raises(IdeaLifecycleError):
        env.service.reopen(idea_id)

    second = env.close(idea_id, at=datetime(2026, 11, 16, 15, 0), outcome="confirmed")
    assert [review.outcome for review in second.reviews] == ["abandoned", "confirmed"]
    assert second.reviews[0].to_dict() == first_review, "an earlier review is never edited"
    assert second.current_review.opened_at == datetime(2026, 11, 12, 14, 0, 1), "the episode starts at the reopen"
    with pytest.raises(IdeaValidationError, match="kept as written"):
        env.store.update(idea_id, lambda idea: replace(idea, reviews=(replace(idea.reviews[0], lesson="Rewritten."), idea.reviews[1])))


def test_a_closed_idea_archives_and_restores_as_closed(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    env.close(idea_id, at=datetime(2026, 11, 10, 15, 0))
    archived = env.service.archive(idea_id)
    assert archived.status == "archived" and archived.current_review is not None
    restored = env.service.restore(idea_id)
    assert restored.status == "closed" and restored.current_review is not None


# ---------------------------------------------------------------------------
# Review statistics
# ---------------------------------------------------------------------------


def _trigger_invalidation(env: _Env, idea_id: str, at: datetime) -> None:
    env.service.add_criterion(
        idea_id,
        IdeaCriterionRequest(
            kind="invalidate",
            observable=ObservableRef(observable_id="equity_close", params={"symbol": "DOWN"}, label="DOWN close"),
            condition="below",
            threshold=98.5,
        ),
    )

    def fire(idea: Idea) -> Idea:
        criterion = idea.criteria[-1]
        evaluation = CriterionEvaluation(state="triggered", evaluated_at=at, value=98.0, first_met_at=at - timedelta(hours=2))
        return replace(idea, criteria=(replace(criterion, triggered_at=at, trigger_evaluation=evaluation),))

    env.store.update(idea_id, fire)


def test_review_statistics_describe_the_closed_record(tmp_path):
    env = _Env(tmp_path)
    winner = env.active_idea("UP", title="Winner")
    loser = env.active_idea("DOWN", title="Loser with a fired invalidation")
    loser_ignored = env.active_idea("DOWN", title="Loser without rules")
    still_open = env.active_idea("UP", title="Still open")
    reopened = env.active_idea("UP", title="Reopened")

    _trigger_invalidation(env, loser, datetime(2026, 11, 11, 16, 0))
    env.close(winner, at=datetime(2026, 11, 13, 15, 0), outcome="confirmed")
    env.close(loser, at=datetime(2026, 11, 13, 16, 0), outcome="invalidated")
    env.close(loser_ignored, at=datetime(2026, 11, 16, 15, 0), outcome="expired")
    env.service.archive(loser_ignored)
    env.close(reopened, at=datetime(2026, 11, 12, 15, 0), outcome="abandoned")
    env.clock.set(datetime(2026, 11, 13, 14, 0))
    env.service.reopen(reopened)
    env.tracking_clock.set(datetime(2026, 11, 18, 12, 0))
    for idea_id in (winner, loser, loser_ignored):
        env.tracker.compute(idea_id)

    stats = env.service.review_statistics()
    titles = [row["title"] for row in stats.rows]
    assert titles == ["Loser without rules", "Loser with a fired invalidation", "Winner"], "newest close first"
    assert "Still open" not in titles and "Reopened" not in titles, "only current closes count"
    assert stats.outcomes == {"confirmed": 1, "invalidated": 1, "abandoned": 0, "expired": 1}
    assert stats.realized["count"] == 3 and stats.realized["negative"] == 2 and stats.realized["positive"] == 1
    assert stats.invalidation == {
        "losses": 2,
        "losses_with_invalidation_criteria": 1,
        "losses_with_trigger_before_close": 1,
        "share_of_losses": 0.5,
        "share_of_losses_with_criteria": 1.0,
    }
    winner_row = next(row for row in stats.rows if row["title"] == "Winner")
    # Cerrada el viernes antes del cierre: sale al cierre del viernes; registro final.
    assert winner_row["realized_final"] is True and winner_row["realized_as_of"] == FRI.isoformat()
    assert winner_row["net_return"] == pytest.approx(UP[FRI] / UP[MON] - 1 - 0.0005 - 0.0005 * UP[FRI] / UP[MON])
    assert winner_row["excess_return"] == pytest.approx(winner_row["net_return"])
    holding = stats.holding_days
    assert holding["count"] == 3 and holding["min"] < holding["median"] < holding["max"]
    assert holding["median_by_outcome"]["abandoned"] is None


def test_statistics_handle_an_empty_record(tmp_path):
    stats = build_review_statistics([], retrieved_at=datetime(2026, 11, 18))
    assert stats.rows == [] and stats.holding_days["median"] is None
    assert stats.invalidation["share_of_losses"] is None


def test_refresh_follows_a_closed_idea_until_its_exit_is_priced(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    env.close(idea_id, at=datetime(2026, 11, 12, 15, 0))
    env.tracking_clock.set(datetime(2026, 11, 12, 16, 0))  # antes del cierre del jueves
    env.tracker.compute(idea_id)
    assert env.service.get_idea(idea_id).tracking.snapshot.final is False
    env.tracking_clock.set(datetime(2026, 11, 18, 12, 0))
    assert env.tracker.refresh_all() == 1
    assert env.service.get_idea(idea_id).tracking.snapshot.final is True
    assert env.tracker.refresh_all() == 0, "a final record is not rebuilt again"


# ---------------------------------------------------------------------------
# Migration and routes
# ---------------------------------------------------------------------------


def test_v3_files_migrate_with_no_reviews(tmp_path):
    env = _Env(tmp_path)
    idea_id = env.active_idea("UP")
    path = tmp_path / "ideas" / "items" / f"{idea_id}.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 3
    legacy.pop("reviews")
    for key in ("evidence", "journal", "criteria"):
        for item in legacy[key]:
            item["schema_version"] = 3
    path.write_text(json.dumps(legacy), encoding="utf-8")
    (tmp_path / "ideas" / "index.json").unlink()
    migrated = IdeaStore(tmp_path / "ideas").require(idea_id)
    assert migrated.schema_version == IDEA_SCHEMA_VERSION == 4
    assert migrated.reviews == () and migrated.tracking.open_segment is not None


@pytest.fixture()
def demo_client(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    with TestClient(create_app(runtime)) as client:
        client.runtime = runtime  # type: ignore[attr-defined]
        yield client


def test_close_reopen_and_review_routes(demo_client):
    runtime = demo_client.runtime
    runtime.idea_service._clock = _Clock(datetime(2026, 1, 12, 14, 0))
    runtime.idea_tracking._clock = _Clock(datetime(2026, 1, 16, 12, 0))
    created = demo_client.post(
        "/ideas",
        json={
            "title": "Long AAPL",
            "thesis": "Services carry the quarter.",
            "stance": "long",
            "legs": [{"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": None}],
        },
    ).json()
    idea_id = created["idea_id"]
    assert demo_client.post(f"/ideas/{idea_id}/close", json={"outcome": "confirmed", "lesson": "x" * 10}).status_code == 422
    assert demo_client.post(f"/ideas/{idea_id}/activate").status_code == 200
    assert demo_client.post(f"/ideas/{idea_id}/close", json={"outcome": "won", "lesson": "Fine."}).status_code == 422
    assert demo_client.post(f"/ideas/{idea_id}/close", json={"outcome": "confirmed", "lesson": ""}).status_code == 422

    closed = demo_client.post(
        f"/ideas/{idea_id}/close",
        json={"outcome": "confirmed", "lesson": "Services did carry it.", "realized_note": "Beat on margins."},
    )
    assert closed.status_code == 200
    body = closed.json()
    assert body["status"] == "closed" and body["reviews"][0]["outcome"] == "confirmed"
    assert body["reviews"][0]["realized"]["as_of"] == "2026-01-15", "the record as it stood at close"
    assert body["reviews"][0]["holding_days"] > 0

    review = demo_client.get("/ideas/review").json()
    assert review["outcomes"]["confirmed"] == 1 and review["rows"][0]["idea_id"] == idea_id
    assert review["rows"][0]["tracked"] is True and review["label"] == "Hypothetical, not executed"
    board = next(item for item in demo_client.get("/ideas").json()["items"] if item["idea_id"] == idea_id)
    assert board["review"]["outcome"] == "confirmed"

    markdown = demo_client.get(f"/ideas/{idea_id}/export?format=md").text
    assert "## Reviews" in markdown and "Lesson: Services did carry it." in markdown

    reopened = demo_client.post(f"/ideas/{idea_id}/reopen")
    assert reopened.status_code == 200 and reopened.json()["status"] == "active"
    assert len(reopened.json()["reviews"]) == 1
    assert demo_client.get("/ideas/review").json()["rows"] == []
    assert demo_client.post(f"/ideas/{idea_id}/reopen").status_code == 422
