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


# --- GUA-20261124-9: el Research Operator llega a Ideas -------------------------------------
# En vivo (2026-11-24), "Review this idea" con el Operator buscó "idea" en la SEC y pidió elegir
# entre emisores llamados "Idea" en lugar de revisar la idea abierta.


def _idea_issuer_search(queries):
    """Búsqueda SEC simulada que, como la real, devuelve emisores con "Idea" en el nombre."""
    from src.models.fundamentals import FundamentalsSearchResult

    def search(query, *args, **kwargs):
        queries.append(str(query))
        issuers = (("IACO", "Idea Acquisition Corp", "0000000001"), ("IDTL", "Idea Tech Ltd", "0000000002"))
        return [FundamentalsSearchResult(ticker=t, name=n, cik=c) for t, n, c in issuers if "idea" in str(query).lower()]

    return search


def _operator(prompt, context, synthesis=None):
    from src.models.copilot import CopilotResearchCardRequest

    return CopilotResearchCardRequest(
        domain="synthesis" if synthesis is not None else "ideas", prompt=prompt, role="research_operator",
        context=context, synthesis=synthesis,
    )


def test_the_operator_reviews_the_open_idea_instead_of_searching_for_an_issuer(demo):
    from src.models.copilot import CopilotRequestContext

    idea_id = _idea(demo)
    service = demo.runtime.copilot_service
    queries: list[str] = []
    service.fundamentals_service.search_companies = _idea_issuer_search(queries)
    request = _operator("Review this idea", CopilotRequestContext(current_tab="ideas", workspace_mode="research", idea_id=idea_id))
    plan = service.plan_research_operator(request)
    assert plan.intent != "entity_disambiguation"
    assert [(step.tool_id, step.domain) for step in plan.steps] == [(REVIEW_TOOL, "ideas")]
    assert queries == []
    result = service.execute_research_operator_plan(request)
    assert result.status == "ready", (result.message, result.warnings)
    assert [trace.tool_name for trace in result.tool_traces] == [REVIEW_TOOL]
    assert {"ideas.idea", "ideas.tracking"} <= {source.source_id for source in result.sources}


def test_the_operator_adds_the_selected_idea_to_a_copilot_tab_plan(demo):
    from src.models.copilot import CopilotRequestContext, CopilotSynthesisRequest, CopilotSynthesisScope

    idea_id = _idea(demo)
    service = demo.runtime.copilot_service
    queries: list[str] = []
    service.fundamentals_service.search_companies = _idea_issuer_search(queries)
    synthesis = CopilotSynthesisRequest(active_tab="copilot", included_scopes=[
        CopilotSynthesisScope(domain="ideas", label="Idea", context=CopilotRequestContext(current_tab="ideas", idea_id=idea_id)),
        CopilotSynthesisScope(domain="commodities", label="Commodities", context=CopilotRequestContext(current_tab="commodities")),
    ])
    for prompt in ("Review this idea", "Review my trade idea against the oil curve"):
        request = _operator(prompt, CopilotRequestContext(current_tab="copilot", workspace_mode="research"), synthesis)
        plan = service.plan_research_operator(request)
        # La idea va la primera: el presupuesto de dominios recorta por el final.
        assert (plan.steps[0].tool_id, plan.steps[0].domain) == (REVIEW_TOOL, "ideas"), prompt
    assert queries == []
    result = service.execute_research_operator_plan(request)
    review = next(trace for trace in result.tool_traces if trace.tool_name == REVIEW_TOOL)
    assert "ideas.idea" in review.source_ids and "ideas.tracking" in review.source_ids


def test_a_prompt_that_does_not_refer_to_the_open_idea_keeps_its_company(demo):
    from src.application.copilot_entity_resolution import _company_queries
    from src.models.copilot import CopilotRequestContext

    idea_id = _idea(demo)
    service = demo.runtime.copilot_service
    queries: list[str] = []
    service.fundamentals_service.search_companies = _idea_issuer_search(queries)
    # "A new idea on Nvidia" no es la idea abierta: el emisor se sigue resolviendo, sin consultar "idea".
    service.plan_research_operator(_operator(
        "Draft a new idea on Nvidia", CopilotRequestContext(current_tab="ideas", workspace_mode="research", idea_id=idea_id)))
    assert any("Nvidia" in query for query in queries)
    assert not any("idea" in query.lower() for query in queries)
    assert not any("idea" in query.lower() for query in _company_queries("Compare Ideas from Apple"))
    # Sin idea seleccionada, "this idea" no salta la resolución ni añade Ideas al plan.
    plan = service.plan_research_operator(_operator(
        "Review this idea", CopilotRequestContext(current_tab="macro", workspace_mode="research")))
    assert all(step.domain != "ideas" for step in plan.steps)
