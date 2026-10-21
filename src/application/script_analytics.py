"""Server-owned validation and deliberate, non-durable analytical materialization."""
from __future__ import annotations

import json
from dataclasses import replace

from pydantic import ValidationError

from src.analytics.script_weight_book import BOOK_ASSUMPTIONS, BookOptions, WeightBookError, compute_weight_book
from src.models.script_analytics import AnalyticalPayload, FILENAME, MAX_BYTES, Returns, Weights
from src.models.research_lab import ImportedReturnStreamRequest
from src.application.research_script_service import ResearchScriptValidationError
from src.application.script_parameters import canonical_parameters

WEIGHT_BOOK_ID = "weight_book"


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not permitted.")
        result[key] = value
    return result


def parse_payload(content: bytes) -> AnalyticalPayload:
    if len(content) > MAX_BYTES:
        raise ValueError(f"Optional analytical payload exceeds {MAX_BYTES} bytes.")
    def invalid_constant(value):
        raise ValueError(f"Nonfinite JSON number: {value}")
    raw = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=invalid_constant)
    return AnalyticalPayload.model_validate(raw)


def _parameters_valid(run) -> bool:
    if run.parameters_sha256 is None:
        return run.parameters is None
    try:
        return canonical_parameters(run.parameters or {})[2] == run.parameters_sha256
    except ValueError:
        return False


def inspect_analytics(service, run_id: str, book_options: BookOptions | None = None) -> dict:
    """Always read retained bytes. Optional validation never rewrites execution status."""
    run = service.get_run(run_id)
    options = (book_options or BookOptions()).validated()
    reports = []
    for output in run.outputs:
        if output.filename != FILENAME:
            continue
        report = {"output_id": output.output_id, "valid": False, "eligible": False,
                  "errors": [], "results": [], "provenance": {}, "warnings": list(run.warnings),
                  "weight_book": None}
        reports.append(report)
        try:
            if not output.content_sha256:
                raise ValueError("Retained artifact has no immutable content hash; legacy output is inspection-only.")
            if output.byte_size > MAX_BYTES:
                raise ValueError(f"Optional analytical payload exceeds {MAX_BYTES} bytes.")
            _, _, content = service.get_output_artifact(run_id, output.output_id)
            revision = service.store.load_revision(run.script_id, run.revision_id)
            snapshot = service.get_input_snapshot(run.input_snapshot_id)
            if (revision is None or revision.script_id != run.script_id
                    or revision.status in {"staged", "rejected"}
                    or service.source_sha256(revision.source) != run.source_sha256
                    or revision.source_sha256 != run.source_sha256
                    or snapshot.script_id != run.script_id
                    or snapshot.manifest_sha256 != run.input_manifest_sha256
                    or service.manifest_sha256(service._input_manifest_identity(snapshot)) != run.input_manifest_sha256
                    or not _parameters_valid(run)):
                raise ValueError("Run/source/input/parameter association is invalid.")
            payload = parse_payload(content)
            provenance = {
                "contract_version": payload.contract_version, "script_id": run.script_id,
                "run_id": run.run_id, "revision_id": run.revision_id, "source_sha256": run.source_sha256,
                "input_snapshot_id": run.input_snapshot_id, "input_manifest_sha256": run.input_manifest_sha256,
                "artifact_ref": output.artifact_ref, "output_id": output.output_id,
                "artifact_sha256": output.content_sha256, "runtime_kind": run.runtime_kind,
                "artifact_run_association_verified": output.run_association_verified,
                "runtime_provider": run.runtime_provider, "executes_source": run.usage.get("executes_source") is True,
                "source_provider": run.source_provider, "retrieved_at": output.created_at.isoformat(),
                "origin": "script_analytics.inspect_retained_artifact",
                "transformation_note": "Validated optional retained JSON; no data acquisition, filling or resampling.",
                "input_source_refs": snapshot.source_refs,
            }
            if run.parameters_sha256 or run.sweep_id:
                # Solo en ejecuciones E5: las vistas previas heredadas conservan su hash exacto.
                provenance.update(parameters=run.parameters, parameters_sha256=run.parameters_sha256,
                                  sweep_id=run.sweep_id, sweep_point_index=run.sweep_point_index)
            report.update(valid=True, provenance=provenance, instruments=[i.model_dump() for i in payload.instruments])
            executed = (run.status == "completed" and run.completed_at is not None
                        and run.usage.get("executes_source") is True
                        and run.usage.get("executed_code") is True
                        and output.run_association_verified is True
                        and run.runtime_kind != "mock_safe_preview")
            report["eligible"] = executed
            if not executed:
                report["warnings"].append("Analytical handoff unavailable: requires completed, association-valid Python execution and an artifact verified as newly produced in this run's workspace. Safe previews are not calculations.")
            for result in payload.results:
                reason = _unsupported(result)
                if reason is None and service.research_service is None:
                    reason = "Strategy Lab owning service is unavailable. The standalone result remains retained."
                mapping = None
                if reason is None:
                    mapping = {
                        "target": "strategy_lab_returns", "date_column": "date", "value_column": "value",
                        "value_kind": "return", "frequency": "daily", "periods_per_year": 252, "return_type": "simple",
                        "conversion": "percent / 100" if result.unit == "percent" else "identity (fraction)",
                        "rows": [{"date": p.date, "value": p.value / 100 if result.unit == "percent" else p.value}
                                 for p in result.observations],
                        "assumptions": ["Existing owning-service daily frequency inference, 252 periods/year annualization; zero risk-free rate.",
                                        "No benchmark, costs, filling, resampling or signal-to-position conversion."],
                    }
                result_data = result.model_dump()
                binding = {"provenance": provenance, "result": result_data, "mapping": mapping}
                preview_hash = service.manifest_sha256(binding)
                report["results"].append({"result": result_data, "mapping": mapping,
                                          "preview_sha256": preview_hash,
                                          "can_open": executed and reason is None,
                                          "unsupported_reason": reason})
            report["weight_book"] = _weight_book(service, payload, provenance, options, executed)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            report["errors"] = [f"{'.'.join(str(part) for part in error['loc']) or 'payload'}: {error['msg']}"[:600] for error in errors[:20]]
            if len(errors) > 20:
                report["errors"].append(f"{len(errors) - 20} more validation errors; inspect the retained file against the schema.")
        except (ValueError, RuntimeError) as exc:
            report["errors"] = [str(exc)[:3000]]
    return {"run_id": run.run_id, "execution_status": run.status,
            "executes_source": run.usage.get("executes_source") is True, "artifacts": reports}


