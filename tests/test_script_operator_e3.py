from dataclasses import replace
import json

import pytest

from test_script_dataset_catalog import setup
from test_research_script_operator import _runtime, _operator_request, _assert_strict_objects
from src.application.research_script_service import ResearchScriptConflictError, ResearchScriptValidationError
from src.models.research_script import ResearchScriptInputBundleRequest, ResearchScriptInputFileCreateRequest, ResearchScriptRevisionCreateRequest
from src.services.research_script_store import ResearchScriptStore


@pytest.fixture
def e3(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, monkeypatch)
    script_service, script_id, _ = setup(tmp_path / "catalog")  # every owner explicitly mocked
    runtime.copilot_service.research_script_service = script_service
    request = _operator_request("Fetch and combine datasets, draft a Python Script, but do not run it.", session_id="test")
    copilot = runtime.copilot_service
    context = copilot._build_strategy_lab_context(request)

    def call(operation, args, req=None):
        tool_id = "strategy_lab.script_" + operation
        validated = copilot.action_registry.validate_arguments(tool_id, args)
        return copilot._execute_registered_operator_action(tool_id, validated, context,
            request=req or request, run_id="e3-operator").output

    yield runtime, script_service, script_id, request, call
    runtime.shutdown()


def selection(script_id, domain="equity_history", object_id=None, filename="equity.json"):
    from src.application.script_dataset_catalog import ScriptDatasetCatalog
    identity = object_id or next(k for k, i in ScriptDatasetCatalog.equities().items() if i.symbol == "SPY")
    return dict(script_id=script_id, domain=domain, object_id=identity, logical_filename=filename,
        region=None, timeframe=None, outcome_id=None, lookback_days=30, frequency="daily")


def mixed_bundle(service, script_id, call):
    external = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest(input_files=[
        ResearchScriptInputFileCreateRequest("external.json", "application/json", b'{"scale":2}')]))
    eq = selection(script_id)
    preview = call("inspect", eq)
    assert preview["status"] == "preview_only"
    first = call("add_input", {**eq, "preview_id": preview["preview_id"], "base_snapshot_id": external.snapshot_id})
    commodity = selection(script_id, "commodity_history", "wti", "oil.json")
    preview2 = call("inspect", commodity)
    second = call("add_input", {**commodity, "preview_id": preview2["preview_id"], "base_snapshot_id": first["input_snapshot_id"]})
    assert len(second["files"]) == 3
    assert [{k:v for k,v in f.items() if k != "artifact_ref"} for f in second["files"][:2]] == [{k:v for k,v in f.items() if k != "artifact_ref"} for f in first["files"]]
    assert second["files"][0]["sample"] == '{"scale":2}'
    assert second["files"][1]["logical_filename"] == "equity.json"
    data = json.loads(second["files"][1]["sample"])
    assert data["metadata"]["object_id"] == eq["object_id"]
    assert any("close" in field["name"] for field in data["metadata"]["fields"])
    assert all("preview_id" not in ref for ref in second["dataset_refs"])
    return first, second


