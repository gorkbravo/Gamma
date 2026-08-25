from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from tempfile import TemporaryDirectory
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.copilot_agents_operator import CopilotAgentsOperatorConfig
from src.api.session_auth import GAMMA_SESSION_ENV, GAMMA_SESSION_HEADER

PROFILE_COMPARISON_CASE_IDS = {
    "dcf_edit_apply_stop",
    "checkpoint5_nvda_research",
    "checkpoint5_cpi_fed_research",
    "checkpoint5_oil_disruption",
    "risk_rate_shock",
}


@dataclass(frozen=True)
class CopilotOperatorEvalCase:
    case_id: str
    prompt: str
    context: dict[str, Any]
    expected_tools: tuple[str, ...] = ()
    expected_any_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    expected_events: tuple[str, ...] = ("plan", "final-report")
    expected_warning_terms: tuple[str, ...] = ()
    expected_domains: tuple[str, ...] = ()
    expected_omitted_domains: tuple[str, ...] = ()
    require_confirmation_checkpoint: bool = False
    require_report: bool = False
    current_gap: str | None = None


@dataclass(frozen=True)
class CopilotOperatorEvalOutcome:
    case_id: str
    orchestrator: str
    profile: str
    evidence_mode: str
    status: str
    passed: bool
    score: float
    checks: dict[str, bool]
    model: str | None = None
    resolved_profile: str | None = None
    model_policy_version: str | None = None
    routing_reason: str | None = None
    orchestration_path: str | None = None
    reasoning_effort: str | None = None
    duration_ms: int | None = None
    provider_duration_ms: int | None = None
    sdk_duration_ms: int | None = None
    model_usage: dict[str, Any] = field(default_factory=dict)
    grounding_quality: float = 0.0
    citation_validity_quality: float = 0.0
    domain_decision_quality: float = 0.0
    warning_preservation_quality: float = 0.0
    tool_selection_quality: float = 0.0
    permission_stop_quality: float = 0.0
    trace_report_quality: float = 0.0
    final_usefulness_quality: float = 0.0
    tool_traces: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    selected_domains: list[str] = field(default_factory=list)
    omitted_domains: list[str] = field(default_factory=list)
    current_gap: str | None = None
    report_generated: bool = False


@dataclass(frozen=True)
class CopilotOperatorEvalSuiteResult:
    outcomes: list[CopilotOperatorEvalOutcome]

    @property
    def passed(self) -> bool:
        return all(outcome.passed for outcome in self.outcomes)

    @property
    def average_score(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(outcome.score for outcome in self.outcomes) / len(self.outcomes)

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "average_score": self.average_score,
            "variant_summaries": self.variant_summaries,
            "routing_decision": self.routing_decision,
            "outcomes": [asdict(outcome) for outcome in self.outcomes],
        }

    @property
    def variant_summaries(self) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str], list[CopilotOperatorEvalOutcome]] = {}
        for outcome in self.outcomes:
            grouped.setdefault(
                (outcome.profile, outcome.orchestrator, outcome.evidence_mode),
                [],
            ).append(outcome)
        summaries: list[dict[str, Any]] = []
        for (profile, orchestrator, evidence_mode), rows in grouped.items():
            durations = [row.duration_ms for row in rows if row.duration_ms is not None]
            provider_durations = [
                row.provider_duration_ms
                for row in rows
                if row.provider_duration_ms is not None
            ]
            summaries.append(
                {
                    "profile": profile,
                    "orchestrator": orchestrator,
                    "evidence_mode": evidence_mode,
                    "case_count": len(rows),
                    "passed_count": sum(row.passed for row in rows),
                    "average_score": sum(row.score for row in rows) / len(rows),
                    "average_duration_ms": (
                        sum(durations) / len(durations) if durations else None
                    ),
                    "average_provider_duration_ms": (
                        sum(provider_durations) / len(provider_durations)
                        if provider_durations
                        else None
                    ),
                }
            )
        return summaries

    @property
    def routing_decision(self) -> dict[str, Any]:
        live_rows = [
            item for item in self.outcomes if item.evidence_mode == "live_authorized"
        ]
        if not live_rows:
            return {
                "default_changed": False,
                "selected_default": "gamma_custom_loop",
                "reason": (
                    "Retain the Gamma-owned custom loop: this run contains "
                    "deterministic/mock contract evidence only and no intentionally "
                    "authorized live-provider evidence."
                ),
            }
        return {
            "default_changed": False,
            "selected_default": "gamma_custom_loop",
            "reason": (
                "Retain the Gamma-owned custom loop unless a separately reviewed "
                "live comparison demonstrates a material quality, latency, reliability, "
                "or cost advantage across the complete retained case set."
            ),
        }


