import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { CopilotWorkingAnalysis } from "../lib/api/types";
import CopilotRiskWorkingAnalysis from "./CopilotRiskWorkingAnalysis.svelte";

describe("CopilotRiskWorkingAnalysis", () => {
  it("renders exact temporary legs, shocks, result, provenance, and safety boundary", () => {
    const analysis: CopilotWorkingAnalysis = {
      analysis_id: "work-aapl-tlt",
      session_id: "session-risk",
      run_id: "oprun-risk",
      tool_id: "run_hypothetical_portfolio_comparison",
      domain: "risk",
      analysis_type: "hypothetical_portfolio_risk_scenario",
      title: "Hypothetical AAPL/TLT risk scenario",
      status: "active",
      state_scope: "session_ephemeral",
      entity: {
        entity_type: "hypothetical_portfolio",
        portfolio_label: "Hypothetical AAPL/TLT",
        benchmark_symbol: "SPY",
        legs: [
          { symbol: "AAPL", weight: 0.6, sec_type: "STK" },
          { symbol: "TLT", weight: 0.4, sec_type: "ETF" }
        ]
      },
      inputs: {
        portfolio: {
          portfolio_label: "Hypothetical AAPL/TLT",
          benchmark_symbol: "SPY"
        },
        risk_scenario: {
          scenario_label: "rate_shock_+100bps"
        }
      },
      outputs: {
        portfolio_comparison: { relative: { correlation: 0.42 } },
        risk_scenario: {
          scenario_label: "rate_shock_+100bps",
          scenario_type: "rate_shock",
          shock_parameters: {
            scenario_type: "rate_shock",
            rate_shift_bps: 100,
            equity_shock_pct: -0.1,
            duration_proxy_years: null,
            symbol_shocks: []
          },
          shock_proxy: {
            estimated_pnl: -124_000,
            estimated_return_pct: -0.124
          },
          metrics: { risk_coverage_ratio: 1, annual_vol: 0.18 },
          warnings: ["Transparent proxy, not full repricing."]
        }
      },
      source_ids: ["research.hypothetical_portfolio.operator_comparison", "risk.scenario.analysis"],
      warnings: [],
      context_fingerprint: "fp-risk",
      owning_tab: "risk",
      owning_mode: "scenarios",
      materialization: {
        contract_version: "copilot.materialization.v1",
        payload_contract: "copilot.risk-working-analysis.v1",
        target_tab: "risk",
        target_mode: "scenarios",
        durable: false
      },
      created_at: "2026-08-25T10:00:00Z",
      updated_at: "2026-08-25T10:01:00Z",
      expires_at: "2026-09-01T10:00:00Z",
      materialized_at: "2026-08-25T10:02:00Z",
      discarded_at: null,
      read_only_safety: {},
      source_provider: "gamma",
      origin: "gamma.risk.compute",
      transformation_note: "Read-only temporary workflow.",
      contract_version: "copilot.working-analysis.v1"
    };

    const { body } = render(CopilotRiskWorkingAnalysis, { props: { analysis } });

    expect(body).toContain("Temporary");
    expect(body).toContain("Session ephemeral · unsaved");
    expect(body).toContain("AAPL");
    expect(body).toContain("60.0%");
    expect(body).toContain("TLT");
    expect(body).toContain("40.0%");
    expect(body).toContain("+100 bps");
    expect(body).toContain("-10.0%");
    expect(body).toContain("USD -124,000");
    expect(body).toContain("-12.4%");
    expect(body).toContain("gamma.risk.compute");
    expect(body).toContain("does not save");
    expect(body).toContain("rebalance");
    expect(body).toContain("trade");
    expect(body).not.toMatch(/>Save portfolio<|>Rebalance<|>Place order</i);
  });
});