def test_mixed_inputs_revision_review_exact_execution_and_restart(e3):
    runtime, service, script_id, request, call = e3
    first, bundle = mixed_bundle(service, script_id, call)
    parent = service.get_script(script_id).revisions[0]
    # Ordinary calculation, no strategy entrypoint or typed analytical result.
    source = '''import json
with open("equity.json") as f: equity = json.load(f)["data"]
with open("oil.json") as f: oil = json.load(f)["data"]
with open("external.json") as f: scale = json.load(f)["scale"]
print("Equity observations:", len(equity["points"]), "oil observations:", len(oil["points"]), "scale:", scale)
'''
    arguments = dict(script_id=script_id, input_snapshot_id=bundle["input_snapshot_id"],
        expected_parent_sha256=parent.source_sha256, python_source=source,
        change_summary="Combine exact SPY and WTI observations with external scale; report counts without joining different units.")
    candidate = call("draft_from_bundle", arguments)
    assert candidate["status"] == "staged"
    assert "canonical.py" in candidate["source_diff"] and "equity.json" in candidate["source_diff"]
    assert service.get_script(script_id).script.canonical_revision_id == parent.revision_id
    exact = dict(script_id=script_id, revision_id=candidate["revision_id"],
        input_snapshot_id=bundle["input_snapshot_id"], source_sha256=candidate["source_sha256"], manifest_sha256=bundle["manifest_sha256"])
    with pytest.raises(ResearchScriptValidationError, match="Accept it first"):
        service.create_exact_run(**exact)
    # Rejection preserves user source. A fresh candidate can later be accepted.
    service.reject_staged_revision(script_id, candidate["revision_id"], expected_parent_sha256=parent.source_sha256)
    candidate = call("draft_from_bundle", arguments)
    service.accept_staged_revision(script_id, candidate["revision_id"], expected_parent_sha256=parent.source_sha256)
    exact["revision_id"] = candidate["revision_id"]
    # Restart retains the candidate's reviewed bundle binding.
    service.store = ResearchScriptStore(service.store.base_dir)
    with pytest.raises(ResearchScriptConflictError, match="different input bundle"):
        service.create_exact_run(**{**exact, "input_snapshot_id": first["input_snapshot_id"], "manifest_sha256": first["manifest_sha256"]})
    run_request = replace(request, prompt="Run this Python Script.")
    output = runtime.copilot_service._execute_registered_operator_action("strategy_lab.run_research_script", exact,
        runtime.copilot_service._build_strategy_lab_context(run_request), request=run_request).output
    assert output["status"] == "completed"
    assert output["execution_evidence"] == "mock_safe_preview"  # never proof of Python execution
    assert any(item["text"] or item["rows"] or item["metric_value"] is not None for item in output["outputs"])
    retained = service.get_run(output["run_id"])
    assert retained.input_snapshot_id == bundle["input_snapshot_id"]
    assert retained.source_sha256 == candidate["source_sha256"]


@pytest.mark.parametrize("operation", ["discover", "inspect", "add_input", "read_inputs", "draft_from_bundle"])
def test_agent_cannot_acquire_operator_authority(e3, operation):
    runtime, service, script_id, request, call = e3
    # Reauthorization is independent of model tool exposure and argument validation.
    result = runtime.copilot_service._execute_registered_operator_action("strategy_lab.script_" + operation, {},
        runtime.copilot_service._build_strategy_lab_context(request), request=replace(request, role="research_agent"))
    assert result.output["status"] == "rejected"
    assert service.list_input_bundles(script_id) == []


@pytest.mark.parametrize("invalid", [False, True])
def test_operator_observes_retained_validity_and_never_upgrades_preview_authority(e3, invalid):
    from test_script_analytics import FixtureRuntime, payload
    runtime, service, script_id, request, _ = e3
    owner = service.research_service
    service.runtime = FixtureRuntime(b"{" if invalid else json.dumps(payload()).encode(), executed=False)
    bundle = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest())
    revision = service.get_script(script_id).revisions[0]
    exact = dict(script_id=script_id, revision_id=revision.revision_id,
                 input_snapshot_id=bundle.snapshot_id, source_sha256=revision.source_sha256, manifest_sha256=bundle.manifest_sha256)
    req = replace(request, prompt="Run this Python Script.")
    observed = runtime.copilot_service._execute_registered_operator_action("strategy_lab.run_research_script", exact,
        runtime.copilot_service._build_strategy_lab_context(req), request=req).output
    assert observed["status"] == "completed"
    report = observed["analytical_results"]
    assert not report["executes_source"]
    artifact = report["artifacts"][0]
    assert artifact["valid"] is not invalid
    assert artifact["eligible"] is False
    if not invalid:
        assert artifact["provenance"]["source_sha256"] == revision.source_sha256
        assert artifact["results"][0]["result"]["observations"][0]["value"] == 1.0
        assert all(not item["can_open"] for item in artifact["results"])
    else:
        assert artifact["errors"]
    assert service.research_service is owner  # no additional analytics/saving authority


