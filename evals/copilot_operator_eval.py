from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from fastapi.testclient import TestClient

from src.application.copilot_agents_operator import CopilotAgentsOperatorConfig
from src.api.session_auth import GAMMA_SESSION_ENV, GAMMA_SESSION_HEADER


@dataclass(frozen=True)
class CopilotOperatorEvalCase:
    case_id: str
    prompt: str
    context: dict[str, Any]
    expected_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    expected_events: tuple[str, ...] = ("plan", "final-report")
    expected_warning_terms: tuple[str, ...] = ()
    require_confirmation_checkpoint: bool = False
    require_report: bool = False
    current_gap: str | None = None


@dataclass(frozen=True)
class CopilotOperatorEvalOutcome:
    case_id: str
    orchestrator: str
    status: str
    passed: bool
    score: float
    checks: dict[str, bool]
    tool_traces: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
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
            "outcomes": [asdict(outcome) for outcome in self.outcomes],
        }


def default_operator_eval_cases(*, portfolio_snapshot: dict[str, Any] | None = None) -> list[CopilotOperatorEvalCase]:
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
    return [
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
            case_id="single_name_event_report",
            prompt="Research AAPL into CPI/Fed week and produce a cross-domain event report",
            context=copilot_context,
            expected_tools=("run_fundamentals_reverse_valuation",),
            expected_events=("plan", "final-report"),
            require_report=True,
        ),
    ]


def run_operator_eval_suite(
    client: TestClient,
    cases: Iterable[CopilotOperatorEvalCase],
    *,
    orchestrators: tuple[str, ...] = ("custom", "agents_sdk_stub"),
) -> CopilotOperatorEvalSuiteResult:
    outcomes: list[CopilotOperatorEvalOutcome] = []
    for orchestrator in orchestrators:
        with _operator_orchestrator(client, orchestrator):
            for case in cases:
                outcomes.append(_run_eval_case(client, case, orchestrator))
    return CopilotOperatorEvalSuiteResult(outcomes=outcomes)


def _run_eval_case(
    client: TestClient,
    case: CopilotOperatorEvalCase,
    orchestrator: str,
) -> CopilotOperatorEvalOutcome:
    response = client.post(
        "/copilot/operator-plan/execute",
        json={"domain": "synthesis", "prompt": case.prompt, "context": case.context},
    )
    payload = response.json()
    tool_traces = [str(item.get("tool_name")) for item in payload.get("tool_traces", [])]
    event_types = [str(item.get("event_type")) for item in payload.get("operator_events", [])]
    warnings = [str(item) for item in payload.get("warnings", [])]
    report_generated = _maybe_generate_report(client, case)
    checks = {
        "http_ok": response.status_code == 200,
        "status_ready_or_gap": payload.get("status") == "ready" or bool(case.current_gap),
        "expected_tools": all(tool in tool_traces for tool in case.expected_tools),
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
    }
    if case.current_gap:
        checks["expected_tools"] = True
        checks["warning_terms"] = True
        checks["report_generated"] = True
    passed = all(checks.values())
    score = sum(1 for value in checks.values() if value) / len(checks)
    return CopilotOperatorEvalOutcome(
        case_id=case.case_id,
        orchestrator=orchestrator,
        status=str(payload.get("status") or "unknown"),
        passed=passed,
        score=score,
        checks=checks,
        tool_traces=tool_traces,
        event_types=event_types,
        warnings=warnings,
        current_gap=case.current_gap,
        report_generated=report_generated,
    )


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
        self.previous_key = os.environ.get("OPENAI_API_KEY")
        self.previous_loader = None

    def __enter__(self) -> None:
        if self.orchestrator == "custom":
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="custom"
            )
            return
        if self.orchestrator == "agents_sdk_stub":
            from src.application import copilot_agents_operator

            self.previous_loader = copilot_agents_operator._load_agents_sdk
            copilot_agents_operator._load_agents_sdk = _load_stub_agents_sdk
            os.environ["OPENAI_API_KEY"] = "test-key"
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="agents_sdk",
                model="gpt-test-operator-eval",
                max_turns=8,
            )
            return
        if self.orchestrator == "agents_sdk_live":
            self.runtime.copilot_service.agents_operator_service.config = CopilotAgentsOperatorConfig(
                orchestrator="agents_sdk",
                model=os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL", "gpt-5.4"),
                max_turns=8,
            )
            return
        raise ValueError(f"Unsupported eval orchestrator: {self.orchestrator}")

    def __exit__(self, *_exc: object) -> None:
        self.runtime.copilot_service.agents_operator_service.config = self.previous_config
        if self.previous_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.previous_key
        if self.previous_loader is not None:
            from src.application import copilot_agents_operator

            copilot_agents_operator._load_agents_sdk = self.previous_loader


def _load_stub_agents_sdk() -> Any:
    from src.application.copilot_agents_operator import _AgentsSdkModule

    class _StubModelSettings:
        def __init__(self, *, parallel_tool_calls: bool | None = None) -> None:
            self.parallel_tool_calls = parallel_tool_calls

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
            for tool_id in payload.get("allowed_tool_ids", []):
                agent.tools[0](tool_id, "{}")
            return type("_StubRunResult", (), {"final_output": "ok"})()

    return _AgentsSdkModule(
        Agent=_StubAgent,
        Runner=_StubRunner,
        function_tool=lambda func: func,
        ModelSettings=_StubModelSettings,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Copilot Research Operator evals.")
    parser.add_argument("--include-agents-sdk-live", action="store_true")
    args = parser.parse_args()

    from src.api.main import create_app
    from src.application.runtime import build_runtime

    os.environ.setdefault(GAMMA_SESSION_ENV, "copilot-operator-eval")
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=Path(".tmp_copilot_operator_eval_cache"),
        history_dir=Path(".tmp_copilot_operator_eval_data"),
        sample_data_dir="sample_data",
    )
    try:
        client = TestClient(
            create_app(runtime),
            headers={GAMMA_SESSION_HEADER: os.environ[GAMMA_SESSION_ENV]},
        )
        snapshot = client.get("/portfolio/snapshot").json()
        orchestrators = ("custom", "agents_sdk_stub")
        if args.include_agents_sdk_live and os.getenv("OPENAI_API_KEY"):
            orchestrators = (*orchestrators, "agents_sdk_live")
        result = run_operator_eval_suite(
            client,
            default_operator_eval_cases(portfolio_snapshot=snapshot),
            orchestrators=orchestrators,
        )
        print(json.dumps(result.to_json(), indent=2, default=str))
        return 0 if result.passed else 1
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
