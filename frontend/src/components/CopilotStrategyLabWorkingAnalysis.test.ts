import { render } from "svelte/server";
import { describe, expect, it } from "vitest";

import type { CopilotWorkingAnalysis } from "../lib/api/types";
import CopilotStrategyLabWorkingAnalysis from "./CopilotStrategyLabWorkingAnalysis.svelte";

function analysis(): CopilotWorkingAnalysis {
  return {
    analysis_id: "work-strategy-1",
    session_id: "session-1",
    run_id: "run-1",
    tool_id: "run_strategy_lab_portfolio_backtest",
    domain: "strategy_lab",
    analysis_type: "strategy_lab_portfolio_backtest",
    title: "Temporary QQQ/IWM",
    status: "active",
    state_scope: "session_ephemeral",
    entity: { entity_type: "strategy_lab_portfolio" },
    inputs: {
      name: "Temporary QQQ/IWM",
      benchmark_symbol: "SPY",
      lookback_days: 504,
      min_observations: 100,
      legs: [
        { label: "Long QQQ", asset_class: "etf", identifier: "QQQ", weight: 0.6 },
        { label: "Short IWM", asset_class: "etf", identifier: "IWM", weight: -0.4 }
      ]
    },
    outputs: {
      metrics: { total_return: 0.12, annual_volatility: 0.18, observation_count: 503 },
      temporary_assumptions: { transaction_costs_included: false }
    },
    source_ids: [],
    warnings: [],
    context_fingerprint: null,
    owning_tab: "strategy_lab",
    owning_mode: "composer",
    materialization: {
      payload_contract: "copilot.strategy-lab-working-analysis.v1",
      target_tab: "strategy_lab",
      target_mode: "composer",
      durable: false
    },
    created_at: "2026-09-04T10:00:00Z",
    updated_at: "2026-09-04T10:00:00Z",
    expires_at: "2026-09-11T10:00:00Z",
    materialized_at: null,
    discarded_at: null,
    read_only_safety: { execution_enabled: false },
    source_provider: "fixture",
    origin: "tests",
    transformation_note: null,
    contract_version: "copilot.working-analysis.v1"
  };
}

describe("CopilotStrategyLabWorkingAnalysis", () => {
  it("shows exact signed legs, assumptions, metrics, and the non-execution boundary", () => {
    const { body } = render(CopilotStrategyLabWorkingAnalysis, { props: { analysis: analysis() } });
    expect(body).toContain("Copilot Working Analysis");
    expect(body).toContain("Temporary QQQ/IWM");
    expect(body).toContain("504 days");
    expect(body).toContain("100 obs");
    expect(body).toContain("Long QQQ");
    expect(body).toContain("+0.600");
    expect(body).toContain("Short IWM");
    expect(body).toContain("-0.400");
    expect(body).toContain("does not rebalance, trade, or change a portfolio");
  });
});
