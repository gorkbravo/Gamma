"""Workstream 12 - Ideas, checkpoint I5: what Copilot sees and proposes about ideas.

Pure facts and validation only (no model call): the Ideas context, the
``review_idea`` and ``explain_criterion_state`` facts, and the
``draft_idea_from_context`` proposal and its acceptance as a draft idea.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.application.idea_copilot import (
    build_idea_draft,
    draft_from_dict,
    draft_tool_schema,
    explain_criterion_facts,
    idea_context_summary,
    review_idea_facts,
)
from src.application.idea_observables import ObservableRegistry
from src.application.idea_service import IdeaCreateRequest, IdeaService
from src.models.ideas import IdeaOrigin, IdeaValidationError
from src.services.idea_explanations import EXPLANATIONS
from src.services.idea_store import IdeaStore
from test_idea_tracking import _Clock, _ids, _leg


class _Registry:
    """The real registry's validation and wording, with every observable available."""

    def __init__(self) -> None:
        self._real = ObservableRegistry()

    def validate(self, ref, *, condition, cadence):
        return self._real.validate(ref, condition=condition, cadence=cadence)

    def describe(self, ref, *, condition, threshold, window):
        return self._real.describe(ref, condition=condition, threshold=threshold, window=window)

    def describe_all(self):
        rows = self._real.describe_all()
        for row in rows:
            if row["observable_id"] == "option_atm_iv":
                row.update(available=False, unavailable_reason="Needs Trader Workstation.")
            else:
                row.update(available=True, unavailable_reason=None)
        return rows


DRAFT = {
    "title": "Oil producers lag crude",
    "thesis": "XOM underperforms Brent while OPEC adds supply.",
    "stance": "relative",
    "legs": [
        {"entity_type": "equity", "symbol": "XOM", "weight": -1},
        {"entity_type": "etf", "symbol": "USO", "weight": 1},
    ],
    "criteria": [
        {"kind": "invalidate", "observable_id": "equity_close", "params": [{"name": "symbol", "value": "XOM"}],
         "condition": "change_over_window", "threshold": 8, "window": "1m", "rationale": "A rally in XOM breaks the lag."},
        {"kind": "review", "observable_id": "calendar_date", "params": [{"name": "date", "value": "2026-12-31"}],
         "condition": "date_reached", "threshold": None, "window": None, "rationale": "Year-end check."},
    ],
    "rationale": "The Commodities card shows Brent backwardation widening.",
}


def _service(tmp_path):
    clock = _Clock(datetime(2026, 11, 20, 12, 0))
    service = IdeaService(IdeaStore(tmp_path / "ideas"), clock=clock, id_factory=_ids())
    service.criteria_registry = _Registry()
    return clock, service


def test_a_draft_is_validated_against_the_registry_and_changes_nothing(tmp_path):
    clock, service = _service(tmp_path)
    proposal = build_idea_draft(DRAFT, _Registry(), source_label="Commodities card")
    assert proposal.stance == "relative" and [leg.entity.normalized_id for leg in proposal.legs] == ["XOM", "USO"]
    assert [item.label for item in proposal.criteria] == ["XOM close up 8.00% or more over 1 month", "Date reached 2026-12-31"] or all(item.label for item in proposal.criteria)
    assert proposal.criteria[0].observable.params["symbol"] == "XOM"
    assert proposal.to_dict()["creates"].startswith("A draft idea.")
    # Proponer no escribe nada.
    assert service.list_ideas().items == []
    # Round trip por el JSON que guarda el flujo de confirmación.
    assert draft_from_dict(proposal.to_dict()).to_dict() == proposal.to_dict()


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"criteria": DRAFT["criteria"][:1]}, "between 2 and 4"),
        ({"stance": "bullish"}, "stance"),
        ({"legs": [{"entity_type": "future", "symbol": "CL", "weight": 1}]}, "equity, ETF or crypto"),
        ({"criteria": [{**DRAFT["criteria"][0], "observable_id": "script_signal"}, DRAFT["criteria"][1]]}, "not one Copilot can propose"),
        ({"criteria": [{**DRAFT["criteria"][0], "threshold": None}, DRAFT["criteria"][1]]}, "needs a threshold"),
        ({"criteria": [{**DRAFT["criteria"][0], "params": []}, DRAFT["criteria"][1]]}, "needs"),
        ({"thesis": ""}, "thesis"),
    ],
)
def test_bad_drafts_are_refused_with_the_reason(patch, message):
    with pytest.raises(IdeaValidationError, match=message):
        build_idea_draft({**DRAFT, **patch}, _Registry())


def test_a_draft_without_invalidation_or_with_unavailable_rules_carries_warnings():
    criteria = [
        {**DRAFT["criteria"][0], "kind": "confirm"},
        {"kind": "review", "observable_id": "option_atm_iv", "params": [{"name": "symbol", "value": "XOM"}],
         "condition": "above", "threshold": 40, "window": None, "rationale": "IV spike."},
    ]
    proposal = build_idea_draft({**DRAFT, "criteria": criteria}, _Registry())
    assert any("No invalidation criterion" in item for item in proposal.warnings)
    assert any("unavailable right now" in item and "Trader Workstation" in item for item in proposal.warnings)


