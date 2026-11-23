"""Ideas in Copilot (Workstream 12, checkpoint I5).

Gamma computes every fact Copilot sees about an idea; the model reads them and
writes prose, never the other way round:

* :func:`idea_context_summary` is the Ideas context contract: the selected
  idea's thesis, evidence with stance and provenance, criteria and their
  states, test and risk snapshots, the hypothetical tracking summary, the
  signal and trial count, the journal tail and, when asked, the review
  statistics.
* :func:`review_idea_facts` (the ``review_idea`` tool) compares the expected
  path with the realized one and lists the evidence that held or failed.
* :func:`explain_criterion_facts` (``explain_criterion_state``) says why a
  criterion is pending, holding, triggered, unavailable or stale, from its own
  evaluation and the shared "What is this?" registry.
* :func:`build_idea_draft` (``draft_idea_from_context``) validates a proposed
  idea against the observable registry. It changes nothing: the proposal waits
  for the user's acceptance, and accepting creates a *draft* idea. Copilot
  never activates, closes or edits an idea or its criteria, and an idea never
  carries order, account or execution authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.models.handoff import HandoffEntity
from src.models.ideas import (
    CRITERION_KINDS,
    CRITERION_WINDOWS,
    IDEA_STANCES,
    IDEA_THESIS_MAX,
    IDEA_TITLE_MAX,
    TRACKING_LABEL,
    Idea,
    IdeaLeg,
    IdeaValidationError,
    ObservableRef,
    thaw_captured_values,
)

IDEAS_CONTEXT_ORIGIN = "idea_copilot.context"
JOURNAL_TAIL = 8
EVIDENCE_CONTEXT_MAX = 24
VALUES_PER_PIN = 6
DRAFT_CRITERIA_MIN = 2
DRAFT_CRITERIA_MAX = 4
DRAFT_LEGS_MAX = 8
RATIONALE_MAX = 600
# Observables que un borrador de Copilot puede proponer: los de lectura ya existentes, sin TWS primero.
DRAFT_OBSERVABLES = (
    "equity_close",
    "crypto_price",
    "macro_series",
    "prediction_probability",
    "commodity_price",
    "calendar_date",
    "option_atm_iv",
)
DRAFT_CONDITIONS = ("above", "below", "crosses_above", "crosses_below", "change_over_window", "date_reached", "event_occurs")
DRAFT_LEG_TYPES = ("equity", "etf", "crypto")
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-^=]{0,23}$")


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _provenance(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    return {
        "source_provider": record.source_provider,
        "retrieved_at": _iso(record.retrieved_at),
        "origin": record.origin,
        "transformation_note": record.transformation_note,
    }


def _pin_values(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The first few label/value pairs of a pin, as captured (frozen, never refreshed)."""
    raw = thaw_captured_values(values)
    pairs: list[dict[str, Any]] = []
    for row in raw.get("metrics") or []:
        if isinstance(row, Mapping) and row.get("label"):
            pairs.append({"label": str(row.get("label")), "value": row.get("value")})
    series = raw.get("series")
    if isinstance(series, Mapping) and series.get("points"):
        points = series["points"]
        pairs.append({"label": f"{series.get('label') or 'Series'} (last of {len(points)})", "value": points[-1]})
    if raw.get("text"):
        pairs.append({"label": "Text", "value": str(raw["text"])[:240]})
    return pairs[:VALUES_PER_PIN]


def _evaluation(evaluation: Any) -> dict[str, Any] | None:
    if evaluation is None:
        return None
    return {
        "state": evaluation.state,
        "evaluated_at": _iso(evaluation.evaluated_at),
        "value": evaluation.value_display or evaluation.value,
        "as_of": _iso(evaluation.as_of),
        "met_value": evaluation.met_display or evaluation.met_value,
        "first_met_at": _iso(evaluation.first_met_at),
        "reason": evaluation.reason,
        "effective_cadence": evaluation.effective_cadence,
        "cadence_note": evaluation.cadence_note,
        "known_at_arming": evaluation.known_at_arming,
        "provenance": _provenance(evaluation.provenance),
        "warnings": list(evaluation.warnings),
    }