def default_operator_eval_cases(
    *,
    portfolio_snapshot: dict[str, Any] | None = None,
    research_result: dict[str, Any] | None = None,
) -> list[CopilotOperatorEvalCase]:
    portfolio_context = {
        "current_tab": "portfolio",
        "workspace_mode": "portfolio",
        "portfolio_state": {"snapshot": portfolio_snapshot or {}},
    }
    copilot_context = {"current_tab": "copilot", "workspace_mode": "research"}
    strategy_context = {
        "current_tab": "strategy_lab",
        "workspace_mode": "research",
        "strategy_lab_state": {
            "imported_result": {
                "label": "Eval strategy",
                "source_provider": "uploaded_csv",
                "metrics": {"observation_count": 8, "annualized_return": 0.12},
                "warnings": [],
                "retrieved_at": "2026-05-31T00:00:00",
            }
        },
    }
    research_context = {
        "current_tab": "research",
        "workspace_mode": "research",
        "research_state": {"result": research_result or {}},
    }
    cases = [
        CopilotOperatorEvalCase(
            case_id="dcf_edit_apply_stop",
            prompt="Research AAPL and adjust the DCF revenue growth assumption",
            context=copilot_context,
            forbidden_tools=("fundamentals.apply_dcf_update",),
            expected_events=("plan", "confirmation-needed", "final-report"),
            require_confirmation_checkpoint=True,
        ),
        CopilotOperatorEvalCase(
            case_id="reverse_valuation_report",
            prompt="Research AAPL and run reverse valuation plus a report",
            context=copilot_context,
            expected_tools=("run_fundamentals_reverse_valuation",),
            expected_events=("plan", "tool-result", "final-report"),
            require_report=True,
        ),
        CopilotOperatorEvalCase(
            case_id="risk_rate_shock",
            prompt="Is my portfolio exposed to a rate shock?",
            context=portfolio_context,
            expected_tools=("run_risk_contribution_analysis", "run_risk_scenario_analysis"),
            expected_events=("plan", "step-start", "tool-result", "final-report"),
            expected_domains=("portfolio", "risk", "macro"),
            expected_omitted_domains=("commodities", "maritime", "external_context"),
        ),
        CopilotOperatorEvalCase(
            case_id="checkpoint5_nvda_research",
            prompt="Research NVDA using the relevant Gamma domains.",
            context=copilot_context,
            expected_any_tools=(
                "get_fundamentals_company_context",
                "inspect_equity_research_context",
                "inspect_options_structure",
                "get_news_items_context",
            ),
            expected_events=("plan", "tool-result", "final-report"),
            expected_domains=("fundamentals", "equity_research", "iv", "external_context"),
            expected_omitted_domains=("portfolio", "commodities", "maritime"),
        ),
        CopilotOperatorEvalCase(
            case_id="checkpoint5_cpi_fed_research",
            prompt="Research CPI and the next Fed decision using relevant Gamma domains.",
            context=copilot_context,
            expected_tools=("get_macro_workspace_drilldown",),
            expected_events=("plan", "tool-result", "final-report"),
            expected_domains=("macro", "prediction_markets", "external_context"),
            expected_omitted_domains=("portfolio", "commodities", "maritime"),
        ),
        CopilotOperatorEvalCase(
            case_id="checkpoint5_oil_disruption",
            prompt="Research an oil supply disruption using relevant Gamma domains.",
            context=copilot_context,
            expected_tools=("get_commodities_workspace_summary",),
            expected_events=("plan", "tool-result", "final-report"),
            expected_domains=(
                "commodities",
                "maritime",
                "macro",
                "prediction_markets",
                "external_context",
            ),
            expected_omitted_domains=("portfolio", "risk", "iv"),
        ),
        CopilotOperatorEvalCase(
            case_id="hypothetical_portfolio_comparison",
            prompt="Compare a hypothetical 60/40 AAPL/MSFT research portfolio to SPY",
            context=copilot_context,
            expected_tools=("run_hypothetical_portfolio_comparison",),
            expected_events=("plan", "tool-result", "final-report"),
        ),
        CopilotOperatorEvalCase(
            case_id="strategy_lab_backtest",
            prompt="Run a Strategy Lab backtest on the imported strategy",
            context=strategy_context,
            expected_tools=("run_strategy_lab_backtest",),
            expected_events=("plan", "tool-result", "final-report"),
        ),
        CopilotOperatorEvalCase(
            case_id="options_realized_implied",
            prompt="Run options IV realized implied comparison for AAPL",
            context=copilot_context,
            expected_tools=("run_options_realized_implied_comparison",),
            expected_events=("plan", "tool-result", "final-report"),
        ),
        CopilotOperatorEvalCase(
            case_id="single_name_event_report",
            prompt="Research AAPL into CPI/Fed week and produce a cross-domain event report",
            context=copilot_context,
            expected_tools=("run_fundamentals_reverse_valuation",),
            expected_events=("plan", "final-report"),
            require_report=True,
        ),
    ]
    if research_result:
        cases.append(
            CopilotOperatorEvalCase(
                case_id="research_scope_analysis",
                prompt="Run research scope analysis on the current scope",
                context=research_context,
                expected_tools=("run_research_scope_analysis",),
                expected_events=("plan", "tool-result", "final-report"),
            )
        )
    return cases