def _weight_book(service, payload, provenance, options: BookOptions, executed: bool) -> dict | None:
    """Libro causal de pesos: todos los calendarios ``weights`` del fichero más los ``returns`` de cada instrumento."""
    schedules = [r for r in payload.results if isinstance(r, Weights)]
    if not schedules:
        return None
    book = {"book_id": WEIGHT_BOOK_ID, "options": options.as_dict(),
            "weight_result_ids": [r.result_id for r in schedules], "return_result_ids": [],
            "instruments": sorted({r.instrument_id for r in schedules}), "mapping": None,
            "can_open": False, "unsupported_reason": None}
    reason = None
    by_instrument: dict[str, list] = {}
    for result in payload.results:
        if isinstance(result, Returns):
            by_instrument.setdefault(result.instrument_id, []).append(result)
    if len({r.instrument_id for r in schedules}) != len(schedules):
        reason = "Several weight schedules reference the same instrument; one book needs exactly one schedule per instrument."
    returns = {}
    for instrument in book["instruments"]:
        if reason:
            break
        candidates = by_instrument.get(instrument, [])
        if len(candidates) > 1:
            reason = f"Several returns results reference {instrument}; the book cannot choose one."
            break
        if not candidates:
            continue  # compute_weight_book informa del instrumento sin rendimientos
        series = candidates[0]
        if series.return_type != "simple" or series.frequency != "daily" or series.periods_per_year != 252:
            reason = f"Returns for {instrument} must be daily simple returns declaring 252 periods/year."
            break
        book["return_result_ids"].append(series.result_id)
        scale = 100 if series.unit == "percent" else 1
        returns[instrument] = [(p.date, None if p.value is None else p.value / scale) for p in series.observations]
    details = None
    if reason is None:
        try:
            computed = compute_weight_book({r.instrument_id: [(p.date, p.value) for p in r.observations] for r in schedules},
                                           returns, options)
            reason = _daily_target_reason(computed.rows)
            details = computed
        except WeightBookError as exc:
            reason = str(exc)
    if reason is None and service.research_service is None:
        reason = "Strategy Lab owning service is unavailable. The standalone schedules remain retained."
    if details is not None:
        book["mapping"] = {
            "target": "strategy_lab_returns", "date_column": "date", "value_column": "value",
            "value_kind": "return", "frequency": "daily", "periods_per_year": 252, "return_type": "simple",
            "conversion": "Gamma-computed causal book returns from exact signed NAV weights and per-instrument simple returns",
            "rows": details.rows,
            "assumptions": [*BOOK_ASSUMPTIONS, f"Execution lag: {options.execution_lag} period(s); costs: {options.cost_bps:g} bps per unit of turnover."],
            "details": {
                "calendar_start": details.calendar_start, "calendar_end": details.calendar_end,
                "trimmed_observations": details.trimmed_observations, "rebalances": details.rebalances,
                "superseded_decisions": details.superseded_decisions, "ignored_decisions": details.ignored_decisions,
                "total_turnover": details.total_turnover, "total_cost_fraction": details.total_cost_fraction,
                "max_gross_exposure": details.max_gross_exposure, "warnings": details.warnings,
            },
        }
    book["unsupported_reason"] = reason
    book["can_open"] = executed and reason is None
    book["preview_sha256"] = service.manifest_sha256({"provenance": provenance, "book": {
        key: book[key] for key in ("book_id", "options", "weight_result_ids", "return_result_ids", "instruments", "mapping")}})
    return book


