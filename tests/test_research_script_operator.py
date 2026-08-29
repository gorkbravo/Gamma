from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.research_script_service import ResearchScriptConflictError
from src.application.runtime import build_runtime
from src.models.copilot import CopilotResearchCardRequest, CopilotRequestContext
from src.models.research_script import (
    ResearchScriptRevisionCreateRequest,
    ResearchScriptRunCreateRequest,
)
from src.services.openai_copilot_provider import OpenAIResponsesCopilotProvider


SCRIPT = """from pathlib import Path
print('gamma research script')
Path('summary.csv').write_text('metric,value\\nreturn,0.12\\n', encoding='utf-8')
"""


def _runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("GAMMA_RESEARCH_SCRIPT_RUNTIME", "mock")
    return build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )


def _operator_request(
    prompt: str,
    *,
    session_id: str = "operator-script-session",
    script_state: dict | None = None,
) -> CopilotResearchCardRequest:
    return CopilotResearchCardRequest(
        domain="strategy_lab",
        prompt=prompt,
        user_session_id=session_id,
        role="research_operator",
        context=CopilotRequestContext(
            current_tab="copilot",
            workspace_mode="research",
            strategy_lab_state=(
                {"script_state": script_state}
                if script_state is not None
                else None
            ),
        ),
    )


def _draft_arguments(source: str = SCRIPT) -> dict:
    return {
        "title": "SPY monthly crossover",
        "research_intent": "Compare monthly fast and slow moving averages for SPY.",
        "python_source": source,
        "language": "python",
        "authorized_input_references": [
            {
                "reference_id": "historical-price.spy.monthly",
                "source_kind": "provider",
                "provider": "gamma_fixture",
                "dataset_id": "spy-monthly-v1",
                "logical_filename": "spy_monthly.csv",
                "media_type": "text/csv",
                "coverage_start": "2020-01-01",
                "coverage_end": "2025-12-31",
                "symbol": "SPY",
                "benchmark_symbol": "SPY",
                "timeframe": "monthly",
                "lookback_days": 756,
                "frequency": "monthly",
            }
        ],
    }


def _assert_strict_objects(schema: dict) -> None:
    if schema.get("type") == "object":
        properties = schema.get("properties") or {}
        assert schema.get("additionalProperties") is False
        assert set(schema.get("required") or []) == set(properties)
        for child in properties.values():
            if isinstance(child, dict):
                _assert_strict_objects(child)
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        _assert_strict_objects(schema["items"])


