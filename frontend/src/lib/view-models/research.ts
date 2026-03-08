import type { ResearchWeightPoint } from "../api/types";

export interface SyntheticPositionDraft {
  symbol: string;
  weight: number;
}

export interface WeightSummary {
  totalWeight: number;
  normalizedTopWeight: number | null;
  effectivePositions: number | null;
}

export function parseSyntheticText(text: string): SyntheticPositionDraft[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [symbol, weight] = line.split(/[\s,:]+/);
      return {
        symbol: (symbol ?? "").trim().toUpperCase(),
        weight: Number(weight)
      };
    })
    .filter((item) => item.symbol);
}

export function normalizeSyntheticText(text: string): string {
  const parsed = parseSyntheticText(text).filter((item) => Number.isFinite(item.weight) && item.weight > 0);
  const total = parsed.reduce((sum, item) => sum + item.weight, 0);
  if (total <= 0) {
    return text;
  }
  return parsed
    .map((item) => `${item.symbol} ${(item.weight / total).toFixed(4)}`)
    .join("\n");
}

export function summarizeWeights(weights: ResearchWeightPoint[]): WeightSummary {
  if (!weights.length) {
    return {
      totalWeight: 0,
      normalizedTopWeight: null,
      effectivePositions: null
    };
  }
  const absoluteWeights = weights.map((item) => Math.abs(item.weight));
  const totalWeight = absoluteWeights.reduce((sum, value) => sum + value, 0);
  if (totalWeight <= 0) {
    return {
      totalWeight,
      normalizedTopWeight: null,
      effectivePositions: null
    };
  }
  const normalized = absoluteWeights.map((value) => value / totalWeight);
  const hhi = normalized.reduce((sum, value) => sum + value * value, 0);
  return {
    totalWeight,
    normalizedTopWeight: Math.max(...normalized),
    effectivePositions: hhi > 0 ? 1 / hhi : null
  };
}
