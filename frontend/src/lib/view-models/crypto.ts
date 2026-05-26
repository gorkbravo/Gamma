import type { CryptoNarrativeBasket, CryptoToken } from "../api/types";
import type { CryptoSortBy } from "../stores/app";

export type CryptoMode = "overview" | "deep_dive" | "flows_liquidity";
export type HeroCanvas = "token" | "basket";

export interface TreemapRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CryptoTreemapTile {
  token: CryptoToken;
  rect: TreemapRect;
  metricWeight: number;
  metricValue: number | null;
}

export interface CryptoTreemapSection {
  label: string;
  rect: TreemapRect;
  tiles: CryptoTreemapTile[];
  metricWeight: number;
  tokenCount: number;
}

export interface HeadlineMetric {
  label: string;
  value: string;
  meta: string | null;
  metaTone?: string | null;
}

export interface FocusRow {
  label: string;
  value: string;
  body: string;
  tone?: string;
}

export interface BasketPreset {
  id: string;
  label: string;
  text: string;
}

export interface PreviewRow {
  symbol: string;
  inputWeight: number;
  normalizedWeight: number;
  resolvedToken: CryptoToken | null;
}

export interface SyntheticDraftRow {
  symbol: string;
  weight: number;
}

export function weightedAverageCryptoTokens(
  rows: CryptoToken[],
  valueGetter: (token: CryptoToken) => number | null | undefined,
  weightGetter: (token: CryptoToken) => number | null | undefined
) {
  const pairs = rows
    .map((token) => ({
      value: valueGetter(token),
      weight: weightGetter(token) ?? 0
    }))
    .filter((row) => row.value != null && row.weight > 0) as Array<{ value: number; weight: number }>;
  if (!pairs.length) {
    return null;
  }
  const denominator = pairs.reduce((sum, row) => sum + row.weight, 0);
  if (denominator <= 0) {
    return null;
  }
  return pairs.reduce((sum, row) => sum + row.value * row.weight, 0) / denominator;
}

export function medianNumbers(values: Array<number | null | undefined>) {
  const clean = values.filter((value): value is number => value != null).sort((left, right) => left - right);
  if (!clean.length) {
    return null;
  }
  const middle = Math.floor(clean.length / 2);
  if (clean.length % 2 === 0) {
    return (clean[middle - 1] + clean[middle]) / 2;
  }
  return clean[middle];
}

export function sumNullableNumbers(values: Array<number | null | undefined>) {
  return values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
}

export function narrativePresetText(basket: CryptoNarrativeBasket) {
  if (!basket.top_tokens.length) {
    return "";
  }
  const equalWeight = 1 / basket.top_tokens.length;
  return basket.top_tokens
    .map((token) => `${(token.symbol ?? token.token_id ?? "").toUpperCase()} ${equalWeight.toFixed(4)}`)
    .join("\n");
}

export function buildSyntheticPreviewRows(rows: SyntheticDraftRow[], tokens: CryptoToken[]) {
  const valid = rows.filter((item) => item.symbol && Number.isFinite(item.weight) && item.weight > 0);
  const total = valid.reduce((sum, item) => sum + item.weight, 0);
  const lookup = new Map(tokens.map((token) => [token.symbol.toUpperCase(), token]));
  return valid.map<PreviewRow>((item) => ({
    symbol: item.symbol,
    inputWeight: item.weight,
    normalizedWeight: total > 0 ? item.weight / total : 0,
    resolvedToken: lookup.get(item.symbol.toUpperCase()) ?? null
  }));
}

interface SortMetricConfig {
  label: string;
  direction: "asc" | "desc";
  extractor: (token: CryptoToken) => number | null | undefined;
}

const SORT_METRIC_CONFIG: Record<CryptoSortBy, SortMetricConfig> = {
  market_cap_desc: {
    label: "Market Cap",
    direction: "desc",
    extractor: (token) => token.market_cap
  },
  screen_score_desc: {
    label: "Screen Score",
    direction: "desc",
    extractor: (token) => token.screen_score
  },
  volume_desc: {
    label: "Volume",
    direction: "desc",
    extractor: (token) => token.total_volume
  },
  turnover_desc: {
    label: "Turnover",
    direction: "desc",
    extractor: (token) => token.turnover_ratio_24h
  },
  momentum_desc: {
    label: "Momentum",
    direction: "desc",
    extractor: (token) => token.price_change_pct_30d ?? token.price_change_pct_7d ?? token.price_change_pct_24h
  },
  fdv_premium_asc: {
    label: "FDV Discount",
    direction: "asc",
    extractor: (token) => token.fdv_premium_ratio
  }
};

export function cryptoSortMetricLabel(sortBy: CryptoSortBy) {
  return SORT_METRIC_CONFIG[sortBy]?.label ?? "Market Cap";
}

function sortMetricValue(token: CryptoToken, sortBy: CryptoSortBy): number | null {
  const extracted = SORT_METRIC_CONFIG[sortBy]?.extractor(token);
  return extracted == null || !Number.isFinite(extracted) ? null : extracted;
}