def _criterion(item: Any) -> dict[str, Any]:
    return {
        "criterion_id": item.criterion_id,
        "kind": item.kind,
        "label": item.label,
        "observable": {"observable_id": item.observable.observable_id, "params": dict(item.observable.params), "label": item.observable.label},
        "condition": item.condition,
        "threshold": item.threshold,
        "window": item.window,
        "cadence": item.cadence,
        "state": item.state,
        "armed_at": _iso(item.armed_at),
        "triggered_at": _iso(item.triggered_at),
        "acknowledged_at": _iso(item.acknowledged_at),
        "last_evaluation": _evaluation(item.last_evaluation),
        "trigger_evaluation": _evaluation(item.trigger_evaluation),
    }


def _tracking_summary(idea: Idea, tracking: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if idea.tracking is None:
        return None
    snapshot = idea.tracking.snapshot
    data: dict[str, Any] = {
        "label": TRACKING_LABEL,
        "benchmark": idea.tracking.benchmark,
        "segments": len(idea.tracking.segments),
        "open": idea.tracking.open_segment is not None,
    }
    if tracking is not None:
        data.update(
            status=tracking.get("status"),
            status_reason=tracking.get("status_reason"),
            summary=dict(tracking.get("summary") or {}),
            warnings=list(tracking.get("warnings") or [])[:6],
            source="rebuilt from provider closes for this context",
        )
    elif snapshot is not None:
        data.update(
            status=snapshot.status,
            summary={
                "net_return": snapshot.net_return,
                "gross_return": snapshot.gross_return,
                "benchmark_return": snapshot.benchmark_return,
                "sessions": snapshot.sessions,
                "gaps": snapshot.gaps,
                "as_of": _iso(snapshot.as_of),
                "final": snapshot.final,
            },
            source="last stored headline",
        )
    return data


def _snapshot_figures(snapshot: Any, kind: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "created_at": _iso(snapshot.created_at),
        "source": snapshot.source,
        "window": [_iso(snapshot.window_start), _iso(snapshot.window_end)],
        "observations": snapshot.observations,
        "legs": [{"label": leg.entity.label, "share": leg.weight} for leg in snapshot.legs],
        "metrics": dict(snapshot.metrics),
        "warnings": list(snapshot.warnings)[:4],
    }
    if kind == "test":
        data.update(sample=snapshot.sample, costs_included=snapshot.costs_included, trial_count=snapshot.trial_count)
    else:
        worst = snapshot.worst_episode
        data.update(alpha=snapshot.alpha, worst_episode=None if worst is None else {"label": worst.label, "book_return": worst.book_return, "status": worst.status})
    return data


def idea_context_summary(
    idea: Idea,
    *,
    tracking: Mapping[str, Any] | None = None,
    review_statistics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The Ideas context contract for one idea (compact, provenance kept, nothing inferred)."""
    evidence = sorted(idea.evidence, key=lambda item: item.captured_at, reverse=True)[:EVIDENCE_CONTEXT_MAX]
    signal = idea.current_signal
    data: dict[str, Any] = {
        "idea_id": idea.idea_id,
        "title": idea.title,
        "thesis": idea.thesis,
        "stance": idea.stance,
        "status": idea.status,
        "horizon": idea.horizon.to_dict(),
        "tags": list(idea.tags),
        "legs": [{"label": leg.entity.label, "entity_type": leg.entity.entity_type, "id": leg.entity.normalized_id, "weight": leg.weight} for leg in idea.legs],
        "origin": idea.origin.to_dict() if hasattr(idea.origin, "to_dict") else {"kind": idea.origin.kind},
        "evidence_counts": idea.evidence_counts(),
        "evidence": [
            {
                "evidence_id": pin.evidence_id,
                "stance": pin.stance,
                "kind": pin.kind,
                "title": pin.title,
                "captured_at": _iso(pin.captured_at),
                "values_as_captured": _pin_values(pin.captured_values),
                "note": pin.note[:300],
                "provenance": _provenance(pin.provenance),
            }
            for pin in evidence
        ],
        "evidence_omitted": max(0, len(idea.evidence) - len(evidence)),
        "criteria": [_criterion(item) for item in idea.criteria],
        "tests": [_snapshot_figures(item, "test") for item in idea.tests[-2:]],
        "risks": [_snapshot_figures(item, "risk") for item in idea.risks[-2:]],
        "tracking": _tracking_summary(idea, tracking),
        "signal": None
        if signal is None
        else {
            "label": signal.label,
            "source": signal.source,
            "output_kind": signal.output_kind,
            "drives_tracking": signal.is_book,
            "trial_count": signal.trial_count,
            "out_of_sample": dict(signal.validation.out_of_sample) if signal.validation else None,
        },
        "trial_count": idea.trial_count,
        "journal_tail": [
            {"created_at": _iso(entry.created_at), "kind": entry.kind, "author": entry.author, "body": entry.body[:400]}
            for entry in idea.journal[-JOURNAL_TAIL:]
        ],
        "reviews": [
            {"outcome": review.outcome, "closed_at": _iso(review.closed_at), "lesson": review.lesson[:400]} for review in idea.reviews[-3:]
        ],
        "boundary": "Local research record. Tracking is hypothetical, not executed. Copilot can explain and propose; the user decides every change.",
    }
    if review_statistics is not None:
        data["review_statistics"] = dict(review_statistics)
    return data


def review_idea_facts(idea: Idea, tracking: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Expected against realized, the evidence that held or failed, and the criteria that fired."""
    review = idea.current_review or idea.latest_review
    verdicts = {item.evidence_id: item.verdict for item in (review.evidence_verdicts if review else ())}
    evidence_rows = []
    for pin in idea.evidence:
        evidence_rows.append(
            {
                "evidence_id": pin.evidence_id,
                "title": pin.title,
                "stance": pin.stance,
                "verdict": verdicts.get(pin.evidence_id, "not judged"),
                "captured_at": _iso(pin.captured_at),
            }
        )
    triggered = [
        {
            "criterion_id": item.criterion_id,
            "kind": item.kind,
            "label": item.label,
            "triggered_at": _iso(item.triggered_at),
            "first_met_at": _iso(item.trigger_evaluation.first_met_at) if item.trigger_evaluation else None,
            "met_value": (item.trigger_evaluation.met_display or item.trigger_evaluation.met_value) if item.trigger_evaluation else None,
        }
        for item in idea.criteria
        if item.triggered_at is not None
    ]
    realized_now = _tracking_summary(idea, tracking)
    realized_at_close = None
    if review is not None and review.realized is not None:
        realized_at_close = {
            "net_return": review.realized.net_return,
            "benchmark_return": review.realized.benchmark_return,
            "sessions": review.realized.sessions,
            "as_of": _iso(review.realized.as_of),
            "final": review.realized.final,
        }
    invalidations = [row for row in triggered if row["kind"] == "invalidate"]
    held = [row for row in evidence_rows if row["verdict"] == "held"]
    failed = [row for row in evidence_rows if row["verdict"] == "failed"]
    notes: list[str] = []
    if review is None:
        notes.append("The idea has no review yet; evidence verdicts are written when it is closed.")
    if idea.tracking is None:
        notes.append("The idea was never tracked, so there is no realized hypothetical path.")
    return {
        "idea_id": idea.idea_id,
        "title": idea.title,
        "status": idea.status,
        "expected": (review.expected if review and review.expected else idea.thesis),
        "outcome": review.outcome if review else None,
        "lesson": review.lesson if review else None,
        "realized_note": review.realized_note if review else None,
        "realized_at_close": realized_at_close,
        "realized_now": realized_now,
        "evidence": evidence_rows,
        "held": [row["title"] for row in held],
        "failed": [row["title"] for row in failed],
        "triggered_criteria": triggered,
        "invalidation_fired": bool(invalidations),
        "first_invalidation_at": min((row["first_met_at"] or row["triggered_at"] for row in invalidations if row["first_met_at"] or row["triggered_at"]), default=None),
        "notes": notes,
        "label": TRACKING_LABEL,
    }


STATE_READINGS = {
    "pending": "Not evaluated yet: the idea is a draft, or no pass has run since the rule was armed.",
    "holding": "Evaluated: the latest observation does not meet the rule.",
    "triggered": "The rule was met by an observation newer than its arming; the trigger latches until the rule is edited.",
    "unavailable": "The observable could not be read; the reason names the missing dependency or the provider failure.",
    "stale": "The latest observation is older than this observable tolerates, and it did not meet the rule.",
}


def explain_criterion_facts(idea: Idea, criterion_id: str, explanations: Mapping[str, Any]) -> dict[str, Any]:
    """Why a criterion is in its state, from its own evaluation and the shared explanation registry."""
    item = idea.criterion(criterion_id)
    if item is None:
        raise IdeaValidationError(f"Criterion {criterion_id} is not on idea {idea.idea_id}.")

    def text(key: str) -> dict[str, Any] | None:
        entry = explanations.get(key)
        if entry is None:
            return None
        payload = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
        return {"title": payload.get("title"), "measures": payload.get("measures"), "computed": payload.get("computed"),
                "why_for_this_stance": (payload.get("why") or {}).get(idea.stance)}

    evaluation = item.trigger_evaluation if item.triggered_at is not None else item.last_evaluation
    facts = _criterion(item)
    facts.update(
        idea_id=idea.idea_id,
        idea_status=idea.status,
        state_reading=STATE_READINGS.get(item.state),
        decisive_evaluation=_evaluation(evaluation),
        baseline={"as_of": _iso(item.baseline_as_of), "for": _iso(item.baseline_for)},
        rule_note=(
            "Only observations not yet known when the rule was armed can trigger it; a level already met at arming holds until a new observation meets it."
        ),
        explanations={
            "state": text(f"state.{item.state}"),
            "condition": text(f"condition.{item.condition}"),
            "observable": text(f"observable.{item.observable.observable_id}"),
            "kind": text(f"kind.{item.kind}"),
        },
    )
    if idea.status != "active":
        facts["note"] = f"Criteria are evaluated only while the idea is active; this one is {idea.status}."
    return facts


@dataclass(frozen=True)
class DraftCriterion:
    kind: str
    observable: ObservableRef
    condition: str
    threshold: float | None
    window: str | None
    cadence: str
    label: str
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "observable": {"observable_id": self.observable.observable_id, "params": dict(self.observable.params), "label": self.observable.label},
            "condition": self.condition,
            "threshold": self.threshold,
            "window": self.window,
            "cadence": self.cadence,
            "label": self.label,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class IdeaDraftProposal:
    """A validated idea proposal; it becomes a draft idea only when the user accepts it."""

    title: str
    thesis: str
    stance: str
    legs: tuple[IdeaLeg, ...] = ()
    criteria: tuple[DraftCriterion, ...] = ()
    rationale: str = ""
    source_label: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "thesis": self.thesis,
            "stance": self.stance,
            "legs": [
                {"entity_type": leg.entity.entity_type, "symbol": leg.entity.native_id or leg.entity.normalized_id, "label": leg.entity.label, "weight": leg.weight}
                for leg in self.legs
            ],
            "criteria": [item.to_dict() for item in self.criteria],
            "rationale": self.rationale,
            "source_label": self.source_label,
            "warnings": list(self.warnings),
            "creates": "A draft idea. Nothing is activated, tracked or evaluated until you activate it.",
        }


def _leg(raw: Mapping[str, Any]) -> IdeaLeg:
    entity_type = str(raw.get("entity_type") or "equity").strip().lower()
    if entity_type not in DRAFT_LEG_TYPES:
        raise IdeaValidationError(f"A drafted leg is an equity, ETF or crypto instrument, not {entity_type}.")
    symbol = str(raw.get("symbol") or "").strip()
    if not SYMBOL_PATTERN.match(symbol):
        raise IdeaValidationError(f"{symbol!r} is not a ticker or a CoinGecko id.")
    label = " ".join(str(raw.get("label") or "").split())[:80] or symbol.upper()
    weight = raw.get("weight")
    number = None if weight is None else float(weight)
    if entity_type == "crypto":
        token = symbol.lower()
        entity = HandoffEntity(entity_type="crypto", label=label, normalized_id=token.upper(), native_id=token, metadata={"coingecko_id": token})
    else:
        entity = HandoffEntity(entity_type=entity_type, label=label, normalized_id=symbol.upper())
    return IdeaLeg(entity=entity, weight=number)


def build_idea_draft(arguments: Mapping[str, Any], registry: Any, *, source_label: str = "") -> IdeaDraftProposal:
    """Validate a proposed idea against Gamma's rules and observable registry; nothing is written."""
    title = " ".join(str(arguments.get("title") or "").split())
    thesis = " ".join(str(arguments.get("thesis") or "").split())
    if not title or len(title) > IDEA_TITLE_MAX:
        raise IdeaValidationError(f"A drafted idea needs a title of at most {IDEA_TITLE_MAX} characters.")
    if not thesis or len(thesis) > IDEA_THESIS_MAX:
        raise IdeaValidationError(f"A drafted idea needs a thesis of at most {IDEA_THESIS_MAX} characters.")
    stance = str(arguments.get("stance") or "").strip().lower()
    if stance not in IDEA_STANCES:
        raise IdeaValidationError(f"The stance must be one of {IDEA_STANCES}.")
    raw_legs = list(arguments.get("legs") or [])
    if len(raw_legs) > DRAFT_LEGS_MAX:
        raise IdeaValidationError(f"A drafted idea holds at most {DRAFT_LEGS_MAX} legs.")
    legs = tuple(_leg(item) for item in raw_legs if isinstance(item, Mapping))
    raw_criteria = [item for item in (arguments.get("criteria") or []) if isinstance(item, Mapping)]
    if not DRAFT_CRITERIA_MIN <= len(raw_criteria) <= DRAFT_CRITERIA_MAX:
        raise IdeaValidationError(f"Propose between {DRAFT_CRITERIA_MIN} and {DRAFT_CRITERIA_MAX} criteria, stated in advance.")
    criteria: list[DraftCriterion] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_criteria, start=1):
        kind = str(raw.get("kind") or "").strip().lower()
        if kind not in CRITERION_KINDS:
            raise IdeaValidationError(f"Criterion {index}: the kind must be one of {CRITERION_KINDS}.")
        observable_id = str(raw.get("observable_id") or "").strip().lower()
        if observable_id not in DRAFT_OBSERVABLES:
            raise IdeaValidationError(f"Criterion {index}: {observable_id or 'an empty observable'} is not one Copilot can propose.")
        params = {str(pair.get("name")): str(pair.get("value")) for pair in (raw.get("params") or []) if isinstance(pair, Mapping) and pair.get("name") and pair.get("value") not in (None, "")}
        condition = str(raw.get("condition") or "").strip().lower()
        if condition not in DRAFT_CONDITIONS:
            raise IdeaValidationError(f"Criterion {index}: unknown condition {condition!r}.")
        threshold = raw.get("threshold")
        threshold = None if threshold is None else float(threshold)
        window = raw.get("window") or None
        if window is not None and window not in CRITERION_WINDOWS:
            raise IdeaValidationError(f"Criterion {index}: the window must be one of {tuple(CRITERION_WINDOWS)}.")
        if condition in {"above", "below", "crosses_above", "crosses_below", "change_over_window"} and threshold is None:
            raise IdeaValidationError(f"Criterion {index}: {condition} needs a threshold.")
        if condition == "change_over_window" and window is None:
            raise IdeaValidationError(f"Criterion {index}: a change needs its window.")
        cadence = "daily_close"
        ref = registry.validate(ObservableRef(observable_id=observable_id, params=params), condition=condition, cadence=cadence)
        label = registry.describe(ref, condition=condition, threshold=threshold, window=window)
        definition = next((row for row in registry.describe_all() if row["observable_id"] == observable_id), None)
        if definition and not definition.get("available"):
            warnings.append(f"Criterion {index} ({label}) is unavailable right now: {definition.get('unavailable_reason')}")
        criteria.append(
            DraftCriterion(
                kind=kind, observable=ref, condition=condition, threshold=threshold, window=window, cadence=cadence, label=label,
                rationale=" ".join(str(raw.get("rationale") or "").split())[:RATIONALE_MAX],
            )
        )
    if not any(item.kind == "invalidate" for item in criteria):
        warnings.append("No invalidation criterion: nothing states in advance what would prove the thesis wrong.")
    return IdeaDraftProposal(
        title=title,
        thesis=thesis,
        stance=stance,
        legs=legs,
        criteria=tuple(criteria),
        rationale=" ".join(str(arguments.get("rationale") or "").split())[:RATIONALE_MAX],
        source_label=source_label[:200],
        warnings=tuple(warnings),
    )