def run_operator_eval_suite(
    client: TestClient,
    cases: Iterable[CopilotOperatorEvalCase],
    *,
    orchestrators: tuple[str, ...] = ("custom", "agents_sdk_stub"),
    on_progress: Callable[[str], None] | None = None,
) -> CopilotOperatorEvalSuiteResult:
    outcomes: list[CopilotOperatorEvalOutcome] = []
    retained_cases = list(cases)
    variants = [
        *((profile, "custom") for profile in ("auto", "quick", "standard", "deep"))
    ]
    variants.extend(
        ("standard", orchestrator)
        for orchestrator in orchestrators
        if orchestrator != "custom"
    )
    if "custom" not in orchestrators:
        variants = [
            (profile, orchestrator)
            for profile, orchestrator in variants
            if orchestrator != "custom"
        ]
    for profile, orchestrator in variants:
        with _operator_orchestrator(client, orchestrator):
            variant_cases = (
                retained_cases
                if (profile, orchestrator) == ("auto", "custom")
                else [
                    case
                    for case in retained_cases
                    if case.case_id in PROFILE_COMPARISON_CASE_IDS
                ]
            )
            for case in variant_cases:
                if on_progress is not None:
                    on_progress(f"{profile}/{orchestrator}: {case.case_id}")
                outcomes.append(_run_eval_case(client, case, orchestrator, profile))
    return CopilotOperatorEvalSuiteResult(outcomes=outcomes)


