"""Validación walk-forward de un barrido de parámetros de Script (E5).

Cada pliegue elige el punto del barrido con la mejor métrica calculada **solo** con observaciones de
entrenamiento y aplica esa elección a las observaciones de prueba, todas estrictamente posteriores. El flujo
fuera de muestra concatena los tramos de prueba. El mejor punto dentro de la muestra completa se informa
aparte y etiquetado como descriptivo: no es evidencia de validación (sesgo de selección entre N pruebas).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from src.analytics.research_returns import compute_return_stream_metrics

CONTRACT_VERSION = "gamma-script-walk-forward.v1"
PERIODS_PER_YEAR = 252
MIN_TRAIN_OBSERVATIONS = 10
MIN_TEST_OBSERVATIONS = 5
MAX_FOLDS = 250

SelectionMetric = Literal["sharpe", "total_return"]
WindowKind = Literal["anchored", "rolling"]

IN_SAMPLE_LABEL = (
    "In-sample reference: chosen with every observation, including the out-of-sample dates. "
    "Descriptive only; the maximum of {trials} trials is biased upward and is not a validation result."
)


class WalkForwardError(ValueError):
    pass


@dataclass(frozen=True)
class WalkForwardConfig:
    train_observations: int
    test_observations: int
    window: WindowKind = "anchored"
    selection_metric: SelectionMetric = "sharpe"

    def validated(self) -> "WalkForwardConfig":
        if isinstance(self.train_observations, bool) or not isinstance(self.train_observations, int) \
                or self.train_observations < MIN_TRAIN_OBSERVATIONS:
            raise WalkForwardError(f"train_observations must be an integer of at least {MIN_TRAIN_OBSERVATIONS}.")
        if isinstance(self.test_observations, bool) or not isinstance(self.test_observations, int) \
                or self.test_observations < MIN_TEST_OBSERVATIONS:
            raise WalkForwardError(f"test_observations must be an integer of at least {MIN_TEST_OBSERVATIONS}.")
        if self.window not in ("anchored", "rolling"):
            raise WalkForwardError("window must be anchored or rolling.")
        if self.selection_metric not in ("sharpe", "total_return"):
            raise WalkForwardError("selection_metric must be sharpe or total_return.")
        return self


def selection_value(values: list[float], metric: SelectionMetric) -> float | None:
    """Métrica de selección sobre un tramo; misma definición que Strategy Lab (rf = 0, 252 periodos)."""
    if not values:
        return None
    if metric == "total_return":
        return math.prod(1.0 + value for value in values) - 1.0
    if len(values) < 2:
        return None
    deviation = statistics.stdev(values)
    if not math.isfinite(deviation) or deviation <= 0:
        return None
    return statistics.fmean(values) * PERIODS_PER_YEAR / (deviation * math.sqrt(PERIODS_PER_YEAR))


def align_points(series_by_point: dict[int, list[tuple[str, float]]]) -> tuple[list[str], dict[int, dict[str, float]], list[dict[str, Any]]]:
    """Intersección exacta de fechas entre puntos (sin relleno) y lo excluido de cada uno."""
    if len(series_by_point) < 2:
        raise WalkForwardError("A walk-forward selection needs at least two sweep points.")
    common = set.intersection(*(set(day for day, _ in rows) for rows in series_by_point.values()))
    dates = sorted(common)
    values = {index: {day: float(value) for day, value in rows if day in common} for index, rows in series_by_point.items()}
    alignment = [{"point_index": index, "observations": len(rows), "excluded_observations": len(rows) - len(dates)}
                 for index, rows in sorted(series_by_point.items())]
    return dates, values, alignment


def describe(rows: list[tuple[str, float]]) -> dict[str, Any]:
    """Métricas descriptivas con la función de Strategy Lab (anualización 252, rf 0)."""
    if not rows:
        return {"observations": 0}
    series = pd.Series([value for _, value in rows], index=pd.to_datetime([day for day, _ in rows]), dtype=float)
    metrics = compute_return_stream_metrics(series, periods_per_year=PERIODS_PER_YEAR, frequency_label="daily")
    return {
        "observations": metrics.observation_count, "start": rows[0][0], "end": rows[-1][0],
        "total_return": metrics.total_return, "annual_return": metrics.annual_return,
        "annual_volatility": metrics.annual_volatility, "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown": metrics.max_drawdown,
    }


def _select(candidates: dict[int, float | None]) -> int | None:
    # Desempate: el índice de punto más bajo, declarado en el resultado.
    ranked = [(value, -index) for index, value in candidates.items() if value is not None and math.isfinite(value)]
    return -max(ranked)[1] if ranked else None


def run_walk_forward(series_by_point: dict[int, list[tuple[str, float]]], config: WalkForwardConfig) -> dict[str, Any]:
    config = config.validated()
    dates, values, alignment = align_points(series_by_point)
    n = len(dates)
    if n < config.train_observations + 1:
        raise WalkForwardError(
            f"The common window has {n} observations; at least train_observations + 1 = {config.train_observations + 1} are required."
        )
    fold_starts = list(range(config.train_observations, n, config.test_observations))
    if len(fold_starts) > MAX_FOLDS:
        raise WalkForwardError(f"{len(fold_starts)} folds exceed the limit of {MAX_FOLDS}; increase test_observations.")
    folds = []
    oos_rows: list[tuple[str, float]] = []
    selection_frequency: dict[int, int] = {}
    for number, test_start in enumerate(fold_starts, start=1):
        test_end = min(test_start + config.test_observations, n)
        train_start = 0 if config.window == "anchored" else test_start - config.train_observations
        train_dates, test_dates = dates[train_start:test_start], dates[test_start:test_end]
        # La selección solo ve train_dates: cualquier cambio en fechas >= test_dates[0] no puede alterarla.
        train_metrics = {index: selection_value([point[day] for day in train_dates], config.selection_metric)
                         for index, point in values.items()}
        selected = _select(train_metrics)
        if selected is None:
            raise WalkForwardError(
                f"Fold {number}: the {config.selection_metric} metric is undefined for every point on {train_dates[0]}..{train_dates[-1]}."
            )
        test_values = [values[selected][day] for day in test_dates]
        oos_rows.extend(zip(test_dates, test_values))
        selection_frequency[selected] = selection_frequency.get(selected, 0) + 1
        folds.append({
            "fold": number, "train_start": train_dates[0], "train_end": train_dates[-1],
            "train_observations": len(train_dates), "test_start": test_dates[0], "test_end": test_dates[-1],
            "test_observations": len(test_dates), "partial": len(test_dates) < config.test_observations,
            "selected_point": selected, "selected_train_metric": train_metrics[selected],
            "train_metrics": {str(index): value for index, value in sorted(train_metrics.items())},
            "test_return": math.prod(1.0 + value for value in test_values) - 1.0,
            "causal": train_dates[-1] < test_dates[0],
        })
    full_metrics = {index: selection_value([point[day] for day in dates], config.selection_metric) for index, point in values.items()}
    reference = _select(full_metrics)
    oos = describe(oos_rows)
    oos_selection_metric = selection_value([value for _, value in oos_rows], config.selection_metric)
    selected_train = [fold["selected_train_metric"] for fold in folds if fold["selected_train_metric"] is not None]
    trials = len(values)
    warnings = []
    if any(item["excluded_observations"] for item in alignment):
        warnings.append("Points cover different dates; only the exact common dates are used (no filling).")
    if folds and folds[-1]["partial"]:
        warnings.append("The last test fold is shorter than test_observations.")
    if len(selection_frequency) > 1:
        warnings.append(f"Selection changed across folds ({len(selection_frequency)} distinct points); parameter choice is unstable.")
    return {
        "contract_version": CONTRACT_VERSION,
        "config": {"train_observations": config.train_observations, "test_observations": config.test_observations,
                   "window": config.window, "selection_metric": config.selection_metric,
                   "tie_break": "lowest point index", "periods_per_year": PERIODS_PER_YEAR, "risk_free_rate": 0.0},
        "trials": trials,
        "common_window": {"start": dates[0], "end": dates[-1], "observations": n},
        "alignment": alignment,
        "folds": folds,
        "selection_frequency": {str(index): count for index, count in sorted(selection_frequency.items())},
        "out_of_sample": {**oos, "selection_metric_value": oos_selection_metric,
                           "rows": [{"date": day, "value": value} for day, value in oos_rows]},
        "in_sample_selected_mean_metric": statistics.fmean(selected_train) if selected_train else None,
        "in_sample_reference": {
            "point_index": reference, "metric": config.selection_metric,
            "value": full_metrics.get(reference) if reference is not None else None,
            "label": IN_SAMPLE_LABEL.format(trials=trials),
        },
        "causality": {
            "rule": "Each fold selects with training observations only; its test observations are strictly later and are never used for that selection.",
            "verified": all(fold["causal"] for fold in folds),
        },
        "warnings": warnings,
    }