def draft_from_dict(payload: Mapping[str, Any]) -> IdeaDraftProposal:
    """Rebuild a stored proposal (the confirmation flow keeps it as JSON until the user decides)."""
    legs = tuple(_leg(item) for item in payload.get("legs") or [] if isinstance(item, Mapping))
    criteria = []
    for raw in payload.get("criteria") or []:
        observable = raw.get("observable") or {}
        criteria.append(
            DraftCriterion(
                kind=str(raw.get("kind")),
                observable=ObservableRef(observable_id=str(observable.get("observable_id")), params=dict(observable.get("params") or {}), label=str(observable.get("label") or "")),
                condition=str(raw.get("condition")),
                threshold=raw.get("threshold"),
                window=raw.get("window"),
                cadence=str(raw.get("cadence") or "daily_close"),
                label=str(raw.get("label") or ""),
                rationale=str(raw.get("rationale") or ""),
            )
        )
    return IdeaDraftProposal(
        title=str(payload.get("title") or ""),
        thesis=str(payload.get("thesis") or ""),
        stance=str(payload.get("stance") or "neutral"),
        legs=legs,
        criteria=tuple(criteria),
        rationale=str(payload.get("rationale") or ""),
        source_label=str(payload.get("source_label") or ""),
        warnings=tuple(payload.get("warnings") or ()),
    )


