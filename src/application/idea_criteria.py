"""Pure criterion logic for Ideas (Workstream 12, checkpoint I2).

This module decides what a reading means for a criterion; it never fetches.
The observable registry (``src/application/idea_observables.py``) produces an
``ObservableReading`` through existing read-only services, and
:func:`evaluate_criterion` turns it into a ``CriterionEvaluation``.

Rules that make the record honest:

- **No look-ahead, no look-back:** only observations dated on or after the day
  the rule was armed (and the idea activated) can trigger it.
- **Absence is a state:** a reading that could not be taken is
  ``unavailable`` with its reason, never ``holding``.
- **While you were away:** when the observable has a history, the trigger
  carries the date the condition was first met, not the time Gamma noticed.
- **Stale is not holding:** a value older than the observable tolerates is
  ``stale`` unless it already met the condition (a real close below the
  threshold is still a fact).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.models.ideas import (
    CRITERION_WINDOWS,
    CriterionEvaluation,
    IdeaCriterion,
)
from src.models.provenance import ProvenanceRecord

CHANGE_UNITS = ("percent", "points")

WINDOW_LABELS = {"1d": "1 day", "5d": "5 days", "1m": "1 month", "3m": "3 months", "6m": "6 months", "1y": "1 year"}
CONDITION_LABELS = {
    "above": "above",
    "below": "below",
    "crosses_above": "crosses above",
    "crosses_below": "crosses below",
    "change_over_window": "changes by",
    "date_reached": "date reached",
    "event_occurs": "occurs",
}


@dataclass(frozen=True)
class ObservablePoint:
    """One dated observation; ``at`` is naive UTC (a session date at midnight for daily data)."""

    at: datetime
    value: float


@dataclass(frozen=True)
class ObservableReading:
    """What an observable returned for one evaluation pass.

    ``history`` is ascending and ends with the latest observation when the
    source has one. ``unavailable_reason`` set means nothing else can be
    trusted. Event observables use ``event_time`` and ``event_released``.
    """

    value: float | None = None
    as_of: datetime | None = None
    history: tuple[ObservablePoint, ...] = ()
    value_display: str | None = None
    provenance: ProvenanceRecord | None = None
    unavailable_reason: str | None = None
    stale_reason: str | None = None
    warnings: tuple[str, ...] = ()
    event_time: datetime | None = None
    event_released: bool | None = None
    event_value: float | None = None

    @property
    def is_unavailable(self) -> bool:
        return bool(self.unavailable_reason)

    @classmethod
    def unavailable(cls, reason: str, *, provenance: ProvenanceRecord | None = None, warnings: Sequence[str] = ()) -> "ObservableReading":
        return cls(unavailable_reason=reason, provenance=provenance, warnings=tuple(warnings))


def evaluate_criterion(
    criterion: IdeaCriterion,
    reading: ObservableReading,
    *,
    armed_from: datetime,
    now: datetime,
    change_unit: str = "percent",
    effective_cadence: str | None = None,
    cadence_note: str | None = None,
    format_value=None,
) -> CriterionEvaluation:
    """Evaluate one criterion against one reading. Pure: same inputs, same result."""
    cadence = effective_cadence or criterion.cadence
    base = {
        "evaluated_at": now,
        "effective_cadence": cadence,
        "cadence_note": cadence_note,
        "provenance": reading.provenance,
        "warnings": tuple(reading.warnings),
    }
    if reading.is_unavailable:
        return CriterionEvaluation(state="unavailable", reason=reading.unavailable_reason, **base)

    condition = criterion.condition
    if condition in ("date_reached", "event_occurs"):
        return _evaluate_event(criterion, reading, armed_from=armed_from, now=now, base=base)

    threshold = float(criterion.threshold or 0.0)
    points = _usable_points(reading)
    if not points:
        return CriterionEvaluation(state="unavailable", reason="The source returned no value.", **base)
    latest = points[-1]
    show = format_value or _plain_number
    display = reading.value_display or show(latest.value)
    since = armed_from.date()
    common = {**base, "value": latest.value, "value_display": display, "as_of": latest.at}

    if condition in ("above", "below"):
        met = next((point for point in points if point.at.date() >= since and _level_met(condition, point.value, threshold)), None)
        if met is not None:
            return CriterionEvaluation(
                state="triggered", first_met_at=met.at, met_value=met.value, met_display=show(met.value), **common
            )
        return _holding_or_stale(reading, common)

    if condition in ("crosses_above", "crosses_below"):
        previous: ObservablePoint | None = None
        for point in points:
            if previous is not None and point.at.date() >= since and _crossed(condition, previous.value, point.value, threshold):
                return CriterionEvaluation(
                    state="triggered",
                    first_met_at=point.at,
                    met_value=point.value,
                    met_display=show(point.value),
                    reference_value=previous.value,
                    **common,
                )
            previous = point
        reference = points[-2].value if len(points) > 1 else None
        if reference is None:
            # One observation cannot show a crossing; say so instead of claiming it holds.
            return CriterionEvaluation(
                state="unavailable",
                reason="A crossing needs at least two observations; the source returned one.",
                **common,
            )
        return _holding_or_stale(reading, {**common, "reference_value": reference})

    # change_over_window
    window_days = CRITERION_WINDOWS[str(criterion.window)]
    latest_change: tuple[float, float] | None = None
    for index, point in enumerate(points):
        reference = _reference_point(points[: index + 1], point.at - timedelta(days=window_days))
        if reference is None:
            continue
        change = _change(reference.value, point.value, change_unit)
        if change is None:
            continue
        if point is latest:
            latest_change = (reference.value, change)
        if point.at.date() >= since and _change_met(change, threshold):
            return CriterionEvaluation(
                state="triggered",
                first_met_at=point.at,
                met_value=point.value,
                met_display=show(point.value),
                reference_value=reference.value,
                change=change,
                **common,
            )
    if latest_change is None:
        label = WINDOW_LABELS.get(str(criterion.window), str(criterion.window))
        return CriterionEvaluation(
            state="unavailable",
            reason=f"The source history is too short for a {label} change.",
            **common,
        )
    return _holding_or_stale(reading, {**common, "reference_value": latest_change[0], "change": latest_change[1]})


def describe_criterion(
    *,
    observable_label: str,
    condition: str,
    threshold: float | None,
    window: str | None,
    change_unit: str = "percent",
    format_threshold=None,
) -> str:
    """Plain-language label generated from the rule; the user may edit it.

    The frontend mirrors this in ``lib/idea-criteria.ts`` for the live preview.
    """
    subject = observable_label.strip() or "Observable"
    shown = format_threshold(threshold) if (format_threshold and threshold is not None) else _plain_number(threshold)
    if condition in ("above", "below", "crosses_above", "crosses_below"):
        return f"{subject} {CONDITION_LABELS[condition]} {shown}"
    if condition == "change_over_window":
        magnitude = abs(float(threshold or 0.0))
        verb = "rises" if (threshold or 0.0) > 0 else "falls"
        unit = "%" if change_unit == "percent" else " pts"
        return f"{subject} {verb} {_plain_number(magnitude)}{unit} over {WINDOW_LABELS.get(str(window), str(window))}"
    if condition == "date_reached":
        return f"{subject} reached"
    if condition == "event_occurs":
        return f"{subject} is released"
    return subject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evaluate_event(criterion: IdeaCriterion, reading: ObservableReading, *, armed_from: datetime, now: datetime, base: dict) -> CriterionEvaluation:
    target = reading.event_time
    if criterion.condition == "date_reached":
        if target is None:
            return CriterionEvaluation(state="unavailable", reason="The source gave no date for this event.", **base)
        days_left = (target.date() - now.date()).days
        common = {
            **base,
            "value": float(days_left),
            "value_display": _days_display(days_left),
            "as_of": target,
        }
        if now >= target:
            return CriterionEvaluation(state="triggered", first_met_at=max(target, armed_from), **common)
        return CriterionEvaluation(state="holding", **common)

    # event_occurs
    if reading.event_released is None:
        return CriterionEvaluation(state="unavailable", reason="The source does not say whether the event was released.", **base)
    common = {
        **base,
        "value": reading.event_value,
        "value_display": reading.value_display or ("Released" if reading.event_released else "Scheduled"),
        "as_of": target,
    }
    if reading.event_released:
        return CriterionEvaluation(
            state="triggered",
            first_met_at=max(target or now, armed_from),
            met_value=reading.event_value,
            met_display=common["value_display"],
            **common,
        )
    return _holding_or_stale(reading, common)


def _holding_or_stale(reading: ObservableReading, common: dict) -> CriterionEvaluation:
    if reading.stale_reason:
        return CriterionEvaluation(state="stale", reason=reading.stale_reason, **common)
    return CriterionEvaluation(state="holding", **common)


def _usable_points(reading: ObservableReading) -> list[ObservablePoint]:
    points = [point for point in reading.history if _finite(point.value)]
    points.sort(key=lambda point: point.at)
    if reading.value is not None and _finite(reading.value):
        latest_at = reading.as_of or (points[-1].at if points else None)
        if latest_at is not None and (not points or latest_at > points[-1].at):
            points.append(ObservablePoint(at=latest_at, value=float(reading.value)))
        elif latest_at is not None and points and latest_at == points[-1].at:
            points[-1] = ObservablePoint(at=latest_at, value=float(reading.value))
    return points


def _reference_point(points: Sequence[ObservablePoint], cutoff: datetime) -> ObservablePoint | None:
    """The last observation on or before ``cutoff`` (the start of the window)."""
    reference = None
    for point in points:
        if point.at <= cutoff:
            reference = point
        else:
            break
    return reference


def _level_met(condition: str, value: float, threshold: float) -> bool:
    return value > threshold if condition == "above" else value < threshold


def _crossed(condition: str, previous: float, current: float, threshold: float) -> bool:
    if condition == "crosses_above":
        return previous <= threshold < current
    return previous >= threshold > current


def _change(reference: float, current: float, unit: str) -> float | None:
    if unit == "points":
        return current - reference
    if reference == 0:
        return None
    return (current / reference - 1.0) * 100.0


def _change_met(change: float, threshold: float) -> bool:
    return change >= threshold if threshold > 0 else change <= threshold


def _finite(value: float | None) -> bool:
    return value is not None and isinstance(value, (int, float)) and math.isfinite(float(value))


def _plain_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}"
    if abs(number) >= 100:
        return f"{number:,.2f}"
    return f"{number:,.4g}" if abs(number) < 1 else f"{number:,.2f}"


def _days_display(days_left: int) -> str:
    if days_left > 1:
        return f"In {days_left} days"
    if days_left == 1:
        return "Tomorrow"
    if days_left == 0:
        return "Today"
    return f"{-days_left} days ago"


def session_date_instant(value: date) -> datetime:
    """A session date as the naive-UTC midnight instant the readers use for daily points."""
    return datetime(value.year, value.month, value.day)
