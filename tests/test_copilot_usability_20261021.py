"""Regresiones de la auditoría de usabilidad 2026-10-21 (GUA-20261021-6 y GUA-20261021-13).

Todas las pruebas son herméticas: el proveedor OpenAI se sustituye por flujos simulados y
nunca se hace una llamada real.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.application.copilot_context_helpers import coalesce_warnings, summarize_commodities_workspace
from src.application.copilot_entity_resolution import (
    _safe_search,
    extract_explicit_equity_tickers,
    resolve_equity_entity,
    should_attempt_equity_resolution,
)
from src.application.runtime import build_runtime
from src.models.copilot import (
    CopilotContextBundle,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotRequestContext,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSynthesisRequest,
    CopilotSynthesisScope,
    ResearchCard,
)
from src.services.copilot_store import CopilotStore
from src.services.fundamentals_adapters import SecIdentityMissingError
from src.services.openai_copilot_provider import (
    MAX_RESEARCH_CARD_OUTPUT_TOKENS,
    OpenAIResponsesCopilotProvider,
    expanded_output_budget,
    requested_section_count,
    research_card_output_budget,
    salvage_partial_research_card,
)

AUDIT_PROMPT = (
    "Using the attached contexts: 1) Dec-26 and Apr-27 Brent and WTI prices and the same-month "
    "spread; 2) the Hormuz normalisation probability; 3) the Strategy Lab and Risk stats; "
    "4) every stale input with its date. Cite sources."
)

CARD = {
    "title": "Brent-WTI prompt premium",
    "hypothesis": "The spread is concentrated in the prompt months.",
    "rationale": "| Delivery | Brent | WTI |\n| --- | ---: | ---: |\n| Dec-26 | 111.05 | 99.93 |",
    "required_data": [],
    "proposed_test": "",
    "confounders": [],
    "next_steps": [],
    "caveats": [],
    "source_backed_claims": [],
    "inferred_claims": [],
}


def _synthesis_context(scope_size: int) -> CopilotContextBundle:
    return CopilotContextBundle(
        domain="synthesis",
        current_tab="synthesis",
        summary_data={"scope_size": scope_size},
    )


def _incomplete_event(partial_text: str = "") -> dict:
    output = (
        [{"type": "message", "content": [{"type": "output_text", "text": partial_text}]}]
        if partial_text
        else []
    )
    return {
        "type": "response.incomplete",
        "response": {
            "id": "resp_cut",
            "model": "gpt-test",
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": output,
            "usage": {"input_tokens": 99_000, "output_tokens": 1_422},
        },
    }


def _completed_event(card: dict) -> dict:
    return {
        "type": "response.completed",
        "response": {
            "id": "resp_ok",
            "model": "gpt-test",
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(card)}]}],
        },
    }


class _ScriptedStreamProvider(OpenAIResponsesCopilotProvider):
    """Devuelve un flujo SSE distinto por llamada y guarda cada carga enviada."""

    def __init__(self, streams: list[list[dict]]):
        super().__init__(api_key="test-key", model="gpt-test", reasoning_effort="medium", store_responses=False)
        self.streams = list(streams)
        self.payloads: list[dict] = []

    def _open_stream(self, payload):
        self.payloads.append(payload)
        return iter(self.streams.pop(0))


def _stream_card(provider: _ScriptedStreamProvider, request: CopilotResearchCardRequest, context):
    emitted: list[tuple[str, dict]] = []
    result = provider.stream_research_card(
        request=request,
        context=context,
        tool_specs=[],
        execute_tool=lambda *args: (_ for _ in ()).throw(AssertionError("no tools expected")),
        emit=lambda event_type, data: emitted.append((event_type, data)),
        should_cancel=lambda: False,
    )
    return result, emitted


# ── GUA-20261021-6: presupuesto, continuación y respuesta parcial ─────────────────────────


def test_output_budget_scales_with_contexts_sections_and_profile_within_ceiling():
    quick_single = research_card_output_budget(
        CopilotResearchCardRequest(domain="macro", prompt="Summarise.", selected_profile="quick"),
        CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
    )
    audit = research_card_output_budget(
        CopilotResearchCardRequest(domain="synthesis", prompt=AUDIT_PROMPT, selected_profile="auto"),
        _synthesis_context(5),
    )
    deep_huge = research_card_output_budget(
        CopilotResearchCardRequest(domain="synthesis", prompt=AUDIT_PROMPT, selected_profile="deep"),
        _synthesis_context(14),
    )

    assert requested_section_count(AUDIT_PROMPT) == 4
    assert quick_single == 2_000
    # Auto se resuelve a standard: 4.000 + 4 contextos extra x 1.500 + 3 partes extra x 600.
    assert audit == 11_800
    assert audit > 1_400 * 8
    assert deep_huge == MAX_RESEARCH_CARD_OUTPUT_TOKENS
    expanded = research_card_output_budget(
        CopilotResearchCardRequest(
            domain="synthesis", prompt=AUDIT_PROMPT, selected_profile="auto", output_budget="expanded"
        ),
        _synthesis_context(5),
    )
    assert expanded == expanded_output_budget(audit) == 23_600
    assert expanded_output_budget(expanded) == MAX_RESEARCH_CARD_OUTPUT_TOKENS


def test_stream_continues_once_with_larger_budget_after_max_output_tokens():
    provider = _ScriptedStreamProvider(
        [
            [
                {"type": "response.output_text.delta", "delta": '{"title": "Brent'},
                _incomplete_event('{"title": "Brent'),
            ],
            [_completed_event(CARD)],
        ]
    )
    request = CopilotResearchCardRequest(domain="synthesis", prompt=AUDIT_PROMPT, selected_profile="auto")
    result, emitted = _stream_card(provider, request, _synthesis_context(5))

    assert result.status == "ready"
    assert result.card is not None and result.card.title == CARD["title"]
    first, second = (payload["max_output_tokens"] for payload in provider.payloads)
    assert first == 11_800
    assert second == expanded_output_budget(first)
    # El segundo intento repite la misma entrada más una nota de concisión de Gamma.
    assert provider.payloads[1]["input"][0] == provider.payloads[0]["input"][0]
    assert "ran out of output tokens" in provider.payloads[1]["input"][-1]["content"][0]["text"]
    continuation = [data for event_type, data in emitted if event_type == "warning"]
    assert continuation and continuation[0]["reset_provisional_text"] is True
    assert continuation[0]["continuation"] == "output_budget_expanded"
    assert not [data for event_type, data in emitted if event_type == "incomplete"]
    assert any("retried the same request once" in warning for warning in result.warnings)


def test_stream_shows_partial_card_when_the_continuation_is_also_cut():
    partial = json.dumps(CARD)[:150]
    provider = _ScriptedStreamProvider(
        [
            [_incomplete_event()],
            [{"type": "response.output_text.delta", "delta": partial}, _incomplete_event(partial)],
        ]
    )
    request = CopilotResearchCardRequest(domain="synthesis", prompt=AUDIT_PROMPT, selected_profile="auto")
    result, emitted = _stream_card(provider, request, _synthesis_context(5))

    assert len(provider.payloads) == 2  # una sola continuación automática
    assert result.status == "incomplete"
    assert ("incomplete", {"reason": "max_output_tokens"}) in emitted
    assert result.card is not None
    assert result.card.title == CARD["title"]
    assert result.card.hypothesis == CARD["hypothesis"]
    assert "partial answer" in (result.message or "")
    assert "max_output_tokens" in (result.message or "")


def test_stream_without_any_text_reports_reasoning_exhaustion_honestly():
    provider = _ScriptedStreamProvider([[_incomplete_event()], [_incomplete_event()]])
    result, _ = _stream_card(
        provider,
        CopilotResearchCardRequest(domain="macro", prompt="Summarise.", selected_profile="quick"),
        CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
    )
    assert result.status == "incomplete"
    assert result.card is None
    assert "No answer text arrived" in (result.message or "")


def test_non_streaming_path_applies_the_same_continuation_policy():
    class _SyncProvider(OpenAIResponsesCopilotProvider):
        def __init__(self, responses):
            super().__init__(api_key="test-key", model="gpt-test", reasoning_effort="low", store_responses=False)
            self.responses = list(responses)
            self.payloads: list[dict] = []

        def _post_json(self, payload):
            self.payloads.append(payload)
            return self.responses.pop(0)

    provider = _SyncProvider([_incomplete_event()["response"], _completed_event(CARD)["response"]])
    result = provider.generate_research_card(
        request=CopilotResearchCardRequest(domain="macro", prompt="Summarise.", selected_profile="quick"),
        context=CopilotContextBundle(domain="macro", current_tab="macro", summary_data={}),
        tool_specs=[],
        execute_tool=lambda *args: None,
    )
    assert result.status == "ready"
    assert [payload["max_output_tokens"] for payload in provider.payloads] == [2_000, 6_000]


def test_operator_loop_continues_once_after_max_output_tokens():
    provider = _ScriptedStreamProvider([[_incomplete_event()], [_completed_event(CARD)]])
    plan = CopilotOperatorPlan(
        intent="commodity_curve_research",
        role="research_operator",
        depth_profile="quick",
        steps=[
            CopilotOperatorPlanStep(
                step_id="step-1",
                order=1,
                title="Inspect curve",
                domain="commodities",
                action_type="read_context",
                tool_id="inspect_commodity_curve_fundamentals",
            )
        ],
        max_tool_calls=2,
        max_provider_calls=2,
        max_elapsed_ms=60_000,
    )
    emitted: list[tuple[str, dict]] = []
    result = provider.stream_research_operator(
        request=CopilotResearchCardRequest(domain="synthesis", prompt="Brent curve", role="research_operator"),
        plan=plan,
        tool_specs=[],
        execute_tool=lambda *args: (_ for _ in ()).throw(AssertionError("no tools expected")),
        emit=lambda event_type, data: emitted.append((event_type, data)),
        should_cancel=lambda: False,
    )
    assert result.status == "ready"
    budgets = [payload["max_output_tokens"] for payload in provider.payloads]
    assert budgets == [1_600, expanded_output_budget(1_600)]
    assert any(data.get("reset_provisional_text") for event_type, data in emitted if event_type == "warning")


def test_salvage_keeps_only_values_that_arrived():
    text = json.dumps(CARD)
    assert salvage_partial_research_card(text[:40]).title == CARD["title"]
    mid_rationale = salvage_partial_research_card(text[: text.index("99.93")])
    assert mid_rationale is not None
    assert mid_rationale.rationale.startswith("| Delivery | Brent | WTI |")
    assert salvage_partial_research_card('{"tit') is None
    assert salvage_partial_research_card("") is None


def _workspace() -> dict:
    retrieved_at = "2026-10-21T10:40:00+00:00"

    def curve(instrument_id: str, symbol: str, prices: list[float]) -> dict:
        return {
            "instrument_id": instrument_id,
            "as_of": retrieved_at,
            "shape_label": "backwardation",
            "front_spread": round(prices[0] - prices[1], 2),
            "nodes": [
                {
                    "contract": {
                        "contract_id": f"{symbol}-{index}",
                        "symbol": f"{symbol}{index}",
                        "contract_month": f"2026-{12 + index:02d}" if index == 0 else f"2027-{index:02d}",
                        "expiry_date": None,
                        "is_front_month": index == 0,
                    },
                    "price": price,
                    "days_to_expiry": 12 + 30 * index,
                    "source_provider": "ibkr",
                    "retrieved_at": retrieved_at,
                    "origin": "ibkr.commodities.curve",
                }
                for index, price in enumerate(prices)
            ],
            "source_provider": "gamma",
            "retrieved_at": retrieved_at,
            "origin": "gamma.commodities.curve_analytics",
            "warnings": [],
        }

    return {
        "mode": "curves_spreads",
        "selected_instrument_id": "wti",
        "source_provider": "gamma",
        "origin": "gamma.commodities.workspace",
        "retrieved_at": retrieved_at,
        "coverage": {"provider_id": "ibkr", "coverage_status": "live", "retrieved_at": retrieved_at, "caveats": []},
        "instruments": [{"instrument_id": "wti"}, {"instrument_id": "brent"}, {"instrument_id": "gold"}],
        "market_summaries": [],
        "spreads": [],
        "curves": [
            curve("wti", "CL", [99.93, 98.05, 96.9, 95.8, 92.19, 91.5]),
            curve("brent", "BZ", [111.05, 107.33, 104.84, 103.15, 97.43, 96.63]),
        ],
        "inventories": [],
        "events": [],
        "warnings": [
            "FRED series GOLDAMGBD228NLBM failed: HTTPError.",
            "FRED series SLVPRUSD failed: HTTPError.",
            "FRED series PPLTUSDM failed: HTTPError.",
        ],
    }


def _strategy_lab_state() -> dict:
    return {
        "composition": {
            "portfolio_inputs": {
                "name": "Brent minus WTI",
                "benchmark_symbol": "SPY",
                "lookback_days": 252,
                "legs": [
                    {"label": "Brent", "asset_class": "commodity", "identifier": "brent", "weight": 1.0},
                    {"label": "WTI", "asset_class": "commodity", "identifier": "wti", "weight": -1.0},
                ],
            }
        }
    }


def _runtime(tmp_path: Path):
    return build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )


def test_summary_includes_focus_curves_beyond_the_selected_instrument():
    summary = summarize_commodities_workspace(_workspace(), focus_instrument_ids=["wti", "brent", "zinc"])
    assert summary["selected_curve"]["instrument_id"] == "wti"
    assert summary["focus_instrument_ids"] == ["wti", "brent", "zinc"]
    assert [curve["instrument_id"] for curve in summary["focus_curves"]] == ["brent"]
    assert summary["focus_curves"][0]["front_nodes"][4]["price"] == 97.43
    # Sin foco el resumen no cambia de forma.
    assert "focus_curves" not in summarize_commodities_workspace(_workspace())


def test_synthesis_commodities_context_includes_strategy_lab_legs_and_viewed_curves(tmp_path):
    runtime = _runtime(tmp_path)
    try:
        service = runtime.copilot_service
        request = CopilotResearchCardRequest(
            domain="synthesis",
            prompt=AUDIT_PROMPT,
            context=CopilotRequestContext(current_tab="synthesis"),
            synthesis=CopilotSynthesisRequest(
                active_tab="copilot",
                included_scopes=[
                    CopilotSynthesisScope(
                        domain="commodities",
                        context=CopilotRequestContext(
                            current_tab="commodities",
                            commodities_state={"workspace": _workspace(), "viewed_instrument_ids": ["wti"]},
                        ),
                    ),
                    CopilotSynthesisScope(
                        domain="strategy_lab",
                        context=CopilotRequestContext(
                            current_tab="strategy_lab",
                            strategy_lab_state=_strategy_lab_state(),
                        ),
                    ),
                ],
            ),
        )
        synthesis = service._build_synthesis_context(request)
        commodities = synthesis.tool_state["included_bundles"]["commodities"]
        assert commodities.tool_state["focus_instrument_ids"] == ["wti", "brent"]
        assert [row["instrument_id"] for row in commodities.summary_data["commodities"]["focus_curves"]] == ["brent"]

        drilldown = service._execute_tool("get_synthesis_domain_context", {"domain": "commodities"}, synthesis)
        assert "commodities.curve.wti" in drilldown.trace.source_ids
        assert "commodities.curve.brent" in drilldown.trace.source_ids
        brent = drilldown.output["drilldown"]["inspect_commodity_curve_fundamentals.focus"]["brent"]
        assert brent["curve"]["nodes"][4]["price"] == 97.43
    finally:
        runtime.shutdown()


def test_viewed_instruments_reach_a_single_commodities_context(tmp_path):
    runtime = _runtime(tmp_path)
    try:
        request = CopilotResearchCardRequest(
            domain="commodities",
            prompt="Compare the curves.",
            context=CopilotRequestContext(
                current_tab="commodities",
                commodities_state={"workspace": _workspace(), "viewed_instrument_ids": ["brent", "wti", "unknown"]},
            ),
        )
        bundle = runtime.copilot_service._build_commodities_context(request)
        assert bundle.tool_state["focus_instrument_ids"] == ["wti", "brent"]
        assert bundle.summary_data["focus_instrument_ids"] == ["wti", "brent"]
    finally:
        runtime.shutdown()


# ── GUA-20261021-13: ruido de trazas y avisos ─────────────────────────────────────────────


def test_coalesce_warnings_groups_same_kind_failures():
    groups = coalesce_warnings(
        [*_workspace()["warnings"], "Roll-yield proxy annualizes the front calendar spread only."]
    )
    assert groups[0][0] == "3 FRED series failed: HTTPError (GOLDAMGBD228NLBM, SLVPRUSD, PPLTUSDM)."
    assert len(groups[0][1]) == 3
    assert groups[1] == (
        "Roll-yield proxy annualizes the front calendar spread only.",
        ["Roll-yield proxy annualizes the front calendar spread only."],
    )


def test_operator_records_one_warning_step_per_warning_kind(tmp_path):
    runtime = _runtime(tmp_path)
    try:
        request = CopilotResearchCardRequest(
            domain="commodities",
            prompt="Inspect the loaded commodities workspace.",
            role="research_operator",
            context=CopilotRequestContext(
                current_tab="commodities",
                commodities_state={"workspace": _workspace()},
            ),
        )
        result = runtime.copilot_service.execute_research_operator_plan(request)
        fred_steps = [
            event
            for event in result.operator_events
            if event.event_type == "warning" and "FRED" in str(event.message)
        ]
        assert len(fred_steps) == 1
        assert fred_steps[0].message.startswith("3 FRED series failed")
        assert len(fred_steps[0].payload["coalesced_warnings"]) == 3
        # La procedencia completa sigue en los avisos del resultado.
        assert all(warning in result.warnings for warning in _workspace()["warnings"])
    finally:
        runtime.shutdown()


def test_commodity_prompt_never_triggers_sec_company_lookup():
    prompt = (
        "Load the Brent curve and report same-month Brent, WTI and spread, Dec-26 to Nov-27, "
        "with timestamps."
    )
    calls: list[str] = []

    def search(query, limit=12):
        calls.append(query)
        raise SecIdentityMissingError()

    assert extract_explicit_equity_tickers(prompt) == []
    assert should_attempt_equity_resolution(prompt) is False
    assert resolve_equity_entity(prompt=prompt, context_ticker=None, search_companies=search) is None
    assert calls == []
    # Un ticker marcado explícitamente sigue funcionando.
    assert extract_explicit_equity_tickers("Value $WTI shares") == ["WTI"]
    assert should_attempt_equity_resolution("What is the fair value of Lockheed Martin?") is True


def test_literal_operator_commodity_prompt_does_not_reach_sec_search():
    """Verificación en vivo 2026-10-27: el prompt literal del Operator de la auditoría seguía
    emitiendo "Gamma cannot resolve company names…" porque "Commodities" (pestaña) y "Then" /
    "Read-only" (inicio de frase) pasaban por posibles nombres de empresa."""
    prompt = (
        "Load the Brent Crude Oil futures curve from Commodities and report, for each delivery month "
        "from Dec-26 to Nov-27, the Brent price, the WTI price and the same-month Brent-WTI spread. "
        "Then state whether the spread is concentrated in the first three months. Read-only research; "
        "cite the curve objects and their quote timestamps."
    )
    calls: list[str] = []

    def search(query, limit=12):
        calls.append(query)
        raise SecIdentityMissingError()

    assert should_attempt_equity_resolution(prompt) is False
    assert resolve_equity_entity(prompt=prompt, context_ticker=None, search_companies=search) is None
    assert calls == []
    # Un nombre propio en mitad de frase, o una sola palabra, siguen pasando por la búsqueda SEC.
    assert should_attempt_equity_resolution("Compare the Brent curve with Exxon Mobil margins.") is True
    assert should_attempt_equity_resolution("Microsoft") is True


def test_sec_identity_warning_is_scoped_to_name_lookups():
    def search(query, limit=12):
        raise SecIdentityMissingError()

    explicit = resolve_equity_entity(prompt="Run a DCF for LMT", context_ticker=None, search_companies=search)
    assert explicit is not None and explicit.status == "resolved"
    assert not any("cannot resolve company names" in warning for warning in explicit.warnings)
    assert any("LMT was used without SEC verification" in warning for warning in explicit.warnings)

    warnings: list[str] = []
    _safe_search(search, "Lockheed", warnings)
    assert "cannot resolve company names" in warnings[0]


def test_snapshot_is_compact_and_keeps_request_context_without_duplicate_events(tmp_path):
    store = CopilotStore(base_dir=tmp_path / "copilot")
    event = CopilotOperatorProgressEvent(
        run_id="run-1",
        event_id="opevent-1",
        sequence=1,
        event_type="plan",
        timestamp=__import__("src.utils.time", fromlist=["now_utc"]).now_utc(),
        payload={"outputs": {"blob": "x" * 2_000}},
    )
    result = CopilotResearchCardResult(
        domain="synthesis",
        current_tab="copilot",
        status="incomplete",
        provider="openai_responses_operator",
        message="OpenAI ended the Operator response early: max_output_tokens.",
        card=ResearchCard(title="t", hypothesis="h", rationale="r", required_data=[], proposed_test="",
                          confounders=[], next_steps=[], caveats=[], source_backed_claims=[], inferred_claims=[]),
        operator_events=[event],
    )
    request_context = {"context": {"commodities_state": {"workspace": _workspace()}}, "synthesis": None}
    _, snapshot, turn = store.record_turn(
        session_id="session-1",
        title=None,
        domain="synthesis",
        current_tab="copilot",
        workspace_mode=None,
        prompt="Brent curve",
        context_fingerprint="ctx",
        context_summary={"operator_plan": {"intent": "x"}, "operator_events": [{"event_id": "opevent-1"}]},
        result=result,
        role="research_operator",
        request_context=request_context,
    )
    raw = (store.snapshots_dir / f"{snapshot.snapshot_id}.json").read_text(encoding="utf-8")
    assert "\n" not in raw  # sin sangría
    stored = json.loads(raw)
    assert "operator_events" not in stored["summary"]
    assert stored["summary"]["operator_events_ref"]["event_count"] == 1
    assert stored["request_context"] == json.loads(json.dumps(request_context))
    reloaded = store.get_context_snapshot(snapshot.snapshot_id)
    assert reloaded is not None and reloaded.request_context["context"]["commodities_state"]["workspace"]["curves"]
    # Los eventos siguen íntegros en el turno y el resultado parcial conserva su tarjeta.
    detail_turn = store._load_turns_unlocked("session-1")[0]
    assert detail_turn.result.operator_events[0].payload["outputs"]["blob"] == "x" * 2_000
    assert detail_turn.result.card is not None and detail_turn.turn_id == turn.turn_id


def test_expanded_budget_request_field_reaches_the_domain_request():
    from src.api.schemas.copilot import CopilotResearchCardRequestModel

    model = CopilotResearchCardRequestModel(domain="synthesis", prompt="x", output_budget="expanded")
    assert model.to_domain().output_budget == "expanded"
    assert replace(model.to_domain(), output_budget=None).output_budget is None


def test_related_markets_for_model_keeps_series_siblings_and_caps_rows():
    """GUA-20261021-15: los hermanos de serie van detrás de los análogos; deben llegar al modelo con tope."""
    from types import SimpleNamespace

    from src.application.copilot_service import _related_markets_for_model

    analogs = [SimpleNamespace(market_id=f"analog-{index}", sibling_scope=None) for index in range(12)]
    siblings = [SimpleNamespace(market_id=f"sibling-{index}", sibling_scope="same_series") for index in range(30)]

    selected = _related_markets_for_model([*analogs, *siblings], analog_limit=5, sibling_limit=5)

    assert [row.market_id for row in selected] == [
        *[f"analog-{index}" for index in range(5)],
        *[f"sibling-{index}" for index in range(5)],
    ]