def draft_tool_schema() -> dict[str, Any]:
    """Strict function schema for ``draft_idea_from_context`` (every field required; nullable where optional)."""
    param = {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}}, "required": ["name", "value"], "additionalProperties": False}
    leg = {
        "type": "object",
        "properties": {
            "entity_type": {"type": "string", "enum": list(DRAFT_LEG_TYPES)},
            "symbol": {"type": "string", "description": "Ticker (AAPL, SPY) or CoinGecko id (bitcoin)."},
            "label": {"type": "string"},
            "weight": {"type": ["number", "null"], "description": "Signed weight; null for an equal-weight long or short book."},
        },
        "required": ["entity_type", "symbol", "label", "weight"],
        "additionalProperties": False,
    }
    criterion = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(CRITERION_KINDS)},
            "observable_id": {"type": "string", "enum": list(DRAFT_OBSERVABLES)},
            "params": {
                "type": "array",
                "items": param,
                "description": "equity_close/option_atm_iv: symbol (the ticker); crypto_price: token_id; macro_series: series_id; prediction_probability: market_id (and optional outcome_id); commodity_price: instrument_id; calendar_date: date (YYYY-MM-DD).",
            },
            "condition": {"type": "string", "enum": list(DRAFT_CONDITIONS)},
            "threshold": {"type": ["number", "null"]},
            "window": {"type": ["string", "null"], "enum": [*CRITERION_WINDOWS, None]},
            "rationale": {"type": "string", "description": "One sentence: why this rule tests the thesis."},
        },
        "required": ["kind", "observable_id", "params", "condition", "threshold", "window", "rationale"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "thesis": {"type": "string", "description": "One-line thesis, falsifiable."},
            "stance": {"type": "string", "enum": list(IDEA_STANCES)},
            "legs": {"type": "array", "items": leg},
            "criteria": {"type": "array", "items": criterion, "minItems": DRAFT_CRITERIA_MIN, "maxItems": DRAFT_CRITERIA_MAX},
            "rationale": {"type": "string", "description": "Which evidence in the current context the draft rests on."},
        },
        "required": ["title", "thesis", "stance", "legs", "criteria", "rationale"],
        "additionalProperties": False,
    }


__all__ = [
    "DRAFT_OBSERVABLES",
    "IdeaDraftProposal",
    "build_idea_draft",
    "draft_from_dict",
    "draft_tool_schema",
    "explain_criterion_facts",
    "idea_context_summary",
    "review_idea_facts",
]