def test_accepting_a_draft_creates_a_draft_idea_with_its_criteria_in_one_write(tmp_path):
    clock, service = _service(tmp_path)
    proposal = build_idea_draft(DRAFT, _Registry(), source_label="Commodities card")
    idea = service.create_idea_from_draft(proposal, origin=IdeaOrigin(kind="copilot", source_ref="run-1", label="Commodities card"))
    assert idea.status == "draft" and idea.origin.kind == "copilot" and idea.origin.source_ref == "run-1"
    assert [item.kind for item in idea.criteria] == ["invalidate", "review"]
    assert all(item.state == "pending" for item in idea.criteria)
    assert idea.notes.startswith("Copilot's rationale:")
    kinds = [entry.kind for entry in idea.journal]
    assert kinds == ["created", "criterion_added", "criterion_added"]
    assert "Copilot draft you accepted" in idea.journal[0].body
    assert idea.tracking is None  # un borrador no se sigue
    # Un criterio que el registro rechaza no deja nada a medias.
    bad = draft_from_dict({**proposal.to_dict(), "criteria": [{**proposal.to_dict()["criteria"][0], "condition": "event_occurs"}]})
    with pytest.raises(IdeaValidationError):
        service.create_idea_from_draft(bad, origin=IdeaOrigin(kind="copilot"))
    assert len(service.list_ideas().items) == 1


def test_a_drafted_leg_is_named_by_its_ticker_not_by_the_model(tmp_path):
    """GUA-20261124-9: the energy draft showed the model's note ("Proposed oil ETF proxy; …") as the leg."""
    note = "Proposed oil ETF proxy; verify tracking error against Brent before use"
    legs = [
        {"entity_type": "etf", "symbol": "uso", "label": note, "weight": 1},
        {"entity_type": "crypto", "symbol": "Bitcoin", "label": "Digital gold proxy", "weight": None},
    ]
    proposal = build_idea_draft({**DRAFT, "legs": legs}, _Registry())
    assert [leg.entity.label for leg in proposal.legs] == ["USO", "bitcoin"]
    assert [leg.entity.normalized_id for leg in proposal.legs] == ["USO", "BITCOIN"]
    payload = proposal.to_dict()
    assert [(leg["symbol"], leg["label"]) for leg in payload["legs"]] == [("USO", "USO"), ("bitcoin", "bitcoin")]
    assert note not in str(payload)
    # Una propuesta guardada antes del cambio conserva la nota en su JSON: aceptarla crea la pata con el ticker.
    stored = {**payload, "legs": [{**payload["legs"][0], "label": note}]}
    _, service = _service(tmp_path)
    idea = service.create_idea_from_draft(draft_from_dict(stored), origin=IdeaOrigin(kind="copilot", source_ref="run-4"))
    assert [leg.entity.label for leg in idea.legs] == ["USO"]
    # El modelo ya no rellena la etiqueta: el esquema solo pide tipo, símbolo y peso.
    leg_schema = draft_tool_schema()["properties"]["legs"]["items"]
    assert sorted(leg_schema["properties"]) == ["entity_type", "symbol", "weight"]


def test_the_tool_schema_is_strict():
    schema = draft_tool_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert sorted(node["required"]) == sorted(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)


def _active_idea(tmp_path):
    clock, service = _service(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Pair", thesis="AAPL beats MSFT.", stance="relative", legs=(_leg("AAPL", 1), _leg("MSFT", -1))))
    from src.application.idea_service import IdeaCriterionRequest
    from src.models.ideas import ObservableRef

    idea, criterion = service.add_criterion(idea.idea_id, IdeaCriterionRequest(
        kind="invalidate", observable=ObservableRef(observable_id="equity_close", params={"symbol": "AAPL"}), condition="below", threshold=150))
    clock.set(datetime(2026, 11, 21, 12, 0))
    service.activate(idea.idea_id)
    return clock, service, service.get_idea(idea.idea_id), criterion


def test_the_context_summary_keeps_states_provenance_and_the_boundary(tmp_path):
    clock, service, idea, criterion = _active_idea(tmp_path)
    summary = idea_context_summary(idea, review_statistics={"closed": 0})
    assert summary["thesis"] == "AAPL beats MSFT." and summary["status"] == "active"
    assert summary["criteria"][0]["state"] == "pending" and summary["criteria"][0]["observable"]["params"] == {"symbol": "AAPL"}
    assert summary["tracking"]["label"] == "Hypothetical, not executed" and summary["tracking"]["segments"] == 1
    assert summary["journal_tail"][-1]["kind"] == "tracking_segment"
    assert summary["review_statistics"] == {"closed": 0}
    assert "user decides every change" in summary["boundary"]


def test_explain_criterion_reads_its_own_evaluation_and_the_registry(tmp_path):
    clock, service, idea, criterion = _active_idea(tmp_path)
    facts = explain_criterion_facts(idea, criterion.criterion_id, EXPLANATIONS)
    assert facts["state"] == "pending" and "Not evaluated yet" in facts["state_reading"]
    assert facts["explanations"]["condition"]["title"] and facts["explanations"]["observable"]["why_for_this_stance"]
    assert facts["decisive_evaluation"] is None
    with pytest.raises(IdeaValidationError, match="not on idea"):
        explain_criterion_facts(idea, "missing", EXPLANATIONS)


def test_review_facts_compare_expected_and_realized_and_list_verdicts(tmp_path):
    clock, service, idea, criterion = _active_idea(tmp_path)
    facts = review_idea_facts(idea)
    assert facts["expected"] == "AAPL beats MSFT." and facts["outcome"] is None
    assert any("no review yet" in note for note in facts["notes"])
    from src.application.idea_service import IdeaCloseRequest

    clock.set(datetime(2026, 11, 28, 12, 0))
    closed = service.close(idea.idea_id, IdeaCloseRequest(outcome="invalidated", lesson="The pair reverted faster than expected."))
    facts = review_idea_facts(closed)
    assert facts["outcome"] == "invalidated" and facts["lesson"].startswith("The pair")
    assert facts["realized_at_close"] is not None or closed.tracking is not None
    assert facts["invalidation_fired"] is False and facts["label"] == "Hypothetical, not executed"
