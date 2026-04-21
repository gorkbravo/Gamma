import type { IvSurface, TimeSeriesPoint } from "../api/types";

export type OptionsMode =
  | "surface"
  | "skew_term"
  | "realized_implied"
  | "distribution"
  | "source";

export const optionsModes: Array<{ id: OptionsMode; label: string }> = [
  { id: "surface", label: "Surface" },
  { id: "skew_term", label: "Skew & Term" },
  { id: "realized_implied", label: "Realized vs Implied" },
  { id: "distribution", label: "Implied Distribution" },
  { id: "source", label: "Source" },
];

export interface SurfaceStats {
  atmStrike: number | null;
  frontExpiry: string | null;
  frontAtmIv: number | null;
  backAtmIv: number | null;
  termSlope: number | null;
  minIv: number | null;
  maxIv: number | null;
  averageIv: number | null;
  populatedPoints: number;
}

export interface SkewRow {
  expiry: string;
  atmIv: number | null;
  putWingStrike: number | null;
  putWingIv: number | null;
  callWingStrike: number | null;
  callWingIv: number | null;
  putSkew: number | null;
  callSkew: number | null;
  wingSpread: number | null;
}

export interface RealizedVolatilityPoint {
  window: number;
  realizedVol: number | null;
  spreadToFrontIv: number | null;
  observationCount: number;
}

export interface DistributionBucket {
  price: number;
  probability: number;
  label: string;
}

export interface SurfacePath {
  id: string;
  points: string;
  value: number | null;
}