def _run_eval_case(
    client: TestClient,
    case: CopilotOperatorEvalCase,
    orchestrator: str,
    profile: str,
) -> CopilotOperatorEvalOutcome:
    started_at = perf_counter()
    plan_response = client.post(
        "/copilot/research-plan",
        json={
            "domain": "synthesis",
            "prompt": case.prompt,
            "selected_profile": profile,
            "context": case.context,
        },
    )
    plan_payload = plan_response.json()
    selected_domains = [
        str(item.get("domain"))
        for item in list(plan_payload.get("domain_plan") or [])
        if isinstance(item, dict) and item.get("domain")
    ]
    domain_decisions = {
        str(item.get("domain")): item
        for item in list(plan_payload.get("domain_decisions") or [])
        if isinstance(item, dict) and item.get("domain")
    }
    omitted_domains = [
        domain
        for domain, decision in domain_decisions.items()
        if not bool(decision.get("used"))
    ]
    response = client.post(
        "/copilot/operator-plan/execute",
        json={
            "domain": "synthesis",
            "prompt": case.prompt,
            "selected_profile": profile,
            "context": case.context,
        },
    )
    duration_ms = int((perf_counter() - started_at) * 1000)
    payload = response.json()
    tool_traces = [str(item.get("tool_name")) for item in payload.get("tool_traces", [])]
    event_types = [str(item.get("event_type")) for item in payload.get("operator_events", [])]
    warnings = [str(item) for item in payload.get("warnings", [])]
    report_generated = _maybe_generate_report(client, case)
    final_payload = _final_event_payload(payload)
    checks = {
        "http_ok": response.status_code == 200,
        "status_ready_or_gap": payload.get("status") == "ready" or bool(case.current_gap),
        "expected_tools": all(tool in tool_traces for tool in case.expected_tools),
        "expected_any_tools": (
            not case.expected_any_tools
            or any(tool in tool_traces for tool in case.expected_any_tools)
        ),
        "forbidden_tools_absent": not any(tool in tool_traces for tool in case.forbidden_tools),
        "expected_events": all(event in event_types for event in case.expected_events),
        "permission_compliance": not any(tool in tool_traces for tool in case.forbidden_tools),
        "confirmation_stop": (
            not case.require_confirmation_checkpoint
            or any(event.get("event_type") == "confirmation-needed" for event in payload.get("operator_events", []))
        ),
        "warning_terms": all(
            any(term in warning for warning in warnings)
            for term in case.expected_warning_terms
        ),
        "trace_completeness": bool(event_types) and event_types[0] == "plan" and event_types[-1] == "final-report",
        "report_generated": (not case.require_report) or report_generated,
        "trace_has_outputs": (
            not case.expected_tools
            or bool(final_payload.get("output_summaries"))
            or any(event.get("event_type") == "confirmation-needed" for event in payload.get("operator_events", []))
        ),
        "routing_http_ok": plan_response.status_code == 200,
        "selected_domains": (
            not case.expected_domains
            or set(selected_domains) == set(case.expected_domains)
        ),
        "omission_reasons": (
            not case.expected_omitted_domains
            or all(
                domain in domain_decisions
                and not bool(domain_decisions[domain].get("used"))
                and bool(str(domain_decisions[domain].get("classification") or "").strip())
                and bool(str(domain_decisions[domain].get("reason") or "").strip())
                for domain in case.expected_omitted_domains
            )
        ),
        "closed_loop_synthesis": (
            final_payload.get("operator_contract") != "copilot.operator.loop.v1"
            or payload.get("status") != "ready"
            or (
                final_payload.get("synthesis_source") == "model_final_output"
                and _has_useful_model_final_card(payload)
            )
        ),
    }
    if case.current_gap:
        checks["expected_tools"] = True
        checks["warning_terms"] = True
        checks["report_generated"] = True
    passed = all(checks.values())
    grounding_quality, citation_validity_quality = _grounding_and_citation_quality(
        payload
    )
    domain_decision_quality = (
        float(checks["selected_domains"] + checks["omission_reasons"]) / 2.0
    )
    warning_preservation_quality = _warning_preservation_quality(
        plan_payload=plan_payload,
        result_warnings=warnings,
        expected_terms=case.expected_warning_terms,
    )
    tool_selection_quality = _tool_selection_quality(case, tool_traces)
    permission_stop_quality = float(
        checks["permission_compliance"] and checks["confirmation_stop"]
    )
    trace_report_quality = _trace_report_quality(
        event_types=event_types,
        final_payload=final_payload,
        report_generated=report_generated,
        require_report=case.require_report,
    )
    final_usefulness_quality = _final_usefulness_quality(
        payload=payload,
        final_payload=final_payload,
        event_types=event_types,
    )
    score_dimensions = (
        grounding_quality,
        citation_validity_quality,
        domain_decision_quality,
        warning_preservation_quality,
        tool_selection_quality,
        permission_stop_quality,
        trace_report_quality,
        final_usefulness_quality,
    )
    score = sum(score_dimensions) / len(score_dimensions)
    resolution = (
        payload.get("model_resolution")
        if isinstance(payload.get("model_resolution"), dict)
        else {}
    )
    observability = (
        payload.get("observability")
        if isinstance(payload.get("observability"), dict)
        else {}
    )
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    model_usage = {
        key: value
        for key, value in usage.items()
        if key != "raw" and value is not None
    }
    final_model_usage = final_payload.get("model_usage")
    if isinstance(final_model_usage, dict):
        model_usage.update(
            {
                key: value
                for key, value in final_model_usage.items()
                if value is not None
            }
        )
    return CopilotOperatorEvalOutcome(
        case_id=case.case_id,
        orchestrator=orchestrator,
        profile=profile,
        evidence_mode=(
            "live_authorized"
            if orchestrator.startswith("agents_sdk_live")
            else "deterministic_mock"
        ),
        status=str(payload.get("status") or "unknown"),
        passed=passed,
        score=score,
        checks=checks,
        model=str(payload.get("model") or final_payload.get("model") or "") or None,
        resolved_profile=str(resolution.get("resolved_profile") or "") or None,
        model_policy_version=str(resolution.get("policy_version") or "") or None,
        routing_reason=str(resolution.get("routing_reason") or "") or None,
        orchestration_path=(
            str(resolution.get("orchestration_path") or "") or None
        ),
        reasoning_effort=(
            str(
                observability.get("reasoning_effort")
                or final_payload.get("reasoning_effort")
                or ""
            )
            or None
        ),
        duration_ms=duration_ms,
        provider_duration_ms=(
            int(observability["provider_latency_ms"])
            if isinstance(observability.get("provider_latency_ms"), int)
            else None
        ),
        sdk_duration_ms=(
            int(final_payload["sdk_duration_ms"])
            if isinstance(final_payload.get("sdk_duration_ms"), int)
            else None
        ),
        model_usage=model_usage,
        grounding_quality=grounding_quality,
        citation_validity_quality=citation_validity_quality,
        domain_decision_quality=domain_decision_quality,
        warning_preservation_quality=warning_preservation_quality,
        tool_selection_quality=tool_selection_quality,
        permission_stop_quality=permission_stop_quality,
        trace_report_quality=trace_report_quality,
        final_usefulness_quality=final_usefulness_quality,
        tool_traces=tool_traces,
        event_types=event_types,
        warnings=warnings,
        selected_domains=selected_domains,
        omitted_domains=omitted_domains,
        current_gap=case.current_gap,
        report_generated=report_generated,
    )


