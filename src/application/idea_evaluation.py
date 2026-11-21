"""Criterion evaluation and notifications for Ideas (Workstream 12, checkpoint I2).

Evaluation runs only while Gamma runs: once at start (every cadence, so
triggers that happened while Gamma was closed are found with the date they
were first met), when an idea is opened (``on_open``), after each US daily
close (``daily_close``) and, while Trader Workstation is connected, every few
minutes for ``intraday`` criteria whose observable has an intraday source.
Only ``active`` ideas are evaluated.

Every read goes through the observable registry, which calls existing
read-only services. Nothing here can place, stage or route anything.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.application.idea_criteria import ObservableReading, evaluate_criterion, latest_known_before
from src.models.ideas import (
    CRITERION_CADENCES,
    CriterionEvaluation,
    Idea,
    IdeaCriterion,
    IdeaJournalEntry,
    IdeaValidationError,
    ObservableRef,
)
from src.services.idea_store import IdeaNotFoundError, IdeaStore
from src.utils.time import now_utc

logger = logging.getLogger(__name__)

EVALUATION_TRIGGERS = ("startup", "daily_close", "intraday", "open", "manual", "criterion_saved", "activated")
_US_EASTERN = ZoneInfo("America/New_York")
# A US session's closes settle at providers a little after 16:00 New York time.
DAILY_CLOSE_PASS_AFTER = time(16, 20)
INTRADAY_PASS_SECONDS = 300
SCHEDULER_TICK_SECONDS = 60
STARTUP_DELAY_SECONDS = 3.0


class ObservableRegistryProtocol(Protocol):
    def read(self, ref: ObservableRef, *, now: datetime, intraday: bool = False) -> ObservableReading: ...

    def change_unit(self, ref: ObservableRef) -> str: ...

    def format_value(self, ref: ObservableRef, value: float | None) -> str: ...

    def intraday_capable(self, observable_id: str) -> bool: ...

    def tws_connected(self) -> bool: ...


@dataclass(frozen=True)
class IdeaNotification:
    """One item for the notification center and Sitrep "Your ideas"."""

    notification_id: str
    kind: str  # criterion_triggered | review_due
    idea_id: str
    idea_title: str
    created_at: datetime
    criterion_id: str | None = None
    criterion_kind: str | None = None
    label: str = ""
    value_display: str | None = None
    first_met_at: datetime | None = None
    review_date: date | None = None
    days_overdue: int | None = None
    provenance: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "kind": self.kind,
            "idea_id": self.idea_id,
            "idea_title": self.idea_title,
            "created_at": self.created_at.isoformat(),
            "criterion_id": self.criterion_id,
            "criterion_kind": self.criterion_kind,
            "label": self.label,
            "value_display": self.value_display,
            "first_met_at": self.first_met_at.isoformat() if self.first_met_at else None,
            "review_date": self.review_date.isoformat() if self.review_date else None,
            "days_overdue": self.days_overdue,
            "provenance": dict(self.provenance) if self.provenance else None,
        }


@dataclass(frozen=True)
class _Outcome:
    """One criterion's evaluation, the arming it was taken for, and a new baseline to store."""

    armed_at: datetime
    evaluation: CriterionEvaluation
    baseline: tuple[datetime, datetime] | None = None


@dataclass
class EvaluationPassResult:
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    ideas_evaluated: int = 0
    criteria_evaluated: int = 0
    readings_taken: int = 0
    new_triggers: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "ideas_evaluated": self.ideas_evaluated,
            "criteria_evaluated": self.criteria_evaluated,
            "readings_taken": self.readings_taken,
            "new_triggers": list(self.new_triggers),
            "errors": list(self.errors),
        }


def cadences_for_trigger(trigger: str) -> frozenset[str] | None:
    """Which criterion cadences a pass evaluates; ``None`` means every criterion."""
    if trigger == "open":
        return frozenset({"on_open"})
    if trigger == "daily_close":
        # Intraday criteria also take the canonical close.
        return frozenset({"daily_close", "intraday"})
    if trigger == "intraday":
        return frozenset({"intraday"})
    return None