def test_script_actions_are_strict_and_do_not_repurpose_strategy_backtest(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        definitions = {
            item.tool_id: item
            for item in runtime.copilot_service.list_research_action_definitions()
        }
        draft = definitions["strategy_lab.draft_research_script"]
        run = definitions["strategy_lab.run_research_script"]
        assert draft.action_type == "draft_change"
        assert draft.permission_policy == "automatic_draft"
        assert run.action_type == "run_analysis"
        assert run.permission_policy == "automatic"
        _assert_strict_objects(draft.input_schema)
        _assert_strict_objects(run.input_schema)
        assert definitions["run_strategy_lab_backtest"].tool_id == "run_strategy_lab_backtest"
    finally:
        runtime.shutdown()


def test_script_plan_distinguishes_draft_from_explicit_run(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        draft_plan = runtime.copilot_service.plan_research_operator(
            _operator_request("Build a monthly moving-average Research Script for SPY. Show the code.")
        )
        assert draft_plan.intent == "research_script_workflow"
        assert [step.tool_id for step in draft_plan.steps] == [
            "strategy_lab.draft_research_script"
        ]

        run_plan = runtime.copilot_service.plan_research_operator(
            _operator_request(
                "Run it.",
                script_state={"script_id": "script-fixture", "source_sha256": "a" * 64},
            )
        )
        assert [step.tool_id for step in run_plan.steps] == [
            "strategy_lab.run_research_script"
        ]

        combined_plan = runtime.copilot_service.plan_research_operator(
            _operator_request("Build and run a monthly Research Script for SPY.")
        )
        assert [step.tool_id for step in combined_plan.steps] == [
            "strategy_lab.draft_research_script",
            "strategy_lab.run_research_script",
        ]

        blocked = runtime.copilot_service.plan_research_operator(
            _operator_request("Build a Research Script and connect it to my broker account.")
        )
        assert blocked.steps == []
        assert any("refused" in warning.lower() for warning in blocked.warnings)
    finally:
        runtime.shutdown()


def test_operator_draft_run_and_working_analysis_preserve_exact_identities(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        service = runtime.copilot_service
        service.create_session(session_id="operator-script-session")
        draft_request = _operator_request(
            "Build a monthly moving-average Research Script for SPY. Show the code, but do not run it."
        )
        draft_context = service._build_strategy_lab_context(draft_request)
        draft = service._execute_registered_operator_action(
            "strategy_lab.draft_research_script",
            _draft_arguments(),
            draft_context,
            request=draft_request,
            run_id="operator-run-draft",
        )
        assert not (isinstance(draft.output, dict) and draft.output.get("error"))
        assert draft.output["revision_status"] == "canonical"
        assert draft.output["source_sha256"] == runtime.research_script_service.source_sha256(SCRIPT)
        assert draft.output["materialization"] == {
            "target_tab": "strategy_lab",
            "target_mode": "script",
            "payload_contract": "copilot.strategy-lab-script-working-analysis.v1",
            "durable": False,
            "navigation_context": {
                "script_id": draft.output["script_id"],
                "revision_id": draft.output["revision_id"],
                "input_snapshot_id": draft.output["input_snapshot_id"],
                "selected_run_id": None,
            },
        }
        input_requirement = draft.output["input_requirements"][0]
        assert input_requirement["symbol"] == "SPY"
        assert input_requirement["benchmark_symbol"] == "SPY"
        assert input_requirement["timeframe"] == "monthly"
        assert input_requirement["frequency"] == "monthly"
        retained_snapshot = runtime.research_script_store.load_input_snapshot(
            draft.output["input_snapshot_id"]
        )
        assert retained_snapshot is not None
        assert retained_snapshot.files[0].logical_filename == "spy_monthly.csv"
        assert retained_snapshot.files[0].source_kind == "provider"

        run_request = _operator_request(
            "Run it.",
            script_state={
                "script_id": draft.output["script_id"],
                "source_sha256": draft.output["source_sha256"],
            },
        )
        run_context = service._build_strategy_lab_context(run_request)
        run_arguments = {
            "script_id": draft.output["script_id"],
            "revision_id": draft.output["revision_id"],
            "input_snapshot_id": draft.output["input_snapshot_id"],
            "source_sha256": draft.output["source_sha256"],
            "manifest_sha256": draft.output["manifest_sha256"],
        }
        run = service._execute_registered_operator_action(
            "strategy_lab.run_research_script",
            run_arguments,
            run_context,
            request=run_request,
            run_id="operator-run-execute",
        )
        assert run.output["status"] == "completed"
        assert run.output["revision_id"] == draft.output["revision_id"]
        assert run.output["source_sha256"] == draft.output["source_sha256"]
        assert run.output["manifest_sha256"] == draft.output["manifest_sha256"]
        assert all(item["generated"] and item["derived"] for item in run.output["outputs"])

        attached = service._attach_operator_working_analysis(
            run,
            tool_id="strategy_lab.run_research_script",
            arguments=run_arguments,
            context=run_context,
            request=run_request,
            run_id="operator-run-execute",
        )
        analysis_id = attached.output["working_analysis"]["analysis_id"]
        materialized = service.materialize_working_analysis(analysis_id)
        assert materialized.owning_tab == "strategy_lab"
        assert materialized.owning_mode == "script"
        assert materialized.materialization["payload_contract"] == (
            "copilot.strategy-lab-script-working-analysis.v1"
        )
        assert materialized.entity["selected_run_id"] == run.output["run_id"]
    finally:
        runtime.shutdown()


def test_degraded_input_acquisition_is_explicit_and_does_not_expand_authority(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        copilot = runtime.copilot_service
        draft_request = _operator_request("Build a Research Script from the authorized dataset.")
        arguments = _draft_arguments()
        arguments["authorized_input_references"][0]["symbol"] = None
        draft = copilot._execute_registered_operator_action(
            "strategy_lab.draft_research_script",
            arguments,
            copilot._build_strategy_lab_context(draft_request),
            request=draft_request,
            run_id="operator-degraded-input",
        )
        assert draft.output.get("error") is None
        assert any("could not be acquired" in item for item in draft.output["warnings"])
        snapshot = runtime.research_script_store.load_input_snapshot(
            draft.output["input_snapshot_id"]
        )
        assert snapshot is not None and snapshot.files == []
        assert snapshot.dataset_refs[0]["reference_id"] == "historical-price.spy.monthly"
    finally:
        runtime.shutdown()


def test_operator_revision_is_staged_and_accept_reject_enforces_parent_hash(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        service = runtime.copilot_service
        request = _operator_request("Build a Research Script for SPY. Show the code.")
        initial = service._execute_registered_operator_action(
            "strategy_lab.draft_research_script",
            _draft_arguments(),
            service._build_strategy_lab_context(request),
            request=request,
            run_id="operator-initial",
        ).output
        script_state = {
            "script_id": initial["script_id"],
            "source_sha256": initial["source_sha256"],
        }
        edit_request = _operator_request(
            "Edit the Research Script to add a warning.",
            script_state=script_state,
        )
        staged = service._execute_registered_operator_action(
            "strategy_lab.draft_research_script",
            _draft_arguments(f"{SCRIPT}\nprint('warning: fixture')\n"),
            service._build_strategy_lab_context(edit_request),
            request=edit_request,
            run_id="operator-candidate",
        ).output
        assert staged["revision_status"] == "staged"
        detail = runtime.research_script_service.get_script(initial["script_id"])
        assert detail.script.canonical_revision_id == initial["revision_id"]

        rejected = runtime.research_script_service.reject_staged_revision(
            initial["script_id"],
            staged["revision_id"],
            expected_parent_sha256=initial["source_sha256"],
        )
        assert rejected.script.canonical_revision_id == initial["revision_id"]
        assert next(item for item in rejected.revisions if item.revision_id == staged["revision_id"]).status == "rejected"

        second = runtime.research_script_service.stage_operator_revision(
            initial["script_id"],
            source=f"{SCRIPT}\nprint('second candidate')\n",
            expected_parent_sha256=initial["source_sha256"],
            change_summary="Second candidate",
            operator_run_id="operator-second-candidate",
        )
        second_candidate = next(item for item in second.revisions if item.status == "staged")
        user_revision = runtime.research_script_service.create_revision(
            initial["script_id"],
            ResearchScriptRevisionCreateRequest(
                source=f"{SCRIPT}\nprint('canonical user edit')\n",
                expected_parent_sha256=initial["source_sha256"],
            ),
        )
        with pytest.raises(ResearchScriptConflictError, match="canonical source changed"):
            runtime.research_script_service.accept_staged_revision(
                initial["script_id"],
                second_candidate.revision_id,
                expected_parent_sha256=initial["source_sha256"],
            )
        assert runtime.research_script_service.get_script(initial["script_id"]).script.canonical_revision_id == user_revision.script.canonical_revision_id
    finally:
        runtime.shutdown()


def test_staged_revision_accept_and_reject_api_contract(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    detail, _ = runtime.research_script_service.create_operator_draft(
        session_id="operator-api-session",
        title="API candidate fixture",
        research_intent="Verify explicit user decision routes.",
        source=SCRIPT,
        authorized_input_references=[],
        operator_run_id="operator-api-seed",
    )
    canonical = detail.revisions[0]
    staged = runtime.research_script_service.stage_operator_revision(
        detail.script.script_id,
        source=f"{SCRIPT}\nprint('candidate accepted')\n",
        expected_parent_sha256=canonical.source_sha256,
        change_summary="Accept candidate",
        operator_run_id="operator-api-candidate-1",
    )
    candidate = next(item for item in staged.revisions if item.status == "staged")
    client = TestClient(create_app(runtime))
    try:
        accepted = client.post(
            f"/research/strategy-lab/scripts/{detail.script.script_id}/revisions/{candidate.revision_id}/accept",
            json={"expected_parent_sha256": canonical.source_sha256},
        )
        assert accepted.status_code == 200
        accepted_payload = accepted.json()
        assert accepted_payload["script"]["canonical_revision_id"] == candidate.revision_id

        accepted_hash = candidate.source_sha256
        next_staged = runtime.research_script_service.stage_operator_revision(
            detail.script.script_id,
            source=f"{SCRIPT}\nprint('candidate rejected')\n",
            expected_parent_sha256=accepted_hash,
            change_summary="Reject candidate",
            operator_run_id="operator-api-candidate-2",
        )
        rejected_candidate = max(
            (item for item in next_staged.revisions if item.status == "staged"),
            key=lambda item: item.revision_number,
        )
        rejected = client.post(
            f"/research/strategy-lab/scripts/{detail.script.script_id}/revisions/{rejected_candidate.revision_id}/reject",
            json={"expected_parent_sha256": accepted_hash},
        )
        assert rejected.status_code == 200
        rejected_payload = rejected.json()
        assert rejected_payload["script"]["canonical_revision_id"] == candidate.revision_id
        assert next(
            item
            for item in rejected_payload["revisions"]
            if item["revision_id"] == rejected_candidate.revision_id
        )["status"] == "rejected"
    finally:
        client.close()
        runtime.shutdown()


def test_research_agent_has_no_script_action_authority(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        result = runtime.copilot_service.generate_research_card(
            replace(
                _operator_request("Draft and run a Research Script for SPY."),
                role="research_agent",
            )
        )
        assert result.status == "incomplete"
        assert "Switch explicitly to Research Operator" in (result.message or "")
        assert result.tool_traces == []
    finally:
        runtime.shutdown()


def test_research_agent_may_inspect_attached_completed_script_result_read_only(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        result = runtime.copilot_service.generate_research_card(
            replace(
                _operator_request(
                    "Summarize the attached completed Research Script result and warnings.",
                    script_state={
                        "script_id": "script-read-only",
                        "source_sha256": "a" * 64,
                        "selected_run_id": "run-read-only",
                        "selected_run_status": "completed",
                        "selected_run_outputs": [
                            {"kind": "metric", "metric_name": "drawdown", "metric_value": -0.12}
                        ],
                        "selected_run_warnings": ["Fixture warning"],
                    },
                ),
                role="research_agent",
            )
        )
        assert "Switch explicitly to Research Operator" not in (result.message or "")
        assert result.tool_traces == []
    finally:
        runtime.shutdown()


def test_provider_without_custom_responses_loop_fails_cleanly_without_script_state(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    try:
        result = runtime.copilot_service.execute_research_operator_plan(
            _operator_request("Build and run a Research Script for SPY.")
        )
        assert result.status == "unavailable"
        assert "custom Responses loop" in (result.message or "")
        assert result.tool_traces == []
        assert runtime.research_script_service.list_scripts() == []
    finally:
        runtime.shutdown()


def test_responses_operator_observes_draft_before_identity_citing_synthesis(
    tmp_path,
    monkeypatch,
) -> None:
    class ScriptDraftOperator(OpenAIResponsesCopilotProvider):
        def __init__(self) -> None:
            super().__init__(
                api_key="test-key",
                model="gpt-test-operator",
                reasoning_effort="low",
                store_responses=False,
            )
            self.payloads: list[dict] = []

        def _post_json_stream(self, payload, emit, should_cancel):
            assert should_cancel() is False
            self.payloads.append(deepcopy(payload))
            if len(self.payloads) == 1:
                tools = {item["name"]: item for item in payload["tools"]}
                assert set(tools) == {"strategy_lab.draft_research_script"}
                assert tools["strategy_lab.draft_research_script"]["strict"] is True
                return (
                    {
                        "id": "resp-script-draft-tool",
                        "model": self.model,
                        "output": [
                            {
                                "type": "function_call",
                                "id": "fc-script-draft",
                                "call_id": "call-script-draft",
                                "name": "strategy_lab.draft_research_script",
                                "arguments": json.dumps(_draft_arguments()),
                            }
                        ],
                    },
                    "completed",
                )
            observations = [
                json.loads(item["output"])
                for item in payload["input"]
                if item.get("type") == "function_call_output"
            ]
            assert len(observations) == 1
            observation = observations[0]
            assert observation["status"] == "completed"
            assert observation["output"]["revision_status"] == "canonical"
            assert observation["output"]["source_sha256"] == runtime.research_script_service.source_sha256(SCRIPT)
            revision_source = observation["output"]["sources"][0]
            card = {
                "title": "SPY monthly crossover Script draft",
                "hypothesis": "The requested Script is ready for user review.",
                "rationale": (
                    f"Drafted script `{observation['output']['script_id']}` revision "
                    f"`{observation['output']['revision_id']}` without executing it."
                ),
                "required_data": ["Gamma-provided SPY monthly historical-price snapshot"],
                "proposed_test": "Review the canonical source and explicitly request execution.",
                "confounders": ["Input bytes still require Gamma acquisition."],
                "next_steps": ["Open Strategy Lab / Script and review the source."],
                "caveats": list(observation["output"]["warnings"]),
                "source_backed_claims": [
                    {
                        "claim": "Gamma created the immutable Script revision.",
                        "evidence_refs": [revision_source],
                    }
                ],
                "inferred_claims": [],
                "stop_reason": "final_answer",
            }
            return (
                {
                    "id": "resp-script-draft-final",
                    "model": self.model,
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": json.dumps(card)}
                            ],
                        }
                    ],
                },
                "completed",
            )

    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    runtime = _runtime(tmp_path, monkeypatch)
    provider = ScriptDraftOperator()
    runtime.copilot_service.provider = provider
    client = TestClient(create_app(runtime))
    try:
        client.post(
            "/copilot/sessions",
            json={"session_id": "operator-script-session", "title": "Script session"},
        )
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "strategy_lab",
                "prompt": "Build a monthly moving-average Research Script for SPY. Show the code, but do not run it.",
                "user_session_id": "operator-script-session",
                "context": {"current_tab": "copilot", "workspace_mode": "research"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert len(provider.payloads) == 2
        event_types = [item["event_type"] for item in payload["operator_events"]]
        assert event_types.index("script-draft-created") < event_types.index("tool-result")
        assert event_types.index("input-snapshot-created") < event_types.index("tool-result")
        assert not any(item.get("tool_id") == "strategy_lab.run_research_script" for item in payload["operator_events"])
        analyses = client.get(
            "/copilot/sessions/operator-script-session/working-analyses"
        ).json()
        assert analyses[0]["owning_mode"] == "script"
        assert analyses[0]["materialization"]["durable"] is False
        assert payload["card"]["rationale"].find("revision") >= 0
    finally:
        client.close()
        runtime.shutdown()


def test_responses_operator_run_observation_precedes_identity_citing_synthesis(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    runtime = _runtime(tmp_path, monkeypatch)
    detail, snapshot = runtime.research_script_service.create_operator_draft(
        session_id="operator-script-session",
        title="SPY monthly crossover",
        research_intent="Run the reviewed immutable Script.",
        source=SCRIPT,
        authorized_input_references=[],
        operator_run_id="operator-draft-seed",
    )
    revision = detail.revisions[0]
    exact_arguments = {
        "script_id": detail.script.script_id,
        "revision_id": revision.revision_id,
        "input_snapshot_id": snapshot.snapshot_id,
        "source_sha256": revision.source_sha256,
        "manifest_sha256": snapshot.manifest_sha256,
    }

    class ScriptRunOperator(OpenAIResponsesCopilotProvider):
        def __init__(self) -> None:
            super().__init__(
                api_key="test-key",
                model="gpt-test-operator",
                reasoning_effort="low",
                store_responses=False,
            )
            self.turn = 0

        def _post_json_stream(self, payload, emit, should_cancel):
            self.turn += 1
            if self.turn == 1:
                tools = {item["name"]: item for item in payload["tools"]}
                assert set(tools) == {"strategy_lab.run_research_script"}
                return (
                    {
                        "id": "resp-script-run-tool",
                        "model": self.model,
                        "output": [
                            {
                                "type": "function_call",
                                "id": "fc-script-run",
                                "call_id": "call-script-run",
                                "name": "strategy_lab.run_research_script",
                                "arguments": json.dumps(exact_arguments),
                            }
                        ],
                    },
                    "completed",
                )
            observations = [
                json.loads(item["output"])
                for item in payload["input"]
                if item.get("type") == "function_call_output"
            ]
            assert observations[-1]["status"] == "completed"
            output = observations[-1]["output"]
            assert output["status"] == "completed"
            assert output["revision_id"] == revision.revision_id
            assert output["source_sha256"] == revision.source_sha256
            assert output["manifest_sha256"] == snapshot.manifest_sha256
            assert output["outputs"]
            run_source = output["sources"][-1]
            card = {
                "title": "Research Script run complete",
                "hypothesis": "The exact reviewed Script completed in the bounded runtime.",
                "rationale": (
                    f"Run `{output['run_id']}` observed revision `{output['revision_id']}` "
                    f"with source hash `{output['source_sha256']}`."
                ),
                "required_data": ["Immutable Gamma input snapshot"],
                "proposed_test": "Inspect retained typed outputs in Strategy Lab / Script.",
                "confounders": [],
                "next_steps": ["Review retained outputs and warnings."],
                "caveats": list(output["warnings"]),
                "source_backed_claims": [
                    {
                        "claim": "The immutable Research Script run completed.",
                        "evidence_refs": [run_source],
                    }
                ],
                "inferred_claims": [],
                "stop_reason": "final_answer",
            }
            return (
                {
                    "id": "resp-script-run-final",
                    "model": self.model,
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": json.dumps(card)}
                            ],
                        }
                    ],
                },
                "completed",
            )

    runtime.copilot_service.provider = ScriptRunOperator()
    client = TestClient(create_app(runtime))
    try:
        client.post(
            "/copilot/sessions",
            json={"session_id": "operator-script-session", "title": "Script session"},
        )
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "strategy_lab",
                "prompt": "Run it.",
                "user_session_id": "operator-script-session",
                "context": {
                    "current_tab": "strategy_lab",
                    "workspace_mode": "research",
                    "strategy_lab_state": {
                        "script_state": {
                            "script_id": detail.script.script_id,
                            "source_sha256": revision.source_sha256,
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        event_types = [item["event_type"] for item in payload["operator_events"]]
        assert event_types.index("run-started") < event_types.index("tool-result")
        assert event_types.index("output-artifact-created") < event_types.index("tool-result")
        assert "run `" in payload["card"]["rationale"].lower()
        assert revision.revision_id in payload["card"]["rationale"]
    finally:
        client.close()
        runtime.shutdown()


def test_timed_out_script_observation_prevents_false_success_synthesis(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom")
    runtime = _runtime(tmp_path, monkeypatch)
    detail, snapshot = runtime.research_script_service.create_operator_draft(
        session_id="operator-timeout-session",
        title="Timeout fixture",
        research_intent="Verify failure synthesis.",
        source=SCRIPT,
        authorized_input_references=[],
        operator_run_id="operator-timeout-seed",
    )
    revision = detail.revisions[0]
    timed_out_run = runtime.research_script_service.create_run(
        detail.script.script_id,
        ResearchScriptRunCreateRequest(
            revision_id=revision.revision_id,
            input_snapshot_id=snapshot.snapshot_id,
            runtime_scenario="timed_out",
        ),
    )
    exact_arguments = {
        "script_id": detail.script.script_id,
        "revision_id": revision.revision_id,
        "input_snapshot_id": snapshot.snapshot_id,
        "source_sha256": revision.source_sha256,
        "manifest_sha256": snapshot.manifest_sha256,
    }
    monkeypatch.setattr(
        runtime.research_script_service,
        "create_exact_run",
        lambda *args, **kwargs: timed_out_run,
    )

    class FalseSuccessOperator(OpenAIResponsesCopilotProvider):
        def __init__(self) -> None:
            super().__init__(
                api_key="test-key",
                model="gpt-test-operator",
                reasoning_effort="low",
                store_responses=False,
            )
            self.turn = 0

        def _post_json_stream(self, payload, emit, should_cancel):
            self.turn += 1
            if self.turn == 1:
                return (
                    {
                        "id": "resp-timeout-tool",
                        "model": self.model,
                        "output": [
                            {
                                "type": "function_call",
                                "id": "fc-timeout",
                                "call_id": "call-timeout",
                                "name": "strategy_lab.run_research_script",
                                "arguments": json.dumps(exact_arguments),
                            }
                        ],
                    },
                    "completed",
                )
            return (
                {
                    "id": "resp-false-success",
                    "model": self.model,
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "title": "Incorrect success",
                                            "hypothesis": "The run succeeded.",
                                            "rationale": "Everything completed.",
                                            "required_data": [],
                                            "proposed_test": "None",
                                            "confounders": [],
                                            "next_steps": [],
                                            "caveats": [],
                                            "source_backed_claims": [],
                                            "inferred_claims": [],
                                            "stop_reason": "final_answer",
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "completed",
            )

    runtime.copilot_service.provider = FalseSuccessOperator()
    client = TestClient(create_app(runtime))
    try:
        client.post(
            "/copilot/sessions",
            json={"session_id": "operator-timeout-session", "title": "Timeout"},
        )
        response = client.post(
            "/copilot/operator-plan/execute",
            json={
                "domain": "strategy_lab",
                "prompt": "Run it.",
                "user_session_id": "operator-timeout-session",
                "context": {
                    "current_tab": "strategy_lab",
                    "workspace_mode": "research",
                    "strategy_lab_state": {
                        "script_state": {
                            "script_id": detail.script.script_id,
                            "source_sha256": revision.source_sha256,
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "incomplete"
        assert payload["card"] is None
        assert timed_out_run.run_id in payload["message"]
        assert "timed_out" in payload["message"]
        assert any(
            item["event_type"] == "run-timed-out"
            for item in payload["operator_events"]
        )
    finally:
        client.close()
        runtime.shutdown()
