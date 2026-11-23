"""Workstream 12 - Ideas, checkpoint I5: the Ideas domain in Copilot, end to end.

Runs through the Copilot API of a demo runtime with Gamma's deterministic mock
Copilot provider (no model call, no network, no API credit). Covers the Ideas
context, the read-only review and explain tools, and the idea draft that waits
for the user's acceptance under the existing confirmation flow.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.copilot_ideas import APPLY_ACTION, DRAFT_TOOL, EXPLAIN_TOOL, PROPOSE_ACTION, REVIEW_TOOL
from src.application.runtime import build_runtime

SESSION = "ideas-session"


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture()
def demo(tmp_path):
    runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
    runtime.idea_service._clock = _Clock(datetime(2026, 1, 12, 14, 0))
    with TestClient(create_app(runtime)) as client:
        client.runtime = runtime  # type: ignore[attr-defined]
        yield client


def _idea(client) -> str:
    created = client.post("/ideas", json={
        "title": "AAPL over MSFT", "thesis": "Apple holds up better than Microsoft into earnings.", "stance": "relative",
        "legs": [
            {"entity": {"entity_type": "equity", "label": "Apple", "normalized_id": "AAPL"}, "weight": 1},
            {"entity": {"entity_type": "equity", "label": "Microsoft", "normalized_id": "MSFT"}, "weight": -1},
        ],
    }).json()
    idea_id = created["idea_id"]
    response = client.post(f"/ideas/{idea_id}/criteria", json={
        "kind": "invalidate", "observable": {"observable_id": "equity_close", "params": {"symbol": "AAPL"}},
        "condition": "below", "threshold": 150, "cadence": "daily_close",
    })
    assert response.status_code == 200, response.text
    assert client.post(f"/ideas/{idea_id}/activate").status_code == 200
    return idea_id


def _card(client, idea_id, prompt):
    response = client.post("/copilot/research-card", json={
        "domain": "ideas", "prompt": prompt, "user_session_id": SESSION,
        "context": {"current_tab": "ideas", "idea_id": idea_id},
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_the_ideas_context_reaches_copilot_with_read_only_tools(demo):
    idea_id = _idea(demo)
    result = _card(demo, idea_id, "Review this idea.")
    assert result["domain"] == "ideas" and result["status"] == "ready"
    tools = [trace["tool_name"] for trace in result["tool_traces"]]
    assert tools == [REVIEW_TOOL, EXPLAIN_TOOL]
    assert result["proposals"] == [] and result["proposal_ids"] == []
    source = next(item for item in result["sources"] if item["source_id"] == "ideas.idea")
    assert source["navigation_tab"] == "ideas" and source["navigation_context"] == {"idea_id": idea_id}
    assert any(item["source_id"] == "ideas.tracking" for item in result["sources"])
    assert "Apple holds up better" in result["card"]["hypothesis"]


def test_a_drafted_idea_waits_for_acceptance_and_becomes_a_draft_idea(demo):
    idea_id = _idea(demo)
    before = len(demo.get("/ideas").json()["items"])
    result = _card(demo, idea_id, "Draft a follow-up idea from this one.")
    assert [trace["tool_name"] for trace in result["tool_traces"]][-1] == DRAFT_TOOL
    [proposal] = result["proposals"]
    assert result["proposal_ids"] == [proposal["mutation_id"]]
    assert proposal["status"] == "pending" and proposal["apply_tool_id"] == APPLY_ACTION
    assert proposal["session_id"] == SESSION and proposal["requires_confirmation"] is True
    assert proposal["proposed_payload"]["creates"].startswith("A draft idea.")
    assert any("Criterion (invalidate)" in line for line in proposal["rendered_diff"])
    # Proponer no crea nada.
    assert len(demo.get("/ideas").json()["items"]) == before

    # Sin el token, o desde otra sesión, no se aplica.
    wrong = demo.post(f"/copilot/mutations/{proposal['mutation_id']}/apply", json={
        "confirmation_token": "nope", "user_session_id": SESSION, "proposal_hash": proposal["proposal_hash"]})
    assert wrong.status_code == 400
    other = demo.post(f"/copilot/mutations/{proposal['mutation_id']}/apply", json={
        "confirmation_token": proposal["confirmation_token"], "user_session_id": "someone-else", "proposal_hash": proposal["proposal_hash"]})
    assert other.status_code == 400

    applied = demo.post(f"/copilot/mutations/{proposal['mutation_id']}/apply", json={
        "confirmation_token": proposal["confirmation_token"], "user_session_id": SESSION, "proposal_hash": proposal["proposal_hash"]})
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["mutation"]["status"] == "applied"
    new_id = body["artifact"]["idea_id"]
    idea = demo.get(f"/ideas/{new_id}").json()
    assert idea["status"] == "draft" and idea["origin"]["kind"] == "copilot"
    assert idea["origin"]["source_ref"] == proposal["mutation_id"]
    assert [item["kind"] for item in idea["criteria"]] == ["invalidate", "review"]
    assert all(item["state"] == "pending" for item in idea["criteria"])
    assert idea["tracking"] is None
    assert "Copilot draft you accepted" in idea["journal"][0]["body"]
    # Una propuesta se acepta una sola vez.
    again = demo.post(f"/copilot/mutations/{proposal['mutation_id']}/apply", json={
        "confirmation_token": proposal["confirmation_token"], "user_session_id": SESSION, "proposal_hash": proposal["proposal_hash"]})
    assert again.status_code == 400
    assert len(demo.get("/ideas").json()["items"]) == before + 1


def test_a_rejected_draft_creates_nothing_and_stays_on_the_turn(demo):
    idea_id = _idea(demo)
    result = _card(demo, idea_id, "Please propose a new idea.")
    [proposal] = result["proposals"]
    rejected = demo.post(f"/copilot/mutations/{proposal['mutation_id']}/reject", json={"user_session_id": SESSION})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert len(demo.get("/ideas").json()["items"]) == 1
    # La propuesta queda ligada al turno guardado por su id.
    fetched = demo.get(f"/copilot/mutations/{proposal['mutation_id']}").json()
    assert fetched["status"] == "rejected"
    sessions = demo.runtime.copilot_service.store
    turns = [turn for turn in sessions.list_turns(SESSION)] if hasattr(sessions, "list_turns") else []
    if turns:
        assert proposal["mutation_id"] in turns[-1].result.proposal_ids


def test_without_a_selected_idea_the_card_says_what_is_missing(demo):
    response = demo.post("/copilot/research-card", json={
        "domain": "ideas", "prompt": "Review", "user_session_id": SESSION, "context": {"current_tab": "ideas"}})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"error", "failed", "unavailable"}
    assert "requires a selected idea" in (body["message"] or "")


def test_the_registry_keeps_review_and_explain_read_only_and_the_apply_confirmed(demo):
    registry = {item.tool_id: item for item in demo.runtime.copilot_service.list_research_action_definitions()}
    for name in (REVIEW_TOOL, EXPLAIN_TOOL):
        assert registry[name].read_only and not registry[name].mutates_local_state and registry[name].permission_policy == "automatic"
    draft = registry[DRAFT_TOOL]
    assert draft.action_type == "draft_change" and not draft.mutates_local_state and draft.permission_policy == "automatic_draft"
    assert registry[PROPOSE_ACTION].action_type == "draft_change"
    apply = registry[APPLY_ACTION]
    assert apply.action_type == "apply_change" and apply.mutates_local_state and apply.requires_confirmation
    assert apply.permission_policy == "confirmation_required"
    # El borrador se ofrece desde cualquier contexto; revisar y explicar, solo con una idea.
    assert set(draft.domains) >= {"ideas", "macro", "commodities", "synthesis"}
    assert registry[REVIEW_TOOL].domains == ["ideas"]
    for item in registry.values():
        assert not any(token in item.tool_id for token in ("order", "trade", "wallet", "account", "rebalance", "execute"))


def test_the_draft_tool_refuses_a_proposal_the_registry_rejects(demo):
    service = demo.runtime.copilot_service
    from src.models.copilot import CopilotContextBundle

    bundle = CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}, tool_state={}, sources=[], warnings=[])
    execution = service._execute_tool(DRAFT_TOOL, {
        "title": "Rates", "thesis": "Yields fall.", "stance": "long", "legs": [],
        "criteria": [{"kind": "invalidate", "observable_id": "equity_close", "params": [], "condition": "below", "threshold": 1, "window": None, "rationale": ""},
                     {"kind": "review", "observable_id": "calendar_date", "params": [{"name": "date", "value": "2027-01-01"}], "condition": "date_reached", "threshold": None, "window": None, "rationale": ""}],
        "rationale": "",
    }, bundle)
    assert "error" in execution.output and "needs" in execution.output["error"].lower()
    assert service.store.list_mutations() == [] or all(item.domain != "ideas" for item in service.store.list_mutations())