def _final_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("operator_events", [])
    if not isinstance(events, list):
        return {}
    for event in reversed(events):
        if isinstance(event, dict) and event.get("event_type") == "final-report":
            event_payload = event.get("payload")
            return event_payload if isinstance(event_payload, dict) else {}
    return {}


def _grounding_and_citation_quality(
    payload: dict[str, Any],
) -> tuple[float, float]:
    sources = list(payload.get("sources") or [])
    source_ids = {
        str(item.get("source_id"))
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    claims = [
        item
        for item in list(card.get("source_backed_claims") or [])
        if isinstance(item, dict)
    ]
    trace_refs = [
        str(source_id)
        for trace in list(payload.get("tool_traces") or [])
        if isinstance(trace, dict)
        for source_id in list(trace.get("source_ids") or [])
    ]
    if claims:
        grounded = sum(
            bool(str(item.get("claim") or "").strip())
            and bool(list(item.get("evidence_refs") or []))
            for item in claims
        ) / len(claims)
        cited_refs = [
            str(ref)
            for item in claims
            for ref in list(item.get("evidence_refs") or [])
        ]
        citation_validity = (
            sum(ref in source_ids for ref in cited_refs) / len(cited_refs)
            if cited_refs
            else 0.0
        )
        return grounded, citation_validity
    if trace_refs:
        return (
            float(bool(source_ids)),
            sum(ref in source_ids for ref in trace_refs) / len(trace_refs),
        )
    # A permission stop before tool execution has no evidence claims to validate.
    confirmation_stop = any(
        isinstance(event, dict) and event.get("event_type") == "confirmation-needed"
        for event in list(payload.get("operator_events") or [])
    )
    return (1.0, 1.0) if confirmation_stop else (0.0, 1.0)


def _warning_preservation_quality(
    *,
    plan_payload: dict[str, Any],
    result_warnings: list[str],
    expected_terms: tuple[str, ...],
) -> float:
    normalized = [warning.lower() for warning in result_warnings]
    expected = [
        str(item)
        for item in list(plan_payload.get("warnings") or [])
        if str(item).strip()
    ]
    expected.extend(expected_terms)
    if not expected:
        return 1.0
    return sum(
        any(term.lower() in warning for warning in normalized)
        for term in expected
    ) / len(expected)


def _final_usefulness_quality(
    *,
    payload: dict[str, Any],
    final_payload: dict[str, Any],
    event_types: list[str],
) -> float:
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    if final_payload.get("operator_contract") == "copilot.operator.loop.v1":
        indicators = [
            payload.get("status") == "ready",
            "final-report" in event_types,
            final_payload.get("synthesis_source") == "model_final_output",
            bool(final_payload.get("output_summaries")),
            _has_useful_model_final_card(payload),
            bool(str(final_payload.get("stop_reason") or "").strip()),
        ]
        return sum(bool(item) for item in indicators) / len(indicators)
    indicators = [
        payload.get("status") == "ready",
        "final-report" in event_types,
        bool(final_payload.get("output_summaries"))
        or bool(card.get("rationale")),
        bool(card.get("proposed_test"))
        or bool(final_payload.get("next_steps"))
        or bool(final_payload.get("warnings")),
    ]
    return sum(bool(item) for item in indicators) / len(indicators)


def _has_useful_model_final_card(payload: dict[str, Any]) -> bool:
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    title = str(card.get("title") or "").strip()
    rationale = str(card.get("rationale") or "").strip()
    proposed_test = str(card.get("proposed_test") or "").strip()
    normalized = f"{title} {rationale}".lower()
    generic_only = (
        "executed " in normalized
        and " tool" in normalized
        and not any(
            term in normalized
            for term in (
                "risk",
                "rate",
                "valuation",
                "portfolio",
                "macro",
                "commodity",
                "equity",
                "options",
                "evidence",
                "observation",
            )
        )
    )
    return (
        len(title) >= 8
        and len(rationale) >= 40
        and len(proposed_test) >= 12
        and not generic_only
    )


def _tool_selection_quality(case: CopilotOperatorEvalCase, tool_traces: list[str]) -> float:
    required = set(case.expected_tools)
    forbidden = set(case.forbidden_tools)
    allowed_any = set(case.expected_any_tools)
    if not required and not forbidden and not allowed_any:
        return 1.0
    if not required and allowed_any:
        return 1.0 if allowed_any.intersection(tool_traces) else 0.0
    if not required:
        return 0.0 if forbidden.intersection(tool_traces) else 1.0
    hits = len(required.intersection(tool_traces))
    misses = len(required.difference(tool_traces))
    violations = len(forbidden.intersection(tool_traces))
    denominator = max(1, len(required) + len(forbidden))
    return max(0.0, (hits - misses - violations) / denominator)


def _trace_report_quality(
    *,
    event_types: list[str],
    final_payload: dict[str, Any],
    report_generated: bool,
    require_report: bool,
) -> float:
    checks = [
        bool(event_types) and event_types[0] == "plan",
        "step-start" in event_types or "confirmation-needed" in event_types,
        "tool-result" in event_types or "confirmation-needed" in event_types,
        bool(final_payload.get("output_summaries")) or "confirmation-needed" in event_types,
        event_types[-1] == "final-report" if event_types else False,
        report_generated if require_report else True,
    ]
    return sum(1 for item in checks if item) / len(checks)


def _maybe_generate_report(client: TestClient, case: CopilotOperatorEvalCase) -> bool:
    if not case.require_report:
        return False
    sessions = client.get("/copilot/sessions").json()
    if not isinstance(sessions, list) or not sessions:
        return False
    session_id = sessions[0].get("session_id")
    if not session_id:
        return False
    response = client.post(
        f"/copilot/sessions/{session_id}/report",
        json={"title": f"Operator eval: {case.case_id}", "notes": "Generated by local Copilot operator eval."},
    )
    if response.status_code != 200:
        return False
    payload = response.json()
    return bool(payload.get("tool_trace_summary") or payload.get("source_backed_claims"))


class _operator_orchestrator:
    def __init__(self, client: TestClient, orchestrator: str) -> None:
        self.client = client
        self.orchestrator = orchestrator
        self.runtime = client.app.state.runtime
        self.previous_config = self.runtime.copilot_service.agents_operator_service.config
        self.previous_policy_orchestrator = (
            self.runtime.copilot_service.model_policy.operator_orchestrator
        )
        self.previous_key = os.environ.get("OPENAI_API_KEY")
        self.previous_loader = None

    def __enter__(self) -> None:
        if self.orchestrator == "custom":
            self.runtime.copilot_service.model_policy.operator_orchestrator = "custom"
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="custom"
            )
            return
        if self.orchestrator == "agents_sdk_stub":
            from src.application import copilot_agents_operator

            self.previous_loader = copilot_agents_operator._load_agents_sdk
            copilot_agents_operator._load_agents_sdk = lambda: _load_stub_agents_sdk(
                self.runtime.copilot_service.action_registry
            )
            os.environ["OPENAI_API_KEY"] = "test-key"
            self.runtime.copilot_service.model_policy.operator_orchestrator = "agents_sdk"
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="agents_sdk",
                model="gpt-test-operator-eval",
                max_turns=8,
            )
            return
        if self.orchestrator == "agents_sdk_live":
            self.runtime.copilot_service.model_policy.operator_orchestrator = "agents_sdk"
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="agents_sdk",
                model=os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", "gpt-5.5"),
                reasoning_effort=os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_REASONING_EFFORT") or "low",
                max_turns=8,
            )
            return
        if self.orchestrator.startswith("agents_sdk_live:"):
            _prefix, model, reasoning = (*self.orchestrator.split(":", 2), None, None)[:3]
            del _prefix
            self.runtime.copilot_service.model_policy.operator_orchestrator = "agents_sdk"
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="agents_sdk",
                model=model or "gpt-5.5",
                reasoning_effort=reasoning or None,
                verbosity="low",
                include_usage=True,
                max_turns=8,
            )
            return
        raise ValueError(f"Unsupported eval orchestrator: {self.orchestrator}")

    def __exit__(self, *_exc: object) -> None:
        self.runtime.copilot_service.agents_operator_service.config = self.previous_config
        self.runtime.copilot_service.model_policy.operator_orchestrator = (
            self.previous_policy_orchestrator
        )
        if self.previous_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.previous_key
        if self.previous_loader is not None:
            from src.application import copilot_agents_operator

            copilot_agents_operator._load_agents_sdk = self.previous_loader


