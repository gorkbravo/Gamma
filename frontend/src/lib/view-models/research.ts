import type {
  ResearchConstituent,
  ResearchCoverage,
  ResearchOverviewMetricId,
  ResearchOverviewNode,
  ResearchOverviewResponse,
  ResearchOverviewSortId,
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

export interface ResearchTreemapTile {
  node: ResearchOverviewNode;
  rect: TreemapRect;
  metricWeight: number;
  metricValue: number | null;
  colorValue: number | null;
}

export interface ResearchTreemapSection {
  label: string;
  rect: TreemapRect;
  tiles: ResearchTreemapTile[];
  metricWeight: number;
  nodeCount: number;
}

export interface TreemapRect {
  x: number;
  y: number;
  width: number;
  height: number;
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

interface ResearchSortMetricConfig {
  label: string;
  direction: "asc" | "desc";
  extractor: (node: ResearchOverviewNode) => number | null | undefined;
  weightTransform?: (value: number) => number;
}

const RESEARCH_SORT_METRIC_CONFIG: Record<ResearchOverviewSortId, ResearchSortMetricConfig> = {
  market_cap_desc: {
    label: "Market Cap",
    direction: "desc",
    extractor: (node) => node.market_cap_usd
  },
  universe_weight_desc: {
    label: "Universe Weight",
    direction: "desc",
    extractor: (node) => node.weight ?? node.size
  },
  return_desc: {
    label: "Return",
    direction: "desc",
    extractor: (node) => node.metrics.total_return
  },
  volatility_desc: {
    label: "Volatility",
    direction: "desc",
    extractor: (node) => node.metrics.annual_volatility
  },
  beta_desc: {
    label: "Beta",
    direction: "desc",
    extractor: (node) => node.metrics.beta
  },
  drawdown_desc: {
    label: "Drawdown",
    direction: "desc",
    extractor: (node) => node.metrics.max_drawdown,
    weightTransform: (value) => Math.abs(value)
  }
};

export function researchSortMetricLabel(sortBy: ResearchOverviewSortId) {
  return RESEARCH_SORT_METRIC_CONFIG[sortBy]?.label ?? "Market Cap";
}

export function getResearchOverviewSortValue(
  node: ResearchOverviewNode,
  sortBy: ResearchOverviewSortId
): number | null {
  const extracted = RESEARCH_SORT_METRIC_CONFIG[sortBy]?.extractor(node);
  return extracted == null || !Number.isFinite(extracted) ? null : extracted;
}

export function formatResearchOverviewSortValue(
  value: number | null | undefined,
  sortBy: ResearchOverviewSortId
) {
  if (value == null || !Number.isFinite(value)) {
    return "N/A";
  }
  switch (sortBy) {
    case "market_cap_desc": {
      const absolute = Math.abs(value);
      if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
      if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
      if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
      return `$${value.toFixed(0)}`;
    }
    case "universe_weight_desc":
      return value >= 1_000_000 ? formatResearchOverviewSortValue(value, "market_cap_desc") : value.toFixed(2);
    case "beta_desc":
      return value.toFixed(2);
    case "return_desc":
      return formatResearchOverviewMetricValue(value, "return");
    case "volatility_desc":
      return formatResearchOverviewMetricValue(value, "volatility");
    case "drawdown_desc":
      return formatResearchOverviewMetricValue(value, "drawdown");
  }
}

function sortMetricWeightMap(nodes: ResearchOverviewNode[], sortBy: ResearchOverviewSortId) {
  const config = RESEARCH_SORT_METRIC_CONFIG[sortBy] ?? RESEARCH_SORT_METRIC_CONFIG.market_cap_desc;
  const rawValues = nodes.map((node) => {
    const value = getResearchOverviewSortValue(node, sortBy);
    return value == null ? null : config.weightTransform ? config.weightTransform(value) : value;
  });
  const validValues = rawValues.filter((value): value is number => value != null && Number.isFinite(value));
  if (!validValues.length) {
    return nodes.map((node) => (Number.isFinite(node.size) && node.size > 0 ? node.size : 1));
  }
  const allEqual = validValues.every((value) => value === validValues[0]);
  if (allEqual) {
    return nodes.map((_, index) => (rawValues[index] == null ? 0 : 1));
  }
  if (config.direction === "asc") {
    const maxValue = Math.max(...validValues);
    return rawValues.map((value) => (value == null ? 0 : Math.max(maxValue - value, 0) + 1));
  }
  const minValue = Math.min(...validValues);
  const shift = minValue <= 0 ? Math.abs(minValue) + 1 : 0;
  return rawValues.map((value) => (value == null ? 0 : value + shift));
}

function sumWeights(weights: number[]) {
  return weights.reduce((sum, weight) => sum + Math.max(weight, 0), 0);
}

function chooseSplitIndex(weights: number[]) {
  const total = sumWeights(weights);
  if (weights.length <= 1 || total <= 0) {
    return 1;
  }
  let running = 0;
  let bestIndex = 1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < weights.length - 1; index += 1) {
    running += Math.max(weights[index], 0);
    const distance = Math.abs(total / 2 - running);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index + 1;
    }
  }
  return bestIndex;
}