def _daily_target_reason(rows) -> str | None:
    if len(rows) < 5:
        return "Existing Strategy Lab analytics require at least five book return observations."
    from datetime import date
    gaps = [(date.fromisoformat(b["date"]) - date.fromisoformat(a["date"])).days for a, b in zip(rows, rows[1:])]
    if any(gap > 4 for gap in gaps):
        return "Book returns have gaps longer than four days; annualization is ambiguous. Retained unchanged."
    import pandas as pd
    from src.analytics.research_returns import infer_return_frequency
    if infer_return_frequency(pd.to_datetime([row["date"] for row in rows])).label != "daily":
        return "Book returns are not inferred as daily by the owning service; retained unchanged."
    return None


def _unsupported(result):
    if not isinstance(result, Returns):
        if result.kind == "weights":
            return ("Dated signed NAV exposures are retained exactly. They open only through the causal weight book, which needs each weighted instrument's daily simple returns in this same file. "
                    "Composer gross normalization and Risk's static research-book legs are not used; no history acquisition, account selection or contract substitution is authorized.")
        return "Standalone result: metrics and signals have no owning-service mapping; signals do not imply positions or performance."
    if result.return_type != "simple":
        return "Log returns are retained; this target accepts simple returns only. No implicit exponentiation."
    if result.frequency != "daily":
        return "This mapping supports daily returns only; owning-service frequency inference cannot guarantee the declared non-daily convention."
    if result.periods_per_year != 252:
        return "This target annualizes daily observations at 252 periods/year. Other calendars remain standalone; no implicit calendar substitution."
    if any(p.value is None for p in result.observations):
        return "Missing observations are preserved. This target cleans missing rows; opening would change coverage."
    if len(result.observations) < 5:
        return "Existing Strategy Lab analytics require at least five return observations."
    from datetime import date
    gaps = [(date.fromisoformat(b.date) - date.fromisoformat(a.date)).days
            for a, b in zip(result.observations, result.observations[1:])]
    if any(gap > 4 for gap in gaps):
        return "Daily coverage has gaps longer than four days; annualization is ambiguous. Retained unchanged."
    import pandas as pd
    from src.analytics.research_returns import infer_return_frequency
    if infer_return_frequency(pd.to_datetime([p.date for p in result.observations])).label != "daily":
        return "Declared daily frequency conflicts with owning-service frequency inference; retained unchanged."
    return None


def open_analytics(service, run_id: str, output_id: str, result_id: str, preview_sha256: str, *,
                   target: str = "result", book_options: BookOptions | None = None):
    try:
        report = inspect_analytics(service, run_id, book_options)
    except WeightBookError as exc:
        raise ResearchScriptValidationError([str(exc)]) from exc
    artifact = next((a for a in report["artifacts"] if a["output_id"] == output_id), None)
    if target == "weight_book":
        book = artifact.get("weight_book") if artifact else None
        item = None if book is None or result_id != WEIGHT_BOOK_ID else {
            **book, "result": {"result_id": WEIGHT_BOOK_ID, "name": "Causal weight book", "limitations": [],
                               "assumptions": [], "weight_result_ids": book["weight_result_ids"],
                               "return_result_ids": book["return_result_ids"], "instruments": book["instruments"]}}
    elif target == "result":
        item = next((r for r in artifact["results"] if r["result"]["result_id"] == result_id), None) if artifact else None
    else:
        raise ResearchScriptValidationError(["Unknown analytical handoff target."])
    if not item or not item["can_open"] or item["preview_sha256"] != preview_sha256:
        raise ResearchScriptValidationError(["Analytical handoff is unavailable or its exact preview binding changed. Inspect the retained run again."])
    if service.research_service is None:
        raise ResearchScriptValidationError(["Strategy Lab owning service is unavailable; standalone results remain retained."])
    result = item["result"]
    mapping = item["mapping"]
    try:
        analysis = service.research_service.analyze_strategy_lab(ImportedReturnStreamRequest(
            rows=mapping["rows"], date_column="date", value_column="value", value_kind="return", name=result["name"],
        ))
    except (ValueError, OverflowError) as exc:
        raise ResearchScriptValidationError([f"Owning analytics cannot represent this result: {exc}"]) from exc
    if analysis.metrics.frequency != "daily":
        raise ResearchScriptValidationError(["Owning service did not infer daily frequency; no analytical handoff was opened."])
    analysis = replace(analysis, warnings=list(dict.fromkeys([
        *analysis.warnings, *artifact["warnings"], *result["limitations"], *result["assumptions"], *mapping["assumptions"],
        "Temporary Script-derived analysis. Saving requires a separate explicit action.",
    ])), source_provider="gamma_script_analytics", origin="script_analytics.open_strategy_lab",
        retrieved_at=service.get_run(run_id).completed_at,
        transformation_note=f"{mapping['conversion']}; exact validated daily simple returns passed to existing Strategy Lab analytics.")
    evidence = {**artifact["provenance"], "result_id": result_id, "preview_sha256": preview_sha256,
                "result": result, "instruments": artifact["instruments"], "mapping": mapping}
    if target == "weight_book":
        evidence.update(target="weight_book", book_options=item["options"])
    return analysis, evidence