def _load_stub_agents_sdk(action_registry: Any | None = None) -> Any:
    from src.application.copilot_agents_operator import _AgentsSdkModule

    class _StubModelSettings:
        def __init__(
            self,
            *,
            parallel_tool_calls: bool | None = None,
            reasoning: dict[str, Any] | None = None,
            verbosity: str | None = None,
            include_usage: bool | None = None,
        ) -> None:
            self.parallel_tool_calls = parallel_tool_calls
            self.reasoning = reasoning
            self.verbosity = verbosity
            self.include_usage = include_usage

    class _StubAgent:
        def __init__(self, *, name, model, instructions, tools, model_settings=None) -> None:
            self.name = name
            self.model = model
            self.instructions = instructions
            self.tools = tools
            self.model_settings = model_settings

    class _StubRunner:
        @staticmethod
        async def run(agent, prompt, max_turns):
            del max_turns
            payload = json.loads(prompt)
            observations: list[dict[str, Any]] = []
            for tool_id in payload.get("allowed_tool_ids", []):
                arguments = _stub_operator_arguments(
                    tool_id,
                    action_registry=action_registry,
                )
                raw_observation = agent.tools[0](
                    tool_id,
                    json.dumps(arguments),
                )
                try:
                    observation = json.loads(raw_observation)
                except (TypeError, json.JSONDecodeError):
                    observation = {"status": "invalid_stub_observation"}
                observations.append(
                    {
                        "tool_id": tool_id,
                        "status": observation.get("status"),
                        "trace_summary": observation.get("trace_summary"),
                    }
                )
            completed = [
                item
                for item in observations
                if item.get("status") == "completed"
            ]
            tool_labels = ", ".join(
                item["tool_id"] for item in completed[:4]
            ) or "the authorized Gamma observations"
            final_output = {
                "title": "Gamma Operator evidence synthesis",
                "hypothesis": (
                    "The requested research question can be assessed from the "
                    "returned read-only Gamma observations."
                ),
                "rationale": (
                    f"The deterministic SDK fixture inspected the returned "
                    f"observations from {tool_labels} and retained their warnings "
                    "and evidence boundaries in this final analytical card."
                ),
                "required_data": [
                    "Returned Gamma action observations",
                    "Canonical Operator trace",
                ],
                "proposed_test": (
                    "Review the observation-linked output summaries and compare "
                    "the strongest evidence against the stated caveats."
                ),
                "confounders": [
                    "Deterministic fixtures do not measure live-provider quality."
                ],
                "next_steps": [
                    "Inspect the retained tool observations and source references."
                ],
                "caveats": [
                    "This eval fixture validates orchestration, not investment conclusions."
                ],
                "source_backed_claims": [],
                "inferred_claims": [],
                "stop_reason": "final_answer",
            }
            return type(
                "_StubRunResult",
                (),
                {"final_output": final_output},
            )()

    return _AgentsSdkModule(
        Agent=_StubAgent,
        Runner=_StubRunner,
        function_tool=lambda func: func,
        ModelSettings=_StubModelSettings,
    )


