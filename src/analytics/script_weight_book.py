"""Libro causal de pesos para resultados opcionales de Script (cierre del traspaso de pesos de E4).

Convierte calendarios de exposición firmada sobre NAV (``weights``) y los rendimientos simples diarios de
cada instrumento (``returns``) declarados en el mismo ``gamma_analytics.json`` en un único flujo de
rendimientos del libro. Reglas, todas explícitas en el resultado:

- Timing causal: una decisión fechada ``t`` se aplica desde el primer periodo de rendimiento que empieza en
  ``t`` o después (periodo k = (D[k-1], D[k]] con D[k-1] >= t), más ``execution_lag - 1`` periodos. Nunca
  gana el rendimiento del propio día en que se decide.
- Deriva: entre rebalanceos las posiciones evolucionan con sus rendimientos; el residuo 1 - sum(w) es caja al 0%.
- Pesos exactos: sin normalizar, conservando cortos y apalancamiento.
- Costes: ``cost_bps`` por unidad de rotación unidireccional sum|objetivo - derivado|, descontados del NAV al
  inicio del periodo de rebalanceo: R = (1 - c * rotación) * (1 + sum(w * r)) - 1.
- Alineación estricta: solo el tramo común de fechas de todos los instrumentos ponderados, sin huecos dentro ni
  relleno; lo recortado fuera del tramo se informa.

Sin adquisición de datos, sin cuentas, sin órdenes: es aritmética sobre datos ya retenidos.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Any

MAX_EXECUTION_LAG = 5
MAX_COST_BPS = 1000.0
MAX_REPORTED_REBALANCES = 500


class WeightBookError(ValueError):
    """El libro no se puede calcular fielmente; el motivo es apto para mostrarse al usuario."""


@dataclass(frozen=True)
class BookOptions:
    execution_lag: int = 1
    cost_bps: float = 0.0

    def validated(self) -> "BookOptions":
        if isinstance(self.execution_lag, bool) or not isinstance(self.execution_lag, int) \
                or not 1 <= self.execution_lag <= MAX_EXECUTION_LAG:
            raise WeightBookError(f"execution_lag must be an integer between 1 and {MAX_EXECUTION_LAG}; lag 0 would use the decision date's own return.")
        cost = float(self.cost_bps)
        if not math.isfinite(cost) or not 0 <= cost <= MAX_COST_BPS:
            raise WeightBookError(f"cost_bps must be between 0 and {MAX_COST_BPS:g}.")
        return BookOptions(execution_lag=self.execution_lag, cost_bps=cost)

    def as_dict(self) -> dict[str, Any]:
        return {"execution_lag": self.execution_lag, "cost_bps": self.cost_bps}


@dataclass(frozen=True)
class WeightBookResult:
    rows: list[dict[str, Any]]
    instruments: list[str]
    calendar_start: str
    calendar_end: str
    trimmed_observations: dict[str, int]
    rebalances: list[dict[str, Any]]
    superseded_decisions: list[str]
    ignored_decisions: list[str]
    total_turnover: float
    total_cost_fraction: float
    max_gross_exposure: float
    warnings: list[str] = field(default_factory=list)


def compute_weight_book(
    weights: dict[str, list[tuple[str, float | None]]],
    returns: dict[str, list[tuple[str, float | None]]],
    options: BookOptions,
) -> WeightBookResult:
    """``weights``/``returns``: instrumento -> [(fecha ISO, valor)], fracciones, fechas estrictamente crecientes."""
    options = options.validated()
    instruments = sorted(weights)
    if not instruments:
        raise WeightBookError("No weight schedule is present.")
    missing = [item for item in instruments if item not in returns]
    if missing:
        raise WeightBookError(
            "Each weighted instrument needs its own daily simple returns in this file; missing for "
            + ", ".join(missing) + ". Gamma does not acquire histories for a weight-only artifact."
        )

    decision_dates = [day for day, _ in weights[instruments[0]]]
    for item in instruments:
        dates = [day for day, _ in weights[item]]
        if dates != decision_dates:
            raise WeightBookError(
                "Weight schedules must share identical decision dates. State every instrument's target "
                f"(including 0) on each rebalance date; {item} differs from {instruments[0]}."
            )
        if any(value is None for _, value in weights[item]):
            raise WeightBookError(f"Weight schedule for {item} contains null targets; no target is inferred.")

    # Tramo común: desde la primera fecha que todos tienen hasta la última que todos tienen.
    start = max(series[0][0] for series in (returns[item] for item in instruments))
    end = min(series[-1][0] for series in (returns[item] for item in instruments))
    if start >= end:
        raise WeightBookError("Weighted instruments' return histories do not overlap on at least two dates.")
    calendar: list[str] | None = None
    trimmed: dict[str, int] = {}
    values: dict[str, dict[str, float]] = {}
    for item in instruments:
        inside = [(day, value) for day, value in returns[item] if start <= day <= end]
        trimmed[item] = len(returns[item]) - len(inside)
        days = [day for day, _ in inside]
        if calendar is None:
            calendar = days
        elif days != calendar:
            first = min(set(days) ^ set(calendar))
            raise WeightBookError(
                f"Return calendars differ inside the common span {start}..{end} ({item} near {first}). "
                "Gamma does not fill or align missing observations."
            )
        nulls = [day for day, value in inside if value is None]
        if nulls:
            raise WeightBookError(f"Returns for {item} contain null observations inside the common span (first {nulls[0]}).")
        values[item] = {day: float(value) for day, value in inside}
    assert calendar is not None

    # Periodo efectivo de cada decisión; varias en el mismo periodo: gana la más reciente.
    targets: dict[int, tuple[str, dict[str, float]]] = {}
    superseded: list[str] = []
    ignored: list[str] = []
    for position, decided in enumerate(decision_dates):
        first_period = max(bisect_left(calendar, decided) + 1, 1)  # primer k con calendar[k-1] >= decided
        period = first_period + options.execution_lag - 1
        if period >= len(calendar):
            ignored.append(decided)
            continue
        if period in targets:
            superseded.append(targets[period][0])
        targets[period] = (decided, {item: float(weights[item][position][1]) for item in instruments})
    if not targets:
        raise WeightBookError(
            f"No decision takes effect inside the common return calendar {start}..{end} with execution lag {options.execution_lag}."
        )

    cost_rate = options.cost_bps / 10_000.0
    current = {item: 0.0 for item in instruments}  # antes de la primera decisión: todo caja
    rows: list[dict[str, Any]] = []
    rebalances: list[dict[str, Any]] = []
    total_turnover = total_cost = max_gross = 0.0
    for period in range(min(targets), len(calendar)):
        day = calendar[period]
        cost_fraction = 0.0
        if period in targets:
            decided, target = targets[period]
            turnover = sum(abs(target[item] - current[item]) for item in instruments)
            cost_fraction = cost_rate * turnover
            if cost_fraction >= 1:
                raise WeightBookError(f"Costs on {day} would consume the whole NAV (turnover {turnover:.4g}).")
            current = dict(target)
            total_turnover += turnover
            total_cost += cost_fraction
            gross = sum(abs(value) for value in current.values())
            max_gross = max(max_gross, gross)
            if len(rebalances) < MAX_REPORTED_REBALANCES:
                rebalances.append({
                    "decision_date": decided, "effective_period_end": day,
                    "effective_period_start": calendar[period - 1], "turnover": turnover,
                    "cost_fraction": cost_fraction, "gross_exposure": gross,
                    "net_exposure": sum(current.values()), "cash_weight": 1.0 - sum(current.values()),
                })
        growth = 1.0 + sum(current[item] * values[item][day] for item in instruments)
        if growth <= 0:
            raise WeightBookError(f"Book NAV becomes non-positive on {day}; the leverage is outside the representable range.")
        rows.append({"date": day, "value": (1.0 - cost_fraction) * growth - 1.0})
        # Deriva hasta el final del periodo; la caja (1 - sum w) rinde 0.
        current = {item: current[item] * (1.0 + values[item][day]) / growth for item in instruments}

    warnings = []
    if superseded:
        warnings.append(f"{len(superseded)} decision(s) were superseded by a later decision effective in the same period.")
    if ignored:
        warnings.append(f"{len(ignored)} decision(s) dated after the last usable period never take effect.")
    if any(trimmed.values()):
        warnings.append("Return observations outside the common span were excluded: "
                        + ", ".join(f"{item} {count}" for item, count in trimmed.items() if count) + ".")
    if len(targets) > MAX_REPORTED_REBALANCES:
        warnings.append(f"Only the first {MAX_REPORTED_REBALANCES} rebalances are itemized; totals include all.")
    return WeightBookResult(
        rows=rows, instruments=instruments, calendar_start=calendar[0], calendar_end=calendar[-1],
        trimmed_observations=trimmed, rebalances=rebalances, superseded_decisions=superseded,
        ignored_decisions=ignored, total_turnover=total_turnover, total_cost_fraction=total_cost,
        max_gross_exposure=max_gross, warnings=warnings,
    )


BOOK_ASSUMPTIONS = [
    "A decision dated t applies from the first return period that starts on or after t, plus execution_lag - 1 further periods; the decision date's own return is never earned.",
    "Holdings drift with their own returns between decisions; the residual 1 - sum(weights) is cash earning 0% (no risk-free rate, financing, borrow or dividend adjustments beyond the supplied returns).",
    "Signed NAV exposures are used exactly: no normalization, shorts and leverage preserved.",
    "Costs: cost_bps per unit of one-way turnover |target - drifted weight|, deducted from NAV at the start of the rebalance period.",
    "Only the common return span of all weighted instruments is used; no filling or resampling.",
]
