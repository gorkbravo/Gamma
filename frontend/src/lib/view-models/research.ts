import type {
  ResearchConstituent,
  ResearchCoverage,
  ResearchOverviewMetricId,
  ResearchOverviewNode,
  ResearchOverviewResponse,
  ResearchResult,
  ResearchStructure,
  ResearchWeightPoint
} from "../api/types";

export type ResearchMode = "overview" | "scope_analysis";

export interface SyntheticPositionDraft {
  symbol: string;
  weight: number;
}

export interface ResearchPreviewRow {
  symbol: string;
  inputWeight: number;
  normalizedWeight: number;
}

export interface WeightSummary {
  totalWeight: number;
  normalizedTopWeight: number | null;
  top5Weight: number | null;
  concentrationHhi: number | null;
  effectivePositions: number | null;
}

export interface ResearchTreemapRect {
  node: ResearchOverviewNode;
  x: number;
  y: number;
  width: number;
  height: number;
  size: number;
  metricValue: number | null;
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

export function buildPreviewRows(
  scopeType: "single_ticker" | "synthetic_portfolio",
  primarySymbol: string,
  parsedSynthetic: SyntheticPositionDraft[]
): ResearchPreviewRow[] {
  if (scopeType === "single_ticker") {
    const symbol = primarySymbol.trim().toUpperCase();
    return symbol ? [{ symbol, inputWeight: 1, normalizedWeight: 1 }] : [];
  }

  const valid = parsedSynthetic.filter((item) => item.symbol && Number.isFinite(item.weight) && item.weight > 0);
  const totalWeight = valid.reduce((sum, item) => sum + item.weight, 0);
  return valid.map((item) => ({
    symbol: item.symbol,
    inputWeight: item.weight,
    normalizedWeight: totalWeight > 0 ? item.weight / totalWeight : 0
  }));
}

export function doesResearchDraftMatchResult(
  result: ResearchResult | null,
  draft: {
    scopeType: "single_ticker" | "synthetic_portfolio";
    primarySymbol: string;
    benchmarkSymbol: string;
  },
  previewRows: ResearchPreviewRow[]
): boolean {
  if (!result) {
    return false;
  }

  const normalizedBenchmark = draft.benchmarkSymbol.trim().toUpperCase() || "SPY";
  if (result.scope_type !== draft.scopeType || result.benchmark_symbol !== normalizedBenchmark) {
    return false;
  }

  if (draft.scopeType === "single_ticker") {
    return (result.primary_symbol ?? "") === (draft.primarySymbol.trim().toUpperCase() || "");
  }

  const normalizedPreview = [...previewRows]
    .map((row) => ({
      symbol: row.symbol,
      weight: Number(row.normalizedWeight.toFixed(4))
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));
  const normalizedResult = [...(result.weights ?? [])]
    .map((row) => ({
      symbol: row.symbol,
      weight: Number(row.weight.toFixed(4))
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));

  if (normalizedPreview.length !== normalizedResult.length) {
    return false;
  }

  return normalizedPreview.every((row, index) => {
    const candidate = normalizedResult[index];
    return candidate != null && candidate.symbol === row.symbol && Math.abs(candidate.weight - row.weight) < 1e-4;
  });
}

export function deriveStructureFromWeights(weights: ResearchWeightPoint[]): ResearchStructure {
  const summary = summarizeWeights(weights);
  return {
    total_weight: summary.totalWeight || null,
    top_weight: summary.normalizedTopWeight,
    top5_weight: summary.top5Weight,
    concentration_hhi: summary.concentrationHhi,
    effective_positions: summary.effectivePositions,
    aligned_symbol_count: weights.length
  };
}

export function deriveCoverageFromResearchResult(result: ResearchResult | null): ResearchCoverage {
  if (!result) {
    return {
      available_symbols: [],
      missing_symbols: [],
      benchmark_overlap_count: 0
    };
  }

  const available = result.weights?.map((item) => item.symbol) ?? [];
  const allSnapshotSymbols =
    result.snapshot?.positions
      ?.map((position) => position.symbol)
      .filter((symbol) => !String(symbol ?? "").startsWith("CASH")) ?? [];

  return {
    available_symbols: available,
    missing_symbols: allSnapshotSymbols.filter((symbol) => !available.includes(symbol)),
    benchmark_overlap_count: 0
  };
}

export function deriveConstituentsFromResearchResult(result: ResearchResult | null): ResearchConstituent[] {
  if (!result?.weights?.length) {
    return [];
  }

  return result.weights.map((weight) => ({
    symbol: weight.symbol,
    weight: weight.weight,
    total_return: null,
    annual_vol: null,
    max_drawdown: null,
    weighted_return: null
  }));
}

export function hasPopulatedStructure(structure: ResearchStructure | null | undefined): boolean {
  return Boolean(structure && (structure.aligned_symbol_count > 0 || structure.total_weight != null));
}

export function hasPopulatedCoverage(coverage: ResearchCoverage | null | undefined): boolean {
  return Boolean(
    coverage &&
      (coverage.available_symbols.length > 0 ||
        coverage.missing_symbols.length > 0 ||
        coverage.benchmark_overlap_count > 0)
  );
}

export function summarizeWeights(weights: ResearchWeightPoint[]): WeightSummary {
  if (!weights.length) {
    return {
      totalWeight: 0,
      normalizedTopWeight: null,
      top5Weight: null,
      concentrationHhi: null,
      effectivePositions: null
    };
  }
  const absoluteWeights = weights.map((item) => Math.abs(item.weight));
  const totalWeight = absoluteWeights.reduce((sum, value) => sum + value, 0);
  if (totalWeight <= 0) {
    return {
      totalWeight,
      normalizedTopWeight: null,
      top5Weight: null,
      concentrationHhi: null,
      effectivePositions: null
    };
  }
  const normalized = absoluteWeights.map((value) => value / totalWeight);
  const hhi = normalized.reduce((sum, value) => sum + value * value, 0);
  return {
    totalWeight,
    normalizedTopWeight: Math.max(...normalized),
    top5Weight: normalized.sort((left, right) => right - left).slice(0, 5).reduce((sum, value) => sum + value, 0),
    concentrationHhi: hhi,
    effectivePositions: hhi > 0 ? 1 / hhi : null
  };
}

export function getResearchOverviewMetricValue(
  node: ResearchOverviewNode,
  metricId: ResearchOverviewMetricId
): number | null {
  switch (metricId) {
    case "return":
      return node.metrics.total_return;
    case "volatility":
      return node.metrics.annual_volatility;
    case "beta":
      return node.metrics.beta;
    case "drawdown":
      return node.metrics.max_drawdown;
    case "relative_return":
      return node.metrics.relative_return;
  }
}

export function formatResearchOverviewMetricValue(
  value: number | null | undefined,
  metricId: ResearchOverviewMetricId
) {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  if (metricId === "beta") {
    return value.toFixed(2);
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function buildResearchTreemapLayout(
  overview: ResearchOverviewResponse | null,
  metricId: ResearchOverviewMetricId
): ResearchTreemapRect[] {
  const nodes = (overview?.nodes ?? [])
    .filter((node) => node.level === "instrument")
    .map((node) => ({
      node,
      size: Number.isFinite(node.size) && node.size > 0 ? node.size : 1,
      metricValue: getResearchOverviewMetricValue(node, metricId)
    }))
    .sort((left, right) => {
      const groupCompare = String(left.node.group ?? "").localeCompare(String(right.node.group ?? ""));
      if (groupCompare !== 0) {
        return groupCompare;
      }
      return right.size - left.size || left.node.label.localeCompare(right.node.label);
    });

  const rects: ResearchTreemapRect[] = [];
  layoutTreemapItems(nodes, 0, 0, 100, 100, rects);
  return rects;
}

function layoutTreemapItems(
  items: Array<{ node: ResearchOverviewNode; size: number; metricValue: number | null }>,
  x: number,
  y: number,
  width: number,
  height: number,
  rects: ResearchTreemapRect[]
) {
  if (!items.length || width <= 0 || height <= 0) {
    return;
  }

  if (items.length === 1) {
    const item = items[0];
    rects.push({
      node: item.node,
      x,
      y,
      width,
      height,
      size: item.size,
      metricValue: item.metricValue
    });
    return;
  }

  const total = items.reduce((sum, item) => sum + item.size, 0);
  if (total <= 0) {
    return;
  }

  const splitIndex = findBalancedTreemapSplit(items, total);
  const leftItems = items.slice(0, splitIndex);
  const rightItems = items.slice(splitIndex);
  const leftTotal = leftItems.reduce((sum, item) => sum + item.size, 0);
  const leftRatio = leftTotal / total;

  if (width >= height) {
    const leftWidth = width * leftRatio;
    layoutTreemapItems(leftItems, x, y, leftWidth, height, rects);
    layoutTreemapItems(rightItems, x + leftWidth, y, width - leftWidth, height, rects);
  } else {
    const topHeight = height * leftRatio;
    layoutTreemapItems(leftItems, x, y, width, topHeight, rects);
    layoutTreemapItems(rightItems, x, y + topHeight, width, height - topHeight, rects);
  }
}

function findBalancedTreemapSplit(
  items: Array<{ node: ResearchOverviewNode; size: number; metricValue: number | null }>,
  total: number
) {
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  let running = 0;
  for (let index = 0; index < items.length - 1; index += 1) {
    running += items[index].size;
    const distance = Math.abs(total / 2 - running);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index + 1;
    }
  }
  return bestIndex;
}
