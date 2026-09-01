import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { CopilotWorkingAnalysis } from "../lib/api/types";
import CopilotOptionsWorkingAnalysis from "./CopilotOptionsWorkingAnalysis.svelte";

describe("CopilotOptionsWorkingAnalysis", () => {
  it("renders the exact comparison, provider boundary, warnings, and non-trading state", () => {
    const analysis: CopilotWorkingAnalysis = {
      analysis_id: "work-options-aapl",
      session_id: "session-options",
      run_id: "oprun-options",
      tool_id: "run_options_realized_implied_comparison",
      domain: "iv",
      analysis_type: "options_realized_implied_comparison",
      title: "AAPL realized vs implied volatility",
      status: "active",
      state_scope: "session_ephemeral",
      entity: {
        entity_type: "listed_instrument",
        symbol: "AAPL",
        ticker: "AAPL"
      },
      inputs: {
        symbol: "AAPL",
        max_expiries: 4,
        depth_preset: "compact",
        market_data_mode: "delayed"
      },
      outputs: {
        symbol: "AAPL",
        spot: 231.42,
        requested: {
          symbol: "AAPL",
          max_expiries: 4,
          depth_preset: "compact",
          market_data_mode: "delayed"
        },
        expiry_comparisons: [
          {
            expiry: "2026-09-18",
            days_to_expiry: 17,
            historical_volatility: 0.22,
            atm_implied_volatility: 0.31,
            volatility_premium: 0.09,
            implied_to_historical_ratio: 1.409,
            implied_move_pct: 0.042,
            comparison_status: "ok"
          }
        ],
        summary: {
          expiry_count: 1,
          ok_count: 1,
          average_volatility_premium: 0.09
        },
        quality: { observed_surface_cells: 21 },
        collection: { market_data_mode: "delayed" },
        warnings: ["Delayed listed-market data."]
      },
      source_ids: ["iv.realized_implied.aapl"],
      warnings: [],
      context_fingerprint: "fp-options",
      owning_tab: "iv",
      owning_mode: "realized_implied",
      materialization: {
        contract_version: "copilot.materialization.v1",
        payload_contract: "copilot.options-working-analysis.v1",
        target_tab: "iv",
        target_mode: "realized_implied",
        durable: false
      },
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-01T10:01:00Z",
      expires_at: "2026-09-08T10:00:00Z",
      materialized_at: "2026-09-01T10:02:00Z",
      discarded_at: null,
      read_only_safety: {},
      source_provider: "ibkr",
      origin: "gamma.iv.surface",
      transformation_note: "Read-only temporary workflow.",
      contract_version: "copilot.working-analysis.v1"
    };

    const { body } = render(CopilotOptionsWorkingAnalysis, { props: { analysis } });

    expect(body).toContain("Temporary");
    expect(body).toContain("Session ephemeral · unsaved");
    expect(body).toContain("AAPL");
    expect(body).toContain("2026/09/18");
    expect(body).toContain("22.0%");
    expect(body).toContain("31.0%");
    expect(body).toContain("9.0%");
    expect(body).toContain("1.41×");
    expect(body).toContain("Delayed listed-market data.");
    expect(body).toContain("gamma.iv.surface");
    expect(body).toContain("does not save an");
    expect(body).toContain("place an order");
    expect(body).not.toMatch(/>Save option set<|>Place order<|>Trade</i);
  });
});