function layoutWeightedRects(weights: number[], rect: TreemapRect): TreemapRect[] {
  if (!weights.length) {
    return [];
  }
  if (weights.length === 1) {
    return [rect];
  }

  const total = sumWeights(weights);
  if (total <= 0) {
    const equalShare = rect.width / weights.length;
    return weights.map((_, index) => ({
      x: rect.x + equalShare * index,
      y: rect.y,
      width: equalShare,
      height: rect.height
    }));
  }

  const splitIndex = chooseSplitIndex(weights);
  const firstWeights = weights.slice(0, splitIndex);
  const secondWeights = weights.slice(splitIndex);
  const ratio = sumWeights(firstWeights) / total;

  if (rect.width >= rect.height) {
    const firstWidth = rect.width * ratio;
    return [
      ...layoutWeightedRects(firstWeights, { x: rect.x, y: rect.y, width: firstWidth, height: rect.height }),
      ...layoutWeightedRects(secondWeights, {
        x: rect.x + firstWidth,
        y: rect.y,
        width: rect.width - firstWidth,
        height: rect.height
      })
    ];
  }

  const firstHeight = rect.height * ratio;
  return [
    ...layoutWeightedRects(firstWeights, { x: rect.x, y: rect.y, width: rect.width, height: firstHeight }),
    ...layoutWeightedRects(secondWeights, {
      x: rect.x,
      y: rect.y + firstHeight,
      width: rect.width,
      height: rect.height - firstHeight
    })
  ];
}

function sectionLayoutWeights(sectionWeights: number[]) {
  const total = sumWeights(sectionWeights);
  if (total <= 0) {
    return sectionWeights.map(() => 1);
  }
  return sectionWeights.map((weight) => Math.max(weight, 0));
}

export function treemapRectStyle(rect: TreemapRect) {
  return `left:${rect.x}%; top:${rect.y}%; width:${rect.width}%; height:${rect.height}%;`;
}

export function treemapArea(rect: TreemapRect) {
  return rect.width * rect.height;
}

export function treemapDensityClass(rect: TreemapRect) {
  const area = treemapArea(rect);
  if (area >= 420) {
    return "hero";
  }
  if (area >= 180) {
    return "major";
  }
  if (area >= 70) {
    return "minor";
  }
  return "micro";
}

export function buildResearchTreemapSections(
  overview: ResearchOverviewResponse | null,
  colorMetric: ResearchOverviewMetricId,
  sortBy: ResearchOverviewSortId = "market_cap_desc"
): ResearchTreemapSection[] {
  const nodes = (overview?.nodes ?? []).filter((node) => node.level === "instrument");
  const weightMap = sortMetricWeightMap(nodes, sortBy);
  const grouped = new Map<string, Array<{ node: ResearchOverviewNode; metricWeight: number; metricValue: number | null }>>();

  nodes.forEach((node, index) => {
    const label = node.group ?? node.sector ?? "Other";
    const rows = grouped.get(label) ?? [];
    rows.push({
      node,
      metricWeight: Math.max(weightMap[index] ?? 0, 0),
      metricValue: getResearchOverviewSortValue(node, sortBy)
    });
    grouped.set(label, rows);
  });

  const sections = Array.from(grouped.entries())
    .map(([label, rows]) => {
      const sortedRows = rows
        .slice()
        .sort(
          (left, right) =>
            right.metricWeight - left.metricWeight ||
            (left.node.sort_rank ?? Number.POSITIVE_INFINITY) - (right.node.sort_rank ?? Number.POSITIVE_INFINITY) ||
            left.node.label.localeCompare(right.node.label)
        );
      return {
        label,
        rows: sortedRows,
        metricWeight: sumWeights(sortedRows.map((row) => row.metricWeight))
      };
    })
    .filter((section) => section.rows.length > 0)
    .sort((left, right) => right.metricWeight - left.metricWeight || left.label.localeCompare(right.label));

  if (!sections.length) {
    return [];
  }

  const sectionRects = layoutWeightedRects(
    sectionLayoutWeights(sections.map((section) => (section.metricWeight > 0 ? section.metricWeight : 1))),
    { x: 0, y: 0, width: 100, height: 100 }
  );

  return sections.map<ResearchTreemapSection>((section, sectionIndex) => {
    const tileRects = layoutWeightedRects(
      section.rows.map((row) => (row.metricWeight > 0 ? row.metricWeight : 1)),
      { x: 0, y: 0, width: 100, height: 100 }
    );
    return {
      label: section.label,
      rect: sectionRects[sectionIndex],
      metricWeight: section.metricWeight,
      nodeCount: section.rows.length,
      tiles: section.rows.map<ResearchTreemapTile>((row, tileIndex) => ({
        node: row.node,
        metricWeight: row.metricWeight,
        metricValue: row.metricValue,
        colorValue: getResearchOverviewMetricValue(row.node, colorMetric),
        rect: tileRects[tileIndex]
      }))
    };
  });
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
