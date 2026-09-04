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

  it("renders exact temporary option-set legs without save or order authority", () => {
    const analysis: CopilotWorkingAnalysis = {
      analysis_id: "work-options-strategy-aapl",
      session_id: "session-options",
      run_id: "oprun-options",
      tool_id: "draft_options_strategy",
      domain: "iv",
      analysis_type: "options_strategy_draft",
      title: "AAPL call spread",
      status: "active",
      state_scope: "session_ephemeral",
      entity: { entity_type: "option_set", symbol: "AAPL" },
      inputs: {},
      outputs: {
        symbol: "AAPL",
        spot: 231.42,
        contracts: 2,
        requested: { depth_preset: "compact", market_data_mode: "delayed" },
        legs: [
          { side: "long", option_type: "call", expiry: "2026-09-18", strike: 230, quantity: 1, premium: 8.4, price_source: "midpoint" },
          { side: "short", option_type: "call", expiry: "2026-09-18", strike: 240, quantity: 1, premium: 3.2, price_source: "midpoint" }
        ],
        summary: {
          resolved_leg_count: 2,
          net_premium_total: -1040,
          premium_direction: "debit"
        },
        collection: { depth_preset: "compact", market_data_mode: "delayed" },
        quality: { observed_surface_cells: 21 },
        warnings: ["Delayed listed-market data."]
      },
      source_ids: ["iv.option_set.AAPL"],
      warnings: [],
      context_fingerprint: "fp-options",
      owning_tab: "iv",
      owning_mode: "strategies",
      materialization: {
        contract_version: "copilot.materialization.v1",
        payload_contract: "copilot.options-strategy-working-analysis.v1",
        target_tab: "iv",
        target_mode: "strategies",
        durable: false
      },
      created_at: "2026-09-04T10:00:00Z",
      updated_at: "2026-09-04T10:01:00Z",
      expires_at: "2026-09-11T10:00:00Z",
      materialized_at: "2026-09-04T10:02:00Z",
      discarded_at: null,
      read_only_safety: {},
      source_provider: "ibkr",
      origin: "gamma.iv.surface",
      transformation_note: "Exact-match option legs.",
      contract_version: "copilot.working-analysis.v1"
    };

    const { body } = render(CopilotOptionsWorkingAnalysis, { props: { analysis } });

    expect(body).toContain("AAPL call spread");
    expect(body).toContain("LONG");
    expect(body).toContain("SHORT");
    expect(body).toContain("2026/09/18");
    expect(body).toContain("230.00");
    expect(body).toContain("240.00");
    expect(body).toContain("8.40");
    expect(body).toContain("3.20");
    expect(body).toContain("midpoint");
    expect(body).toContain("does not save an");
    expect(body).toContain("place an order");
    expect(body).not.toMatch(/>Save option set<|>Place order<|>Trade</i);
  });
});