class IdeaEvaluationService:
    def __init__(
        self,
        store: IdeaStore,
        registry: ObservableRegistryProtocol,
        *,
        clock: Callable[[], datetime] = now_utc,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self.store = store
        self.registry = registry
        self._clock = clock
        self._new_id = id_factory
        self._pass_lock = threading.Lock()
        self.last_pass: EvaluationPassResult | None = None

    # -- evaluation ----------------------------------------------------------

    def evaluate_idea(self, idea_id: str, *, trigger: str = "manual", criterion_ids: Iterable[str] | None = None) -> Idea:
        """Evaluate one idea now. Drafts and archived ideas are returned unchanged."""
        idea = self.store.require(idea_id)
        wanted = set(criterion_ids) if criterion_ids is not None else None
        result = EvaluationPassResult(trigger=trigger, started_at=self._clock())
        updated = self._evaluate(idea, trigger=trigger, readings={}, result=result, only=wanted)
        result.finished_at = self._clock()
        return updated

    def evaluate_all(self, *, trigger: str = "manual") -> EvaluationPassResult:
        """One pass over every active idea. Each observable is read once per pass."""
        if trigger not in EVALUATION_TRIGGERS:
            raise IdeaValidationError(f"Unknown evaluation trigger {trigger!r}.")
        result = EvaluationPassResult(trigger=trigger, started_at=self._clock())
        with self._pass_lock:
            readings: dict[str, ObservableReading] = {}
            for summary in self.store.list_summaries():
                if summary.status != "active" or not summary.criteria_total:
                    continue
                try:
                    # La lectura va dentro del try: un fichero dañado no debe abortar la pasada entera.
                    idea = self.store.get(summary.idea_id)
                    if idea is None:
                        continue
                    self._evaluate(idea, trigger=trigger, readings=readings, result=result)
                except Exception as exc:  # noqa: BLE001 - one bad idea must not stop the pass
                    logger.exception("Idea evaluation failed for %s", summary.idea_id)
                    result.errors.append(f"{summary.idea_id}: {exc}")
            result.readings_taken = len(readings)
        result.finished_at = self._clock()
        self.last_pass = result
        return result

    def has_intraday_criteria(self) -> bool:
        for summary in self.store.list_summaries():
            if summary.status != "active" or not summary.criteria_total:
                continue
            idea = self.store.get(summary.idea_id)
            if idea and any(item.cadence == "intraday" for item in idea.criteria):
                return True
        return False

    def _evaluate(
        self,
        idea: Idea,
        *,
        trigger: str,
        readings: dict[str, ObservableReading],
        result: EvaluationPassResult,
        only: set[str] | None = None,
    ) -> Idea:
        if idea.status != "active" or not idea.criteria:
            return idea
        cadences = cadences_for_trigger(trigger)
        activated_at = idea.activated_at
        tws = self.registry.tws_connected()
        outcomes: dict[str, _Outcome] = {}
        for criterion in idea.criteria:
            if only is not None and criterion.criterion_id not in only:
                continue
            due = cadences is None or criterion.cadence in cadences or criterion.last_evaluation is None
            if not due:
                continue
            intraday = criterion.cadence == "intraday" and tws and self.registry.intraday_capable(criterion.observable.observable_id)
            if trigger == "intraday" and not intraday:
                continue
            effective, note = self._effective_cadence(criterion, tws=tws)
            key = criterion.observable.key + ("|intraday" if intraday else "")
            reading = readings.get(key)
            now = self._clock()
            if reading is None:
                reading = self._read(criterion.observable, now=now, intraday=bool(intraday))
                readings[key] = reading
            armed_from = max(criterion.armed_at, activated_at) if activated_at else criterion.armed_at
            # The baseline is taken once per arming moment; a re-activation takes a new one.
            if criterion.baseline_for == armed_from:
                known_until = criterion.baseline_as_of
                baseline = None
            else:
                known_until = None if reading.is_unavailable else latest_known_before(reading, armed_from)
                baseline = (known_until, armed_from) if known_until is not None else None
            ref = criterion.observable
            evaluation = evaluate_criterion(
                criterion,
                reading,
                armed_from=armed_from,
                now=now,
                change_unit=self.registry.change_unit(ref),
                effective_cadence=effective,
                cadence_note=note,
                format_value=lambda value, _ref=ref: self.registry.format_value(_ref, value),
                known_until=known_until,
            )
            outcomes[criterion.criterion_id] = _Outcome(criterion.armed_at, evaluation, baseline)
        if not outcomes:
            return idea
        result.ideas_evaluated += 1
        result.criteria_evaluated += len(outcomes)
        return self._apply(idea.idea_id, outcomes, result)

    def _read(self, ref: ObservableRef, *, now: datetime, intraday: bool) -> ObservableReading:
        try:
            return self.registry.read(ref, now=now, intraday=intraday)
        except Exception as exc:  # noqa: BLE001 - a provider failure is a state, not a crash
            logger.warning("Observable %s failed: %s", ref.key, exc)
            return ObservableReading.unavailable(f"The source failed: {_clip(str(exc) or exc.__class__.__name__)}")

    def _effective_cadence(self, criterion: IdeaCriterion, *, tws: bool) -> tuple[str, str | None]:
        if criterion.cadence != "intraday":
            return criterion.cadence, None
        if not self.registry.intraday_capable(criterion.observable.observable_id):
            return "daily_close", "This observable has no intraday source; it is evaluated at the daily close."
        if not tws:
            return "daily_close", "Intraday needs Trader Workstation; evaluated at the daily close until it connects."
        return "intraday", None

    def _apply(
        self,
        idea_id: str,
        outcomes: Mapping[str, _Outcome],
        result: EvaluationPassResult,
    ) -> Idea:
        def mutate(current: Idea) -> Idea:
            # Una idea archivada o cerrada durante una lectura lenta no recibe triggers ni diario.
            if current.status != "active":
                return current
            now = self._clock()
            criteria: list[IdeaCriterion] = []
            entries: list[IdeaJournalEntry] = []
            changed = False
            for criterion in current.criteria:
                outcome = outcomes.get(criterion.criterion_id)
                # A rule edited while it was being read keeps its new, unevaluated state.
                if outcome is None or outcome.armed_at != criterion.armed_at:
                    criteria.append(criterion)
                    continue
                evaluation = outcome.evaluation
                updated = replace(criterion, last_evaluation=evaluation)
                if outcome.baseline is not None:
                    updated = replace(updated, baseline_as_of=outcome.baseline[0], baseline_for=outcome.baseline[1])
                if evaluation.state == "triggered" and criterion.triggered_at is None:
                    updated = replace(updated, triggered_at=now, trigger_evaluation=evaluation, acknowledged_at=None)
                    entries.append(self._trigger_entry(current, updated, evaluation, now))
                    result.new_triggers.append(
                        {
                            "idea_id": current.idea_id,
                            "criterion_id": criterion.criterion_id,
                            "label": criterion.label,
                            "first_met_at": evaluation.first_met_at.isoformat() if evaluation.first_met_at else None,
                        }
                    )
                criteria.append(updated)
                changed = True
            if not changed:
                return current
            # Evaluations are not user edits: ``updated_at`` moves only when the journal does.
            updated_idea = replace(current, criteria=tuple(criteria))
            for entry in entries:
                updated_idea = updated_idea.with_journal_entry(entry, touched_at=now)
            return updated_idea

        try:
            return self.store.update(idea_id, mutate)
        except IdeaNotFoundError:
            raise

    def _trigger_entry(self, idea: Idea, criterion: IdeaCriterion, evaluation: CriterionEvaluation, now: datetime) -> IdeaJournalEntry:
        met = evaluation.first_met_at
        shown = evaluation.met_display or evaluation.value_display
        body = f"{criterion.kind.capitalize()} criterion triggered: “{criterion.label}”"
        if shown:
            body += f" at {shown}"
        if met is not None and met.date() < now.date():
            body += f", first met {met.strftime('%Y-%m-%d')}"
        if evaluation.value_display and evaluation.met_display and evaluation.value_display != evaluation.met_display:
            body += f"; latest {evaluation.value_display}"
        source = evaluation.provenance.source_provider if evaluation.provenance else None
        body += f" ({source})." if source else "."
        return IdeaJournalEntry(
            entry_id=self._new_id(),
            idea_id=idea.idea_id,
            kind="criterion_triggered",
            author="system",
            body=body,
            created_at=now,
            details={
                "criterion_id": criterion.criterion_id,
                "criterion_kind": criterion.kind,
                "value": evaluation.met_value if evaluation.met_value is not None else evaluation.value,
                "value_display": shown,
                "latest_display": evaluation.value_display,
                "first_met_at": met.isoformat() if met else None,
                "observable": criterion.observable.to_dict(),
            },
        )

    # -- notifications -------------------------------------------------------

    def notifications(self) -> list[IdeaNotification]:
        """Unacknowledged triggers and reviews due, newest first, for active ideas."""
        today = self._clock().date()
        items: list[IdeaNotification] = []
        for summary in self.store.list_summaries():
            if summary.status != "active":
                continue
            review_due = summary.review_date is not None and date.fromisoformat(summary.review_date) <= today
            if not summary.unacknowledged_triggers and not review_due:
                continue
            idea = self.store.get(summary.idea_id)
            if idea is None:
                continue
            for criterion in idea.criteria:
                if not criterion.needs_acknowledgement:
                    continue
                evaluation = criterion.trigger_evaluation
                items.append(
                    IdeaNotification(
                        notification_id=f"trigger:{idea.idea_id}:{criterion.criterion_id}",
                        kind="criterion_triggered",
                        idea_id=idea.idea_id,
                        idea_title=idea.title,
                        created_at=criterion.triggered_at or self._clock(),
                        criterion_id=criterion.criterion_id,
                        criterion_kind=criterion.kind,
                        label=criterion.label,
                        value_display=(evaluation.met_display or evaluation.value_display) if evaluation else None,
                        first_met_at=evaluation.first_met_at if evaluation else None,
                        provenance=evaluation.provenance.to_dict() if evaluation and evaluation.provenance else None,
                    )
                )
            if review_due and idea.horizon.review_date is not None:
                review_date = idea.horizon.review_date
                items.append(
                    IdeaNotification(
                        notification_id=f"review:{idea.idea_id}:{review_date.isoformat()}",
                        kind="review_due",
                        idea_id=idea.idea_id,
                        idea_title=idea.title,
                        created_at=datetime(review_date.year, review_date.month, review_date.day),
                        label=f"Review due {review_date.isoformat()}",
                        review_date=review_date,
                        days_overdue=(today - review_date).days,
                    )
                )
        # Dos ordenaciones estables en lugar de ``-created_at.timestamp()``: en Windows,
        # ``timestamp()`` lanza OSError con fechas anteriores a 1970 (una review_date mal tecleada).
        items.sort(key=lambda item: item.created_at, reverse=True)
        items.sort(key=lambda item: item.kind != "criterion_triggered")
        return items

    def acknowledge(self, idea_id: str, criterion_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            criterion = current.criterion(criterion_id)
            if criterion is None:
                raise IdeaNotFoundError(f"Criterion {criterion_id} was not found on idea {idea_id}.")
            if criterion.triggered_at is None:
                raise IdeaValidationError("Only a triggered criterion can be acknowledged.")
            if criterion.acknowledged_at is not None:
                return current
            now = self._clock()
            updated = replace(criterion, acknowledged_at=now)
            criteria = tuple(updated if item.criterion_id == criterion_id else item for item in current.criteria)
            entry = IdeaJournalEntry(
                entry_id=self._new_id(),
                idea_id=idea_id,
                kind="criterion_acknowledged",
                author="system",
                body=f"Acknowledged the trigger of “{criterion.label}”.",
                created_at=now,
                details={"criterion_id": criterion_id},
            )
            return replace(current, criteria=criteria).with_journal_entry(entry, touched_at=now)

        return self.store.update(idea_id, mutate)


# ---------------------------------------------------------------------------
# Scheduler: start, daily close, intraday (only while Gamma runs)
# ---------------------------------------------------------------------------


def last_daily_close_session(now_utc_value: datetime) -> date:
    """The latest US session date whose close pass is due at ``now`` (weekdays only)."""
    eastern = now_utc_value.replace(tzinfo=ZoneInfo("UTC")).astimezone(_US_EASTERN)
    day = eastern.date()
    if eastern.time() < DAILY_CLOSE_PASS_AFTER:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


class IdeaEvaluationScheduler:
    """A daemon thread that runs the passes; it never blocks startup or requests."""

    def __init__(
        self,
        service: IdeaEvaluationService,
        *,
        clock: Callable[[], datetime] = now_utc,
        tick_seconds: float = SCHEDULER_TICK_SECONDS,
        startup_delay: float = STARTUP_DELAY_SECONDS,
        tracking: Any = None,
    ) -> None:
        self.service = service
        # I3a: tras la pasada de arranque y la de cierre se refresca el titular de seguimiento del tablero.
        self.tracking = tracking
        self._clock = clock
        self._tick = tick_seconds
        self._startup_delay = startup_delay
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_daily_session: date | None = None
        self.last_intraday_at: datetime | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gamma-idea-evaluation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        if self._stop.wait(self._startup_delay):
            return
        self.run_startup()
        while not self._stop.wait(self._tick):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("Idea evaluation tick failed")

    def run_startup(self) -> EvaluationPassResult | None:
        now = self._clock()
        # The start pass covers every cadence, including the latest close.
        self.last_daily_session = last_daily_close_session(now)
        try:
            result = self.service.evaluate_all(trigger="startup")
        except Exception:  # noqa: BLE001
            logger.exception("Idea evaluation at start failed")
            result = None
        self._refresh_tracking()
        return result

    def _refresh_tracking(self) -> None:
        if self.tracking is None:
            return
        try:
            self.tracking.refresh_all()
        except Exception:  # noqa: BLE001 - el seguimiento nunca detiene el planificador
            logger.exception("Idea tracking refresh failed")

    def tick(self) -> list[EvaluationPassResult]:
        now = self._clock()
        results: list[EvaluationPassResult] = []
        session = last_daily_close_session(now)
        if self.last_daily_session is None or session > self.last_daily_session:
            self.last_daily_session = session
            results.append(self.service.evaluate_all(trigger="daily_close"))
            self._refresh_tracking()
        due_intraday = self.last_intraday_at is None or (now - self.last_intraday_at).total_seconds() >= INTRADAY_PASS_SECONDS
        if due_intraday and self.service.registry.tws_connected() and self.service.has_intraday_criteria():
            self.last_intraday_at = now
            results.append(self.service.evaluate_all(trigger="intraday"))
        return results


def _clip(value: str, limit: int = 240) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = [
    "CRITERION_CADENCES",
    "EVALUATION_TRIGGERS",
    "EvaluationPassResult",
    "IdeaEvaluationScheduler",
    "IdeaEvaluationService",
    "IdeaNotification",
    "cadences_for_trigger",
    "last_daily_close_session",
]
