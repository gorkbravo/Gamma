import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { StrategyLabCompositionResult, StrategyLabResult } from "../lib/api/types";
import { compositionBook, importedReturnsPayload, riskAttachTarget, scriptSignalPayload, strategyLabAttachTarget } from "../lib/idea-attach";
import { runOptionLabel, runSelectable, sweepOptionLabel, type PickerRun } from "../lib/idea-script-picker";
import AttachToIdea from "./AttachToIdea.svelte";

const metrics = { total_return: 0.1 } as StrategyLabResult["metrics"];

const RESULT: StrategyLabResult = {
  name: "Imported Strategy",
  value_kind: "return",
  benchmark_column: null,
  benchmark_value_kind: "return",
  metrics,
  returns_points: [],
  equity_curve_points: [],
  drawdown_points: [],
  benchmark_points: [],
  benchmark_equity_curve_points: [],
  rolling_points: [],
  monthly_returns: [],
  annual_returns: [],
  warnings: [],
  source_provider: "uploaded_csv",
  retrieved_at: "2026-11-23T10:00:00",
  origin: "research_service.strategy_lab.analyze",
  transformation_note: null,
  freshness_label: "derived",
};

const leg = (asset_class: string, identifier: string, weight: number) => ({ label: identifier, asset_class, identifier, weight, value_kind: "return" as const, return_points: [] });

const COMPOSITION: StrategyLabCompositionResult = {
  ...RESULT,
  name: "Megacap pair",
  source_provider: "research",
  portfolio_inputs: {
    name: "Megacap pair",
    legs: [leg("equity", "AAPL", 1), leg("crypto", "bitcoin", -0.5)],
    lenses: [],
    overlays: [],
    benchmark_symbol: "SPY",
    benchmark_object: null,
    lookback_days: 252,
    min_observations: 60,
  },
  leg_contributions: {},
  lenses: [],
  overlays: [],
  alignment_diagnostics: {},
};

describe("idea attach builders", () => {
  it("turns a composer book into a recomputable attach and refuses legs Ideas cannot price", () => {
    expect(compositionBook(COMPOSITION, "strategy_lab")).toEqual({
      book: {
        source: "strategy_lab", label: "Megacap pair", benchmark: "SPY", lookback_days: 252,
        legs: [
          { entity_type: "equity", symbol: "AAPL", weight: 1, label: "AAPL" },
          { entity_type: "crypto", symbol: "bitcoin", weight: -0.5, label: "bitcoin" },
        ],
      },
      reason: "",
    });
    const macro = { ...COMPOSITION, portfolio_inputs: { ...COMPOSITION.portfolio_inputs!, legs: [leg("custom_stream", "CPI", 1)] } };
    expect(compositionBook(macro, "strategy_lab").reason).toContain("CPI cannot be attached");
    expect(compositionBook(null, "risk_tab").reason).toBe("Compose a portfolio first.");
  });

  it("reads a Script result's provenance and an imported CSV as signals", () => {
    expect(scriptSignalPayload({ ...RESULT, analytical_provenance: { run_id: "r1", target: "weight_book" } })).toEqual({
      source: "script", output_kind: "weights", run_id: "r1", result_id: null, label: "Imported Strategy",
    });
    expect(scriptSignalPayload({ ...RESULT, analytical_provenance: { run_id: "r1", result_id: "strategy" } })?.output_kind).toBe("returns");
    expect(scriptSignalPayload(RESULT)).toBeNull();
    expect(importedReturnsPayload(RESULT, "date,return,benchmark\n2026-01-02,0.1%,0.2%", "date", "return")).toEqual({
      source: "import", output_kind: "returns", label: "Imported Strategy",
      rows: [{ date: "2026-01-02", return: "0.1%" }], date_column: "date", value_column: "return", value_kind: "return",
    });
    expect(importedReturnsPayload(RESULT, "", "date", "return")).toBeNull();
  });

  it("chooses what Strategy Lab and Risk attach and runs it through the store", async () => {
    const run = vi.fn(async () => null);
    const composed = strategyLabAttachTarget({ composition: COMPOSITION, result: COMPOSITION, csvText: "", dateColumn: "date", valueColumn: "return" }, run);
    expect(composed.target?.kindLabel).toBe("Backtest snapshot");
    await composed.target?.attach("idea1");
    expect(run).toHaveBeenCalledWith("idea1", expect.objectContaining({ kind: "test" }));
    const imported = strategyLabAttachTarget({ composition: null, result: RESULT, csvText: "date,return\n2026-01-02,1%", dateColumn: "date", valueColumn: "return" }, run);
    expect(imported.target?.summary).toContain("validation only");
    expect(strategyLabAttachTarget({ composition: null, result: null, csvText: "", dateColumn: "", valueColumn: "" }, run).reason).toBe("Analyze or compose a strategy first.");
    const risk = riskAttachTarget(COMPOSITION, run);
    expect(risk.target?.kindLabel).toBe("Risk snapshot");
    await risk.target?.attach("idea2");
    expect(run).toHaveBeenLastCalledWith("idea2", expect.objectContaining({ kind: "risk", book: expect.objectContaining({ source: "risk_tab" }) }));
    expect(riskAttachTarget(null, run).reason).toBe("Open a Strategy Lab research book in Risk first.");
  });

  it("labels picker runs and refuses safe previews and unfinished runs", () => {
    const base: PickerRun = {
      run_id: "abcdef123456", revision_id: "rev", status: "completed", started_at: "2026-11-10T14:00:00", completed_at: "2026-11-10T14:02:30",
      parameters_sha256: "ae8f1836bfc5", sweep_id: "sw", sweep_point_index: 2, runtime_kind: "openai_code_interpreter",
    };
    expect(runOptionLabel(base)).toBe("2026-11-10 14:02 UTC · sweep point 2 · parameters ae8f1836");
    expect(runSelectable(base)).toBe(true);
    expect(runSelectable({ ...base, runtime_kind: "mock_safe_preview" })).toBe(false);
    expect(runOptionLabel({ ...base, status: "timed_out", completed_at: null })).toContain("timed out");
    expect(runSelectable({ ...base, status: "failed" })).toBe(false);
    expect(sweepOptionLabel({ sweep_id: "86c63d12aaaa", created_at: "", points: [{ index: 0 }, { index: 1 }], axes: [{ name: "lookback", values: [] }, { name: "leverage", values: [] }] }))
      .toBe("Sweep 86c63d12 · 2 points · lookback × leverage");
  });
});

describe("AttachToIdea", () => {
  it("is disabled with its reason until there is something to attach", () => {
    const { body } = render(AttachToIdea, { props: { target: null, disabledReason: "Compose a portfolio first." } });
    expect(body).toContain("Attach to idea");
    expect(body).toContain("disabled");
    expect(body).toContain('title="Compose a portfolio first."');
  });

  it("names what it will attach in its title when enabled", () => {
    const target = { kindLabel: "Risk snapshot", label: "Book", summary: "Gamma runs Risk on this book again.", attach: async () => null };
    const { body } = render(AttachToIdea, { props: { target } });
    expect(body).toContain('title="Gamma runs Risk on this book again."');
    expect(body).not.toContain("disabled");
  });
});