def test_scoped_permissions_expiry_unavailable_no_substitution_and_conflicts(e3):
    runtime, service, script_id, request, call = e3
    for definition in runtime.copilot_service.list_research_action_definitions():
        if definition.tool_id.startswith("strategy_lab.script_"):
            _assert_strict_objects(definition.input_schema)
    eq = selection(script_id)
    for prompt in ["Compute correlation using native analytics", "Draft a Python Script without fetching data.", "Run this Python Script."]:
        assert call("inspect", eq, replace(request, prompt=prompt))["error"]
    assert call("inspect", eq, replace(request, user_session_id="foreign"))["error"]
    assert call("inspect", {**eq, "object_id": "ambiguous S&P"})["error"]  # exact identity required
    preview = call("inspect", eq)
    service.dataset_catalog.TTL = -1
    assert "expired" in call("add_input", {**eq, "preview_id": preview["preview_id"], "base_snapshot_id": None})["error"]
    service.dataset_catalog.TTL = 600
    preview = call("inspect", eq)
    service.dataset_catalog.services["equity"] = None
    # Add uses the copied preview even after owner disappears.
    bundle = call("add_input", {**eq, "preview_id": preview["preview_id"], "base_snapshot_id": None})
    assert bundle["status"] == "retained"
    assert call("inspect", eq)["error"]
    assert len(service.list_input_bundles(script_id)) == 1
    parent = service.get_script(script_id).revisions[0]
    args = dict(script_id=script_id, input_snapshot_id=bundle["input_snapshot_id"],
        expected_parent_sha256=parent.source_sha256, python_source="print('candidate')", change_summary="Change count output")
    assert call("draft_from_bundle", args, replace(request, prompt="Run this Python Script."))["error"]
    candidate = call("draft_from_bundle", args)
    service.create_revision(script_id, ResearchScriptRevisionCreateRequest("print('user changed')", parent.source_sha256))
    with pytest.raises(ResearchScriptConflictError):
        service.accept_staged_revision(script_id, candidate["revision_id"], expected_parent_sha256=parent.source_sha256)
    assert call("draft_from_bundle", args)["error"]


def test_failed_run_cannot_rewrite_retry_or_fabricate_success(e3, monkeypatch):
    runtime, service, script_id, request, call = e3
    from src.models.copilot import CopilotResearchCardResult, ResearchCard
    from src.models.research_script import ResearchScriptRunCreateRequest
    from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
    bundle = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest())
    revision = service.get_script(script_id).revisions[0]
    failed = service.create_run(script_id, ResearchScriptRunCreateRequest(
        revision_id=revision.revision_id, input_snapshot_id=bundle.snapshot_id, runtime_scenario="failed"))
    monkeypatch.setattr(service, "create_exact_run", lambda *args, **kwargs: failed)

    class RewriteAfterFailure(OpenAIResponsesCopilotProvider):
        def stream_research_operator(self, *, execute_tool, **kwargs):
            exact = dict(script_id=script_id, revision_id=revision.revision_id,
                input_snapshot_id=bundle.snapshot_id, source_sha256=revision.source_sha256,
                manifest_sha256=bundle.manifest_sha256)
            run = execute_tool("strategy_lab.run_research_script", exact)
            assert run.output["status"] == "failed"
            candidate = execute_tool("strategy_lab.script_draft_from_bundle", dict(
                script_id=script_id, input_snapshot_id=bundle.snapshot_id,
                expected_parent_sha256=revision.source_sha256, python_source="print('unreviewed retry')",
                change_summary="Attempt to rewrite after failure"))
            assert candidate.output["stop_reason"] == "script_failure_requires_user"
            retry = execute_tool("strategy_lab.run_research_script", exact)
            assert retry.output["error"]
            return CopilotResearchCardResult(domain="strategy_lab", current_tab="copilot", status="ready",
                provider="test", model="test", card=ResearchCard(title="False success", hypothesis="Completed",
                    rationale="Fabricated result", required_data=[], proposed_test="None", confounders=[], next_steps=[], caveats=[]))

    runtime.copilot_service.provider = RewriteAfterFailure(api_key="test", model="gpt-test", reasoning_effort="low", store_responses=False)
    runtime.copilot_service.create_session(session_id="test")
    result = runtime.copilot_service.execute_research_operator_plan(replace(request,
        prompt="Build and run a Research Script.", context=replace(request.context,
            strategy_lab_state={"script_state": {"script_id": script_id, "source_sha256": revision.source_sha256}})))
    assert result.status == "incomplete" and result.card is None
    assert len(service.get_script(script_id).revisions) == 1
    assert len(service.list_runs(script_id)) == 1


