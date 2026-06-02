from __future__ import annotations

import importlib.util
from pathlib import Path

from evals.copilot_operator_eval import default_operator_eval_cases, run_operator_eval_suite


def _load_copilot_fixtures():
    module_path = Path(__file__).with_name("test_copilot.py")
    spec = importlib.util.spec_from_file_location("_gamma_test_copilot_fixtures", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Copilot test fixtures.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copilot_operator_eval_harness_runs_custom_and_stub_sdk_paths(tmp_path):
    fixtures = _load_copilot_fixtures()
    client, runtime = fixtures._build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = fixtures._StubFundamentalsService()
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

        result = run_operator_eval_suite(
            client,
            default_operator_eval_cases(portfolio_snapshot=snapshot, research_result=research_result),
            orchestrators=("custom", "agents_sdk_stub"),
        )

        assert result.passed
        assert result.average_score >= 0.85
        outcome_ids = {(item.case_id, item.orchestrator) for item in result.outcomes}
        assert ("risk_rate_shock", "custom") in outcome_ids
        assert ("risk_rate_shock", "agents_sdk_stub") in outcome_ids
        assert any(
            item.case_id == "dcf_edit_apply_stop"
            and item.checks["confirmation_stop"]
            and "fundamentals.apply_dcf_update" not in item.tool_traces
            for item in result.outcomes
        )
        assert not any(item.current_gap for item in result.outcomes)
        assert all(
            "run_hypothetical_portfolio_comparison" in item.tool_traces
            for item in result.outcomes
            if item.case_id == "hypothetical_portfolio_comparison"
        )
        assert all(
            "run_research_scope_analysis" in item.tool_traces
            for item in result.outcomes
            if item.case_id == "research_scope_analysis"
        )
    finally:
        runtime.shutdown()
