"""Application service for Ideas (Workstream 12, checkpoints I1, I2, I3a, I3b and I3c).

The service owns the rules around the store: every edit, pin, unpin,
criterion change and lifecycle change writes a system journal entry; the
journal only grows; and the lifecycle is ``draft`` -> ``active`` ->
``closed`` -> ``archived`` (plus reopen, restore and delete). Closing needs a
review (I3b), and reviews only grow: reopening keeps the earlier one. A pin stores
exactly what the user saw, with the provenance they saw. Criteria are
validated against the observable registry here; evaluating them is the job of
``IdeaEvaluationService`` (``src/application/idea_evaluation.py``).

Forward tracking (I3a): activation freezes the legs into an open tracking
segment; editing the legs of an active idea closes it and opens the next one;
archiving closes it and restoring opens a new one. Each change is journaled.
The canonical series itself is rebuilt from provider closes by
``IdeaTrackingService`` (``src/application/idea_tracking.py``).
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.models.handoff import CrossTabHandoffEnvelope
from src.models.ideas import (
    CRITERION_CADENCES,
    EVIDENCE_STANCES,
    EVIDENCE_VERDICTS,
    REVIEW_OUTCOMES,
    IDEA_SCHEMA_VERSION,
    IDEA_STATUSES,
    TRACKING_BP_CLASSES,
    TRACKING_COST_BP_MAX,
    TRACKING_LABEL,
    TRIAL_LEDGER_MAX,
    Idea,
    IdeaSignal,
    IdeaTrial,
    IdeaCostModel,
    IdeaCriterionAtClose,
    IdeaEvidenceVerdict,
    IdeaReview,
    IdeaRiskSnapshot,
    IdeaTestSnapshot,
    IdeaEvidence,
    IdeaCriterion,
    IdeaHorizon,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaLifecycleError,
    IdeaOrigin,
    IdeaTracking,
    IdeaTrackingSnapshot,
    IdeaValidationError,
    ObservableRef,
    normalize_tags,
    tracking_positions,
    tracking_signature,
    prepare_captured_values,
    thaw_captured_values,
    trial_key_for_positions,
)
from src.models.provenance import FreshnessRecord, ProvenanceRecord
from src.services.idea_store import IdeaNotFoundError, IdeaStorageWarning, IdeaStore, IdeaSummary
from src.utils.time import now_utc

IDEA_EXPORT_FORMAT = "gamma.idea"
# Version 2 (I2): the exported idea carries ``criteria``. Version 3 (I3a): ``tracking``
# (segments and cost model) and, when it could be rebuilt, the canonical series.
IDEA_EXPORT_FORMAT_VERSION = 3
IDEAS_SOURCE_PROVIDER = "gamma_ideas"

_TAB_LABELS = {
    "sitrep": "Sitrep",
    "ideas": "Ideas",
    "equity_research": "Equity Research",
    "strategy_lab": "Strategy Lab",
    "macro": "Macro",
    "prediction_markets": "Prediction Markets",
    "crypto": "Crypto",
    "fundamentals": "Fundamentals",
    "commodities": "Commodities",
    "maritime": "Sealanes",
    "copilot": "Copilot",
    "risk": "Risk",
    "iv": "Options",
    "portfolio": "Portfolio",
}
_STANCE_HEADINGS = {"supports": "Supports", "challenges": "Challenges", "context": "Context"}
_EDITABLE_TEXT_FIELDS = ("title", "thesis", "stance")


@dataclass(frozen=True)
class IdeaCreateRequest:
    title: str
    thesis: str = ""
    notes: str = ""
    stance: str = "neutral"
    legs: tuple[IdeaLeg, ...] = ()
    horizon: IdeaHorizon = field(default_factory=IdeaHorizon)
    tags: tuple[str, ...] = ()
    origin: IdeaOrigin = field(default_factory=IdeaOrigin)


@dataclass(frozen=True)
class IdeaPatchRequest:
    """Fields left as ``None`` are unchanged."""

    title: str | None = None
    thesis: str | None = None
    notes: str | None = None
    stance: str | None = None
    legs: tuple[IdeaLeg, ...] | None = None
    horizon: IdeaHorizon | None = None
    tags: tuple[str, ...] | None = None


@dataclass(frozen=True)
class IdeaEvidenceCreateRequest:
    kind: str
    stance: str
    title: str
    captured_values: Mapping[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord | None = None
    freshness: FreshnessRecord | None = None
    reopen: CrossTabHandoffEnvelope | None = None
    note: str = ""


@dataclass(frozen=True)
class IdeaCloseRequest:
    """The review written at close. ``expected`` defaults to the thesis.

    ``evidence_verdicts`` maps a pin id to ``held``, ``failed`` or ``unclear``;
    pins left out have no verdict. ``realized`` is the tracking headline at the
    moment of closing, filled by the caller that can rebuild the series.
    """

    outcome: str
    lesson: str
    expected: str | None = None
    realized_note: str = ""
    evidence_verdicts: Mapping[str, str] = field(default_factory=dict)
    realized: IdeaTrackingSnapshot | None = None


@dataclass(frozen=True)
class IdeaReviewStatistics:
    """The user's own closed record (I3b Review mode). Descriptive only: no score."""

    rows: list[dict[str, Any]]
    outcomes: dict[str, int]
    holding_days: dict[str, Any]
    realized: dict[str, Any]
    invalidation: dict[str, Any]
    retrieved_at: datetime


@dataclass(frozen=True)
class IdeaTrackingSettingsRequest:
    """Tracking assumptions; ``None`` leaves a field unchanged.

    ``per_side_bp`` replaces the listed classes' costs; ``leg_classes`` maps a
    leg key (``type:ID``) to an asset class, and an empty value drops the
    override so the leg returns to its detected class.
    """

    per_side_bp: Mapping[str, float] | None = None
    leg_classes: Mapping[str, str | None] | None = None
    benchmark: str | None = None
    # I4: coste por lado propio de una pierna; None quita el ajuste y vuelve al de su clase.
    leg_bp: Mapping[str, float | None] | None = None


@dataclass(frozen=True)
class IdeaCriterionRequest:
    """A criterion rule as the user wrote it. A blank ``label`` is generated from the rule."""

    kind: str
    observable: ObservableRef
    condition: str
    threshold: float | None = None
    window: str | None = None
    cadence: str = "daily_close"
    label: str | None = None


class CriteriaRegistryProtocol:
    """What the service needs from the observable registry (see ``idea_observables``)."""

    def validate(self, ref: ObservableRef, *, condition: str, cadence: str) -> ObservableRef:  # pragma: no cover
        raise NotImplementedError

    def describe(self, ref: ObservableRef, *, condition: str, threshold: float | None, window: str | None) -> str:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class IdeaListResult:
    items: list[IdeaSummary]
    total: int
    status_counts: dict[str, int]
    tags: list[str]
    storage_warnings: list[IdeaStorageWarning]
    retrieved_at: datetime


