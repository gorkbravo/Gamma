import type { ResearchResult } from "./api/types";
import type { IvLoadOptions, RiskComputeOptions } from "./stores/app";

export function buildRiskRequestFromResearch(research: ResearchResult | null): RiskComputeOptions | null {
  if (!research?.snapshot) {
    return null;
  }
  return {
    snapshot: research.snapshot,
    alpha: 0.95,
    lookbackDays: 252,
    horizonDays: 1,
    mcHorizonDays: 10,
    mcSimulationModel: "Gaussian",
    mcNumSimulations: 2000,
    betaWindow: 126,
    benchmarkSymbol: research.benchmark_symbol || "SPY"
  };
}

export function buildIvRequestFromResearch(
  research: ResearchResult | null,
  marketDataMode: string | null | undefined
): IvLoadOptions | null {
  if (research?.scope_type !== "single_ticker") {
    return null;
  }
  const symbol = research.snapshot?.positions?.[0]?.symbol;
  if (!symbol) {
    return null;
  }
  return {
    symbol,
    marketDataMode: marketDataMode ?? "delayed"
  };
}
