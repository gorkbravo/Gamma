"""Barridos de parámetros, comparación y validación walk-forward de Script (E5).

Un barrido fija revisión, fuente y paquete de entradas; cada punto solo cambia los parámetros. Cada punto se
ejecuta como una ejecución normal ligada a su conjunto de parámetros. La comparación y el walk-forward se
recalculan siempre desde los resultados analíticos retenidos y validados (``gamma_analytics.json``): no hay
caché mutable ni un "mejor resultado" certificado dentro de la muestra.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from src.analytics.script_walk_forward import WalkForwardConfig, WalkForwardError, describe, run_walk_forward
from src.analytics.script_weight_book import BookOptions, WeightBookError
from src.application.research_script_service import (
    ResearchScriptConflictError,
    ResearchScriptNotFoundError,
    ResearchScriptServiceError,
    ResearchScriptValidationError,
)
from src.application.script_parameters import PARAMETERS_FILENAME, canonical_parameters
from src.models.research_script import (
    ResearchScriptRunCreateRequest,
    ResearchScriptSweep,
    ResearchScriptSweepAxis,
    ResearchScriptSweepCreateRequest,
    ResearchScriptSweepPoint,
)
from src.utils.time import now_utc

MAX_SWEEP_AXES = 3
MAX_SWEEP_AXIS_VALUES = 12
MAX_SWEEP_POINTS = 24
MAX_SWEEPS_LISTED = 20

IN_SAMPLE_COMPARISON_LABEL = (
    "Full common-window metrics are in-sample and descriptive. Points are listed in sweep order, not ranked: "
    "picking the best of {trials} trials on the same data overstates what it would earn next. "
    "Use walk-forward validation for out-of-sample evidence."
)
AUTHOR_TIMING_NOTE = (
    "Return timing is declared by the script. Gamma cannot verify that each return used only information available "
    "before it; prefer the weight book target, whose execution lag Gamma enforces."
)


@dataclass(frozen=True)
class EvaluationTarget:
    target: Literal["returns_result", "weight_book"]
    result_id: str | None = None
    book_options: BookOptions = field(default_factory=BookOptions)

    def validated(self) -> "EvaluationTarget":
        if self.target not in ("returns_result", "weight_book"):
            raise ResearchScriptValidationError(["Evaluation target must be returns_result or weight_book."])
        if self.target == "returns_result" and not self.result_id:
            raise ResearchScriptValidationError(["returns_result evaluation requires the result_id of a returns result."])
        try:
            options = self.book_options.validated()
        except WeightBookError as exc:
            raise ResearchScriptValidationError([str(exc)]) from exc
        return EvaluationTarget(self.target, self.result_id if self.target == "returns_result" else None, options)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"target": self.target}
        if self.target == "returns_result":
            data["result_id"] = self.result_id
            data["timing"] = {"enforced_by_gamma": False, "note": AUTHOR_TIMING_NOTE}
        else:
            data.update(self.book_options.as_dict())
            data["timing"] = {"enforced_by_gamma": True, "execution_lag": self.book_options.execution_lag,
                              "note": "Gamma applies each dated weight decision only from a later return period."}
        return data


def _value_key(value: Any) -> tuple:
    # 1 y 1.0 son el mismo valor para la investigación aunque su JSON difiera; True no es 1.
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return (type(value).__name__, value)
    return ("number", float(value))


def _definition(sweep_fields: dict[str, Any]) -> dict[str, Any]:
    return {key: sweep_fields[key] for key in (
        "script_id", "revision_id", "source_sha256", "input_snapshot_id", "input_manifest_sha256",
        "base_parameters", "axes", "points")}


def create_sweep(service, script_id: str, request: ResearchScriptSweepCreateRequest) -> ResearchScriptSweep:
    detail = service.get_script(script_id)
    if detail.script.status in {"archived", "discarded"}:
        raise ResearchScriptConflictError("Restore the archived script before creating a parameter sweep.")
    revision = service.store.load_revision(detail.script.script_id, str(request.revision_id or ""))
    if revision is None or revision.script_id != detail.script.script_id:
        raise ResearchScriptNotFoundError("Sweep revision not found for this script.")
    if revision.status in {"staged", "rejected"}:
        raise ResearchScriptValidationError(["A staged or rejected Operator revision cannot be swept. Accept it first."])
    if service.source_sha256(revision.source) != revision.source_sha256:
        raise ResearchScriptServiceError("Persisted revision source hash does not match its source text.")
    snapshot = service.get_input_snapshot(str(request.input_snapshot_id or ""))
    if snapshot.script_id != detail.script.script_id:
        raise ResearchScriptValidationError(["Input snapshot does not belong to the requested script."])
    if service.manifest_sha256(service._input_manifest_identity(snapshot)) != snapshot.manifest_sha256:
        raise ResearchScriptServiceError("Persisted input manifest hash does not match the immutable snapshot.")
    if any(item.logical_filename.casefold() == PARAMETERS_FILENAME for item in snapshot.files):
        raise ResearchScriptValidationError([f"{PARAMETERS_FILENAME} is reserved for run parameters; rename that input file."])

    errors: list[str] = []
    try:
        base, _, _ = canonical_parameters(request.base_parameters or {})
    except ValueError as exc:
        raise ResearchScriptValidationError([f"Base parameters: {exc}"]) from exc
    axes = list(request.axes or [])
    if not 1 <= len(axes) <= MAX_SWEEP_AXES:
        errors.append(f"A sweep needs between 1 and {MAX_SWEEP_AXES} parameter axes.")
    names = [axis.name for axis in axes]
    if len(set(names)) != len(names):
        errors.append("Sweep axis names must be unique.")
    for axis in axes:
        if axis.name in base:
            errors.append(f"Axis {axis.name!r} also appears in the base parameters; define it in one place.")
        values = list(axis.values or [])
        if not 2 <= len(values) <= MAX_SWEEP_AXIS_VALUES:
            errors.append(f"Axis {axis.name!r} needs between 2 and {MAX_SWEEP_AXIS_VALUES} values.")
        if len({_value_key(value) for value in values if not isinstance(value, (dict, list))}) != len(values):
            errors.append(f"Axis {axis.name!r} values must be distinct scalars.")
        for value in values:
            try:
                canonical_parameters({axis.name: value})
            except ValueError as exc:
                errors.append(str(exc))
    point_count = 1
    for axis in axes:
        point_count *= max(len(axis.values or []), 1)
    if axes and point_count > MAX_SWEEP_POINTS:
        errors.append(f"The sweep has {point_count} points; the limit is {MAX_SWEEP_POINTS}.")
    if errors:
        raise ResearchScriptValidationError(list(dict.fromkeys(errors)))

    points: list[ResearchScriptSweepPoint] = []
    for index, combination in enumerate(itertools.product(*(axis.values for axis in axes))):
        try:
            values, _, digest = canonical_parameters({**base, **{axis.name: value for axis, value in zip(axes, combination)}})
        except ValueError as exc:
            raise ResearchScriptValidationError([str(exc)]) from exc
        points.append(ResearchScriptSweepPoint(index=index, parameters=values, parameters_sha256=digest))
    sweep_axes = [ResearchScriptSweepAxis(name=axis.name, values=list(axis.values)) for axis in axes]
    fields = {
        "script_id": detail.script.script_id, "revision_id": revision.revision_id,
        "source_sha256": revision.source_sha256, "input_snapshot_id": snapshot.snapshot_id,
        "input_manifest_sha256": snapshot.manifest_sha256, "base_parameters": base,
        "axes": [{"name": axis.name, "values": axis.values} for axis in sweep_axes],
        "points": [{"index": point.index, "parameters_sha256": point.parameters_sha256} for point in points],
    }
    sweep = ResearchScriptSweep(
        sweep_id=uuid4().hex, script_id=detail.script.script_id, revision_id=revision.revision_id,
        source_sha256=revision.source_sha256, input_snapshot_id=snapshot.snapshot_id,
        input_manifest_sha256=snapshot.manifest_sha256, base_parameters=base, axes=sweep_axes, points=points,
        definition_sha256=service.manifest_sha256(_definition(fields)), created_at=now_utc(),
        transformation_note="Immutable parameter grid over one revision and one input bundle; each point runs separately.",
    )
    service.store.create_sweep(sweep)
    return sweep


def _verified_sweep(service, sweep_id: str) -> ResearchScriptSweep:
    sweep = service.store.load_sweep(sweep_id)
    if sweep is None:
        raise ResearchScriptNotFoundError("Research script sweep not found.")
    fields = {
        "script_id": sweep.script_id, "revision_id": sweep.revision_id, "source_sha256": sweep.source_sha256,
        "input_snapshot_id": sweep.input_snapshot_id, "input_manifest_sha256": sweep.input_manifest_sha256,
        "base_parameters": sweep.base_parameters,
        "axes": [{"name": axis.name, "values": axis.values} for axis in sweep.axes],
        "points": [{"index": point.index, "parameters_sha256": point.parameters_sha256} for point in sweep.points],
    }
    consistent = all(
        canonical_parameters(point.parameters)[2] == point.parameters_sha256 and point.index == position
        for position, point in enumerate(sweep.points)
    )
    if not consistent or service.manifest_sha256(_definition(fields)) != sweep.definition_sha256:
        raise ResearchScriptServiceError("Persisted sweep definition does not match its recorded hash.")
    return sweep


def get_sweep(service, sweep_id: str) -> ResearchScriptSweep:
    return _verified_sweep(service, sweep_id)


def list_sweeps(service, script_id: str) -> list[ResearchScriptSweep]:
    service.get_script(script_id)
    return service.store.list_sweeps(script_id)[:MAX_SWEEPS_LISTED]


def run_sweep_point(service, sweep_id: str, point_index: int):
    sweep = _verified_sweep(service, sweep_id)
    if not 0 <= point_index < len(sweep.points):
        raise ResearchScriptNotFoundError("Sweep point not found.")
    snapshot = service.get_input_snapshot(sweep.input_snapshot_id)
    if snapshot.manifest_sha256 != sweep.input_manifest_sha256:
        raise ResearchScriptConflictError("The sweep's input bundle no longer matches its recorded manifest hash.")
    point = sweep.points[point_index]
    run = service.create_run(
        sweep.script_id,
        ResearchScriptRunCreateRequest(revision_id=sweep.revision_id, input_snapshot_id=sweep.input_snapshot_id,
                                       parameters=point.parameters),
        _sweep_point=(sweep.sweep_id, point_index),
    )
    if run.source_sha256 != sweep.source_sha256 or run.parameters_sha256 != point.parameters_sha256:
        raise ResearchScriptServiceError("Sweep point run did not bind the sweep's exact source and parameters.")
    return run


def _point_state(service, sweep, point, run, evaluation: EvaluationTarget) -> dict[str, Any]:
    from src.application.script_analytics import inspect_analytics

    state: dict[str, Any] = {"index": point.index, "parameters": point.parameters,
                             "parameters_sha256": point.parameters_sha256, "run_id": None, "run_status": None,
                             "state": "not_run", "reason": "No run retained for this point.", "rows": None}
    if run is None:
        return state
    state.update(run_id=run.run_id, run_status=run.status)
    if (run.revision_id, run.source_sha256, run.input_snapshot_id, run.input_manifest_sha256, run.parameters_sha256) != (
            sweep.revision_id, sweep.source_sha256, sweep.input_snapshot_id, sweep.input_manifest_sha256, point.parameters_sha256):
        return {**state, "state": "binding_mismatch", "reason": "Retained run does not bind this point's exact revision, inputs and parameters."}
    if run.status != "completed":
        return {**state, "state": "run_failed", "reason": f"Latest run ended {run.status}; rerun the point."}
    report = inspect_analytics(service, run.run_id, evaluation.book_options)
    artifacts = report["artifacts"]
    valid = [artifact for artifact in artifacts if artifact["valid"]]
    if not valid:
        reason = artifacts[0]["errors"][0] if artifacts and artifacts[0]["errors"] else "The run retained no gamma_analytics.json."
        return {**state, "state": "invalid_output" if artifacts else "no_analytics", "reason": reason}
    if len(valid) > 1:
        return {**state, "state": "ambiguous", "reason": "The run retained several valid analytical files."}
    artifact = valid[0]
    if not artifact["eligible"]:
        return {**state, "state": "ineligible", "reason": "Requires completed, association-valid Python execution; safe previews are not calculations."}
    if evaluation.target == "returns_result":
        item = next((entry for entry in artifact["results"] if entry["result"]["result_id"] == evaluation.result_id), None)
        if item is None:
            return {**state, "state": "result_missing", "reason": f"No result {evaluation.result_id!r} in this run's analytical file."}
        if item["result"]["kind"] != "returns" or not item["can_open"]:
            return {**state, "state": "unsupported", "reason": item["unsupported_reason"] or "Result is not a supported daily simple return stream."}
        rows = item["mapping"]["rows"]
    else:
        book = artifact["weight_book"]
        if book is None:
            return {**state, "state": "result_missing", "reason": "No weight schedules in this run's analytical file."}
        if not book["can_open"]:
            return {**state, "state": "unsupported", "reason": book["unsupported_reason"]}
        rows = book["mapping"]["rows"]
    return {**state, "state": "ready", "reason": None, "rows": [(row["date"], float(row["value"])) for row in rows],
            "artifact_sha256": artifact["provenance"]["artifact_sha256"]}


def _point_states(service, sweep, evaluation: EvaluationTarget) -> list[dict[str, Any]]:
    latest: dict[int, Any] = {}
    for run in service.list_runs(sweep.script_id):  # más reciente primero: el último intento manda
        if run.sweep_id == sweep.sweep_id and run.sweep_point_index is not None:
            latest.setdefault(run.sweep_point_index, run)
    return [_point_state(service, sweep, point, latest.get(point.index), evaluation) for point in sweep.points]


def _sweep_identity(sweep) -> dict[str, Any]:
    return {"sweep_id": sweep.sweep_id, "definition_sha256": sweep.definition_sha256, "script_id": sweep.script_id,
            "revision_id": sweep.revision_id, "source_sha256": sweep.source_sha256,
            "input_snapshot_id": sweep.input_snapshot_id, "input_manifest_sha256": sweep.input_manifest_sha256}


def evaluate_sweep(service, sweep_id: str, evaluation: EvaluationTarget) -> dict[str, Any]:
    sweep = _verified_sweep(service, sweep_id)
    evaluation = evaluation.validated()
    states = _point_states(service, sweep, evaluation)
    ready = {state["index"]: state["rows"] for state in states if state["state"] == "ready"}
    common_dates: set[str] = set()
    warnings: list[str] = []
    if ready:
        common_dates = set.intersection(*(set(day for day, _ in rows) for rows in ready.values()))
        if not common_dates:
            warnings.append("Ready points share no common dates; metrics are withheld.")
        elif any(len(rows) != len(common_dates) for rows in ready.values()):
            warnings.append("Points cover different dates; metrics use only the exact common dates (no filling).")
    if len(ready) < len(states):
        warnings.append(f"{len(states) - len(ready)} of {len(states)} points are not ready; they still count as trials.")
    ordered = sorted(common_dates)
    common = {"start": ordered[0], "end": ordered[-1], "observations": len(ordered)} if ordered else None
    points = []
    for state in states:
        rows = state.pop("rows")
        entry = {**state, "coverage": None, "metrics": None}
        if rows:
            entry["coverage"] = {"start": rows[0][0], "end": rows[-1][0], "observations": len(rows)}
            if common_dates:
                entry["metrics"] = describe([(day, value) for day, value in rows if day in common_dates])
        points.append(entry)
    return {
        "contract_version": "gamma-script-sweep-evaluation.v1", **_sweep_identity(sweep),
        "evaluation": evaluation.as_dict(), "trials": len(states), "ready_points": len(ready),
        "common_window": common, "points": points,
        "in_sample_label": IN_SAMPLE_COMPARISON_LABEL.format(trials=len(states)),
        "warnings": warnings,
    }


def walk_forward_sweep(service, sweep_id: str, evaluation: EvaluationTarget, config: WalkForwardConfig) -> dict[str, Any]:
    sweep = _verified_sweep(service, sweep_id)
    evaluation = evaluation.validated()
    states = _point_states(service, sweep, evaluation)
    blocked = [state for state in states if state["state"] != "ready"]
    if blocked:
        raise ResearchScriptValidationError([
            f"Point {state['index']} is {state['state']}: {state['reason']}" for state in blocked[:12]
        ] + ([f"{len(blocked) - 12} more points are not ready."] if len(blocked) > 12 else []) + [
            "Walk-forward needs every sweep point; dropping points would silently shrink the trial set."
        ])
    try:
        result = run_walk_forward({state["index"]: state["rows"] for state in states}, config)
    except WalkForwardError as exc:
        raise ResearchScriptValidationError([str(exc)]) from exc
    parameters = {state["index"]: state["parameters"] for state in states}
    for fold in result["folds"]:
        fold["selected_parameters"] = parameters[fold["selected_point"]]
    reference = result["in_sample_reference"]
    reference["parameters"] = parameters.get(reference["point_index"]) if reference["point_index"] is not None else None
    report = {
        **result, **_sweep_identity(sweep), "evaluation": evaluation.as_dict(),
        "points": [{"index": state["index"], "parameters": state["parameters"],
                    "parameters_sha256": state["parameters_sha256"], "run_id": state["run_id"],
                    "artifact_sha256": state["artifact_sha256"]} for state in states],
        "origin": "script_experiments.walk_forward",
        "transformation_note": "Derived from retained, validated per-point analytical results; nothing is fetched, filled or saved.",
    }
    report["report_sha256"] = service.manifest_sha256(json.loads(json.dumps(report, default=str)))
    return report
