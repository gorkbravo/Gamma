import { describe, expect, it } from "vitest";
import type { SavedResearchItem, StrategyLabCompositionResult } from "./api/types";
import { compositionValidation, frozenExperimentBenchmark, frozenExperimentDraft, savedStrategyExperiment, STRATEGY_EXPERIMENT_CONTRACT } from "./strategy-experiments";
import { buildStrategyPortfolioLegInputs } from "./view-models/research";

const points = [{ timestamp: "2026-01-01T00:00:00", value: 0.01 }, { timestamp: "2026-01-02T00:00:00", value: -0.01 }];
const result = () => ({ name: "QQQ minus SPY", returns_points: points, benchmark_points: points,
  risk_legs: [{ label: "QQQ", symbol: "QQQ", instrument_id: "qqq", weight: 0.5, return_points: points, source_provider: "ibkr", warnings: [] },
    { label: "SPY", symbol: "SPY", instrument_id: "spy", weight: -0.5, return_points: points, source_provider: "ibkr", warnings: [] }],
  portfolio_inputs: { name: "QQQ minus SPY", legs: [{ label: "QQQ", asset_class: "etf", identifier: "QQQ", weight: 1 },
    { label: "SPY", asset_class: "etf", identifier: "SPY", weight: -1 }], benchmark_symbol: "SPY", lookback_days: 260, min_observations: 2 },
  warnings: [], metrics: {}, alignment_diagnostics: {}, retrieved_at: "2026-10-06T12:00:00", origin: "fixture" } as unknown as StrategyLabCompositionResult);

describe("saved Strategy Lab experiments", () => {
  it("restores raw signed weights and retained source history for an isolated revision", () => {
    const original = result();
    const draft = frozenExperimentDraft(original);
    expect(draft.map((leg) => leg.weight)).toEqual([1, -1]);
    draft[0].weight = 2;
    const built = buildStrategyPortfolioLegInputs(draft, []);
    expect(built.warnings).toEqual([]);
    expect(built.legs[0].weight).toBe(2);
    expect(built.legs[0].object?.provenance.source_provider).toBe("ibkr");
    expect(built.legs[0].object?.return_points).toEqual(points);
    expect(original.portfolio_inputs?.legs[0].weight).toBe(1);
    expect(frozenExperimentBenchmark(original)?.return_points).toEqual(points);
  });
  it("does not let an edited identity reuse the retained object", () => {
    const draft = frozenExperimentDraft(result());
    draft[0].identifier = "IWM";
    draft[0].historyText = "";
    const input = buildStrategyPortfolioLegInputs(draft, []).legs[0];
    expect(input.object).toBeNull();
    expect(input.return_points).toEqual([]);
    expect(input.identifier).toBe("IWM");
  });
  it("reopens only the supported experiment contract without altering retained result fields", () => {
    const composition = result();
    const item = { object_type: "strategy_lab", payload: { ...composition, experiment_contract: STRATEGY_EXPERIMENT_CONTRACT } } as unknown as SavedResearchItem;
    expect(savedStrategyExperiment(item)?.portfolio_inputs).toEqual(composition.portfolio_inputs);
    expect(savedStrategyExperiment({ ...item, payload: { ...item.payload, experiment_contract: "future.v2" } })).toBeNull();
    expect(savedStrategyExperiment({ ...item, payload: { ...item.payload, risk_legs: [] } })).toBeNull();
    expect(compositionValidation(composition).aligned_observation_count).toBe(2);
  });
});
