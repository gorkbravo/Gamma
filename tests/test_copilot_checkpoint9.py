from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from types import SimpleNamespace

from src.application.copilot_run_recovery import CopilotRunRecovery
from src.models.copilot import CopilotResearchCardRequest, CopilotRequestContext
from src.services.copilot_store import CopilotStore
from src.utils.time import now_utc
from test_copilot import _build_test_client, _StubFundamentalsService


@pytest.fixture
def setup(tmp_path):
    client, runtime = _build_test_client(tmp_path)
    service = runtime.copilot_service
    service.fundamentals_service = _StubFundamentalsService()
    request = CopilotResearchCardRequest(domain="synthesis", prompt="Set AAPL base DCF WACC to 9%",
        user_session_id="session_9", context_fingerprint="context_9", role="research_operator",
        selected_scope_domains=["fundamentals"], context=CopilotRequestContext(current_tab="copilot"))
    result = service.execute_research_operator_plan(request, run_id="run_9")
    mutation = service.store.list_mutations("session_9")[0]
    assert result.status == "awaiting_confirmation"
    yield client, service, request, mutation
    runtime.shutdown()


def decide(service, mutation, decision="approve", **overrides):
    return service.resolve_operator_approval(**{
        "run_id": "run_9", "mutation_id": mutation.mutation_id, "session_id": "session_9",
        "role": "research_operator", "decision": decision,
        "confirmation_token": mutation.confirmation_token, "context_fingerprint": "context_9",
        "proposal_hash": mutation.proposal_hash, **overrides,
    })


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_live_capable_resume_synthesizes_observations_without_tool_authority(setup, decision):
    client, service, _, mutation = setup
    from src.models.copilot import CopilotResearchCardResult, CopilotUsageRecord, ResearchCard
    calls = []
    def synthesize(**kwargs):
        assert kwargs["tool_specs"] == []
        assert kwargs["context"].summary_data["operator_observations"]
        assert kwargs["context"].sources
        assert kwargs["context"].summary_data["approval_effect"]["status"] == ("applied" if decision == "approve" else "rejected")
        assert kwargs["context"].summary_data["approval_effect"]["diff"]
        with pytest.raises(ValueError, match="no tool authority"):
            kwargs["execute_tool"]("fundamentals.apply_dcf_update", {}, kwargs["context"])
        calls.append(kwargs)
        return CopilotResearchCardResult(domain="fundamentals", current_tab="copilot",
            status="ready", provider="live-capable-stub", model="gpt-test",
            card=ResearchCard(title="Observed DCF outcome", hypothesis="Observed only", rationale="Retained evidence"),
            usage=CopilotUsageRecord(provider_calls=1, input_tokens=100, output_tokens=20))
    service.provider = SimpleNamespace(stream_research_operator=lambda **kwargs: None,
                                      stream_research_card=synthesize)
    result = decide(service, mutation, decision)
    assert len(calls) == 1
    assert result.card.title == "Observed DCF outcome"
    assert result.usage.provider_calls == 1
    assert result.response_id == client.get("/copilot/sessions/session_9").json()["turns"][0]["result"]["response_id"]
    assert len(service.fundamentals_service.saved_snapshots) == (1 if decision == "approve" else 0)
    with pytest.raises(ValueError, match="already accepted"):
        decide(service, mutation, decision)
    assert len(calls) == 1


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_same_run_and_turn_continue_after_restart(setup, decision):
    client, service, _, mutation = setup
    before = client.get("/copilot/sessions/session_9").json()["turns"][0]
    state = service.run_recovery.get("run_9")
    assert state["plan_cursor"] == 1
    assert state["pending_tool_call"]["proposal_hash"] == mutation.proposal_hash
    # Reconstruct from disk; no in-memory request, run handle or provider state.
    service.store = CopilotStore(service.store.base_dir)
    service.confirmation_service.store = service.store
    service.run_recovery = CopilotRunRecovery(service.store)
    service._runs.clear()
    result = decide(service, mutation, decision)
    detail = client.get("/copilot/sessions/session_9").json()
    assert len(detail["turns"]) == 1
    after = detail["turns"][0]
    assert after["turn_id"] == before["turn_id"]
    assert after["context_snapshot_id"] == before["context_snapshot_id"]
    assert after["run_id"] == "run_9"
    assert result.response_id == before["result"]["response_id"]
    assert len(result.tool_traces) > len(before["result"]["tool_traces"])
    assert sum(trace.tool_name == "fundamentals.propose_dcf_update" for trace in result.tool_traces) == 1
    assert bool(service.fundamentals_service.saved_payload) == (decision == "approve")
    assert len(service.fundamentals_service.saved_snapshots) == (1 if decision == "approve" else 0)
    assert all(event.run_id == "run_9" for event in result.operator_events)
    assert service.run_recovery.get("run_9")["status"] == result.status
    with pytest.raises(ValueError, match="already accepted"):
        decide(service, mutation, decision)