class IdeaService:
    def __init__(
        self,
        store: IdeaStore,
        *,
        clock: Callable[[], datetime] = now_utc,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
        criteria_registry: CriteriaRegistryProtocol | None = None,
    ) -> None:
        self.store = store
        self._clock = clock
        self._new_id = id_factory
        self.criteria_registry = criteria_registry

    # -- reads ---------------------------------------------------------------

    def list_ideas(self, *, statuses: Sequence[str] = (), tags: Sequence[str] = ()) -> IdeaListResult:
        wanted_statuses = {str(item).strip().lower() for item in statuses if str(item).strip()}
        unknown = wanted_statuses - set(IDEA_STATUSES)
        if unknown:
            raise IdeaValidationError(f"Unknown status filter {sorted(unknown)}; use {IDEA_STATUSES}.")
        wanted_tags = set(normalize_tags(tags))
        summaries = self.store.list_summaries()
        status_counts = {status: 0 for status in IDEA_STATUSES}
        all_tags: set[str] = set()
        for summary in summaries:
            status_counts[summary.status] = status_counts.get(summary.status, 0) + 1
            all_tags.update(summary.tags)
        items = [
            summary
            for summary in summaries
            if (not wanted_statuses or summary.status in wanted_statuses)
            and wanted_tags.issubset(summary.tags)
        ]
        return IdeaListResult(
            items=items,
            total=len(summaries),
            status_counts=status_counts,
            tags=sorted(all_tags),
            storage_warnings=self.store.storage_warnings(),
            retrieved_at=self._clock(),
        )

    def get_idea(self, idea_id: str) -> Idea:
        return self.store.require(idea_id)

    # -- writes --------------------------------------------------------------

    def create_idea(self, request: IdeaCreateRequest) -> Idea:
        now = self._clock()
        idea_id = self._new_id()
        idea = Idea(
            idea_id=idea_id,
            title=request.title,
            thesis=request.thesis,
            notes=request.notes,
            stance=request.stance,
            legs=tuple(request.legs),
            horizon=request.horizon,
            status="draft",
            origin=request.origin,
            tags=tuple(request.tags),
            created_at=now,
            updated_at=now,
        )
        body = "Created the idea."
        if request.origin.kind == "sitrep_follow_up":
            body = f"Promoted from the Sitrep follow-up “{request.origin.label or idea.title}”."
        elif request.origin.kind != "manual":
            body = f"Created from {request.origin.kind.replace('_', ' ')}" + (
                f" “{request.origin.label}”." if request.origin.label else "."
            )
        idea = idea.with_journal_entry(
            self._system_entry(idea_id, "created", body, now, {"origin_kind": request.origin.kind})
        )
        return self.store.create(idea)

    def update_idea(self, idea_id: str, patch: IdeaPatchRequest) -> Idea:
        def mutate(current: Idea) -> Idea:
            now = self._clock()
            changes: dict[str, Any] = {}
            if patch.title is not None:
                changes["title"] = patch.title
            if patch.thesis is not None:
                changes["thesis"] = patch.thesis
            if patch.notes is not None:
                changes["notes"] = patch.notes
            if patch.stance is not None:
                changes["stance"] = patch.stance
            if patch.legs is not None:
                legs = tuple(patch.legs)
                # I4: con una señal de libro adjuntada, las patas son las de la señal.
                if current.book_signal is not None and [leg.to_dict() for leg in legs] != [leg.to_dict() for leg in current.legs]:
                    raise IdeaValidationError(
                        f"The legs follow the attached signal ({current.book_signal.label}); detach the signal to edit them."
                    )
                changes["legs"] = legs
            if patch.horizon is not None:
                changes["horizon"] = patch.horizon
            if patch.tags is not None:
                changes["tags"] = tuple(patch.tags)
            candidate = replace(current, **changes)
            diff = _describe_changes(current, candidate)
            if not diff:
                return current
            candidate = replace(candidate, updated_at=now)
            labels = ", ".join(item["field"] for item in diff)
            edited = candidate.with_journal_entry(
                self._system_entry(idea_id, "edited", f"Edited {labels}.", now, {"changes": diff}),
                touched_at=now,
            )
            return self._reconcile_tracking(current, edited, now)

        return self.store.update(idea_id, mutate)

    def delete_idea(self, idea_id: str) -> bool:
        return self.store.delete(idea_id)

    def pin_evidence(self, idea_id: str, request: IdeaEvidenceCreateRequest) -> tuple[Idea, IdeaEvidence]:
        pinned: dict[str, IdeaEvidence] = {}

        def mutate(current: Idea) -> Idea:
            now = self._clock()
            evidence = IdeaEvidence(
                evidence_id=self._new_id(),
                idea_id=idea_id,
                kind=request.kind,
                stance=request.stance,
                title=request.title,
                captured_values=prepare_captured_values(request.captured_values),
                provenance=request.provenance,
                freshness=request.freshness,
                reopen=request.reopen,
                captured_at=now,
                note=request.note,
            )
            pinned["item"] = evidence
            source = _source_label(evidence)
            body = f"Pinned “{evidence.title}” as {evidence.stance}" + (f" from {source}." if source else ".")
            updated = replace(current, evidence=(*current.evidence, evidence), updated_at=now)
            return updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "evidence_pinned",
                    body,
                    now,
                    {"evidence_id": evidence.evidence_id, "stance": evidence.stance, "kind": evidence.kind},
                ),
                touched_at=now,
            )

        idea = self.store.update(idea_id, mutate)
        return idea, pinned["item"]

    def unpin_evidence(self, idea_id: str, evidence_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            match = next((item for item in current.evidence if item.evidence_id == evidence_id), None)
            if match is None:
                raise IdeaNotFoundError(f"Evidence {evidence_id} was not found on idea {idea_id}.")
            now = self._clock()
            updated = replace(
                current,
                evidence=tuple(item for item in current.evidence if item.evidence_id != evidence_id),
                updated_at=now,
            )
            # The journal keeps what was removed, so unpinning cannot rewrite the record.
            return updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "evidence_unpinned",
                    f"Unpinned “{match.title}” ({match.stance}, captured {match.captured_at.strftime('%Y-%m-%d %H:%M')} UTC).",
                    now,
                    {"evidence_id": match.evidence_id, "stance": match.stance, "kind": match.kind},
                ),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    # -- criteria (I2) ---------------------------------------------------------

    def add_criterion(self, idea_id: str, request: IdeaCriterionRequest) -> tuple[Idea, IdeaCriterion]:
        added: dict[str, IdeaCriterion] = {}

        def mutate(current: Idea) -> Idea:
            _require_editable_criteria(current)
            now = self._clock()
            criterion = self._build_criterion(current.idea_id, self._new_id(), request, now=now, created_at=now)
            added["item"] = criterion
            updated = replace(current, criteria=(*current.criteria, criterion), updated_at=now)
            return updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "criterion_added",
                    f"Added a {criterion.kind} criterion: “{criterion.label}” ({_cadence_text(criterion.cadence)}).",
                    now,
                    {"criterion_id": criterion.criterion_id, "rule": _rule_details(criterion)},
                ),
                touched_at=now,
            )

        idea = self.store.update(idea_id, mutate)
        return idea, added["item"]

    def update_criterion(self, idea_id: str, criterion_id: str, request: IdeaCriterionRequest) -> Idea:
        """Replace a criterion's rule. Changing the rule re-arms it; a label-only edit does not."""

        def mutate(current: Idea) -> Idea:
            _require_editable_criteria(current)
            existing = current.criterion(criterion_id)
            if existing is None:
                raise IdeaNotFoundError(f"Criterion {criterion_id} was not found on idea {idea_id}.")
            now = self._clock()
            candidate = self._build_criterion(idea_id, criterion_id, request, now=now, created_at=existing.created_at)
            if _rule_details(candidate) == _rule_details(existing):
                if candidate.label == existing.label:
                    return current
                updated = replace(existing, label=candidate.label)
                body = f"Renamed a criterion: “{existing.label}” → “{updated.label}”."
                details = {"criterion_id": criterion_id, "label_before": existing.label, "label_after": updated.label}
            else:
                # A new rule starts over: no inherited trigger or evaluation, armed from now.
                updated = candidate
                body = (
                    f"Changed a criterion: “{existing.label}” → “{updated.label}”; "
                    "it is re-armed from now."
                )
                if existing.triggered_at is not None:
                    body += (
                        f" The earlier trigger ({existing.triggered_at.strftime('%Y-%m-%d %H:%M')} UTC) "
                        "stays in this journal."
                    )
                details = {
                    "criterion_id": criterion_id,
                    "before": _rule_details(existing),
                    "after": _rule_details(updated),
                    "previous_state": existing.state,
                }
            criteria = tuple(updated if item.criterion_id == criterion_id else item for item in current.criteria)
            return replace(current, criteria=criteria, updated_at=now).with_journal_entry(
                self._system_entry(idea_id, "criterion_edited", body, now, details),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def remove_criterion(self, idea_id: str, criterion_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            existing = current.criterion(criterion_id)
            if existing is None:
                raise IdeaNotFoundError(f"Criterion {criterion_id} was not found on idea {idea_id}.")
            now = self._clock()
            criteria = tuple(item for item in current.criteria if item.criterion_id != criterion_id)
            body = f"Removed the {existing.kind} criterion “{existing.label}” (state {existing.state})."
            return replace(current, criteria=criteria, updated_at=now).with_journal_entry(
                self._system_entry(
                    idea_id,
                    "criterion_removed",
                    body,
                    now,
                    {
                        "criterion_id": criterion_id,
                        "rule": _rule_details(existing),
                        "state": existing.state,
                        "triggered_at": existing.triggered_at.isoformat() if existing.triggered_at else None,
                    },
                ),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def _build_criterion(
        self,
        idea_id: str,
        criterion_id: str,
        request: IdeaCriterionRequest,
        *,
        now: datetime,
        created_at: datetime,
    ) -> IdeaCriterion:
        if request.cadence not in CRITERION_CADENCES:
            raise IdeaValidationError(f"cadence must be one of {CRITERION_CADENCES}, got {request.cadence!r}.")
        observable = request.observable
        label = " ".join(str(request.label or "").split())
        if self.criteria_registry is not None:
            observable = self.criteria_registry.validate(observable, condition=request.condition, cadence=request.cadence)
            if not label:
                label = self.criteria_registry.describe(
                    observable, condition=request.condition, threshold=request.threshold, window=request.window
                )
        if not label:
            label = observable.label
        return IdeaCriterion(
            criterion_id=criterion_id,
            idea_id=idea_id,
            kind=request.kind,
            label=label,
            observable=observable,
            condition=request.condition,
            threshold=request.threshold,
            window=request.window,
            cadence=request.cadence,
            armed_at=now,
            created_at=created_at,
        )

    def add_journal_entry(self, idea_id: str, *, kind: str, body: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            now = self._clock()
            entry = IdeaJournalEntry(
                entry_id=self._new_id(),
                idea_id=idea_id,
                kind=kind,
                author="user",
                body=body,
                created_at=now,
            )
            return replace(current, updated_at=now).with_journal_entry(entry, touched_at=now)

        return self.store.update(idea_id, mutate)

    def activate(self, idea_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            if current.status != "draft":
                raise IdeaLifecycleError(f"Only a draft idea can be activated; this one is {current.status}.")
            if not current.thesis:
                raise IdeaLifecycleError("Write the thesis before activating the idea.")
            activated = self._transition(current, "active", "Activated the idea.")
            return self._reconcile_tracking(current, activated, activated.updated_at)

        return self.store.update(idea_id, mutate)

    def close(self, idea_id: str, request: IdeaCloseRequest) -> Idea:
        """Close an active idea with its review; tracking exits at the next close."""

        def mutate(current: Idea) -> Idea:
            if current.status != "active":
                raise IdeaLifecycleError(f"Only an active idea can be closed; this one is {current.status}.")
            outcome = str(request.outcome or "").strip().lower()
            if outcome not in REVIEW_OUTCOMES:
                raise IdeaValidationError(f"Choose an outcome: {', '.join(REVIEW_OUTCOMES)}.")
            pins = {item.evidence_id: item for item in current.evidence}
            verdicts = []
            for evidence_id, verdict in (request.evidence_verdicts or {}).items():
                pin = pins.get(str(evidence_id))
                if pin is None:
                    raise IdeaValidationError(f"Evidence {evidence_id} is not pinned on this idea.")
                value = str(verdict or "").strip().lower()
                if not value:
                    continue
                if value not in EVIDENCE_VERDICTS:
                    raise IdeaValidationError(f"An evidence verdict must be one of {EVIDENCE_VERDICTS}.")
                verdicts.append(IdeaEvidenceVerdict(evidence_id=pin.evidence_id, verdict=value, title=pin.title, stance=pin.stance))
            now = self._clock()
            review = IdeaReview(
                review_id=self._new_id(),
                idea_id=idea_id,
                outcome=outcome,
                lesson=request.lesson,
                expected=(request.expected if request.expected is not None and request.expected.strip() else current.thesis),
                realized_note=request.realized_note,
                opened_at=_episode_opened_at(current),
                closed_at=now,
                evidence_verdicts=tuple(verdicts),
                criteria_at_close=tuple(
                    IdeaCriterionAtClose(
                        criterion_id=item.criterion_id,
                        kind=item.kind,
                        label=item.label,
                        state=item.state,
                        triggered_at=item.triggered_at,
                        first_met_at=item.trigger_evaluation.first_met_at if item.trigger_evaluation else None,
                    )
                    for item in current.criteria
                ),
                realized=request.realized,
            )
            closed = replace(current, status="closed", closed_at=now, reviews=(*current.reviews, review), updated_at=now)
            closed = closed.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "status_changed",
                    f"Closed the idea as {outcome}. Lesson: {_clip(review.lesson, 400)}",
                    now,
                    {"from": "active", "to": "closed", "outcome": outcome, "review_id": review.review_id},
                ),
                touched_at=now,
            )
            return self._reconcile_tracking(current, closed, now)

        return self.store.update(idea_id, mutate)

    def reopen(self, idea_id: str) -> Idea:
        """Return a closed idea to active; the review of the close stays, tracking opens a new segment."""

        def mutate(current: Idea) -> Idea:
            if current.status != "closed":
                raise IdeaLifecycleError(f"Only a closed idea can be reopened; this one is {current.status}.")
            now = self._clock()
            review = current.current_review
            kept = f" The review of {review.closed_at.strftime('%Y-%m-%d')} ({review.outcome}) stays in the record." if review else ""
            reopened = replace(current, status="active", closed_at=None, updated_at=now).with_journal_entry(
                self._system_entry(
                    idea_id,
                    "status_changed",
                    "Reopened the idea." + kept,
                    now,
                    {"from": "closed", "to": "active", "review_id": review.review_id if review else None},
                ),
                touched_at=now,
            )
            return self._reconcile_tracking(current, reopened, now)

        return self.store.update(idea_id, mutate)

    # -- test and risk snapshots (I3c) ------------------------------------------

    def add_test_snapshot(self, idea_id: str, snapshot: IdeaTestSnapshot) -> Idea:
        """Keep a backtest snapshot the user asked for; journaled with its headline."""

        def mutate(current: Idea) -> Idea:
            _require_snapshot_status(current)
            now = self._clock()
            # I4: un backtest con un conjunto de pesos nuevo es una prueba más del libro de pruebas.
            key = trial_key_for_positions(snapshot.positions())
            trials = current.trials
            if all(trial.key != key for trial in trials):
                trials = (
                    *trials,
                    IdeaTrial(key=key, kind="legs", recorded_at=now, label=f"Backtest of the legs: {_snapshot_legs_text(snapshot)}"),
                )
            counted = replace(snapshot, trial_count=len(trials), trial_count_lower_bound=current.trials_lower_bound)
            total = counted.metrics.get("total_return")
            body = (
                f"{_snapshot_subject(counted, 'backtest')} ({counted.window_start or 'N/A'} to {counted.window_end or 'N/A'}, "
                f"{counted.observations} observations): total {_pct(total)}, max drawdown {_pct(counted.metrics.get('max_drawdown'))}, "
                f"{counted.benchmark} {_pct(counted.metrics.get('benchmark_total_return'))}. In-sample, no costs. "
                f"Trials recorded for this idea: {_trials_text(len(trials), current.trials_lower_bound)}."
            )
            updated = replace(current, tests=(*current.tests, counted), trials=trials, updated_at=now)
            return updated.with_journal_entry(
                self._system_entry(idea_id, "test_refreshed", body, now, {"snapshot_id": snapshot.snapshot_id, "trial_count": len(trials)}),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def add_risk_snapshot(self, idea_id: str, snapshot: IdeaRiskSnapshot) -> Idea:
        """Keep a risk snapshot the user asked for; journaled with its headline."""

        def mutate(current: Idea) -> Idea:
            _require_snapshot_status(current)
            now = self._clock()
            worst = snapshot.worst_episode
            body = (
                f"{_snapshot_subject(snapshot, 'risk')} ({snapshot.observations} observations): {int(snapshot.alpha * 100)}% one-day historical VaR "
                f"{_pct(_loss(snapshot.metrics.get('historical_var')))}, expected shortfall {_pct(_loss(snapshot.metrics.get('historical_es')))}"
                + (f"; worst replayed episode {worst.label} {_pct(worst.book_return)}." if worst else "; no stress episode in the available history.")
            )
            updated = replace(current, risks=(*current.risks, snapshot), updated_at=now)
            return updated.with_journal_entry(
                self._system_entry(idea_id, "risk_refreshed", body, now, {"snapshot_id": snapshot.snapshot_id}),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def review_statistics(self) -> IdeaReviewStatistics:
        return build_review_statistics(self.store.list_summaries(), retrieved_at=self._clock())

    def archive(self, idea_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            if current.status not in {"draft", "active", "closed"}:
                raise IdeaLifecycleError(f"Only a draft, active or closed idea can be archived; this one is {current.status}.")
            archived = self._transition(current, "archived", f"Archived the idea (was {current.status}).")
            return self._reconcile_tracking(current, archived, archived.updated_at)

        return self.store.update(idea_id, mutate)

    def restore(self, idea_id: str) -> Idea:
        """Return an archived idea to the status it had when it was archived."""

        def mutate(current: Idea) -> Idea:
            if current.status != "archived":
                raise IdeaLifecycleError(f"Only an archived idea can be restored; this one is {current.status}.")
            previous = "draft"
            for entry in reversed(current.journal):
                if entry.kind == "status_changed" and entry.details.get("to") == "archived":
                    previous = str(entry.details.get("from") or "draft")
                    break
            # Una idea cerrada vuelve cerrada solo si conserva el cierre y su revisión.
            if previous not in {"draft", "active", "closed"} or (previous == "closed" and current.current_review is None):
                previous = "draft"
            restored = self._transition(current, previous, f"Restored the idea from the archive to {previous}.")
            return self._reconcile_tracking(current, restored, restored.updated_at)

        return self.store.update(idea_id, mutate)

    # -- signals (I4) -----------------------------------------------------------

    def attach_signal(self, idea_id: str, signal: IdeaSignal, trials: Sequence[IdeaTrial] = ()) -> Idea:
        """Attach a signal built from a Script run or an import; journaled, never executed.

        The trial ledger only grows; the signal's ``trial_count`` is its size
        after this attach. A book signal (positions or weights) sets the legs
        and, on an active idea, closes the open tracking segment and opens the
        next one, which rebalances from the previous book at its exit close.
        A returns signal is validation only and leaves tracking as it was,
        unless it replaces a book signal, whose book then returns to the legs.
        """

        def mutate(current: Idea) -> Idea:
            if current.status not in {"draft", "active"}:
                raise IdeaLifecycleError(f"A signal attaches to a draft or active idea; this one is {current.status}.")
            if signal.idea_id != idea_id:
                raise IdeaValidationError("The signal belongs to another idea.")
            now = self._clock()
            ledger = list(current.trials)
            known = {trial.key for trial in ledger}
            for trial in trials:
                if trial.key not in known:
                    ledger.append(replace(trial, signal_id=trial.signal_id or signal.signal_id))
                    known.add(trial.key)
            if len(ledger) > TRIAL_LEDGER_MAX:
                raise IdeaValidationError(f"The trial ledger holds at most {TRIAL_LEDGER_MAX} entries.")
            attached = replace(
                signal,
                attached_at=now,
                trial_count=max(1, len(ledger)),
                trial_count_lower_bound=current.trials_lower_bound,
            )
            previous = current.current_signal
            signals = list(current.signals)
            if previous is not None:
                signals[-1] = replace(previous, detached_at=now)
            signals.append(attached)
            updated = replace(current, signals=tuple(signals), trials=tuple(ledger), updated_at=now)
            if attached.is_book:
                updated = replace(updated, legs=attached.idea_legs())
            replaced = f" It replaces {previous.label}." if previous is not None else ""
            body = (
                f"Attached the signal {attached.label} ({attached.source}, {attached.output_kind}"
                + (f", as of {attached.as_of.isoformat()}" if attached.as_of else "")
                + f"); {_trials_text(attached.trial_count, attached.trial_count_lower_bound)}."
                + (" A returns signal is validation only; it does not drive tracking." if not attached.is_book else " The legs now follow its book.")
                + replaced
            )
            updated = updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "signal_attached",
                    body,
                    now,
                    {
                        "signal_id": attached.signal_id,
                        "source": attached.source,
                        "output_kind": attached.output_kind,
                        "trial_count": attached.trial_count,
                        "replaced_signal_id": previous.signal_id if previous else None,
                    },
                ),
                touched_at=now,
            )
            return self._reconcile_signal_tracking(current, updated, now)

        return self.store.update(idea_id, mutate)

    def detach_signal(self, idea_id: str) -> Idea:
        """Detach the current signal. It stays in the record; a book returns to the legs as they are."""

        def mutate(current: Idea) -> Idea:
            signal = current.current_signal
            if signal is None:
                raise IdeaValidationError("No signal is attached to this idea.")
            if current.status not in {"draft", "active"}:
                raise IdeaLifecycleError(f"A signal detaches from a draft or active idea; this one is {current.status}.")
            now = self._clock()
            signals = (*current.signals[:-1], replace(signal, detached_at=now))
            updated = replace(current, signals=signals, updated_at=now).with_journal_entry(
                self._system_entry(
                    idea_id,
                    "signal_detached",
                    f"Detached the signal {signal.label}. It stays in the record"
                    + ("; the legs keep its last book and can be edited again." if signal.is_book else "."),
                    now,
                    {"signal_id": signal.signal_id},
                ),
                touched_at=now,
            )
            return self._reconcile_signal_tracking(current, updated, now)

        return self.store.update(idea_id, mutate)

    def _reconcile_signal_tracking(self, before: Idea, after: Idea, now: datetime) -> Idea:
        """Open the next segment when the book signal changes on an active idea."""
        if after.status != "active":
            return after
        old_book = before.book_signal
        new_book = after.book_signal
        if old_book is None and new_book is None:
            return after
        if old_book is not None and new_book is not None and old_book.signal_id == new_book.signal_id:
            return after
        tracking = after.tracking or IdeaTracking()
        open_segment = tracking.open_segment
        closed_number: int | None = None
        if open_segment is not None:
            tracking = tracking.with_open_segment_closed(at=now, reason="signal_changed")
            closed_number = open_segment.number
        opened = None
        if after.legs:
            if new_book is not None:
                start_reason = "signal_changed" if old_book is not None else "signal_attached"
                note = f"{_START_REASON_TEXT[start_reason]}: {new_book.label}"
            else:
                start_reason = "signal_detached"
                note = f"{_START_REASON_TEXT[start_reason]}: {old_book.label if old_book else 'signal'}; the legs keep its book"
            tracking = tracking.with_open_segment(
                legs=after.legs, stance=after.stance, at=now, reason=start_reason, note=note, signal=new_book
            )
            opened = tracking.open_segment
        if closed_number is None and opened is None:
            return after
        tracking = replace(tracking, snapshot=None)
        parts: list[str] = []
        if closed_number is not None:
            parts.append(f"Closed tracking segment {closed_number} (signal changed); its book is rebalanced at the next close.")
        if opened is not None:
            parts.append(
                f"Opened tracking segment {opened.number} ({_tracked_legs_text(opened)}); it enters at the next close, "
                "paying the per-side cost on each instrument's turnover."
            )
            if opened.untracked_reason:
                parts.append(f"It cannot be priced: {opened.untracked_reason}")
        details = {
            "closed_segment": closed_number,
            "end_reason": "signal_changed" if closed_number is not None else None,
            "opened_segment": opened.number if opened else None,
            "start_reason": opened.start_reason if opened else None,
        }
        return replace(after, tracking=tracking).with_journal_entry(
            self._system_entry(after.idea_id, "tracking_segment", f"{TRACKING_LABEL}. " + " ".join(parts), now, details),
            touched_at=after.updated_at,
        )

    # -- tracking (I3a) --------------------------------------------------------

    def update_tracking_settings(self, idea_id: str, request: IdeaTrackingSettingsRequest) -> Idea:
        """Change the cost assumptions or the benchmark; journaled, never rewrites a segment."""

        def mutate(current: Idea) -> Idea:
            now = self._clock()
            tracking = current.tracking or IdeaTracking()
            cost_model = tracking.cost_model
            changes: list[dict[str, Any]] = []
            per_side = dict(cost_model.per_side_bp)
            if request.per_side_bp is not None:
                for asset_class, value in request.per_side_bp.items():
                    if asset_class not in per_side:
                        raise IdeaValidationError(f"{asset_class} has no stated cost in basis points.")
                    number = float(value)
                    if per_side[asset_class] != number:
                        changes.append({"field": f"cost.{asset_class}", "before": per_side[asset_class], "after": number})
                        per_side[asset_class] = number
            leg_classes = dict(cost_model.leg_classes)
            if request.leg_classes is not None:
                known = {leg.key: leg for segment in tracking.segments for leg in segment.legs}
                for key, value in request.leg_classes.items():
                    key_text = str(key or "").strip()
                    if key_text not in known:
                        raise IdeaValidationError(f"{key_text} is not a tracked leg of this idea.")
                    target = str(value or "").strip().lower() or None
                    # Solo clases con coste declarado: el seguimiento diario no lee cotizaciones en vivo.
                    if target is not None and target not in TRACKING_BP_CLASSES:
                        raise IdeaValidationError(f"A tracked leg's cost class must be one of {TRACKING_BP_CLASSES}.")
                    detected = known[key_text].asset_class
                    before = leg_classes.get(key_text, detected)
                    after = target or detected
                    if target is None or target == detected:
                        leg_classes.pop(key_text, None)
                    else:
                        leg_classes[key_text] = target
                    if before != after:
                        changes.append({"field": f"class.{key_text}", "before": before, "after": after})
            leg_bp = dict(cost_model.leg_bp)
            if request.leg_bp is not None:
                known = {leg.key: leg for segment in tracking.segments for leg in segment.legs}
                for key, value in request.leg_bp.items():
                    key_text = str(key or "").strip()
                    if key_text not in known:
                        raise IdeaValidationError(f"{key_text} is not a tracked leg of this idea.")
                    before_bp = leg_bp.get(key_text)
                    if value is None:
                        leg_bp.pop(key_text, None)
                    else:
                        number = float(value)
                        if not 0 <= number <= TRACKING_COST_BP_MAX:
                            raise IdeaValidationError(f"A leg cost must be between 0 and {TRACKING_COST_BP_MAX:g} bp per side.")
                        leg_bp[key_text] = number
                    after_bp = leg_bp.get(key_text)
                    if before_bp != after_bp:
                        changes.append({"field": f"leg_cost.{key_text}", "before": before_bp, "after": after_bp})
            benchmark = tracking.benchmark
            if request.benchmark is not None:
                candidate = str(request.benchmark).strip().upper()
                if candidate and candidate != benchmark:
                    changes.append({"field": "benchmark", "before": benchmark, "after": candidate})
                    benchmark = candidate
            if not changes:
                return current
            updated_model = IdeaCostModel(per_side_bp=per_side, leg_classes=leg_classes, updated_at=now, leg_bp=leg_bp)
            # El snapshot queda obsoleto: el tablero no debe mostrar una cifra calculada con otros supuestos.
            tracking = replace(tracking, cost_model=updated_model, benchmark=benchmark, snapshot=None)
            body = "Changed the tracking assumptions: " + "; ".join(
                f"{_setting_label(item['field'])} {_setting_value(item['before'])} → {_setting_value(item['after'])}"
                for item in changes
            ) + ". The gross record is unchanged; net figures are recomputed with the new assumptions."
            return replace(current, tracking=tracking, updated_at=now).with_journal_entry(
                self._system_entry(idea_id, "tracking_settings", body, now, {"changes": changes}),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def store_tracking_snapshot(
        self, idea_id: str, snapshot: IdeaTrackingSnapshot, *, basis: tuple[Any, ...] | None = None
    ) -> Idea:
        """Keep the latest computed headline for the Board without touching ``updated_at``.

        ``basis`` is the ``tracking_signature`` of the record the series was
        computed from; if the record changed meanwhile (a leg edit, an archive,
        a cost change), the headline describes another book and is dropped.
        """

        def mutate(current: Idea) -> Idea:
            if current.tracking is None or snapshot.same_figures(current.tracking.snapshot):
                return current
            if basis is not None and tracking_signature(current.tracking) != basis:
                return current
            return replace(current, tracking=replace(current.tracking, snapshot=snapshot))

        return self.store.update(idea_id, mutate)

    def _reconcile_tracking(self, before: Idea, after: Idea, now: datetime) -> Idea:
        """Open or close tracking segments for a status or legs change, with a journal entry.

        Only an active idea is tracked. Activation and restore open a segment
        with the current legs; a leg edit that changes the book closes the open
        segment and opens the next one; leaving ``active`` closes it.
        """
        was_active = before.status == "active"
        is_active = after.status == "active"
        if not was_active and not is_active:
            return after
        tracking = after.tracking or IdeaTracking()
        open_segment = tracking.open_segment
        positions_changed = tracking_positions(before.legs, before.stance) != tracking_positions(after.legs, after.stance)
        closed_number: int | None = None
        end_reason: str | None = None
        if open_segment is not None and (not is_active or positions_changed):
            if not is_active:
                end_reason = "closed" if after.status == "closed" else "archived"
            else:
                end_reason = "legs_edited" if after.legs else "legs_removed"
            tracking = tracking.with_open_segment_closed(at=now, reason=end_reason)
            closed_number = open_segment.number
        opened = None
        # Solo se abre un segmento al activar, restaurar o reabrir, o si las patas cambian.
        if is_active and after.legs and tracking.open_segment is None and (not was_active or positions_changed):
            if not was_active:
                start_reason = {"draft": "activated", "closed": "reopened"}.get(before.status, "restored")
            else:
                start_reason = "legs_edited" if closed_number is not None else "legs_added"
            note = _segment_note(start_reason, before, after)
            tracking = tracking.with_open_segment(
                legs=after.legs, stance=after.stance, at=now, reason=start_reason, note=note, signal=after.book_signal
            )
            opened = tracking.open_segment
        if closed_number is None and opened is None:
            return after
        # Cambia el libro: el titular anterior ya no describe el registro actual.
        tracking = replace(tracking, snapshot=None)
        parts: list[str] = []
        if closed_number is not None:
            parts.append(
                f"Closed tracking segment {closed_number} ({_END_REASON_TEXT[end_reason or 'archived']}); "
                "its book exits at the next close."
            )
        if opened is not None:
            parts.append(f"Opened tracking segment {opened.number} ({_tracked_legs_text(opened)}); its book enters at the next close.")
            if opened.untracked_reason:
                parts.append(f"It cannot be priced: {opened.untracked_reason}")
        details: dict[str, Any] = {
            "closed_segment": closed_number,
            "end_reason": end_reason,
            "opened_segment": opened.number if opened else None,
            "start_reason": opened.start_reason if opened else None,
        }
        body = f"{TRACKING_LABEL}. " + " ".join(parts)
        return replace(after, tracking=tracking).with_journal_entry(
            self._system_entry(after.idea_id, "tracking_segment", body, now, details),
            touched_at=after.updated_at,
        )

    # -- export --------------------------------------------------------------

    def export_json(self, idea_id: str, *, tracking_result: Mapping[str, Any] | None = None) -> dict[str, Any]:
        idea = self.store.require(idea_id)
        payload: dict[str, Any] = {
            "format": IDEA_EXPORT_FORMAT,
            "format_version": IDEA_EXPORT_FORMAT_VERSION,
            "exported_at": self._clock().isoformat(),
            "source_provider": IDEAS_SOURCE_PROVIDER,
            "origin": "idea_service.export_json",
            "notice": "Local research record. Evidence is frozen as captured. Not advice and not an order.",
            "idea": idea.to_dict(),
        }
        if idea.tracking is not None:
            payload["tracking_label"] = TRACKING_LABEL
            payload["tracking_series"] = dict(tracking_result) if tracking_result is not None else None
        return payload

    def export_markdown(self, idea_id: str, *, tracking_result: Mapping[str, Any] | None = None) -> str:
        idea = self.store.require(idea_id)
        return render_idea_markdown(idea, exported_at=self._clock(), tracking_result=tracking_result)

    # -- helpers -------------------------------------------------------------

    def _transition(self, current: Idea, status: str, body: str) -> Idea:
        now = self._clock()
        updated = replace(current, status=status, updated_at=now)
        return updated.with_journal_entry(
            self._system_entry(current.idea_id, "status_changed", body, now, {"from": current.status, "to": status}),
            touched_at=now,
        )

    def _system_entry(
        self,
        idea_id: str,
        kind: str,
        body: str,
        created_at: datetime,
        details: Mapping[str, Any] | None = None,
    ) -> IdeaJournalEntry:
        return IdeaJournalEntry(
            entry_id=self._new_id(),
            idea_id=idea_id,
            kind=kind,
            author="system",
            body=body,
            created_at=created_at,
            details=dict(details or {}),
        )


# ---------------------------------------------------------------------------
# Change description and Markdown export
# ---------------------------------------------------------------------------


_END_REASON_TEXT = {
    "legs_edited": "legs edited",
    "legs_removed": "legs removed",
    "archived": "idea archived",
    "closed": "idea closed",
    "signal_changed": "signal changed",
}
_START_REASON_TEXT = {
    "activated": "Activated",
    "reopened": "Reopened after a close",
    "legs_edited": "Legs edited",
    "legs_added": "Legs added",
    "restored": "Restored from the archive",
    "migrated": "Tracking began in a later build",
    "signal_attached": "Signal attached",
    "signal_changed": "Signal changed",
    "signal_detached": "Signal detached",
}


def _snapshot_subject(snapshot: Any, kind: str) -> str:
    """"Ran a backtest of the legs", or "Attached a Strategy Lab backtest of <book>" (I4c)."""
    attached = snapshot.source_ids.get("attached_from") if snapshot.source != "idea_legs" else None
    if attached:
        what = "backtest" if kind == "backtest" else "risk run"
        return f"Attached a {attached} {what} of {snapshot.source_ids.get('attached_label') or 'a book'}"
    return "Ran a backtest of the legs" if kind == "backtest" else "Ran risk on the legs"


def _trials_text(count: int, lower_bound: bool) -> str:
    """"1 trial", "at least 4 trials": the size of the idea's trial ledger."""
    prefix = "at least " if lower_bound else ""
    return f"{prefix}{count} trial{'s' if count != 1 else ''}"


def _snapshot_legs_text(snapshot: Any) -> str:
    return _clip("; ".join(f"{leg.entity.label} {float(leg.weight or 0.0) * 100:+.0f}%" for leg in snapshot.legs), 160)
_SETTING_LABELS = {
    "cost.us_equity_liquid": "liquid US equities and ETFs",
    "cost.equity_other": "other equities and ETFs",
    "cost.futures": "futures",
    "cost.crypto_spot": "spot crypto",
    "benchmark": "benchmark",
}


def _setting_label(field_name: str) -> str:
    if field_name.startswith("class."):
        return f"class of {field_name.split(':', 1)[-1]}"
    if field_name.startswith("leg_cost."):
        return f"cost of {field_name.split(':', 1)[-1]}"
    return _SETTING_LABELS.get(field_name, field_name)


def _setting_value(value: Any) -> str:
    if value is None:
        return "class default"
    if isinstance(value, float):
        return f"{value:g} bp"
    return str(value).replace("_", " ")


def _tracked_legs_text(segment: Any) -> str:
    parts = []
    for leg in segment.legs:
        share = "" if leg.weight is None else f" {leg.weight * 100:+.0f}%"
        parts.append(f"{leg.entity.label}{share}")
    return _clip("; ".join(parts), 240)


def _segment_note(reason: str, before: Idea, after: Idea) -> str:
    text = _START_REASON_TEXT.get(reason, reason)
    if reason in {"legs_edited", "legs_added"}:
        return f"{text}: {_legs_text(before)} → {_legs_text(after)}"
    return text


def _require_snapshot_status(idea: Idea) -> None:
    if idea.status not in {"draft", "active"}:
        raise IdeaLifecycleError(f"Tests and risk run on a draft or active idea; this one is {idea.status}.")


def _episode_opened_at(idea: Idea) -> datetime:
    """When the current episode began: the activation, or the reopen after an earlier close."""
    for entry in reversed(idea.journal):
        if entry.kind == "status_changed" and entry.details.get("to") == "active" and entry.details.get("from") in {"draft", "closed"}:
            return entry.created_at
    return idea.activated_at or idea.created_at


def _median(values: Sequence[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _mean(values: Sequence[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def build_review_statistics(summaries: Sequence[IdeaSummary], *, retrieved_at: datetime) -> IdeaReviewStatistics:
    """Describe the closed record: outcomes, holding time, realized returns, invalidations.

    Only the review of each idea's current close counts (closed, or archived
    after closing). The realized return is the tracking headline as it stands
    now (final once the exit close is priced), falling back to the figure at
    close. Every statistic carries its sample size; nothing is scored.
    """
    rows: list[dict[str, Any]] = []
    for summary in summaries:
        review = summary.review
        if not review:
            continue
        snapshot = (summary.tracking or {}).get("snapshot") if summary.tracking else None
        at_close = review.get("realized_at_close") or None
        source = snapshot if snapshot and snapshot.get("net_return") is not None else at_close
        net = source.get("net_return") if source else None
        benchmark = source.get("benchmark_return") if source else None
        rows.append(
            {
                "idea_id": summary.idea_id,
                "title": summary.title,
                "stance": summary.stance,
                "status": summary.status,
                "tags": list(summary.tags),
                "outcome": review["outcome"],
                "opened_at": review["opened_at"],
                "closed_at": review["closed_at"],
                "holding_days": review["holding_days"],
                "expected": review.get("expected") or "",
                "lesson": review.get("lesson") or "",
                "net_return": net,
                "benchmark": (source or {}).get("benchmark"),
                "benchmark_return": benchmark,
                "excess_return": None if net is None or benchmark is None else net - benchmark,
                "realized_final": bool(snapshot and snapshot.get("final") and source is snapshot),
                "realized_as_of": (source or {}).get("as_of"),
                "tracked": source is not None,
                "invalidation_criteria": int(review.get("invalidation_criteria") or 0),
                "first_invalidation_at": review.get("first_invalidation_at"),
                "evidence_verdicts": dict(review.get("evidence_verdicts") or {}),
            }
        )
    rows.sort(key=lambda row: str(row["closed_at"]), reverse=True)
    outcomes = {outcome: sum(1 for row in rows if row["outcome"] == outcome) for outcome in REVIEW_OUTCOMES}
    days = [float(row["holding_days"]) for row in rows]
    by_outcome = {
        outcome: _median([float(row["holding_days"]) for row in rows if row["outcome"] == outcome]) for outcome in REVIEW_OUTCOMES
    }
    priced = [row for row in rows if row["net_return"] is not None]
    nets = [float(row["net_return"]) for row in priced]
    excess = [float(row["excess_return"]) for row in priced if row["excess_return"] is not None]
    losses = [row for row in priced if float(row["net_return"]) < 0]
    with_rules = [row for row in losses if row["invalidation_criteria"] > 0]
    fired = [row for row in losses if row["first_invalidation_at"]]
    return IdeaReviewStatistics(
        rows=rows,
        outcomes=outcomes,
        holding_days={
            "count": len(days),
            "median": _median(days),
            "mean": _mean(days),
            "min": min(days) if days else None,
            "max": max(days) if days else None,
            "median_by_outcome": by_outcome,
        },
        realized={
            "count": len(priced),
            "untracked": len(rows) - len(priced),
            "median_net": _median(nets),
            "median_excess": _median(excess),
            "excess_count": len(excess),
            "positive": sum(1 for value in nets if value > 0),
            "negative": len(losses),
            "median_net_by_outcome": {
                outcome: _median([float(row["net_return"]) for row in priced if row["outcome"] == outcome]) for outcome in REVIEW_OUTCOMES
            },
        },
        invalidation={
            "losses": len(losses),
            "losses_with_invalidation_criteria": len(with_rules),
            "losses_with_trigger_before_close": len(fired),
            "share_of_losses": (len(fired) / len(losses)) if losses else None,
            "share_of_losses_with_criteria": (len(fired) / len(with_rules)) if with_rules else None,
        },
        retrieved_at=retrieved_at,
    )


def _require_editable_criteria(idea: Idea) -> None:
    if idea.status not in {"draft", "active"}:
        raise IdeaLifecycleError(f"Criteria can change on a draft or active idea; this one is {idea.status}.")


def _rule_details(criterion: IdeaCriterion) -> dict[str, Any]:
    return {
        "kind": criterion.kind,
        "observable": criterion.observable.to_dict(),
        "condition": criterion.condition,
        "threshold": criterion.threshold,
        "window": criterion.window,
        "cadence": criterion.cadence,
    }


def _cadence_text(cadence: str) -> str:
    return {"on_open": "on open", "daily_close": "at the daily close", "intraday": "intraday"}.get(cadence, cadence)


def _describe_changes(before: Idea, after: Idea) -> list[dict[str, Any]]:
    """List changed fields; short fields keep before/after so the journal stays honest."""
    diff: list[dict[str, Any]] = []
    for name in _EDITABLE_TEXT_FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            diff.append({"field": name, "before": _clip(old), "after": _clip(new)})
    if before.notes != after.notes:
        diff.append({"field": "notes", "before_length": len(before.notes), "after_length": len(after.notes)})
    if [leg.to_dict() for leg in before.legs] != [leg.to_dict() for leg in after.legs]:
        diff.append({"field": "legs", "before": _legs_text(before), "after": _legs_text(after)})
    if before.horizon != after.horizon:
        diff.append({"field": "horizon", "before": _horizon_text(before.horizon), "after": _horizon_text(after.horizon)})
    if before.tags != after.tags:
        diff.append({"field": "tags", "before": ", ".join(before.tags), "after": ", ".join(after.tags)})
    return diff


def _clip(value: str, limit: int = 300) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _legs_text(idea: Idea) -> str:
    return _clip("; ".join(_leg_text(leg) for leg in idea.legs) or "none")


def _leg_text(leg: IdeaLeg) -> str:
    weight = "" if leg.weight is None else f" {leg.weight:+g}"
    return f"{leg.entity.label}{weight}"


def _horizon_text(horizon: IdeaHorizon) -> str:
    parts = []
    if horizon.review_date:
        parts.append(f"review {horizon.review_date.isoformat()}")
    if horizon.holding_window:
        parts.append(horizon.holding_window)
    return " · ".join(parts) or "none"


def _tab_label(tab: str | None) -> str:
    if not tab:
        return ""
    return _TAB_LABELS.get(tab, tab.replace("_", " ").title())


def _source_label(evidence: IdeaEvidence) -> str:
    if evidence.reopen is None:
        return ""
    tab = _tab_label(evidence.reopen.source_tab)
    mode = evidence.reopen.source_mode
    return f"{tab} / {mode.replace('_', ' ')}" if mode else tab


def _md(value: Any) -> str:
    """Escape a value for one Markdown table cell or line."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _ts(value: datetime | None) -> str:
    return f"{value.strftime('%Y-%m-%d %H:%M')} UTC" if value else "N/A"


def render_idea_markdown(
    idea: Idea, *, exported_at: datetime, tracking_result: Mapping[str, Any] | None = None
) -> str:
    stance = idea.stance.capitalize()
    lines: list[str] = [
        f"# {idea.title}",
        "",
        "> Research record exported from Gamma. Evidence is frozen as captured with its provenance; "
        "this is not advice and Gamma places no orders.",
        "",
        f"- Status: {idea.status.capitalize()}",
        f"- Stance: {stance}",
        f"- Horizon: {_horizon_text(idea.horizon)}",
        f"- Tags: {', '.join(idea.tags) if idea.tags else 'none'}",
        f"- Origin: {idea.origin.kind.replace('_', ' ')}"
        + (f" — {idea.origin.label}" if idea.origin.label else "")
        + (f" (ref `{idea.origin.source_ref}`)" if idea.origin.source_ref else ""),
        f"- Created: {_ts(idea.created_at)} · Updated: {_ts(idea.updated_at)}",
        "",
        "## Thesis",
        "",
        idea.thesis or "_No thesis written yet._",
        "",
        "## Legs",
        "",
    ]
    if idea.legs:
        lines += ["| Instrument | Type | Id | Weight |", "| --- | --- | --- | ---: |"]
        for leg in idea.legs:
            weight = "" if leg.weight is None else f"{leg.weight:+g}"
            lines.append(
                f"| {_md(leg.entity.label)} | {_md(leg.entity.entity_type)} | `{_md(leg.entity.normalized_id)}` | {weight} |"
            )
    else:
        lines.append("_No legs._")
    lines += ["", "## Notes", "", idea.notes or "_No notes._", "", "## Evidence", ""]
    counts = idea.evidence_counts()
    lines.append(
        " · ".join(f"{_STANCE_HEADINGS[stance_key]} {counts[stance_key]}" for stance_key in EVIDENCE_STANCES)
    )
    for stance_key in EVIDENCE_STANCES:
        pins = [item for item in idea.evidence if item.stance == stance_key]
        lines += ["", f"### {_STANCE_HEADINGS[stance_key]} ({len(pins)})"]
        if not pins:
            lines += ["", "_None._"]
        for pin in pins:
            lines += ["", *_evidence_markdown(pin)]
    lines += ["", "## Criteria", ""]
    if idea.criteria:
        lines += [
            "| Kind | Criterion | Cadence | State | Last value | Triggered | Source |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for criterion in idea.criteria:
            last = criterion.last_evaluation
            trigger = criterion.trigger_evaluation
            value = (last.value_display or "N/A") if last else "N/A"
            if last and last.as_of:
                value += f" ({last.as_of.strftime('%Y-%m-%d')})"
            triggered = "—"
            if criterion.triggered_at:
                met = trigger.first_met_at if trigger else None
                triggered = _ts(criterion.triggered_at) + (f", first met {met.strftime('%Y-%m-%d')}" if met else "")
            source = (trigger or last).provenance.source_provider if (trigger or last) and (trigger or last).provenance else "—"
            state = criterion.state + (f": {last.reason}" if last and last.reason and criterion.state != "triggered" else "")
            lines.append(
                f"| {criterion.kind} | {_md(criterion.label)} | {_cadence_text(criterion.cadence)} | {_md(state)} "
                f"| {_md(value)} | {_md(triggered)} | {_md(source)} |"
            )
        lines.append("")
        lines.append("Criteria are evaluated only while Gamma runs; a trigger stays until its rule is edited.")
    else:
        lines.append("_No criteria._")
    lines += _tracking_markdown(idea, tracking_result)
    lines += _snapshots_markdown(idea, exported_at)
    lines += _signal_markdown(idea)
    lines += _reviews_markdown(idea)
    lines += ["", "## Journal", ""]
    if idea.journal:
        lines += ["| Time | Author | Kind | Entry |", "| --- | --- | --- | --- |"]
        for entry in idea.journal:
            lines.append(
                f"| {_ts(entry.created_at)} | {entry.author} | {entry.kind.replace('_', ' ')} | {_md(entry.body)} |"
            )
    else:
        lines.append("_No entries._")
    lines += [
        "",
        "---",
        "",
        "## Export provenance",
        f"- Idea: `{idea.idea_id}` · schema v{idea.schema_version}",
        f"- Exported: {_ts(exported_at)}",
        f"- Source: {IDEAS_SOURCE_PROVIDER} (local idea store) via idea_service.export_markdown",
        "- Evidence values are the snapshot taken at capture; they were not refreshed for this export.",
        "",
    ]
    return "\n".join(lines)


def _pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:+.2f}%"


def _tracking_markdown(idea: Idea, result: Mapping[str, Any] | None) -> list[str]:
    """The hypothetical record, always labelled; the series as rebuilt for this export."""
    tracking = idea.tracking
    if tracking is None or not tracking.segments:
        return []
    lines = ["", f"## Tracking — {TRACKING_LABEL}", ""]
    lines.append(
        f"> {TRACKING_LABEL}. A hypothetical book rebuilt from provider daily closes; Gamma placed no orders. "
        "Nothing before a segment's freeze is used, and a missing price is a gap, never interpolated."
    )
    lines.append("")
    summary = (result or {}).get("summary") if isinstance(result, Mapping) else None
    if isinstance(summary, Mapping):
        status = str((result or {}).get("status") or "").replace("_", " ")
        lines += [
            f"- Status: {status}" + (f" — {(result or {}).get('status_reason')}" if (result or {}).get("status_reason") else ""),
            f"- Net return since activation: {_pct(summary.get('net_return'))} "
            f"(gross {_pct(summary.get('gross_return'))}, costs {_pct(-(summary.get('cost_drag') or 0.0)) if summary.get('cost_drag') is not None else 'N/A'})",
            f"- Benchmark {tracking.benchmark}: {_pct(summary.get('benchmark_return'))} · "
            f"excess {_pct(summary.get('excess_return'))} · max drawdown {_pct(summary.get('max_drawdown'))}",
            f"- Sessions {summary.get('sessions', 0)} · gaps {summary.get('gaps', 0)} · "
            f"first close {summary.get('first_session') or 'N/A'} · as of {summary.get('as_of') or 'N/A'}"
            + (" · partial: some segments are not tracked" if summary.get("partial") else ""),
        ]
    elif tracking.snapshot is not None:
        snap = tracking.snapshot
        lines.append(
            f"- Last computed {_ts(snap.computed_at)} (as of {snap.as_of.isoformat() if snap.as_of else 'N/A'}): "
            f"net {_pct(snap.net_return)}, gross {_pct(snap.gross_return)}, {tracking.benchmark} {_pct(snap.benchmark_return)}. "
            "The series could not be rebuilt for this export."
        )
    else:
        lines.append("- The series could not be rebuilt for this export.")
    segment_rows = {row.get("number"): row for row in ((result or {}).get("segments") or []) if isinstance(row, Mapping)}
    lines += [
        "",
        "| Segment | Frozen | Reason | Ended | Legs (share of gross) | Entry close | Exit close | Gross | Costs | Net |",
        "| ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for segment in tracking.segments:
        row = segment_rows.get(segment.number) or {}
        legs = "; ".join(
            f"{leg.entity.label}" + ("" if leg.weight is None else f" {leg.weight * 100:+.0f}%") for leg in segment.legs
        )
        ended = f"{_ts(segment.ended_at)} ({(segment.end_reason or '').replace('_', ' ')})" if segment.ended_at else "open"
        cost = row.get("cost")
        lines.append(
            f"| {segment.number} | {_ts(segment.started_at)} | {_md(segment.start_reason.replace('_', ' '))} | {_md(ended)} "
            f"| {_md(legs)} | {row.get('entry_session') or '—'} | {row.get('exit_session') or '—'} "
            f"| {_pct(row.get('gross_return'))} | {_pct(-cost) if cost is not None else 'N/A'} | {_pct(row.get('net_return'))} |"
        )
        reason = segment.untracked_reason or (row.get("reason") if row.get("status") in {"unavailable", "waiting", "never_entered"} else None)
        if reason:
            lines.append(f"| | | | | {_md('Not priced: ' + str(reason))} | | | | | |")
    costs = tracking.cost_model
    lines += [
        "",
        "Cost assumptions (per side): "
        + ", ".join(f"{name.replace('_', ' ')} {value:g} bp" for name, value in costs.per_side_bp.items())
        + (f"; leg classes {', '.join(f'{key} → {value}' for key, value in costs.leg_classes.items())}" if costs.leg_classes else "")
        + ". Net figures subtract entry and exit costs; buy-side stamp duty or FTT are not included.",
    ]
    if isinstance(result, Mapping) and result.get("methodology"):
        lines += ["", f"Method: {_md(result.get('methodology'))}"]
    warnings = (result or {}).get("warnings") if isinstance(result, Mapping) else None
    if warnings:
        lines += ["", "Warnings:"]
        lines += [f"- {_md(item)}" for item in list(warnings)[:20]]
    return lines


def _snapshots_markdown(idea: Idea, exported_at: datetime) -> list[str]:
    from src.models.ideas import snapshot_staleness

    test = idea.tests[-1] if idea.tests else None
    risk = idea.risks[-1] if idea.risks else None
    if test is None and risk is None:
        return []
    lines = ["", "## Test and risk snapshots", ""]
    if test is not None:
        stale = snapshot_staleness(test, idea, exported_at)
        metrics = test.metrics
        lines += [
            f"### Backtest · run {_ts(test.created_at)}" + (f" · stale: {stale}" if stale else ""),
            "",
            "- In-sample only, no costs (Strategy Lab composition of the idea's legs) · "
            + (f"trials: {_trials_text(test.trial_count, test.trial_count_lower_bound)}." if test.trial_count else "trials not recorded (run before I4)."),
            f"- Window {test.window_start or 'N/A'} to {test.window_end or 'N/A'} · {test.observations} observations · legs "
            + "; ".join(f"{leg.entity.label} {leg.weight * 100:+.0f}%" for leg in test.legs if leg.weight is not None),
            f"- Total {_pct(metrics.get('total_return'))} · annual {_pct(metrics.get('annual_return'))} · volatility "
            f"{_pct(metrics.get('annual_volatility'))} · Sharpe {_ratio(metrics.get('sharpe_ratio'))} · max drawdown {_pct(metrics.get('max_drawdown'))}",
            f"- {test.benchmark} {_pct(metrics.get('benchmark_total_return'))} · excess {_pct(metrics.get('excess_total_return'))}",
            "",
        ]
    if risk is not None:
        stale = snapshot_staleness(risk, idea, exported_at)
        metrics = risk.metrics
        worst = risk.worst_episode
        lines += [
            f"### Risk · run {_ts(risk.created_at)}" + (f" · stale: {stale}" if stale else ""),
            "",
            f"- {int(risk.alpha * 100)}% one-day VaR: historical {_pct(_loss(metrics.get('historical_var')))}, parametric "
            f"{_pct(_loss(metrics.get('parametric_var')))} · expected shortfall {_pct(_loss(metrics.get('historical_es')))} (losses as shares of the book)",
            f"- Volatility {_pct(metrics.get('annual_volatility'))} · beta {_ratio(metrics.get('beta'))} · window "
            f"{risk.window_start or 'N/A'} to {risk.window_end or 'N/A'}",
            f"- Worst replayed episode: {worst.label} {_pct(worst.book_return)}" if worst else "- Worst replayed episode: none in the available history",
            "",
        ]
    return lines


def _signal_markdown(idea: Idea) -> list[str]:
    """The attached signal (I4): source ids, book, validation and trial count."""
    signal = idea.current_signal
    if signal is None and not idea.trials:
        return []
    lines = ["", "## Signal and validation", ""]
    lines.append(f"- Trials recorded for this idea: {_trials_text(max(1, idea.trial_count), idea.trials_lower_bound)}." if idea.trials else "- No trials recorded.")
    if signal is None:
        lines.append("- No signal attached.")
        return lines + [""]
    ref = thaw_captured_values(signal.source_ref)
    lines.append(f"- {_md(signal.label)} · {signal.source} · {signal.output_kind} · attached {_ts(signal.attached_at)}"
                 + (f" · as of {signal.as_of.isoformat()}" if signal.as_of else "")
                 + f" · {_trials_text(signal.trial_count, signal.trial_count_lower_bound)} when attached")
    if signal.source == "script":
        lines.append(
            f"- Script {ref.get('script_id')} · revision {ref.get('revision_id')} ({ref.get('revision_status')}) · run {ref.get('run_id')} · "
            f"parameters {ref.get('parameters_sha256') or 'none'} · source {str(ref.get('source_sha256') or '')[:16]}"
        )
    else:
        lines.append(f"- Import {str(ref.get('content_sha256') or '')[:16]} · {ref.get('rows')} rows · columns {', '.join(ref.get('columns') or [])}")
    if signal.is_book:
        lines.append(f"- {TRACKING_LABEL}. Book frozen at attach: " + "; ".join(
            f"{leg.entity.label} {leg.weight * 100:+.1f}%" for leg in signal.legs) + (" of NAV" if signal.output_kind == "weights" else " of gross"))
    elif signal.supplied is not None:
        supplied = signal.supplied
        lines.append(
            f"- {supplied.label}: {supplied.window_start or 'N/A'} to {supplied.window_end or 'N/A'} · total {_pct(supplied.metrics.get('total_return'))} · "
            f"Sharpe {_ratio(supplied.metrics.get('sharpe_ratio'))} · does not drive tracking"
        )
    validation = signal.validation
    if validation is None:
        lines.append("- No out-of-sample validation attached.")
    else:
        oos = validation.out_of_sample
        costs = {True: f"{validation.cost_bps:g} bp per unit of turnover", False: "no costs", None: "costs as written by the script"}[validation.costs_included]
        lines.append(
            f"- Out-of-sample (walk-forward, {len(validation.folds)} folds, {validation.window}, train {validation.train_observations} / test "
            f"{validation.test_observations}, {validation.oos_start or 'N/A'} to {validation.oos_end or 'N/A'}): total {_pct(oos.get('total_return'))} · "
            f"Sharpe {_ratio(oos.get('sharpe_ratio'))} · max drawdown {_pct(oos.get('max_drawdown'))} · {validation.trials} sweep trials · {costs}"
        )
    return lines + [""]


def _loss(value: Any) -> float | None:
    """VaR and expected shortfall are losses: shown negative, never as a gain."""
    return None if value is None else -abs(float(value))


def _ratio(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}"


def _reviews_markdown(idea: Idea) -> list[str]:
    if not idea.reviews:
        return []
    lines = ["", "## Reviews", ""]
    for review in reversed(idea.reviews):
        current = " (current close)" if review is idea.current_review else ""
        lines += [
            f"### {review.outcome.capitalize()} · closed {_ts(review.closed_at)}{current}",
            "",
            f"- Held {review.holding_days:.1f} days, from {_ts(review.opened_at)}",
            f"- Expected: {_md(review.expected) or 'not written'}",
        ]
        realized = review.realized
        if realized is not None:
            lines.append(
                f"- Realized at close ({TRACKING_LABEL.lower()}): net {_pct(realized.net_return)}, gross {_pct(realized.gross_return)}, "
                f"{realized.benchmark or 'benchmark'} {_pct(realized.benchmark_return)}, as of {realized.as_of.isoformat() if realized.as_of else 'N/A'}"
            )
        else:
            lines.append("- Realized at close: no tracked record")
        if review.realized_note:
            lines.append(f"- What happened: {_md(review.realized_note)}")
        if review.evidence_verdicts:
            lines.append("- Evidence: " + "; ".join(f"{_md(item.title)} ({item.stance}) {item.verdict}" for item in review.evidence_verdicts))
        fired = [item for item in review.criteria_at_close if item.triggered_at is not None]
        if fired:
            lines.append("- Triggered criteria at close: " + "; ".join(f"{item.kind} “{_md(item.label)}”" for item in fired))
        lines += [f"- Lesson: {_md(review.lesson)}", ""]
    return lines


def _evidence_markdown(pin: IdeaEvidence) -> list[str]:
    lines = [f"#### {pin.title}", ""]
    lines.append(f"- Kind: {pin.kind.replace('_', ' ')} · Captured: {_ts(pin.captured_at)}")
    lines += _captured_values_markdown(thaw_captured_values(pin.captured_values))
    if pin.note:
        lines.append(f"- Note: {_md(pin.note)}")
    if pin.provenance:
        source = pin.provenance
        detail = f"- Source: {source.source_provider} · retrieved {_ts(source.retrieved_at)} · origin `{source.origin}`"
        if source.transformation_note:
            detail += f" · transformation: {_md(source.transformation_note)}"
        lines.append(detail)
    else:
        lines.append("- Source: no provenance recorded at capture")
    if pin.freshness:
        warnings = f" · warnings: {'; '.join(pin.freshness.warnings)}" if pin.freshness.warnings else ""
        lines.append(f"- Freshness at capture: {pin.freshness.label.value}{warnings}")
    if pin.reopen:
        entity = pin.reopen.selected_entity
        target = _tab_label(pin.reopen.intended_target_tab)
        mode = pin.reopen.intended_target_mode
        where = f"{target} / {mode.replace('_', ' ')}" if mode else target
        on = f" on {entity.label} (`{entity.normalized_id}`)" if entity else ""
        lens = f" · lens {pin.reopen.selected_timeframe.label}" if pin.reopen.selected_timeframe else ""
        lines.append(f"- Reopen: {where}{on}{lens}")
    return lines


def _captured_values_markdown(values: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    metrics = values.get("metrics")
    if isinstance(metrics, list) and metrics:
        lines.append("- Values:")
        for metric in metrics:
            if isinstance(metric, Mapping):
                label = metric.get("label") or metric.get("name") or "Value"
                shown = metric.get("display")
                if shown is None:
                    shown = metric.get("value")
                unit = f" {metric['unit']}" if metric.get("unit") and metric.get("display") is None else ""
                lines.append(f"  - {_md(label)}: {_md('N/A' if shown is None else shown)}{unit}")
    table = values.get("table")
    if isinstance(table, Mapping) and isinstance(table.get("columns"), list) and isinstance(table.get("rows"), list):
        columns = [str(column) for column in table["columns"]]
        if columns:
            lines += ["", "| " + " | ".join(_md(column) for column in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
            for row in table["rows"]:
                cells = row if isinstance(row, list) else [row]
                lines.append("| " + " | ".join(_md(cell) for cell in cells) + " |")
            lines.append("")
    series = values.get("series")
    if isinstance(series, Mapping) and isinstance(series.get("points"), list):
        points = series["points"]
        summary = f"- Series: {_md(series.get('label') or 'series')} · {len(points)} points"
        if points:
            summary += f" · first {_md(_point_text(points[0]))} · last {_md(_point_text(points[-1]))}"
        downsampling = series.get("downsampling")
        if isinstance(downsampling, Mapping):
            summary += (
                f" · downsampled from {downsampling.get('original_points')} points "
                f"({downsampling.get('method')})"
            )
        lines.append(summary)
    text = values.get("text")
    if isinstance(text, str) and text.strip():
        lines.append(f"- Text: {_md(text)}")
    known = {"metrics", "table", "series", "text"}
    extra = {key: value for key, value in values.items() if key not in known}
    if extra:
        lines.append(f"- Other values: `{_md(json.dumps(extra, sort_keys=True, ensure_ascii=False))}`")
    return lines


def _point_text(point: Any) -> str:
    if isinstance(point, Mapping):
        stamp = point.get("timestamp") or point.get("date") or point.get("t")
        value = point.get("value") if "value" in point else point.get("v")
        return f"{stamp}: {value}" if stamp is not None else str(value)
    if isinstance(point, list) and len(point) == 2:
        return f"{point[0]}: {point[1]}"
    return str(point)



__all__ = [
    "IDEA_EXPORT_FORMAT",
    "IDEA_SCHEMA_VERSION",
    "IdeaCreateRequest",
    "IdeaEvidenceCreateRequest",
    "IdeaListResult",
    "IdeaPatchRequest",
    "IdeaService",
    "render_idea_markdown",
]
