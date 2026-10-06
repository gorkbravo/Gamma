import type { GammaResearchObject, SavedResearchItem, StrategyLabBookValidation, StrategyLabCompositionResult } from "./api/types";
import type { StrategyPortfolioDraftLeg, StrategyPortfolioAssetClass } from "./view-models/research";

export const STRATEGY_EXPERIMENT_CONTRACT = "gamma.strategy-lab-experiment.v1";

export function compositionValidation(result: StrategyLabCompositionResult): StrategyLabBookValidation {
  return { valid: result.returns_points.length >= (result.portfolio_inputs?.min_observations ?? 2), errors: [],
    warnings: result.warnings, usable_leg_count: result.risk_legs?.length ?? 0,
    requested_leg_count: result.portfolio_inputs?.legs.filter((leg) => leg.weight !== 0).length ?? result.risk_legs?.length ?? 0,
    aligned_observation_count: result.returns_points.length, min_observations: result.portfolio_inputs?.min_observations ?? 2,
    alignment_diagnostics: result.alignment_diagnostics, retrieved_at: result.retrieved_at, origin: "strategy_lab.completed_composition" };
}

export function savedStrategyExperiment(item: SavedResearchItem): StrategyLabCompositionResult | null {
  const p = item.payload;
  if (item.object_type !== "strategy_lab" || p.experiment_contract !== STRATEGY_EXPERIMENT_CONTRACT
    || !p.portfolio_inputs || !Array.isArray(p.returns_points) || !Array.isArray(p.risk_legs)
    || !Array.isArray(p.benchmark_points) || !p.metrics || !p.alignment_diagnostics) return null;
  const result = p as unknown as StrategyLabCompositionResult;
  if (!Array.isArray(result.portfolio_inputs?.legs) || !result.risk_legs?.length
    || !result.returns_points.length || result.returns_points.some((p) => !Number.isFinite(p.value))) return null;
  return result;
}

export function frozenExperimentDraft(result: StrategyLabCompositionResult): StrategyPortfolioDraftLeg[] {
  const inputs = result.portfolio_inputs;
  if (!inputs) return [];
  let index = 0;
  return inputs.legs.map((input, position) => {
    const leg = input.weight === 0 ? null : result.risk_legs?.[index++] ?? null;
    const sources = result.alignment_diagnostics.legs;
    const source = Array.isArray(sources) ? sources.find((item) => item.label === input.label && item.identifier === input.identifier) : null;
    const symbol = input.identifier || leg?.symbol || input.label;
    const historyText = leg ? ["date,value", ...leg.return_points.map((p) => `${p.timestamp},${p.value}`)].join("\n") : "";
    const retainedObject: GammaResearchObject | undefined = leg ? {
      object_id: `${leg.instrument_id}:retained:${result.retrieved_at}`, object_type: "retained_strategy_leg",
      display_name: input.label, source_tab: "strategy_lab", source_mode: "saved_runs",
      resolver_capabilities: ["return_leg"], symbols: [symbol], constituents: [], weights: [],
      available_start: leg.return_points[0]?.timestamp ?? null, available_end: leg.return_points.at(-1)?.timestamp ?? null,
      provider_summary: `Retained ${leg.source_provider ?? "unknown"} history`,
      provenance: { ...source, source_provider: leg.source_provider, retrieved_at: result.retrieved_at, origin: source?.origin ?? result.origin,
        asset_class: input.asset_class, identifier: symbol, retained_experiment: true },
      warnings: leg.warnings, return_points: leg.return_points,
    } : undefined;
    return { id: `retained-leg-${position + 1}`, label: input.label, assetClass: input.asset_class as StrategyPortfolioAssetClass,
      identifier: symbol, weight: input.weight, valueKind: "return", historyText, objectOptionId: "", retainedObject };
  });
}

export function frozenExperimentBenchmark(result: StrategyLabCompositionResult): GammaResearchObject | null {
  const symbol = result.portfolio_inputs?.benchmark_symbol ?? result.portfolio_inputs?.benchmark_object?.symbols[0] ?? result.benchmark_column;
  if (!symbol || !result.benchmark_points.length) return null;
  return { object_id: `retained-benchmark:${symbol}:${result.retrieved_at}`, object_type: "retained_strategy_benchmark",
    display_name: result.benchmark_column ?? symbol, source_tab: "strategy_lab", source_mode: "saved_runs",
    resolver_capabilities: ["benchmark"], symbols: [symbol], constituents: [], weights: [],
    available_start: result.benchmark_points[0]?.timestamp ?? null, available_end: result.benchmark_points.at(-1)?.timestamp ?? null,
    provider_summary: "Retained experiment benchmark", provenance: { ...(result.alignment_diagnostics.benchmark as Record<string, unknown> ?? {}),
      retrieved_at: result.retrieved_at, origin: result.origin, retained_experiment: true },
    warnings: result.warnings, return_points: result.benchmark_points };
}