def _stub_operator_arguments(
    tool_id: str,
    *,
    action_registry: Any | None,
) -> dict[str, Any]:
    special = {
        "run_risk_contribution_analysis": {
            "source_scope": "portfolio",
            "top_n": 10,
            "include_monte_carlo": True,
            "temporary_portfolio": None,
        },
        "run_risk_scenario_analysis": {
            "scenario_label": "rate_shock_plus_100bps",
            "source_scope": "portfolio",
            "scenario_type": "rate_shock",
            "rate_shift_bps": 100.0,
            "equity_shock_pct": None,
            "duration_proxy_years": None,
            "symbol_shocks": [],
            "temporary_portfolio": None,
        },
        "run_fundamentals_reverse_valuation": {"ticker": None},
        "inspect_equity_research_context": {"symbol": None, "max_rows": 8},
        "inspect_options_structure": {
            "symbol": None,
            "expiry": None,
            "max_expiries": 6,
        },
        "run_options_realized_implied_comparison": {
            "symbol": None,
            "max_expiries": 6,
            "depth_preset": "compact",
            "market_data_mode": None,
        },
        "get_news_items_context": {"limit": 8},
        "get_macro_series_history_summary": {
            "series_id": "us-cpi-yoy",
            "region": None,
        },
        "get_prediction_market_history_summary": {
            "range": None,
            "resolution_minutes": None,
            "outcome_id": None,
        },
        "inspect_commodity_curve_fundamentals": {
            "instrument_id": None,
            "max_curve_nodes": 8,
            "max_inventory_points": 6,
        },
        "get_maritime_chokepoint_context": {
            "chokepoint_id": None,
            "max_rows": 8,
        },
        "get_maritime_route_context": {"route_id": None, "max_rows": 8},
    }
    if tool_id in special:
        return dict(special[tool_id])
    if action_registry is None:
        return {}
    definition = action_registry.require(tool_id)
    return _stub_value_for_schema(definition.input_schema)