@pytest.mark.parametrize("overrides", [
    {"role": "research_agent"}, {"session_id": "other"}, {"mutation_id": "other"},
    {"confirmation_token": "wrong"}, {"proposal_hash": "wrong"}, {"context_fingerprint": "changed"},
])
def test_invalid_decisions_never_write(setup, overrides):
    _, service, _, mutation = setup
    with pytest.raises(ValueError):
        decide(service, mutation, **overrides)
    assert service.fundamentals_service.saved_payload is None
    assert service.run_recovery.get("run_9")["status"] == "awaiting_confirmation"


def test_stale_saved_dcf_can_be_rejected_but_not_overwritten(setup):
    _, service, _, mutation = setup
    current = service._dcf_payload_from_model(service.fundamentals_service.get_dcf_model("AAPL"))
    current["scenarios"]["base"]["assumptions"]["wacc_pct"] = .12
    service.fundamentals_service.save_dcf_model("AAPL", current)
    with pytest.raises(ValueError, match="saved DCF changed"):
        decide(service, mutation)
    decide(service, mutation, "reject")
    assert service.fundamentals_service.saved_payload == current
    assert not service.fundamentals_service.saved_snapshots


def test_expired_or_tampered_proposal_never_writes(setup):
    _, service, _, mutation = setup
    service.store.update_mutation(mutation.mutation_id, lambda item: replace(item, expires_at=now_utc() - timedelta(seconds=1)))
    with pytest.raises(ValueError, match="expired"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_rollback_snapshot_required(setup, monkeypatch):
    _, service, _, mutation = setup
    monkeypatch.setattr(service.fundamentals_service, "save_dcf_snapshot", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="rollback snapshot"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None
    assert service.run_recovery.get("run_9")["status"] == "recovery_required"
    with pytest.raises(ValueError):
        decide(service, mutation, "recover")


def test_concurrent_approval_applies_once(setup):
    _, service, _, mutation = setup
    def submit():
        try:
            return decide(service, mutation).status
        except ValueError:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: submit(), range(2)))
    assert statuses.count("blocked") == 1
    assert len(service.fundamentals_service.saved_snapshots) == 1


