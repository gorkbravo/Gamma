"""Operator adapters for the shared Script catalog and immutable bundles.

No provider export implementation lives here. References are inspected once,
then appended through the same retained-preview path used by Script's picker.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from difflib import unified_diff
import json
import re

from src.models.copilot import CopilotResearchActionDefinition, CopilotToolExecution, CopilotToolTrace, CopilotSourceRef
from src.models.research_script import ResearchScriptDataExportRequest
from src.application.script_dataset_catalog import DATASETS, DatasetSelectionError
from src.application.research_script_service import ResearchScriptServiceError


# Verbos que por sí solos piden datos externos.
_ACQUIRE_VERBS = r"(?:acquir(?:e|es|ed|ing)|fetch(?:es|ed|ing)?|download(?:s|ed|ing)?)"
# Verbos genéricos: también se usan para editar código ("add a column"), así que
# solo autorizan cuando se refieren a datos.
_COLLECT_VERBS = (
    r"(?:add(?:s|ed|ing)?|combin(?:e|es|ed|ing)|load(?:s|ed|ing)?|includ(?:e|es|ed|ing)|"
    r"retriev(?:e|es|ed|ing)|pull(?:s|ed|ing)?|import(?:s|ed|ing)?|bring(?:s|ing)?\s+in)"
)
_DATA_NOUNS = (
    r"(?:data(?:sets?)?|histor(?:y|ies)|prices?|series|inputs?|quotes?|observations?|curves?|"
    r"captures?|fundamentals|statements?|closes?|bars|spreads?|inventor(?:y|ies)|outcomes?)"
)
_CODE_NOUNS = (
    r"(?:columns?|fields?|features?|indicators?|charts?|plots?|warnings?|comments?|tests?|"
    r"functions?|parameters?|labels?|lines?|steps?|checks?|logs?|prints?)"
)
_NEGATIONS = r"(?:do\s+not|don't|dont|without|never|no\s+need\s+to|avoid|not)"


def script_acquisition_authorized(prompt):
    text = " ".join(str(prompt or "").lower().split())
    # Una negación próxima a cualquier verbo de adquisición, o "no new data", la anula.
    if re.search(rf"\b{_NEGATIONS}\b[^.!?;]{{0,40}}\b(?:{_ACQUIRE_VERBS}|{_COLLECT_VERBS})\b", text):
        return False
    if re.search(rf"\b(?:no|without)\s+(?:any\s+)?(?:new\s+|more\s+|additional\s+|external\s+)?{_DATA_NOUNS}\b", text):
        return False
    if re.search(rf"\b{_ACQUIRE_VERBS}\b", text):
        return True
    for match in re.finditer(rf"\b{_COLLECT_VERBS}\b([^.!?;]{{0,60}})", text):
        span = match.group(1)
        # "add a returns column" edita código; ante la duda no se autoriza.
        if re.search(rf"\b{_DATA_NOUNS}\b", span) and not re.search(rf"\b{_CODE_NOUNS}\b", span):
            return True
    return False


def script_visible_to_request(script, request):
    # El Operator solo actúa sobre el Script adjunto de forma visible a esta petición
    # o sobre uno creado por esta misma sesión de Copilot. Strategy Lab crea los
    # Scripts con su propia sesión de workspace, distinta del id del chat.
    context = getattr(request, "context", None)
    state = getattr(context, "strategy_lab_state", None)
    visible = state.get("script_state") if isinstance(state, dict) else None
    if isinstance(visible, dict) and str(visible.get("script_id") or "").strip() == script.script_id:
        return True
    session_id = str(getattr(request, "user_session_id", None) or "").strip()
    return bool(session_id) and script.session_id == session_id


# Margen bajo el límite de 50 KB del proveedor (MAX_OPERATOR_OBSERVATION_BYTES): por encima,
# el proveedor sustituye los niveles profundos (nombres de fichero, esquemas) por marcadores.
MAX_SCRIPT_OBSERVATION_BYTES = 40_000
SCRIPT_OBSERVATION_BOUNDED_NOTE = (
    "Gamma shortened samples, text, rows or diff so filenames, schemas, hashes and identities stay visible; "
    "the complete content remains retained."
)


def _observation_size(value):
    # Mismo renderizado que el proveedor (ensure_ascii) para medir bytes reales.
    return len(json.dumps(value, ensure_ascii=True, default=str).encode("utf-8"))


def fit_script_observation(output):
    """Ajusta una observación de Script al presupuesto recortando contenido, nunca identidades."""
    if not isinstance(output, dict) or _observation_size(output) <= MAX_SCRIPT_OBSERVATION_BYTES:
        return output
    output = copy.deepcopy(output)
    limit = 6_000
    while _observation_size(output) > MAX_SCRIPT_OBSERVATION_BYTES and limit >= 200:
        max_rows = max(1, limit // 600)
        for item in output.get("files") or []:
            if isinstance(item.get("sample"), str) and len(item["sample"]) > limit:
                item["sample"], item["sample_truncated"] = item["sample"][:limit], True
        for item in output.get("outputs") or []:
            if isinstance(item.get("text"), str) and len(item["text"]) > limit:
                item["text"], item["content_truncated"] = item["text"][:limit], True
            if isinstance(item.get("rows"), list) and len(item["rows"]) > max_rows:
                item["rows"], item["content_truncated"] = item["rows"][:max_rows], True
        for artifact in (output.get("analytical_results") or {}).get("artifacts") or []:
            for result in artifact.get("results") or []:
                observations = (result.get("result") or {}).get("observations")
                if isinstance(observations, list) and len(observations) > max_rows:
                    result["result"]["observations"], result["observations_truncated"] = observations[:max_rows], True
        if isinstance(output.get("source_diff"), str) and len(output["source_diff"]) > 2 * limit:
            output["source_diff"], output["source_diff_truncated"] = output["source_diff"][:2 * limit], True
        limit //= 2
    output["bounded_for_operator"] = SCRIPT_OBSERVATION_BOUNDED_NOTE
    return output


def strict(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def script_action_definitions():
    text = {"type": "string"}
    nullable = {"type": ["string", "null"]}
    selection = {
        "script_id": text, "domain": {"type": "string", "enum": list(DATASETS)},
        "object_id": text, "logical_filename": text, "region": nullable,
        "timeframe": nullable, "outcome_id": nullable,
        "lookback_days": {"type": ["integer", "null"], "minimum": 20, "maximum": 3650},
        "frequency": {"type": ["string", "null"], "enum": [None, "daily", "weekly", "monthly"]},
    }
    specs = [
        ("discover", {"domain": {"type": "string", "enum": list(DATASETS)}, "query": {"type": "string", "maxLength": 128}},
         "Discover exact supported objects through Script's shared catalog. Ambiguous matches require user clarification; never choose a nearby identity.", 3),
        ("inspect", selection,
         "Acquire and inspect one exact dataset's schema, units, source, warnings and coverage. Requires explicit acquisition permission. Returns a temporary preview, not executable input. Use the attached script_state.script_id; draft an empty-input Script first only when no Script is attached.", 3),
        ("add_input", {**selection, "preview_id": text, "base_snapshot_id": nullable},
         "Append previously inspected copied bytes to an immutable bundle. Always pass the current bundle as base to preserve its earlier files. No refetch, filename substitution or external-file invention.", 3),
        ("read_inputs", {"script_id": text, "input_snapshot_id": text},
         "Read a retained immutable bundle, exact filenames, schemas and bounded file samples, including user-supplied external files. Does not fetch data or execute code.", 2),
        ("draft_from_bundle", {"script_id": text, "input_snapshot_id": text, "expected_parent_sha256": text,
                               "python_source": text, "change_summary": {"type": "string", "minLength": 1, "maxLength": 512}},
         "Stage a Python candidate against actual retained filenames/schema. Explain methodology and input changes. Existing canonical code remains user controlled; user must accept before execution. Never accept a candidate yourself.", 1),
    ]
    return [CopilotResearchActionDefinition(
        tool_id=f"strategy_lab.script_{name}", domains=["strategy_lab"],
        action_type="draft_change" if name in {"add_input", "draft_from_bundle"} else "read_context",
        description=description, input_schema=strict(schema), output_schema={"type": "object"},
        read_only=name not in {"add_input", "draft_from_bundle"},
        permission_policy="automatic_draft" if name in {"add_input", "draft_from_bundle"} else "automatic",
        request_limit=limit, retry_policy="none", test_coverage_owner="tests/test_script_operator_e3.py",
        can_call_external_providers=name in {"discover", "inspect"},
        # discover también consulta proveedores (SEC, materias primas, cripto) y cuenta en el presupuesto.
        external_provider="script_catalog" if name in {"discover", "inspect"} else None,
    ) for name, schema, description, limit in specs]


def execute_script_action(copilot, tool_id, arguments, context, *, request, run_id):
    def blocked(message):
        return copilot._blocked_script_execution(tool_id, arguments, message)

    if request is None or request.role != "research_operator":
        return blocked("Script tools require visible Research Operator authorization.")
    prompt = request.prompt or ""
    if not copilot._prompt_requests_script_workflow(prompt, request.context):
        return blocked("The current request does not explicitly authorize a Script workflow; no Python fallback is allowed.")
    if copilot._prompt_requests_forbidden_script_authority(prompt):
        return blocked("Forbidden Script authority was refused.")
    operation = tool_id.removeprefix("strategy_lab.script_")
    if operation in {"inspect", "add_input"} and not script_acquisition_authorized(prompt):
        return blocked("The current request does not authorize data acquisition.")
    if operation == "draft_from_bundle" and not copilot._prompt_requests_script_draft(prompt):
        return blocked("The current request does not authorize code revision.")
    service = copilot.research_script_service
    if service is None:
        return blocked("Script service is unavailable.")
    try:
        if operation == "discover":
            output = service.dataset_catalog.search(arguments["domain"], arguments["query"])
        else:
            script_id = arguments["script_id"]
            detail = service.get_script(script_id)
            if not script_visible_to_request(detail.script, request):
                return blocked("Script is neither attached to this request nor owned by this Copilot session.")
            if operation in {"inspect", "add_input"}:
                selection = {k: v for k, v in arguments.items() if k != "script_id"}
                export = ResearchScriptDataExportRequest(**selection)
                if operation == "inspect":
                    output = {**service.dataset_catalog.preview(script_id, export), "status": "preview_only"}
                else:
                    # Never implicitly discard the latest bundle, including uploads.
                    bundles = service.list_input_bundles(script_id)
                    if bundles and export.base_snapshot_id != bundles[0].snapshot_id:
                        return blocked("Input bundle changed. Read the current bundle and explicitly append to it.")
                    snapshot = service.export_domain_input(script_id, export)
                    output = bundle_observation(service, snapshot)
            else:
                snapshot = service.get_input_snapshot(arguments["input_snapshot_id"])
                if snapshot.script_id != script_id:
                    return blocked("Input bundle belongs to another Script.")
                output = bundle_observation(service, snapshot)
                if operation == "read_inputs":
                    from src.models.script_analytics import AUTHORING_EXAMPLE, FILENAME, MAX_BYTES
                    output["optional_analytical_output"] = {
                        "filename": FILENAME, "contract_version": "gamma-script-analytics.v1", "max_bytes": MAX_BYTES,
                        "example_source": AUTHORING_EXAMPLE,
                        "authority": "Optional serialization only within existing Script scope. Do not modify code, acquire inputs, execute, open or save without the existing separate authorization. Ordinary logs/files remain valid outcomes.",
                    }
                if operation == "draft_from_bundle":
                    parent = next(r for r in detail.revisions if r.revision_id == detail.script.canonical_revision_id)
                    detail = service.stage_operator_revision(script_id, source=arguments["python_source"],
                        expected_parent_sha256=arguments["expected_parent_sha256"],
                        change_summary=arguments["change_summary"], operator_run_id=run_id, input_snapshot_id=snapshot.snapshot_id)
                    candidate = max((r for r in detail.revisions if r.status == "staged" and r.operator_run_id == run_id
                        and r.source_sha256 == service.source_sha256(arguments["python_source"])), key=lambda r: r.revision_number)
                    output.update({"status": "staged", "revision_id": candidate.revision_id,
                        "revision_status": candidate.status, "source_sha256": candidate.source_sha256,
                        "canonical_revision_id": detail.script.canonical_revision_id,
                        "change_summary": candidate.change_summary,
                        "source_diff": "".join(unified_diff(parent.source.splitlines(True), candidate.source.splitlines(True), fromfile="canonical.py", tofile="candidate.py"))[:16000],
                        "materialization": copilot._script_materialization_target(script_id=script_id,
                            revision_id=candidate.revision_id, input_snapshot_id=snapshot.snapshot_id, selected_run_id=None)})
        output = fit_script_observation(output)
        source_ids = list(output.get("sources") or [])
        sources = [CopilotSourceRef(source_id=identity, label="Retained Script input bundle", kind="input_manifest",
            provider="gamma", origin="gamma.strategy_lab.script.input_snapshot",
            description="Immutable retained input bytes; copied data is not executed source.",
            navigation_supported=True, navigation_tab="strategy_lab", navigation_mode="script",
            navigation_context={"script_id": output.get("script_id")}) for identity in source_ids]
        return CopilotToolExecution(output=output, sources=sources, trace=CopilotToolTrace(
            tool_name=tool_id, summary=f"Script {operation}: {output.get('status', 'retained')}; source was not executed.",
            arguments=arguments, source_ids=source_ids))
    except (ResearchScriptServiceError, DatasetSelectionError, ValueError, KeyError) as exc:
        # Only catalog-authored errors are safe; provider exception bodies may contain URLs/secrets.
        if isinstance(exc, (ResearchScriptServiceError, DatasetSelectionError)):
            return blocked(str(exc))
        return blocked("Script input operation unavailable or invalid. Existing bundles and source remain unchanged.")
    except Exception:
        return blocked("The owning provider is unavailable. No substitute data was acquired.")


def bundle_observation(service, snapshot):
    contents = service.store.load_input_contents(snapshot)  # hash verification
    return {"status": "retained", "script_id": snapshot.script_id,
        "input_snapshot_id": snapshot.snapshot_id, "manifest_sha256": snapshot.manifest_sha256,
        "files": [{**asdict(f), "sample": contents[f.logical_filename][:12000].decode("utf-8", errors="replace"),
                   "sample_truncated": len(contents[f.logical_filename]) > 12000} for f in snapshot.files],
        "dataset_refs": snapshot.dataset_refs, "warnings": snapshot.warnings,
        "sources": [f"research-script.input-snapshot.{snapshot.snapshot_id}"]}