def _stub_value_for_schema(schema: dict[str, Any]) -> Any:
    raw_type = schema.get("type")
    allowed_types = raw_type if isinstance(raw_type, list) else [raw_type]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        for value in enum:
            if value is not None:
                return value
        return None
    if "null" in allowed_types:
        return None
    if "object" in allowed_types:
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        return {
            key: _stub_value_for_schema(properties.get(key) or {})
            for key in list(schema.get("required") or [])
        }
    if "array" in allowed_types:
        return []
    if "boolean" in allowed_types:
        return False
    if "integer" in allowed_types:
        return int(schema.get("minimum") or 1)
    if "number" in allowed_types:
        return float(schema.get("minimum") or 0.0)
    if "string" in allowed_types:
        return "fixture"
    return None


def _install_deterministic_eval_services(runtime: Any) -> None:
    """Bind the same in-repo deterministic fixtures used by the harness test.

    This prevents a local CLI eval from turning fixture coverage into an
    accidental SEC/macro provider call when credentials happen to be present.
    """
    fixture_path = REPO_ROOT / "tests" / "test_copilot.py"
    spec = importlib.util.spec_from_file_location(
        "_gamma_copilot_eval_fixtures",
        fixture_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load deterministic Copilot eval fixtures.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime.copilot_service.fundamentals_service = module._StubFundamentalsService()
    runtime.copilot_service.macro_service = module._StubMacroService()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Copilot Research Operator evals.")
    parser.add_argument("--include-agents-sdk-live", action="store_true")
    parser.add_argument(
        "--compare-gpt55",
        action="store_true",
        help=(
            "Run intentionally authorized live Agents SDK variants for the retained "
            "gpt-5.5 baseline and explicit comparison profiles."
        ),
    )
    args = parser.parse_args()

    from src.api.main import create_app
    from src.application.runtime import build_runtime

    os.environ.setdefault(GAMMA_SESSION_ENV, "copilot-operator-eval")
    os.environ.setdefault("COMMODITIES_PROVIDER", "sample")
    os.environ.setdefault("MARITIME_PROVIDER", "sample")
    os.environ.setdefault("NEWS_PROVIDER", "sample")
    with TemporaryDirectory(prefix="gamma-copilot-operator-eval-") as temp_dir:
        temp_root = Path(temp_dir)
        print("[eval] building deterministic runtime", file=sys.stderr, flush=True)
        runtime = build_runtime(
            mock_mode=True,
            cache_dir=temp_root / "cache",
            history_dir=temp_root / "data",
            sample_data_dir="sample_data",
        )
        try:
            _install_deterministic_eval_services(runtime)
            print("[eval] loading retained fixtures", file=sys.stderr, flush=True)
            client = TestClient(
                create_app(runtime),
                headers={GAMMA_SESSION_HEADER: os.environ[GAMMA_SESSION_ENV]},
            )
            snapshot = client.get("/portfolio/snapshot").json()
            research_result = client.post(
                "/research/analyze",
                json={
                    "scope_type": "single_ticker",
                    "primary_symbol": "AAPL",
                    "benchmark_symbol": "SPY",
                    "lookback_days": 252,
                },
            ).json()
            print("[eval] retained fixtures ready", file=sys.stderr, flush=True)
            orchestrators = ("custom", "agents_sdk_stub")
            if args.include_agents_sdk_live and os.getenv("OPENAI_API_KEY"):
                orchestrators = (*orchestrators, "agents_sdk_live")
            if args.compare_gpt55 and os.getenv("OPENAI_API_KEY"):
                orchestrators = (
                    "custom",
                    "agents_sdk_live:gpt-5.5:medium",
                    "agents_sdk_live:gpt-5.6:medium",
                    "agents_sdk_live:gpt-5.6:low",
                )
            result = run_operator_eval_suite(
                client,
                default_operator_eval_cases(
                    portfolio_snapshot=snapshot,
                    research_result=research_result,
                ),
                orchestrators=orchestrators,
                on_progress=lambda message: print(
                    f"[eval] {message}",
                    file=sys.stderr,
                    flush=True,
                ),
            )
            print(json.dumps(result.to_json(), indent=2, default=str))
            return 0 if result.passed else 1
        finally:
            runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
