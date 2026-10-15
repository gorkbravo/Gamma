"""Server-owned validation and deliberate, non-durable analytical materialization."""
from __future__ import annotations

import json
from dataclasses import replace

from pydantic import ValidationError

from src.models.script_analytics import AnalyticalPayload, FILENAME, MAX_BYTES, Returns
from src.models.research_lab import ImportedReturnStreamRequest
from src.application.research_script_service import ResearchScriptValidationError


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


def inspect_analytics(service, run_id: str) -> dict:
    """Always read retained bytes. Optional validation never rewrites execution status."""
    run = service.get_run(run_id)
    reports = []
    for output in run.outputs:
        if output.filename != FILENAME:
            continue
        report = {"output_id": output.output_id, "valid": False, "eligible": False,
                  "errors": [], "results": [], "provenance": {}, "warnings": list(run.warnings)}
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
                    or service.manifest_sha256(service._input_manifest_identity(snapshot)) != run.input_manifest_sha256):
                raise ValueError("Run/source/input association is invalid.")
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
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            report["errors"] = [f"{'.'.join(str(part) for part in error['loc']) or 'payload'}: {error['msg']}"[:600] for error in errors[:20]]
            if len(errors) > 20:
                report["errors"].append(f"{len(errors) - 20} more validation errors; inspect the retained file against the schema.")
        except (ValueError, RuntimeError) as exc:
            report["errors"] = [str(exc)[:3000]]
    return {"run_id": run.run_id, "execution_status": run.status,
            "executes_source": run.usage.get("executes_source") is True, "artifacts": reports}


def _unsupported(result):
    if not isinstance(result, Returns):
        if result.kind == "weights":
            return ("Dated signed NAV exposures are retained exactly. Composer gross-normalizes weights and Risk's research-book path requires an already computed return stream and per-leg histories. "
                    "A weight schedule alone supplies neither; no normalization, history acquisition, account selection or contract substitution is authorized by this output.")
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


def open_analytics(service, run_id: str, output_id: str, result_id: str, preview_sha256: str):
    report = inspect_analytics(service, run_id)
    artifact = next((a for a in report["artifacts"] if a["output_id"] == output_id), None)
    item = next((r for r in artifact["results"] if r["result"]["result_id"] == result_id), None) if artifact else None
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
    return analysis, {**artifact["provenance"], "result_id": result_id, "preview_sha256": preview_sha256,
                      "result": result, "instruments": artifact["instruments"], "mapping": mapping}