def test_crash_after_commit_recovers_without_reapplying(setup, monkeypatch):
    _, service, _, mutation = setup
    execute = service.execute_research_operator_plan
    monkeypatch.setattr(service, "execute_research_operator_plan", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash after commit")))
    with pytest.raises(RuntimeError):
        decide(service, mutation)
    assert service.store.get_mutation(mutation.mutation_id).status == "applied"
    monkeypatch.setattr(service, "execute_research_operator_plan", execute)
    result = decide(service, mutation, "recover")
    assert result.status == "ready"
    assert len(service.fundamentals_service.saved_snapshots) == 1
    assert sum(trace.tool_name == "fundamentals.apply_dcf_update" for trace in result.tool_traces) == 1


def test_api_decision_requires_operator_and_preserves_turn(setup):
    client, _, _, mutation = setup
    payload = dict(mutation_id=mutation.mutation_id, user_session_id="session_9", role="research_agent", decision="reject")
    assert client.post("/copilot/runs/run_9/decision", json=payload).status_code == 409
    payload["role"] = "research_operator"
    response = client.post("/copilot/runs/run_9/decision", json=payload)
    assert response.status_code == 200
    assert len(client.get("/copilot/sessions/session_9").json()["turns"]) == 1


def test_pause_stream_is_not_terminal(setup):
    _, service, request, _ = setup
    events = list(service.stream_research_operator_events(replace(request, user_session_id="session_stream9"), run_id="run_stream9"))
    assert events[-1].event_type == "run.paused"
    assert not any(event.is_terminal for event in events)
    assert events[-1].result.status == "awaiting_confirmation"
    service._runs.clear()
    replay = list(service.stream_existing_run_events("run_stream9"))
    assert [(event.sequence, event.event_type) for event in replay] == [(event.sequence, event.event_type) for event in events]


def test_cancel_paused_run_never_applies(setup):
    client, service, _, mutation = setup
    assert service.cancel_run("run_9")["cancelled"]
    assert service.store.get_mutation(mutation.mutation_id).status == "rejected"
    assert client.get("/copilot/sessions/session_9").json()["turns"][0]["result"]["status"] == "cancelled"
    with pytest.raises(ValueError):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_duplicate_execute_is_replay_and_changed_request_is_blocked(setup):
    _, service, request, _ = setup
    result = service.execute_research_operator_plan(request, run_id="run_9")
    assert result.status == "awaiting_confirmation"
    assert len(service.store.list_mutations("session_9")) == 1
    with pytest.raises(ValueError, match="different persisted request"):
        service.execute_research_operator_plan(replace(request, prompt="Set WACC to 12%"), run_id="run_9")


def test_deleted_session_cannot_be_resurrected(setup):
    _, service, _, mutation = setup
    deleted = service.delete_session("session_9", confirmation="session_9")
    assert deleted.deleted_counts["runs"] == 1
    assert deleted.deleted_counts["mutations"] == 1
    assert service.run_recovery.get("run_9") is None
    with pytest.raises(ValueError, match="deleted"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_tampered_payload_hash_is_rejected(setup):
    _, service, _, mutation = setup
    service.store.update_mutation(mutation.mutation_id,
        lambda item: replace(item, proposed_payload={**item.proposed_payload, "active_scenario_id": "bull"}))
    with pytest.raises(ValueError, match="reviewed proposal"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_insufficient_original_budget_cannot_apply(setup):
    _, service, _, mutation = setup
    state = service.run_recovery.get("run_9")
    service.run_recovery.save({**state, "remaining_tools": 0})
    with pytest.raises(ValueError, match="budget"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_transport_retry_is_bounded_and_does_not_retry_mutation(setup, monkeypatch):
    _, service, _, mutation = setup
    original = service._execute_registered_operator_action
    calls = []
    from src.models.copilot import CopilotToolExecution, CopilotToolTrace
    def fail_once(tool_id, arguments, context, **kwargs):
        calls.append(tool_id)
        if len(calls) == 1:
            return CopilotToolExecution(output={"error": "temporary timeout", "retryable": True},
                trace=CopilotToolTrace(tool_name=tool_id, arguments=arguments, summary="temporary timeout"))
        return original(tool_id, arguments, context, **kwargs)
    monkeypatch.setattr(service, "_execute_registered_operator_action", fail_once)
    result = decide(service, mutation)
    assert calls[0] == calls[1]
    assert any(event.payload.get("retry_attempt") == 1 for event in result.operator_events)
    assert len(service.fundamentals_service.saved_snapshots) == 1
    state = service.run_recovery.get("run_9")
    assert state["remaining_tools"] == state["plan"]["max_tool_calls"] - len(result.tool_traces)


def test_replan_rechecks_read_permissions_without_gaining_tools(setup, monkeypatch):
    _, service, _, mutation = setup
    state = service.run_recovery.get("run_9")
    forbidden = state["plan"]["steps"][1]["tool_id"]
    authorize = service.action_registry.authorize_automatic
    from src.application.research_action_registry import ResearchActionPermissionError
    def recheck(tool_id):
        if tool_id == forbidden:
            raise ResearchActionPermissionError("Read permission removed since preview.")
        return authorize(tool_id)
    monkeypatch.setattr(service.action_registry, "authorize_automatic", recheck)
    result = decide(service, mutation, "reject")
    assert not any(trace.tool_name == forbidden for trace in result.tool_traces)
    revision = service.run_recovery.get("run_9")["plan_revisions"][-1]
    assert revision["omitted_steps"]
    assert set(revision["remaining_step_ids"]) <= {step["step_id"] for step in state["plan"]["steps"]}


def test_read_recovery_keeps_completed_observations_and_spent_budget(setup, monkeypatch):
    _, service, _, mutation = setup
    original = service._execute_registered_operator_action
    calls = []
    def crash_second(tool_id, arguments, context, **kwargs):
        calls.append(tool_id)
        if len(calls) == 2:
            raise RuntimeError("interrupted read")
        return original(tool_id, arguments, context, **kwargs)
    monkeypatch.setattr(service, "_execute_registered_operator_action", crash_second)
    with pytest.raises(RuntimeError, match="interrupted read"):
        decide(service, mutation)
    spent = service.run_recovery.get("run_9")["remaining_tools"]
    result = decide(service, mutation, "recover")
    assert calls.count(calls[0]) == 1
    assert len(service.fundamentals_service.saved_snapshots) == 1
    assert service.run_recovery.get("run_9")["remaining_tools"] < spent
    assert any("reserved attempt" in trace.summary for trace in result.tool_traces)


def test_malformed_recovery_fails_before_any_write(setup):
    _, service, _, mutation = setup
    state = service.run_recovery.get("run_9")
    service.run_recovery.save({**state, "plan": {}})
    with pytest.raises(ValueError, match="incomplete"):
        decide(service, mutation)
    assert service.fundamentals_service.saved_payload is None


def test_retry_exhaustion_is_typed_and_preserves_original_limits(setup, monkeypatch):
    from collections import Counter
    from src.models.copilot import CopilotToolExecution, CopilotToolTrace
    _, service, _, mutation = setup
    calls = Counter()
    initial = service.run_recovery.get("run_9")
    def unavailable(tool_id, arguments, context, **kwargs):
        calls[tool_id] += 1
        return CopilotToolExecution(output={"error": "timeout", "retryable": True},
            trace=CopilotToolTrace(tool_name=tool_id, arguments=arguments, summary="timeout"))
    monkeypatch.setattr(service, "_execute_registered_operator_action", unavailable)
    result = decide(service, mutation)
    assert result.status == "degraded"
    assert calls and max(calls.values()) <= 2
    assert any(event.payload.get("stop_reason") == "tool_retry_exhausted" for event in result.operator_events)
    final = service.run_recovery.get("run_9")
    assert final["remaining_tools"] >= 0
    assert final["plan"]["max_tool_calls"] == initial["plan"]["max_tool_calls"]
    assert len(service.fundamentals_service.saved_snapshots) == 1


def test_streamed_decision_progress_and_reconnect_keep_run_and_turn(setup):
    import json
    client, service, _, mutation = setup
    before = service.store.list_turns("session_9")[0]
    response = client.post("/copilot/runs/run_9/decision/stream", json={
        "mutation_id": mutation.mutation_id, "user_session_id": "session_9", "role": "research_operator",
        "decision": "approve", "confirmation_token": mutation.confirmation_token,
        "context_fingerprint": "context_9", "proposal_hash": mutation.proposal_hash,
    })
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["event"] == "run.resumed"
    assert any(event["event"] == "tool.call" for event in events)
    assert events[-1]["event"] == "completed"
    assert all(event["run_id"] == "run_9" for event in events)
    replay = client.get(f"/copilot/runs/run_9/events?after_sequence={events[0]['sequence']}")
    assert [json.loads(line) for line in replay.text.splitlines()] == events[1:]
    assert service.store.list_turns("session_9")[0].turn_id == before.turn_id
    assert len(service.fundamentals_service.saved_snapshots) == 1


def test_streamed_interrupted_continuation_can_recover_once(setup, monkeypatch):
    _, service, _, mutation = setup
    execute = service.execute_research_operator_plan
    monkeypatch.setattr(service, "execute_research_operator_plan", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("interrupted continuation")))
    kwargs = dict(run_id="run_9", mutation_id=mutation.mutation_id, session_id="session_9", role="research_operator",
        decision="approve", confirmation_token=mutation.confirmation_token,
        context_fingerprint="context_9", proposal_hash=mutation.proposal_hash)
    events = list(service.stream_operator_approval_events(**kwargs))
    assert events[-1].event_type == "failed"
    assert events[-1].result.status == "interrupted"
    assert service.store.list_turns("session_9")[0].result.status == "interrupted"
    monkeypatch.setattr(service, "execute_research_operator_plan", execute)
    events = list(service.stream_operator_approval_events(**{**kwargs, "decision": "recover"}))
    assert events[-1].result.status == "ready"
    assert len(service.fundamentals_service.saved_snapshots) == 1


def test_cancel_resumed_run_stops_at_safe_boundary_without_undo_or_repeat(setup, monkeypatch):
    import threading
    _, service, _, mutation = setup
    entered, release = threading.Event(), threading.Event()
    original = service._execute_registered_operator_action
    calls = []
    def blocked(tool_id, arguments, context, **kwargs):
        calls.append(tool_id)
        entered.set()
        assert release.wait(5)
        return original(tool_id, arguments, context, **kwargs)
    monkeypatch.setattr(service, "_execute_registered_operator_action", blocked)
    events = service.stream_operator_approval_events(run_id="run_9", mutation_id=mutation.mutation_id,
        session_id="session_9", role="research_operator", decision="approve",
        confirmation_token=mutation.confirmation_token, context_fingerprint="context_9", proposal_hash=mutation.proposal_hash)
    assert entered.wait(5)
    assert service.cancel_run("run_9")["cancelled"]
    release.set()
    result = list(events)[-1].result
    assert result.status == "cancelled"
    assert len(calls) == 1
    assert service.store.get_mutation(mutation.mutation_id).status == "applied"
    assert len(service.fundamentals_service.saved_snapshots) == 1
    with pytest.raises(ValueError):
        decide(service, mutation, "recover")


def test_stale_streamed_preview_remains_rejectable(setup):
    _, service, _, mutation = setup
    events = list(service.stream_operator_approval_events(run_id="run_9", mutation_id=mutation.mutation_id,
        session_id="session_9", role="research_operator", decision="approve",
        confirmation_token=mutation.confirmation_token, context_fingerprint="new_context", proposal_hash=mutation.proposal_hash))
    assert events[-1].event_type == "run.paused"
    assert events[-1].result.status == "awaiting_confirmation"
    assert "context changed" in events[-1].result.message
    assert "context changed" in service.store.list_turns("session_9")[0].result.message
    assert service.fundamentals_service.saved_payload is None
    assert decide(service, mutation, "reject").status == "ready"


def test_stop_before_streamed_decision_commits_does_not_wait_for_approval_lock(setup):
    _, service, _, mutation = setup
    # Hold the decision at its serialized boundary while Stop stays responsive.
    with service._approval_lock:
        events = service.stream_operator_approval_events(run_id="run_9", mutation_id=mutation.mutation_id,
            session_id="session_9", role="research_operator", decision="approve",
            confirmation_token=mutation.confirmation_token, context_fingerprint="context_9", proposal_hash=mutation.proposal_hash)
        assert service.cancel_run("run_9")["cancelled"]
    assert list(events)[-1].result.status == "cancelled"
    assert service.fundamentals_service.saved_payload is None
    assert service.store.get_mutation(mutation.mutation_id).status == "rejected"
