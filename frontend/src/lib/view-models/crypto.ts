import type { CryptoNarrativeBasket, CryptoToken } from "../api/types";

export type CryptoMode = "overview" | "deep_dive" | "flows_liquidity";
export type HeroCanvas = "token" | "basket";
export type MosaicVariant = "large" | "medium" | "small";

export interface MosaicTile {
  token: CryptoToken;
  colSpan: number;
  rowSpan: number;
}

export interface HeadlineMetric {
  label: string;
  value: string;
  meta: string | null;
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
  return values.reduce((sum, value) => sum + (value ?? 0), 0);
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

export function buildMosaicTiles(tokens: CryptoToken[], variant: MosaicVariant) {
  const scoped = tokens.slice(0, variant === "large" ? 10 : 8);
  const maxCap = Math.max(...scoped.map((token) => token.market_cap ?? 0), 1);
  const maxLog = Math.log10(maxCap + 1);
  return scoped.map<MosaicTile>((token) => {
    const normalized = maxLog > 0 ? Math.log10((token.market_cap ?? 0) + 1) / maxLog : 0;
    if (variant === "large") {
      return {
        token,
        colSpan: Math.max(3, Math.min(7, Math.round(3 + normalized * 4))),
        rowSpan: Math.max(2, Math.min(4, Math.round(2 + normalized * 2)))
      };
    }
    if (variant === "medium") {
      return {
        token,
        colSpan: Math.max(3, Math.min(5, Math.round(2 + normalized * 3))),
        rowSpan: Math.max(2, Math.min(3, Math.round(1 + normalized * 2)))
      };
    }
    return {
      token,
      colSpan: Math.max(2, Math.min(4, Math.round(2 + normalized * 2))),
      rowSpan: Math.max(1, Math.min(3, Math.round(1 + normalized * 2)))
    };
  });
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

export function mosaicStyle(tile: MosaicTile, variant: MosaicVariant) {
  const emphasis = variant === "large" ? 1 : variant === "medium" ? 0.9 : 0.8;
  return `grid-column: span ${tile.colSpan}; grid-row: span ${tile.rowSpan}; ${heatStyle(tile.token.price_change_pct_24h, emphasis)}`;
}

export function flowLeaderboardScore(token: CryptoToken) {
  const turnover = token.turnover_ratio_24h ?? 0;
  const move = Math.abs(token.price_change_pct_24h ?? 0);
  const volume = token.total_volume ?? 0;
  return (turnover * 120) + move + Math.min(Math.log10(volume + 1), 10);
}