export function nearestStrikeIndex(surface: IvSurface | null): number {
  if (!surface?.strikes.length || surface.spot == null) {
    return 0;
  }
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  surface.strikes.forEach((strike, index) => {
    const distance = Math.abs(strike - surface.spot!);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

export function deriveTermStructure(surface: IvSurface | null): Array<{ expiry: string; iv: number | null }> {
  if (!surface) {
    return [];
  }
  const strikeIndex = nearestStrikeIndex(surface);
  return surface.expiries.map((expiry, rowIndex) => ({
    expiry,
    iv: surface.iv_grid[rowIndex]?.[strikeIndex] ?? null
  }));
}

export function deriveSurfaceStats(surface: IvSurface | null): SurfaceStats {
  const empty: SurfaceStats = {
    atmStrike: null,
    frontExpiry: null,
    frontAtmIv: null,
    backAtmIv: null,
    termSlope: null,
    minIv: null,
    maxIv: null,
    averageIv: null,
    populatedPoints: 0,
  };
  if (!surface?.expiries.length || !surface.strikes.length) {
    return empty;
  }

  const atmIndex = nearestStrikeIndex(surface);
  const values = surface.iv_grid.flat().filter((value) => Number.isFinite(value) && value > 0);
  const frontAtmIv = surface.iv_grid[0]?.[atmIndex] ?? null;
  const backAtmIv = surface.iv_grid[surface.iv_grid.length - 1]?.[atmIndex] ?? null;
  return {
    atmStrike: surface.strikes[atmIndex] ?? null,
    frontExpiry: surface.expiries[0] ?? null,
    frontAtmIv,
    backAtmIv,
    termSlope: frontAtmIv != null && backAtmIv != null ? backAtmIv - frontAtmIv : null,
    minIv: values.length ? Math.min(...values) : null,
    maxIv: values.length ? Math.max(...values) : null,
    averageIv: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
    populatedPoints: surface.points || values.length,
  };
}

export function deriveSkewRows(surface: IvSurface | null): SkewRow[] {
  if (!surface?.expiries.length || !surface.strikes.length) {
    return [];
  }
  const atmIndex = nearestStrikeIndex(surface);
  return surface.expiries.map((expiry, rowIndex) => {
    const row = surface.iv_grid[rowIndex] ?? [];
    const atmIv = row[atmIndex] ?? null;
    const lowerIndex = findNearestWingIndex(surface.strikes, atmIndex, "lower");
    const upperIndex = findNearestWingIndex(surface.strikes, atmIndex, "upper");
    const putWingIv = lowerIndex == null ? null : row[lowerIndex] ?? null;
    const callWingIv = upperIndex == null ? null : row[upperIndex] ?? null;
    return {
      expiry,
      atmIv,
      putWingStrike: lowerIndex == null ? null : surface.strikes[lowerIndex] ?? null,
      putWingIv,
      callWingStrike: upperIndex == null ? null : surface.strikes[upperIndex] ?? null,
      callWingIv,
      putSkew: putWingIv != null && atmIv != null ? putWingIv - atmIv : null,
      callSkew: callWingIv != null && atmIv != null ? callWingIv - atmIv : null,
      wingSpread: putWingIv != null && callWingIv != null ? putWingIv - callWingIv : null,
    };
  });
}

export function deriveRealizedVolatility(
  points: TimeSeriesPoint[] | null | undefined,
  frontAtmIv: number | null | undefined,
  windows = [20, 60, 120]
): RealizedVolatilityPoint[] {
  const prices = (points ?? [])
    .map((point) => Number(point.value))
    .filter((value) => Number.isFinite(value) && value > 0);
  const returns: number[] = [];
  for (let index = 1; index < prices.length; index += 1) {
    returns.push(Math.log(prices[index] / prices[index - 1]));
  }
  return windows.map((window) => {
    const sample = returns.slice(-window);
    const realizedVol = sample.length >= Math.max(5, Math.floor(window * 0.5))
      ? standardDeviation(sample) * Math.sqrt(252)
      : null;
    return {
      window,
      realizedVol,
      spreadToFrontIv: realizedVol != null && frontAtmIv != null ? frontAtmIv - realizedVol : null,
      observationCount: sample.length,
    };
  });
}

export function deriveDistributionBuckets(surface: IvSurface | null, bucketCount = 13): DistributionBucket[] {
  const stats = deriveSurfaceStats(surface);
  if (!surface?.spot || !stats.frontAtmIv || !stats.frontExpiry) {
    return [];
  }
  const days = daysToExpiry(stats.frontExpiry);
  const years = Math.max(days / 365, 1 / 365);
  const sigma = stats.frontAtmIv * Math.sqrt(years);
  if (!Number.isFinite(sigma) || sigma <= 0) {
    return [];
  }
  const count = Math.max(7, bucketCount | 1);
  const minPrice = surface.spot * Math.exp(-2.5 * sigma);
  const maxPrice = surface.spot * Math.exp(2.5 * sigma);
  const step = (maxPrice - minPrice) / Math.max(1, count - 1);
  const buckets = Array.from({ length: count }, (_, index) => {
    const price = minPrice + step * index;
    const lower = index === 0 ? 0 : price - step / 2;
    const upper = index === count - 1 ? Number.POSITIVE_INFINITY : price + step / 2;
    return {
      price,
      probability: logNormalCdf(upper, surface.spot, sigma) - logNormalCdf(lower, surface.spot, sigma),
      label: `${Math.round(price)}`,
    };
  });
  const total = buckets.reduce((sum, bucket) => sum + bucket.probability, 0);
  return total > 0
    ? buckets.map((bucket) => ({ ...bucket, probability: bucket.probability / total }))
    : buckets;
}

export function deriveSurfacePaths(surface: IvSurface | null, width = 520, height = 240): SurfacePath[] {
  if (!surface?.expiries.length || !surface.strikes.length) {
    return [];
  }
  const values = surface.iv_grid.flat().filter((value) => Number.isFinite(value));
  const minIv = values.length ? Math.min(...values) : 0;
  const maxIv = values.length ? Math.max(...values) : 1;
  const valueRange = Math.max(maxIv - minIv, 0.01);
  const rowCount = surface.expiries.length;
  const colCount = surface.strikes.length;

  const project = (rowIndex: number, colIndex: number, value: number | null | undefined) => {
    const xRatio = colCount <= 1 ? 0.5 : colIndex / (colCount - 1);
    const yRatio = rowCount <= 1 ? 0.5 : rowIndex / (rowCount - 1);
    const zRatio = value == null || !Number.isFinite(value) ? 0 : (value - minIv) / valueRange;
    const x = 32 + xRatio * (width - 112) + yRatio * 54;
    const y = height - 42 - yRatio * 92 - zRatio * 92;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  const paths: SurfacePath[] = [];
  surface.iv_grid.forEach((row, rowIndex) => {
    paths.push({
      id: `expiry-${rowIndex}`,
      points: row.map((value, colIndex) => project(rowIndex, colIndex, value)).join(" "),
      value: row[nearestStrikeIndex(surface)] ?? null,
    });
  });
  for (let colIndex = 0; colIndex < colCount; colIndex += Math.max(1, Math.floor(colCount / 8))) {
    paths.push({
      id: `strike-${colIndex}`,
      points: surface.iv_grid.map((row, rowIndex) => project(rowIndex, colIndex, row[colIndex])).join(" "),
      value: surface.iv_grid[0]?.[colIndex] ?? null,
    });
  }
  return paths;
}

export function daysToExpiry(expiry: string | null | undefined, now = new Date()): number {
  if (!expiry) {
    return 0;
  }
  const match = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(expiry);
  if (!match) {
    return 0;
  }
  const expiryDate = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.max(0, Math.round((expiryDate.getTime() - today) / 86_400_000));
}

function findNearestWingIndex(strikes: number[], atmIndex: number, side: "lower" | "upper") {
  if (!strikes.length) {
    return null;
  }
  const targetOffset = Math.max(2, Math.round(strikes.length * 0.18));
  const index = side === "lower" ? atmIndex - targetOffset : atmIndex + targetOffset;
  const bounded = Math.max(0, Math.min(strikes.length - 1, index));
  return bounded === atmIndex ? null : bounded;
}

function standardDeviation(values: number[]) {
  if (values.length < 2) {
    return 0;
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function logNormalCdf(price: number, spot: number, sigma: number) {
  if (price <= 0) {
    return 0;
  }
  if (!Number.isFinite(price)) {
    return 1;
  }
  return normalCdf(Math.log(price / spot) / sigma);
}

function normalCdf(value: number) {
  return 0.5 * (1 + erf(value / Math.SQRT2));
}

function erf(value: number) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * x);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return sign * y;
}
