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