def test_operator_reaches_visibly_attached_strategy_lab_script_but_not_unattached_foreign_ones(e3):
    # Regresión: Strategy Lab crea los Scripts con su sesión de workspace, distinta del id del chat de Copilot.
    from src.models.research_script import ResearchScriptCreateRequest
    runtime, service, _, request, call = e3
    ui_script = service.create_script(ResearchScriptCreateRequest("strategy-lab-script-workspace", "UI script", "print('ui')"))
    ui_id = ui_script.script.script_id
    revision = ui_script.revisions[0]
    attached = replace(request, user_session_id="copilot-chat-1", context=replace(request.context,
        strategy_lab_state={"script_state": {"script_id": ui_id, "source_sha256": revision.source_sha256}}))
    unattached = replace(attached, context=replace(request.context, strategy_lab_state=None))

    assert call("inspect", selection(ui_id), attached)["status"] == "preview_only"
    refused = call("inspect", selection(ui_id), unattached)
    assert "neither attached" in refused["error"]
    # Adjuntar otro Script no concede acceso a éste.
    other = replace(attached, context=replace(request.context, strategy_lab_state={"script_state": {"script_id": "other"}}))
    assert "neither attached" in call("inspect", selection(ui_id), other)["error"]

    bundle = service.create_input_bundle(ui_id, ResearchScriptInputBundleRequest())
    exact = dict(script_id=ui_id, revision_id=revision.revision_id, input_snapshot_id=bundle.snapshot_id,
        source_sha256=revision.source_sha256, manifest_sha256=bundle.manifest_sha256)
    copilot = runtime.copilot_service

    def run(req):
        req = replace(req, prompt="Run this Python Script.")
        return copilot._execute_registered_operator_action("strategy_lab.run_research_script", exact,
            copilot._build_strategy_lab_context(req), request=req).output

    assert run(unattached)["status"] == "rejected"
    assert service.list_runs(ui_id) == []
    assert run(attached)["status"] == "completed"
    assert len(service.list_runs(ui_id)) == 1
    # Un Script creado por la propia sesión de Copilot sigue siendo accesible sin adjuntarlo.
    own = service.create_script(ResearchScriptCreateRequest("copilot-chat-1", "Own script", "print('own')"))
    assert call("inspect", selection(own.script.script_id), unattached)["status"] == "preview_only"


@pytest.mark.parametrize("prompt, expected", [
    ("Fetch and combine datasets, draft a Python Script, but do not run it.", True),
    ("Fetching SPY history for the Python Script.", True),
    ("Add SPY and QQQ daily history to the Research Script.", True),
    ("Combine SPY prices with WTI curves in a Python Script.", True),
    # Regresión: editar código o negar la adquisición no concede permiso para pedir datos.
    ("Edit the Python Script to add a 20-day MA column", False),
    ("Edit the Research Script to add a warning.", False),
    ("Edit the script to add a returns column.", False),
    ("Draft a Python Script, but don't add any new data.", False),
    ("Draft a Python Script without fetching data.", False),
    ("Draft a Python Script with no new data.", False),
    ("Run this Python Script.", False),
])
def test_acquisition_authorization_requires_explicit_data_request(prompt, expected):
    from src.application.copilot_script_tools import script_acquisition_authorized
    assert script_acquisition_authorized(prompt) is expected


