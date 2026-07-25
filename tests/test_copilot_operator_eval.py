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


def test_copilot_operator_eval_harness_runs_custom_and_stub_sdk_paths(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("COMMODITIES_PROVIDER", "sample")
    monkeypatch.setenv("MARITIME_PROVIDER", "sample")
    monkeypatch.setenv("NEWS_PROVIDER", "sample")
    fixtures = _load_copilot_fixtures()
    client, runtime = fixtures._build_test_client(tmp_path)
    try:
        runtime.copilot_service.fundamentals_service = fixtures._StubFundamentalsService()
        runtime.copilot_service.macro_service = fixtures._StubMacroService()
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

        assert result.passed, [
            {
                "case_id": item.case_id,
                "orchestrator": item.orchestrator,
                "failed_checks": [
                    name for name, passed in item.checks.items() if not passed
                ],
                "tool_traces": item.tool_traces,
                "warnings": item.warnings,
            }
            for item in result.outcomes
            if not item.passed
        ]
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
        assert all(
            "run_options_realized_implied_comparison" in item.tool_traces
            for item in result.outcomes
            if item.case_id == "options_realized_implied"
        )
        representative_ids = {
            "checkpoint5_nvda_research",
            "checkpoint5_cpi_fed_research",
            "checkpoint5_oil_disruption",
            "risk_rate_shock",
        }
        representative = [
            item for item in result.outcomes if item.case_id in representative_ids
        ]
        assert len(representative) == len(representative_ids) * 2
        assert all(item.checks["selected_domains"] for item in representative)
        assert all(item.checks["omission_reasons"] for item in representative)
        assert all(item.selected_domains for item in representative)
    finally:
        runtime.shutdown()
