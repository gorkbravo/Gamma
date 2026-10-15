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

  // Regresión 27c18e0: el resultado conservado tras un fallo no debe confundirse con el borrador actual.
  it("marks a retained composition as stale after a failed recompose", () => {
    const point = { timestamp: "2026-03-01T00:00:00Z", value: 0.01 };
    const composition = {
      name: "Previous Composition",
      value_kind: "return",
      benchmark_column: null,
      returns_points: [point],
      equity_curve_points: [{ ...point, value: 1.01 }],
      drawdown_points: [{ ...point, value: 0 }],
      benchmark_points: [],
      benchmark_equity_curve_points: [],
      rolling_points: [],
      monthly_returns: [{ period: "2026-03", value: 0.01 }],
      annual_returns: [{ period: "2026", value: 0.01 }],
      warnings: [],
      metrics: { total_return: 0.01, observation_count: 1, frequency: "daily", max_drawdown: 0, max_drawdown_duration: 0 },
      leg_contributions: { QQQ: 1 },
      lenses: [],
      overlays: [],
      alignment_diagnostics: {}
    } as any;
    const props = { mode: "composer" as const, strategyComposition: composition, onAnalyzeStrategy: vi.fn(), onLoadSaved: vi.fn(), onSaveResearch: vi.fn(), onDeleteSaved: vi.fn() };

    const stale = render(StrategyLabView, { props: { ...props, compositionStaleMessage: "only 0 overlap" } }).body;
    const fresh = render(StrategyLabView, { props }).body;

    expect(stale).toContain("Previous Composition");
    expect(stale).toContain("data-testid=\"composition-stale\"");
    expect(stale).toContain("Latest composition failed; showing the last successful result.");
    expect(fresh).toContain("Previous Composition");
    expect(fresh).not.toContain("data-testid=\"composition-stale\"");
  });
});