def test_accepted_candidate_binding_limits_operator_but_not_user_runs(e3):
    from src.models.research_script import ResearchScriptRunCreateRequest
    runtime, service, script_id, request, call = e3
    reviewed = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest(input_files=[
        ResearchScriptInputFileCreateRequest("settings.json", "application/json", b'{"window":20}')]))
    parent = service.get_script(script_id).revisions[0]
    candidate = call("draft_from_bundle", dict(script_id=script_id, input_snapshot_id=reviewed.snapshot_id,
        expected_parent_sha256=parent.source_sha256, python_source="print(open('settings.json').read())\n",
        change_summary="Print the reviewed settings."))
    service.accept_staged_revision(script_id, candidate["revision_id"], expected_parent_sha256=parent.source_sha256)
    # El usuario añade después un fichero desde la UI.
    newer = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest(base_snapshot_id=reviewed.snapshot_id,
        input_files=[ResearchScriptInputFileCreateRequest("notes.txt", "text/plain", b"user note")]))
    user_run = service.create_run(script_id, ResearchScriptRunCreateRequest(input_snapshot_id=newer.snapshot_id))
    assert user_run.input_snapshot_id == newer.snapshot_id and user_run.revision_id == candidate["revision_id"]
    # El Operator sigue sin poder ejecutar el código revisado sobre entradas no revisadas.
    with pytest.raises(ResearchScriptConflictError, match="different input bundle"):
        service.create_exact_run(script_id, revision_id=candidate["revision_id"], input_snapshot_id=newer.snapshot_id,
            source_sha256=candidate["source_sha256"], manifest_sha256=newer.manifest_sha256)


def test_large_script_observations_keep_filenames_and_schema_for_the_model(e3):
    from src.application.copilot_script_tools import MAX_SCRIPT_OBSERVATION_BYTES, _observation_size
    from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider
    runtime, service, script_id, request, call = e3
    rows = ",".join('{"timestamp":"2026-10-%02d","value":%d.123456}' % (1 + i % 28, i) for i in range(400))
    files = [ResearchScriptInputFileCreateRequest(f"dataset_{i}.json", "application/json",
        ('{"metadata":{"fields":[{"name":"close","unit":"USD"}]},"data":{"points":[%s]}}' % rows).encode()) for i in range(5)]
    bundle = service.create_input_bundle(script_id, ResearchScriptInputBundleRequest(input_files=files))
    observed = call("read_inputs", {"script_id": script_id, "input_snapshot_id": bundle.snapshot_id})
    assert _observation_size(observed) <= MAX_SCRIPT_OBSERVATION_BYTES
    assert "bounded_for_operator" in observed
    # El proveedor ya no necesita compactarla, así que nombres y esquema llegan íntegros al modelo.
    delivered = OpenAIResponsesCopilotProvider._bounded_operator_observation(observed)
    assert [item["logical_filename"] for item in delivered["files"]] == [f"dataset_{i}.json" for i in range(5)]
    assert all(item["sample_truncated"] and '"fields":[{"name":"close","unit":"USD"}]' in item["sample"] for item in delivered["files"])


def test_script_budget_extension_is_limited_to_script_workflows(e3):
    from types import SimpleNamespace
    runtime, service, script_id, request, call = e3
    copilot = runtime.copilot_service
    definitions = {d.tool_id: d for d in copilot.list_research_action_definitions()}
    assert definitions["strategy_lab.script_discover"].external_provider == "script_catalog"
    acquiring = copilot.plan_research_operator(_operator_request("Fetch SPY and QQQ history and draft a Python Script."))
    drafting = copilot.plan_research_operator(_operator_request("Draft a Python Script without fetching data."))
    assert acquiring.intent == drafting.intent == "research_script_workflow"
    assert acquiring.max_provider_calls == 4 and drafting.max_provider_calls == 1
    assert acquiring.max_elapsed_ms == 12_000  # sin proveedor real no se amplía el tiempo
    copilot.provider = SimpleNamespace(stream_research_operator=lambda *args, **kwargs: None)
    live = copilot.plan_research_operator(_operator_request("Fetch SPY and QQQ history and draft a Python Script."))
    other = copilot.plan_research_operator(_operator_request("Compare SPY and QQQ total return over one year."))
    assert live.max_elapsed_ms == 180_000 and live.max_provider_calls == 4
    assert other.intent != "research_script_workflow" and other.max_elapsed_ms < 180_000 and other.max_provider_calls < 4


