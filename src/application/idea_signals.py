"""Signals for ideas: the quant layer (Workstream 12, checkpoint I4a).

A signal is data the user brought, never something Gamma runs:

* **Script:** a completed run of an accepted revision in Strategy Lab, read
  from its retained, validated ``gamma_analytics.json`` (the same checks as the
  analytical handoff, ``script_analytics.inspect_analytics``). Gamma never
  starts a Script run here; runs cost API credit and are the user's action.
* **Import:** CSV rows the user pasted, read with the Strategy Lab import rules
  (``ResearchService.imported_column_values`` and ``analyze_strategy_lab``).
  It is a data path, not an execution path.

A ``positions`` or ``weights`` signal is one book: the schedule's last row
dated on or before the attach day, frozen (I4 design decision 1). A row dated
later is refused. A ``returns`` signal is validation only: Gamma cannot
rebuild it from provider closes, so it never drives tracking (decision 2).

Attaching records trials in the idea's append-only ledger (decision 3): every
completed run of the script at that moment, every point of a validated sweep,
each distinct import. A walk-forward report over an E5 sweep is computed from
retained per-point results (``script_experiments.walk_forward_sweep``) and
frozen as the signal's validation snapshot. Nothing here can place, stage or
route an order, or touch an account.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.models.handoff import HandoffEntity
from src.models.ideas import (
    SIGNAL_BOOK_KINDS,
    SIGNAL_GROSS_MAX,
    SIGNAL_OUTPUT_KINDS,
    SUPPLIED_SERIES_LABEL,
    Idea,
    IdeaSignal,
    IdeaSignalLeg,
    IdeaSourceUnavailableError,
    IdeaSuppliedSeries,
    IdeaTrackedLeg,
    IdeaTrial,
    IdeaValidationError,
    IdeaValidationFold,
    IdeaValidationSnapshot,
    default_tracking_asset_class,
    tracking_market,
)
from src.models.provenance import ProvenanceRecord
from src.utils.time import now_utc

SIGNAL_ORIGIN = "idea_signals"
# Espacios de nombres de instrumentos de Script que se leen directamente como un ticker o un id de CoinGecko.
TICKER_NAMESPACES = {"ticker", "symbol", "yahoo", "yfinance", "equity", "etf"}
CRYPTO_NAMESPACES = {"coingecko", "crypto"}
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-^=]{0,23}$")
SIGNAL_ENTITY_TYPES = ("equity", "etf", "crypto")
IMPORT_ROWS_MAX = 20_000
IMPORT_COLUMNS_MAX = 24
OOS_CURVE_MAX_POINTS = 260
POSITION_PRICE_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class InstrumentMapping:
    """How a source instrument (CSV column or Script instrument) becomes an idea leg."""

    symbol: str
    entity_type: str = "equity"
    label: str | None = None


@dataclass(frozen=True)
class ValidationRequest:
    """A walk-forward over an E5 sweep of the same script."""

    sweep_id: str
    train_observations: int
    test_observations: int
    window: str = "anchored"
    selection_metric: str = "sharpe"
    target: str | None = None  # weight_book | returns_result; por defecto, el del tipo de señal
    result_id: str | None = None
    execution_lag: int = 1
    cost_bps: float | None = None  # None: el coste por lado más alto de las patas (nunca cero por defecto)


@dataclass(frozen=True)
class SignalRequest:
    source: str
    output_kind: str
    label: str | None = None
    # Script
    run_id: str | None = None
    result_id: str | None = None
    validation: ValidationRequest | None = None
    # Importación
    rows: Sequence[Mapping[str, Any]] = ()
    date_column: str | None = None
    columns: Sequence[str] = ()
    value_column: str | None = None
    value_kind: str = "return"
    # Script e importación: identidad de origen -> pata
    instruments: Mapping[str, InstrumentMapping] = field(default_factory=dict)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _entity(mapping: InstrumentMapping, *, source_label: str) -> HandoffEntity:
    entity_type = str(mapping.entity_type or "equity").strip().lower()
    if entity_type not in SIGNAL_ENTITY_TYPES:
        raise IdeaValidationError(f"{source_label}: the instrument type must be one of {SIGNAL_ENTITY_TYPES}.")
    symbol = str(mapping.symbol or "").strip()
    if not SYMBOL_PATTERN.match(symbol):
        raise IdeaValidationError(f"{source_label}: {symbol!r} is not a ticker or a CoinGecko id.")
    label = str(mapping.label or "").strip() or symbol.upper()
    if entity_type == "crypto":
        token = symbol.lower()
        return HandoffEntity(entity_type="crypto", label=label, normalized_id=token.upper(), native_id=token,
                             metadata={"coingecko_id": token})
    return HandoffEntity(entity_type=entity_type, label=label, normalized_id=symbol.upper())


def _content_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _iso_day(value: Any) -> date:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _cumulative(rows: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    level = 1.0
    curve = []
    for day, value in rows:
        level *= 1.0 + float(value)
        curve.append((day, level - 1.0))
    return curve


class IdeaSignalService:
    """Builds signals from Script runs and imports and attaches them through ``IdeaService``."""

    def __init__(
        self,
        idea_service: Any,
        *,
        script_service: Any = None,
        research_service: Any = None,
        prices: Any = None,
        clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self.idea_service = idea_service
        self.script_service = script_service
        self.research_service = research_service
        self.prices = prices
        self._clock = clock

    # -- public ---------------------------------------------------------------

    def attach(self, idea_id: str, request: SignalRequest) -> Idea:
        idea = self.idea_service.get_idea(idea_id)
        if idea.status not in {"draft", "active"}:
            raise IdeaValidationError(f"A signal attaches to a draft or active idea; this one is {idea.status}.")
        if request.output_kind not in SIGNAL_OUTPUT_KINDS:
            raise IdeaValidationError(f"Choose what the signal holds: {', '.join(SIGNAL_OUTPUT_KINDS)}.")
        if request.source == "script":
            signal, trials = self._from_script(idea, request)
        elif request.source == "import":
            signal, trials = self._from_import(idea, request)
        else:
            raise IdeaValidationError("A signal comes from a Script run or an import.")
        return self.idea_service.attach_signal(idea_id, signal, trials)

    def detach(self, idea_id: str) -> Idea:
        return self.idea_service.detach_signal(idea_id)

    # -- Script ------------------------------------------------------------------

    def _from_script(self, idea: Idea, request: SignalRequest) -> tuple[IdeaSignal, list[IdeaTrial]]:
        from src.analytics.script_walk_forward import WalkForwardConfig
        from src.application.research_script_service import ResearchScriptServiceError, ResearchScriptValidationError
        from src.application.script_analytics import inspect_analytics, parse_payload
        from src.application.script_experiments import EvaluationTarget, walk_forward_sweep
        from src.analytics.script_weight_book import BookOptions
        from src.models.script_analytics import Returns, Weights

        service = self.script_service
        if service is None:
            raise IdeaSourceUnavailableError("Research Script is not running in this build.")
        if request.output_kind == "positions":
            raise IdeaValidationError("A Script run supplies weights or returns; positions come from an import.")
        run_id = str(request.run_id or "").strip()
        if not run_id:
            raise IdeaValidationError("Choose the Script run to attach.")
        now = self._clock()
        try:
            run = service.get_run(run_id)
            if run.status != "completed":
                raise IdeaValidationError(f"Run {run_id} ended {run.status}; attach a completed run.")
            revision = service.store.load_revision(run.script_id, run.revision_id)
            if revision is None or revision.status in {"staged", "rejected"}:
                raise IdeaValidationError("The run's revision is not accepted; accept the revision in Strategy Lab first.")
            report = inspect_analytics(service, run_id)
        except ResearchScriptValidationError as exc:
            raise IdeaValidationError("; ".join(exc.errors)) from exc
        except ResearchScriptServiceError as exc:
            raise IdeaValidationError(str(exc)) from exc
        artifacts = [item for item in report["artifacts"] if item["valid"]]
        if not artifacts:
            errors = [error for item in report["artifacts"] for error in item["errors"]]
            raise IdeaValidationError(errors[0] if errors else "The run retained no valid gamma_analytics.json.")
        if len(artifacts) > 1:
            raise IdeaValidationError("The run retained several valid analytical files; Gamma cannot choose one.")
        artifact = artifacts[0]
        if not artifact["eligible"]:
            raise IdeaValidationError(
                "Only a completed run whose Python executed and produced its file in this run can be a signal; safe previews are not calculations."
            )
        provenance_info = artifact["provenance"]
        _, _, content = service.get_output_artifact(run_id, artifact["output_id"])
        payload = parse_payload(content)
        instruments = {item.instrument_id: item for item in payload.instruments}
        warnings: list[str] = []
        legs: tuple[IdeaSignalLeg, ...] = ()
        supplied: IdeaSuppliedSeries | None = None
        as_of: date | None = None
        result_id: str | None = None
        if request.output_kind == "weights":
            schedules = [item for item in payload.results if isinstance(item, Weights)]
            if not schedules:
                raise IdeaValidationError("The run's analytical file has no weight schedules.")
            dated = {
                item.instrument_id: [(date.fromisoformat(point.date), point.value) for point in item.observations]
                for item in schedules
            }
            as_of, weights = self._latest_book(dated, now.date(), what="weight schedule")
            legs = tuple(
                IdeaSignalLeg(
                    entity=_entity(self._script_mapping(request, instruments, key), source_label=key),
                    weight=value,
                    instrument_id=key,
                )
                for key, value in weights.items()
            )
            result_id = ",".join(item.result_id for item in schedules)
        else:
            candidates = [item for item in payload.results if isinstance(item, Returns)]
            if request.result_id:
                candidates = [item for item in candidates if item.result_id == request.result_id]
            if len(candidates) != 1:
                raise IdeaValidationError(
                    "Name the returns result to attach." if len(candidates) > 1 else "The run's analytical file has no such returns result."
                )
            chosen = candidates[0]
            result_id = chosen.result_id
            entry = next((item for item in artifact["results"] if item["result"]["result_id"] == chosen.result_id), None)
            if entry is None or not entry["can_open"]:
                raise IdeaValidationError((entry or {}).get("unsupported_reason") or "This returns result cannot be read as daily simple returns.")
            rows = entry["mapping"]["rows"]
            if rows and date.fromisoformat(rows[-1]["date"]) > now.date():
                raise IdeaValidationError(f"The returns run to {rows[-1]['date']}, after today; a signal cannot hold future rows.")
            supplied = self._supplied(rows, label=f"Supplied by Script run {run_id[:12]}, not rebuilt by Gamma", warnings=warnings)
            as_of = _iso_day(rows[-1]["date"]) if rows else None
        script_title = run.script_id
        try:
            script_title = service.get_script(run.script_id).script.title or run.script_id
        except Exception:  # noqa: BLE001 - el título es solo una etiqueta
            pass
        source_ref = {
            "script_id": run.script_id,
            "script_title": script_title,
            "revision_id": run.revision_id,
            "revision_number": getattr(revision, "revision_number", None),
            "revision_status": revision.status,
            "source_sha256": run.source_sha256,
            "parameters_sha256": run.parameters_sha256,
            "parameters": run.parameters,
            "run_id": run.run_id,
            "sweep_id": run.sweep_id,
            "sweep_point_index": run.sweep_point_index,
            "output_id": artifact["output_id"],
            "artifact_sha256": provenance_info.get("artifact_sha256"),
            "result_id": result_id,
            "input_snapshot_id": run.input_snapshot_id,
            "input_manifest_sha256": run.input_manifest_sha256,
            "runtime_kind": run.runtime_kind,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        signal_id = uuid4().hex
        trials = self._script_trials(run.script_id, now=now, signal_id=signal_id)
        validation = None
        if request.validation is not None:
            spec = request.validation
            target = spec.target or ("weight_book" if request.output_kind == "weights" else "returns_result")
            cost_bps = spec.cost_bps
            if cost_bps is None and target == "weight_book":
                cost_bps = self._default_turnover_bp(idea, legs)
            try:
                sweep = service.store.load_sweep(spec.sweep_id)
                if sweep is None or sweep.script_id != run.script_id:
                    raise IdeaValidationError("Validate with a sweep of the same script.")
                evaluation = EvaluationTarget(
                    target=target,  # type: ignore[arg-type]
                    result_id=spec.result_id or (result_id if target == "returns_result" else None),
                    book_options=BookOptions(execution_lag=int(spec.execution_lag), cost_bps=float(cost_bps or 0.0)),
                )
                config = WalkForwardConfig(
                    train_observations=int(spec.train_observations),
                    test_observations=int(spec.test_observations),
                    window=spec.window,  # type: ignore[arg-type]
                    selection_metric=spec.selection_metric,  # type: ignore[arg-type]
                )
                wf = walk_forward_sweep(service, spec.sweep_id, evaluation, config)
            except ResearchScriptValidationError as exc:
                raise IdeaValidationError("Walk-forward validation: " + "; ".join(exc.errors)) from exc
            except ResearchScriptServiceError as exc:
                raise IdeaValidationError(f"Walk-forward validation: {exc}") from exc
            validation = self._validation_snapshot(wf, now=now)
            if run.sweep_id != spec.sweep_id:
                warnings.append(
                    "The attached run is not a point of the validated sweep; the out-of-sample figures describe the sweep's selection rule, not this run."
                )
            for point in wf["points"]:
                key = f"sweep:{wf['sweep_id']}:{point['index']}"
                trials.append(IdeaTrial(key=key, kind="sweep_point", recorded_at=now, label=f"Sweep point {point['index']}", signal_id=signal_id))
        if request.output_kind == "weights" and validation is None:
            warnings.append("No out-of-sample validation is attached; the run's own figures are in-sample.")
        label = (request.label or "").strip() or f"{script_title} · run {run_id[:8]}"
        signal = IdeaSignal(
            signal_id=signal_id,
            idea_id=idea.idea_id,
            attached_at=now,
            source="script",
            output_kind=request.output_kind,
            label=label,
            source_ref=source_ref,
            as_of=as_of,
            legs=legs,
            supplied=supplied,
            validation=validation,
            warnings=tuple(warnings),
            provenance=ProvenanceRecord(
                source_provider="gamma_script_analytics",
                retrieved_at=run.completed_at or now,
                origin=f"{SIGNAL_ORIGIN}.script",
                transformation_note=(
                    "Read from the run's retained, validated gamma_analytics.json; the latest weight row on or before the attach day is frozen. "
                    "Gamma did not run the script."
                    if request.output_kind == "weights"
                    else "Read from the run's retained, validated gamma_analytics.json as a supplied return stream; it does not drive tracking."
                ),
            ),
        )
        return signal, trials

    def _script_mapping(self, request: SignalRequest, instruments: Mapping[str, Any], key: str) -> InstrumentMapping:
        if key in request.instruments:
            return request.instruments[key]
        item = instruments.get(key)
        if item is None:
            raise IdeaValidationError(f"Instrument {key} is not declared in the run's analytical file.")
        namespace = str(item.namespace).strip().lower()
        if namespace in TICKER_NAMESPACES:
            return InstrumentMapping(symbol=item.native_id, entity_type="equity", label=item.label)
        if namespace in CRYPTO_NAMESPACES:
            return InstrumentMapping(symbol=item.native_id, entity_type="crypto", label=item.label)
        raise IdeaValidationError(
            f"Instrument {key} ({item.namespace}:{item.native_id}) needs a ticker or a CoinGecko id; map it in the signal form."
        )

    def _script_trials(self, script_id: str, *, now: datetime, signal_id: str) -> list[IdeaTrial]:
        """Every completed run of the script so far counts, attached or not (decision 3)."""
        trials: list[IdeaTrial] = []
        try:
            runs = self.script_service.list_runs(script_id)
        except Exception as exc:  # noqa: BLE001
            raise IdeaSourceUnavailableError(f"Could not list the script's runs: {exc}") from exc
        for run in runs:
            if run.status != "completed":
                continue
            if run.sweep_id and run.sweep_point_index is not None:
                key = f"sweep:{run.sweep_id}:{run.sweep_point_index}"
                kind = "sweep_point"
                label = f"Sweep point {run.sweep_point_index} (run {run.run_id[:8]})"
            else:
                key = f"run:{run.run_id}"
                kind = "script_run"
                params = (run.parameters_sha256 or "")[:10]
                label = f"Script run {run.run_id[:8]}" + (f" · parameters {params}" if params else "")
            trials.append(IdeaTrial(key=key, kind=kind, recorded_at=now, label=label, signal_id=signal_id))
        # Más antiguas primero: el libro se lee en el orden en que se probó.
        return list(reversed(trials))

    def _validation_snapshot(self, wf: Mapping[str, Any], *, now: datetime) -> IdeaValidationSnapshot:
        config = wf["config"]
        evaluation = wf["evaluation"]
        oos = wf["out_of_sample"]
        rows = [(row["date"], float(row["value"])) for row in oos.get("rows") or []]
        curve = _cumulative(rows)
        reference = wf.get("in_sample_reference") or {}
        common = wf.get("common_window") or {}
        folds = tuple(
            IdeaValidationFold(
                fold=int(item["fold"]),
                train_start=_iso_day(item["train_start"]),
                train_end=_iso_day(item["train_end"]),
                test_start=_iso_day(item["test_start"]),
                test_end=_iso_day(item["test_end"]),
                test_observations=int(item["test_observations"]),
                selected_point=int(item["selected_point"]),
                test_return=_finite(item.get("test_return")),
                partial=item.get("partial") is True,
            )
            for item in wf["folds"]
        )
        return IdeaValidationSnapshot(
            snapshot_id=uuid4().hex,
            created_at=now,
            sweep_id=wf["sweep_id"],
            definition_sha256=wf["definition_sha256"],
            report_sha256=wf["report_sha256"],
            target=evaluation["target"],
            result_id=evaluation.get("result_id"),
            execution_lag=evaluation.get("execution_lag"),
            cost_bps=evaluation.get("cost_bps"),
            trials=int(wf["trials"]),
            train_observations=int(config["train_observations"]),
            test_observations=int(config["test_observations"]),
            window=config["window"],
            selection_metric=config["selection_metric"],
            window_start=_iso_day(common["start"]) if common.get("start") else None,
            window_end=_iso_day(common["end"]) if common.get("end") else None,
            observations=int(common.get("observations") or 0),
            folds=folds,
            out_of_sample={
                "total_return": oos.get("total_return"),
                "annual_return": oos.get("annual_return"),
                "annual_volatility": oos.get("annual_volatility"),
                "sharpe_ratio": oos.get("sharpe_ratio"),
                "max_drawdown": oos.get("max_drawdown"),
                "observations": oos.get("observations"),
                "selection_metric_value": oos.get("selection_metric_value"),
            },
            oos_start=_iso_day(oos["start"]) if oos.get("start") else None,
            oos_end=_iso_day(oos["end"]) if oos.get("end") else None,
            oos_curve=tuple(curve),
            in_sample_value=_finite(reference.get("value")),
            in_sample_point=reference.get("point_index"),
            in_sample_label=str(reference.get("label") or ""),
            distinct_selections=len(wf.get("selection_frequency") or {}),
            causality_verified=(wf.get("causality") or {}).get("verified") is True,
            warnings=tuple(wf.get("warnings") or ()),
            provenance=ProvenanceRecord(
                source_provider="gamma_script_analytics",
                retrieved_at=now,
                origin=str(wf.get("origin") or "script_experiments.walk_forward"),
                transformation_note=str(wf.get("transformation_note") or ""),
            ),
        )

    def _default_turnover_bp(self, idea: Idea, legs: Sequence[IdeaSignalLeg]) -> float:
        """The highest per-side cost among the book's legs: a walk-forward is never costless by default."""
        tracking = idea.tracking
        model = tracking.cost_model if tracking is not None else None
        if model is None:
            from src.models.ideas import IdeaCostModel

            model = IdeaCostModel()
        costs = []
        for leg in legs:
            tracked = IdeaTrackedLeg(
                entity=leg.entity,
                weight=None,
                asset_class=default_tracking_asset_class(leg.entity),
                market=tracking_market(leg.entity),
            )
            value = model.bp_for_leg(tracked)
            if value is not None:
                costs.append(value)
        return max(costs) if costs else 5.0

    # -- import -----------------------------------------------------------------

    def _from_import(self, idea: Idea, request: SignalRequest) -> tuple[IdeaSignal, list[IdeaTrial]]:
        from src.application.research_service import ResearchService
        from src.application.research_validation import ResearchValidationError

        rows = [dict(row) for row in request.rows if isinstance(row, Mapping)]
        if not rows:
            raise IdeaValidationError("Paste the CSV rows to import.")
        if len(rows) > IMPORT_ROWS_MAX:
            raise IdeaValidationError(f"An import holds at most {IMPORT_ROWS_MAX} rows.")
        date_column = str(request.date_column or "").strip()
        if not date_column:
            raise IdeaValidationError("Name the date column.")
        now = self._clock()
        warnings: list[str] = []
        legs: tuple[IdeaSignalLeg, ...] = ()
        supplied: IdeaSuppliedSeries | None = None
        as_of: date | None = None
        try:
            if request.output_kind in SIGNAL_BOOK_KINDS:
                columns = [str(item).strip() for item in request.columns if str(item or "").strip()]
                if not columns:
                    columns = [str(key) for key in rows[0].keys() if str(key) != date_column]
                if not columns:
                    raise IdeaValidationError("The CSV needs one column per instrument besides the date.")
                if len(columns) > IMPORT_COLUMNS_MAX:
                    raise IdeaValidationError(f"An import holds at most {IMPORT_COLUMNS_MAX} instrument columns.")
                dated: dict[str, list[tuple[date, float | None]]] = {}
                for column in columns:
                    series = ResearchService.imported_column_values(
                        rows, date_column=date_column, value_column=column, label=column, warnings=warnings
                    )
                    dated[column] = [(_iso_day(index), float(value)) for index, value in series.items()]
                as_of, values = self._latest_book(
                    dated, now.date(), what="CSV", require_last_row=True,
                    limit=SIGNAL_GROSS_MAX if request.output_kind == "weights" else None,
                )
                if request.output_kind == "weights":
                    legs = tuple(
                        IdeaSignalLeg(
                            entity=_entity(request.instruments.get(column) or InstrumentMapping(symbol=column), source_label=column),
                            weight=value,
                            instrument_id=column,
                        )
                        for column, value in values.items()
                    )
                    gross = sum(abs(leg.weight) for leg in legs)
                    if gross > 1.0 + 1e-9:
                        warnings.append(f"The latest row holds {gross:.2f}× NAV of gross exposure (leveraged).")
                else:
                    legs = self._positions_book(values, request, as_of=as_of, now=now, warnings=warnings)
                content_columns = columns
            else:
                value_column = str(request.value_column or "").strip()
                if not value_column:
                    raise IdeaValidationError("Name the returns column.")
                if self.research_service is None:
                    raise IdeaSourceUnavailableError("Strategy Lab analytics are not running in this build.")
                last = ResearchService.imported_column_values(
                    rows, date_column=date_column, value_column=value_column, label=value_column, warnings=[]
                )
                if len(last) and _iso_day(last.index[-1]) > now.date():
                    raise IdeaValidationError(f"The CSV runs to {_iso_day(last.index[-1]).isoformat()}, after today; a signal cannot hold future rows.")
                from src.models.research_lab import ImportedReturnStreamRequest

                analysis = self.research_service.analyze_strategy_lab(
                    ImportedReturnStreamRequest(
                        rows=rows, date_column=date_column, value_column=value_column,
                        value_kind=request.value_kind if request.value_kind in {"return", "level"} else "return",  # type: ignore[arg-type]
                        name=request.label or "Imported returns",
                    )
                )
                warnings.extend(item for item in analysis.warnings if "Gamma does not execute strategy code" not in item)
                points = [(_iso_day(index).isoformat(), float(value)) for index, value in analysis.returns.items()]
                supplied = self._supplied_from_analysis(analysis, points)
                as_of = _iso_day(analysis.returns.index[-1]) if len(analysis.returns) else None
                content_columns = [value_column]
        except ResearchValidationError as exc:
            raise IdeaValidationError("; ".join(exc.errors)) from exc
        used = [date_column, *content_columns]
        content_sha = _content_sha256(
            {"output_kind": request.output_kind, "value_kind": request.value_kind, "columns": used,
             "rows": [{key: row.get(key) for key in used} for row in rows]}
        )
        signal_id = uuid4().hex
        kind_label = {"positions": "positions", "weights": "weights", "returns": "returns"}[request.output_kind]
        label = (request.label or "").strip() or f"Imported {kind_label} · {content_sha[:8]}"
        trials = [IdeaTrial(key=f"import:{content_sha[:16]}", kind="import", recorded_at=now, label=label, signal_id=signal_id)]
        warnings.append("No out-of-sample validation: an import carries no walk-forward split.")
        signal = IdeaSignal(
            signal_id=signal_id,
            idea_id=idea.idea_id,
            attached_at=now,
            source="import",
            output_kind=request.output_kind,
            label=label,
            source_ref={
                "content_sha256": content_sha,
                "rows": len(rows),
                "date_column": date_column,
                "columns": content_columns,
                "value_kind": request.value_kind if request.output_kind == "returns" else None,
            },
            as_of=as_of,
            legs=legs,
            supplied=supplied,
            warnings=tuple(dict.fromkeys(warnings)),
            provenance=ProvenanceRecord(
                source_provider="uploaded_csv",
                retrieved_at=now,
                origin=f"{SIGNAL_ORIGIN}.import",
                transformation_note=(
                    "CSV rows read with the Strategy Lab import rules (invalid rows dropped with a warning, duplicate dates keep the last row); "
                    + ("the latest row on or before the attach day is frozen." if request.output_kind in SIGNAL_BOOK_KINDS
                       else "a supplied return stream; it does not drive tracking.")
                ),
            ),
        )
        return signal, trials

    def _positions_book(
        self, units: Mapping[str, float], request: SignalRequest, *, as_of: date, now: datetime, warnings: list[str]
    ) -> tuple[IdeaSignalLeg, ...]:
        """Value signed units at each instrument's latest final close on or before today; hold them as gross shares."""
        if self.prices is None:
            raise IdeaSourceUnavailableError("Provider closes are not available to value the positions.")
        from src.application.idea_tracking import market_horizon

        priced: list[tuple[str, HandoffEntity, float, float, date]] = []
        for column, quantity in units.items():
            entity = _entity(request.instruments.get(column) or InstrumentMapping(symbol=column), source_label=column)
            leg = IdeaTrackedLeg(entity=entity, weight=None, asset_class=default_tracking_asset_class(entity), market=tracking_market(entity))
            closes = self.prices.leg_closes(leg, since=as_of - timedelta(days=POSITION_PRICE_LOOKBACK_DAYS), now=now)
            if closes.unavailable_reason or not closes.closes:
                raise IdeaValidationError(f"{column}: no provider close to value the position ({closes.unavailable_reason or 'no closes'}).")
            horizon = market_horizon(leg.market, now)
            usable = [close for close in closes.closes if close.session <= horizon]
            if not usable:
                raise IdeaValidationError(f"{column}: no final provider close yet to value the position.")
            latest = usable[-1]
            priced.append((column, entity, quantity, latest.price, latest.session))
            warnings.extend(closes.warnings)
        gross = sum(abs(quantity * price) for _, _, quantity, price, _ in priced)
        if gross <= 0:
            raise IdeaValidationError("The latest row holds no position.")
        return tuple(
            IdeaSignalLeg(
                entity=entity,
                weight=quantity * price / gross,
                instrument_id=column,
                units=quantity,
                price=price,
                price_date=session,
            )
            for column, entity, quantity, price, session in priced
        )

    # -- shared -----------------------------------------------------------------

    @staticmethod
    def _latest_book(
        dated: Mapping[str, Sequence[tuple[date, float | None]]],
        today: date,
        *,
        what: str,
        require_last_row: bool = False,
        limit: float | None = SIGNAL_GROSS_MAX,
    ) -> tuple[date, dict[str, float]]:
        """The book on the schedule's last date: each instrument's latest value, zero weights dropped.

        A row dated after ``today`` is refused (decision 1): Gamma freezes the
        latest known book and never follows a schedule into the future.
        """
        future = sorted({day for rows in dated.values() for day, _ in rows if day > today})
        if future:
            raise IdeaValidationError(
                f"The {what} has rows after today ({future[0].isoformat()}); Gamma freezes the latest book on or before the attach day and never follows a schedule into the future."
            )
        latest_dates = {key: max((day for day, value in rows if value is not None), default=None) for key, rows in dated.items()}
        known = [day for day in latest_dates.values() if day is not None]
        if not known:
            raise IdeaValidationError(f"The {what} has no dated values.")
        as_of = max(known)
        values: dict[str, float] = {}
        for key, rows in dated.items():
            if require_last_row and latest_dates[key] != as_of:
                raise IdeaValidationError(
                    f"{key} has no value on the latest row ({as_of.isoformat()}); give every instrument a value there (0 when it is out of the book)."
                )
            current = [value for day, value in rows if value is not None and day <= as_of]
            if not current:
                continue
            number = float(current[-1])
            # Los pesos son fracciones de NAV; las posiciones son unidades y no tienen este límite.
            if limit is not None and abs(number) > limit:
                raise IdeaValidationError(
                    f"{key}: {number:g} on {as_of.isoformat()} is more than {SIGNAL_GROSS_MAX:g}× NAV; weights are fractions (append % for percentages)."
                )
            if number != 0.0:
                values[key] = number
        if not values:
            raise IdeaValidationError(f"The {what}'s latest row ({as_of.isoformat()}) holds no exposure.")
        return as_of, values

    def _supplied(self, rows: Sequence[Mapping[str, Any]], *, label: str, warnings: list[str]) -> IdeaSuppliedSeries:
        """A Script return stream through the Strategy Lab analytics (the same path as its handoff)."""
        if self.research_service is None:
            raise IdeaSourceUnavailableError("Strategy Lab analytics are not running in this build.")
        from src.models.research_lab import ImportedReturnStreamRequest

        analysis = self.research_service.analyze_strategy_lab(
            ImportedReturnStreamRequest(rows=list(rows), date_column="date", value_column="value", value_kind="return", name=label)
        )
        warnings.extend(item for item in analysis.warnings if "Gamma does not execute strategy code" not in item)
        points = [(_iso_day(index).isoformat(), float(value)) for index, value in analysis.returns.items()]
        return self._supplied_from_analysis(analysis, points, label=label)

    @staticmethod
    def _supplied_from_analysis(analysis: Any, points: Sequence[tuple[str, float]], *, label: str = SUPPLIED_SERIES_LABEL) -> IdeaSuppliedSeries:
        metrics = analysis.metrics
        curve = _cumulative(points)
        return IdeaSuppliedSeries(
            label=label,
            window_start=date.fromisoformat(points[0][0]) if points else None,
            window_end=date.fromisoformat(points[-1][0]) if points else None,
            observations=len(points),
            metrics={
                "total_return": metrics.total_return,
                "annual_return": metrics.annual_return,
                "annual_volatility": metrics.annual_volatility,
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown": metrics.max_drawdown,
            },
            curve=tuple(curve),
            warnings=tuple(item for item in analysis.warnings if "Gamma does not execute strategy code" not in item),
        )


__all__ = [
    "IdeaSignalService",
    "InstrumentMapping",
    "SignalRequest",
    "ValidationRequest",
]
