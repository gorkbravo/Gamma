import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";

import StrategyLabView from "./StrategyLabView.svelte";

describe("StrategyLabView Script mode", () => {
  it("exposes Script in the mode bar and selects the safe-preview workspace", () => {
    const { body } = render(StrategyLabView, {
      props: {
        mode: "script",
        onAnalyzeStrategy: vi.fn(),
        onLoadSaved: vi.fn(),
        onSaveResearch: vi.fn(),
        onDeleteSaved: vi.fn()
      }
    });

    expect(body).toContain("aria-label=\"Strategy Lab modes\"");
    expect(body).toContain(">Script</button>");
    expect(body).toMatch(/aria-selected="true"[^>]*>Script/);
    expect(body).toContain("Mock / Safe Preview");
    expect(body).not.toContain("Gamma Object Composer");
  });

  it("renders a temporary Copilot portfolio analysis in Composer", () => {
    const { body } = render(StrategyLabView, {
      props: {
        mode: "composer",
        workingAnalysis: {
          analysis_id: "work-strategy-1",
          title: "Temporary QQQ/IWM",
          status: "active",
          state_scope: "session_ephemeral",
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
          outputs: { metrics: { total_return: 0.12 }, temporary_assumptions: {} },
          warnings: [],
          owning_tab: "strategy_lab",
          owning_mode: "composer",
          materialization: {
            payload_contract: "copilot.strategy-lab-working-analysis.v1",
            target_tab: "strategy_lab",
            target_mode: "composer",
            durable: false
          }
        } as any,
        onAnalyzeStrategy: vi.fn(),
        onLoadSaved: vi.fn(),
        onSaveResearch: vi.fn(),
        onDeleteSaved: vi.fn()
      }
    });

    expect(body).toContain("Temporary Copilot Strategy Lab analysis");
    expect(body).toContain("Temporary QQQ/IWM");
    expect(body).toContain("Min Overlap");
    expect(body).toContain("-0.400");
  });
});