function sortMetricWeightMap(tokens: CryptoToken[], sortBy: CryptoSortBy) {
  const config = SORT_METRIC_CONFIG[sortBy] ?? SORT_METRIC_CONFIG.market_cap_desc;
  const rawValues = tokens.map((token) => sortMetricValue(token, sortBy));
  const validValues = rawValues.filter((value): value is number => value != null);
  if (!validValues.length) {
    return tokens.map(() => 1);
  }
  const allEqual = validValues.every((value) => value === validValues[0]);
  if (allEqual) {
    return tokens.map((_, index) => (rawValues[index] == null ? 0 : 1));
  }
  if (config.direction === "asc") {
    const maxValue = Math.max(...validValues);
    return rawValues.map((value) => {
      if (value == null) {
        return 0;
      }
      return Math.max(maxValue - value, 0) + 1;
    });
  }
  const minValue = Math.min(...validValues);
  const shift = minValue <= 0 ? Math.abs(minValue) + 1 : 0;
  return rawValues.map((value) => {
    if (value == null) {
      return 0;
    }
    return value + shift;
  });
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
  const firstTotal = sumWeights(firstWeights);
  const ratio = firstTotal / total;

  if (rect.width >= rect.height) {
    const firstWidth = rect.width * ratio;
    return [
      ...layoutWeightedRects(firstWeights, {
        x: rect.x,
        y: rect.y,
        width: firstWidth,
        height: rect.height
      }),
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
    ...layoutWeightedRects(firstWeights, {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: firstHeight
    }),
    ...layoutWeightedRects(secondWeights, {
      x: rect.x,
      y: rect.y + firstHeight,
      width: rect.width,
      height: rect.height - firstHeight
    })
  ];
}

function normalizeLayerLabel(token: CryptoToken) {
  return token.layer_bucket ?? "Other";
}

function sectionLayoutWeights(sectionWeights: number[]) {
  const total = sumWeights(sectionWeights);
  if (total <= 0) {
    return sectionWeights.map(() => 1);
  }
  return sectionWeights.map((weight) => {
    const share = Math.max(weight, 0) / total;
    return 0.24 + Math.sqrt(share);
  });
}

export function buildLayerTreemap(tokens: CryptoToken[], sortBy: CryptoSortBy = "market_cap_desc") {
  const weightMap = sortMetricWeightMap(tokens, sortBy);
  const grouped = new Map<string, Array<{ token: CryptoToken; metricWeight: number; metricValue: number | null }>>();

  tokens.forEach((token, index) => {
    const label = normalizeLayerLabel(token);
    const rows = grouped.get(label) ?? [];
    rows.push({
      token,
      metricWeight: Math.max(weightMap[index] ?? 0, 0),
      metricValue: sortMetricValue(token, sortBy)
    });
    grouped.set(label, rows);
  });

  const orderedLabels = ["Layer 1", "Layer 2", "Layer 3", "Other"];
  const sections = Array.from(grouped.entries())
    .sort((left, right) => {
      const leftIndex = orderedLabels.indexOf(left[0]);
      const rightIndex = orderedLabels.indexOf(right[0]);
      const leftOrder = leftIndex >= 0 ? leftIndex : orderedLabels.length;
      const rightOrder = rightIndex >= 0 ? rightIndex : orderedLabels.length;
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      return left[0].localeCompare(right[0]);
    })
    .map(([label, rows]) => {
      const sortedRows = rows
        .slice()
        .sort((left, right) => (right.metricWeight - left.metricWeight) || left.token.name.localeCompare(right.token.name));
      return {
        label,
        rows: sortedRows,
        metricWeight: sumWeights(sortedRows.map((row) => row.metricWeight))
      };
    })
    .filter((section) => section.rows.length > 0);

  if (!sections.length) {
    return [];
  }

  const sectionRects = layoutWeightedRects(
    sectionLayoutWeights(sections.map((section) => section.metricWeight > 0 ? section.metricWeight : 1)),
    { x: 0, y: 0, width: 100, height: 100 }
  );

  return sections.map<CryptoTreemapSection>((section, sectionIndex) => {
    const tileRects = layoutWeightedRects(
      section.rows.map((row) => row.metricWeight > 0 ? row.metricWeight : 1),
      { x: 0, y: 0, width: 100, height: 100 }
    );
    return {
      label: section.label,
      rect: sectionRects[sectionIndex],
      metricWeight: section.metricWeight,
      tokenCount: section.rows.length,
      tiles: section.rows.map<CryptoTreemapTile>((row, tileIndex) => ({
        token: row.token,
        metricWeight: row.metricWeight,
        metricValue: row.metricValue,
        rect: tileRects[tileIndex]
      }))
    };
  });
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

export function treemapMetricText(value: number | null | undefined, sortBy: CryptoSortBy) {
  if (value == null) {
    return "N/A";
  }
  switch (sortBy) {
    case "market_cap_desc":
    case "volume_desc": {
      const absolute = Math.abs(value);
      if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
      if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
      if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
      if (absolute >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
      return `$${value.toFixed(0)}`;
    }
    case "turnover_desc":
    case "fdv_premium_asc":
      return `${value.toFixed(2)}x`;
    case "screen_score_desc":
      return value.toFixed(1);
    case "momentum_desc":
      return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
    default:
      return String(value);
  }
}

export function heatStyle(value: number | null | undefined, emphasis = 1) {
  if (value == null) {
    return "background: color-mix(in srgb, var(--accent) 8%, transparent); border-color: var(--divider);";
  }
  const intensity = Math.min(Math.abs(value) / 14, 1);
  const fill = Math.round((12 + intensity * 28) * emphasis);
  const tone = value >= 0 ? "var(--positive)" : "var(--negative)";
  const border = Math.min(fill + 12, 46);
  return `background: color-mix(in srgb, ${tone} ${fill}%, transparent); border-color: color-mix(in srgb, ${tone} ${border}%, var(--panel-border));`;
}

export function flowLeaderboardScore(token: CryptoToken) {
  const turnover = token.turnover_ratio_24h ?? 0;
  const move = Math.abs(token.price_change_pct_24h ?? 0);
  const volume = token.total_volume ?? 0;
  return (turnover * 120) + move + Math.min(Math.log10(volume + 1), 10);
}