def test_long_research_intent_stages_candidate_with_bounded_change_summary(e3):
    # Regresión (validación en vivo 2026-10-15): un research_intent largo hacía fallar el paso
    # porque el resumen derivado superaba el límite de 512 caracteres.
    from src.application.request_limits import MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS
    runtime, service, script_id, request, call = e3
    parent = service.get_script(script_id).revisions[0]
    edit = replace(request, prompt="Edit the Research Script to print a short summary.", context=replace(request.context,
        strategy_lab_state={"script_state": {"script_id": script_id, "source_sha256": parent.source_sha256}}))
    copilot = runtime.copilot_service
    output = copilot._execute_registered_operator_action("strategy_lab.draft_research_script", {
        "title": "Summary", "research_intent": "Explain every step in detail. " * 60, "python_source": "print('summary')\n",
        "language": "python", "authorized_input_references": []}, copilot._build_strategy_lab_context(edit),
        request=edit, run_id="long-intent").output
    assert output.get("error") is None and output["revision_status"] == "staged"
    staged = next(r for r in service.get_script(script_id).revisions if r.revision_id == output["revision_id"])
    assert len(staged.change_summary) <= MAX_RESEARCH_SCRIPT_CHANGE_SUMMARY_CHARS and staged.change_summary.endswith("…")


def test_operator_model_receives_visibly_attached_script_identities(e3):
    # Regresión (validación en vivo 2026-10-15): el mensaje del loop omitía script_state, así que
    # el modelo no podía rellenar script_id ni hashes exactos y terminaba sin llamar herramientas.
    from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider, MAX_ATTACHED_SCRIPT_SOURCE_CHARS
    runtime, service, script_id, request, call = e3
    provider = OpenAIResponsesCopilotProvider(api_key="test", model="gpt-test", reasoning_effort="low")
    copilot = runtime.copilot_service
    state = {"script_id": script_id, "source_sha256": "f" * 64, "input_snapshot_id": "bundle-1",
             "manifest_sha256": "e" * 64, "canonical_source": "x" * (MAX_ATTACHED_SCRIPT_SOURCE_CHARS + 10),
             "selected_run_outputs": [{"text": "no debe enviarse"}]}
    script_request = replace(request, context=replace(request.context, strategy_lab_state={"script_state": state}))
    body = json.loads(provider._build_operator_user_message(script_request, copilot.plan_research_operator(script_request))["content"][0]["text"])
    attached = body["attached_context"]["script_state"]
    assert attached["script_id"] == script_id and attached["input_snapshot_id"] == "bundle-1"
    assert attached["source_sha256"] == "f" * 64 and attached["manifest_sha256"] == "e" * 64
    assert attached["canonical_source_truncated"] and len(attached["canonical_source"]) == MAX_ATTACHED_SCRIPT_SOURCE_CHARS
    assert "selected_run_outputs" not in attached  # solo identidades y código, no salidas
    other = replace(script_request, prompt="Compare SPY and QQQ total return over one year.")
    other_body = json.loads(provider._build_operator_user_message(other, copilot.plan_research_operator(other))["content"][0]["text"])
    assert "attached_context" not in other_body
    assert "attached_context.script_state" in provider._build_operator_instructions(copilot.plan_research_operator(script_request))


def test_script_operator_turns_allow_full_source_output(e3):
    # Regresión (validación en vivo 2026-10-16): con 1.600 tokens la llamada que propone el código se cortaba.
    from src.services.openai_copilot_provider import (
        MAX_OPERATOR_OUTPUT_TOKENS, MAX_SCRIPT_OPERATOR_OUTPUT_TOKENS, OpenAIResponsesCopilotProvider)
    runtime, service, script_id, request, call = e3
    copilot = runtime.copilot_service
    script_plan = copilot.plan_research_operator(request)
    other_plan = copilot.plan_research_operator(replace(request, prompt="Compare SPY and QQQ total return over one year."))
    assert script_plan.intent == "research_script_workflow" != other_plan.intent
    assert OpenAIResponsesCopilotProvider._operator_max_output_tokens(script_plan) == MAX_SCRIPT_OPERATOR_OUTPUT_TOKENS
    assert OpenAIResponsesCopilotProvider._operator_max_output_tokens(other_plan) == MAX_OPERATOR_OUTPUT_TOKENS == 1_600
