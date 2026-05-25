export type HeroPriceStyle = "line" | "candlestick";
export type MovingAverageWindow = 20 | 50 | 200;

export interface HeroPricePoint {
  time: number;
  close: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
}

export interface ApiHeroPricePoint {
  timestamp: string | null | undefined;
  value?: number | null;
  price?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
}

export interface HeroPriceChartSettings {
  priceStyle: HeroPriceStyle;
  volumeOverlay: boolean;
  movingAverages: MovingAverageWindow[];
}

export interface HeroPriceChartAvailability {
  hasClose: boolean;
  hasOhlc: boolean;
  hasVolume: boolean;
}

export interface HeroChartPoint {
  time: number;
  value: number;
}

export interface HeroCandlestickPoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  type: "line" | "area" | "candlestick" | "histogram";
  data: Array<HeroChartPoint | HeroCandlestickPoint>;
  lineStyle?: "solid" | "dashed";
  priceScaleId?: string;
}

export const movingAverageWindows: MovingAverageWindow[] = [20, 50, 200];

export const defaultHeroPriceChartSettings: HeroPriceChartSettings = {
  priceStyle: "line",
  volumeOverlay: false,
  movingAverages: []
};

const movingAverageWindowSet = new Set<number>(movingAverageWindows);

export function normalizeHeroPriceChartSettings(value: unknown): HeroPriceChartSettings {
  if (!isRecord(value)) {
    return { ...defaultHeroPriceChartSettings, movingAverages: [...defaultHeroPriceChartSettings.movingAverages] };
  }

  const movingAverages = Array.isArray(value.movingAverages)
    ? value.movingAverages.filter((window): window is MovingAverageWindow => movingAverageWindowSet.has(window))
    : [];

  return {
    priceStyle: value.priceStyle === "candlestick" ? "candlestick" : "line",
    volumeOverlay: value.volumeOverlay === true,
    movingAverages: Array.from(new Set(movingAverages))
  };
}

export function heroPriceChartAvailability(points: Array<Partial<HeroPricePoint>> | null | undefined): HeroPriceChartAvailability {
  const rows = points ?? [];
  return {
    hasClose: rows.some((point) => isFiniteNumber(point.close)),
    hasOhlc: rows.some(hasValidOhlc),
    hasVolume: rows.some((point) => isFiniteNumber(point.volume))
  };
}

export function normalizeHeroPricePoints(points: Array<Partial<HeroPricePoint>> | null | undefined): HeroPricePoint[] {
  const byTime = new Map<number, HeroPricePoint>();
  for (const point of points ?? []) {
    if (!isFiniteNumber(point.time) || !isFiniteNumber(point.close)) {
      continue;
    }
    byTime.set(point.time, {
      time: point.time,
      close: point.close,
      ...(isFiniteNumber(point.open) ? { open: point.open } : {}),
      ...(isFiniteNumber(point.high) ? { high: point.high } : {}),
      ...(isFiniteNumber(point.low) ? { low: point.low } : {}),
      ...(isFiniteNumber(point.volume) ? { volume: point.volume } : {})
    });
  }
  return Array.from(byTime.values()).sort((left, right) => left.time - right.time);
}

export function heroPricePointFromApiPoint(point: ApiHeroPricePoint): HeroPricePoint | null {
  const time = parseApiTimestampToUtcSeconds(point.timestamp);
  const close = firstFiniteNumber(point.close, point.value, point.price);
  if (!isFiniteNumber(time) || !isFiniteNumber(close)) {
    return null;
  }
  return {
    time,
    close,
    ...(isFiniteNumber(point.open) ? { open: point.open } : {}),
    ...(isFiniteNumber(point.high) ? { high: point.high } : {}),
    ...(isFiniteNumber(point.low) ? { low: point.low } : {}),
    ...(isFiniteNumber(point.volume) ? { volume: point.volume } : {})
  };
}

export function computeSimpleMovingAverage(points: Array<Partial<HeroPricePoint>>, window: number): HeroChartPoint[] {
  if (!Number.isInteger(window) || window <= 0) {
    return [];
  }

  const normalized = normalizeHeroPricePoints(points);
  const averages: HeroChartPoint[] = [];
  let sum = 0;

  normalized.forEach((point, index) => {
    sum += point.close;
    if (index >= window) {
      sum -= normalized[index - window].close;
    }
    if (index >= window - 1) {
      averages.push({
        time: point.time,
        value: sum / window
      });
    }
  });

  return averages;
}

export function buildHeroPriceChartSeries(
  points: Array<Partial<HeroPricePoint>> | null | undefined,
  settings: HeroPriceChartSettings
): ChartSeries[] {
  const normalized = normalizeHeroPricePoints(points);
  const hasCompleteOhlc = normalized.length > 0 && normalized.every(hasValidOhlc);
  const movingAverages = Array.from(new Set(settings.movingAverages.filter((window) => movingAverageWindowSet.has(window))));
  const series: ChartSeries[] = [
    settings.priceStyle === "candlestick" && hasCompleteOhlc
      ? {
          id: "price",
          label: "Price",
          color: "var(--accent)",
          type: "candlestick",
          data: normalized.map((point) => ({
            time: point.time,
            open: point.open!,
            high: point.high!,
            low: point.low!,
            close: point.close
          }))
        }
      : {
          id: "price",
          label: "Price",
          color: "var(--accent)",
          type: "line",
          data: normalized.map((point) => ({ time: point.time, value: point.close }))
        }
  ];

  for (const window of movingAverages) {
    series.push({
      id: `ma-${window}`,
      label: `MA ${window}`,
      color: movingAverageColor(window),
      type: "line",
      lineStyle: "dashed",
      data: computeSimpleMovingAverage(normalized, window)
    });
  }

  if (settings.volumeOverlay && normalized.some((point) => isFiniteNumber(point.volume))) {
    series.push({
      id: "volume",
      label: "Volume",
      color: "var(--text-2)",
      type: "histogram",
      priceScaleId: "volume",
      data: normalized
        .filter((point) => isFiniteNumber(point.volume))
        .map((point) => ({ time: point.time, value: point.volume! }))
    });
  }

  return series;
}

export function heroPriceSettingsStorageKey(chartKey: string) {
  return `gamma.heroPriceChart.${chartKey}`;
}

function movingAverageColor(window: MovingAverageWindow) {
  switch (window) {
    case 20:
      return "var(--accent)";
    case 50:
      return "var(--warning)";
    case 200:
      return "var(--positive)";
    default:
      return "var(--text-2)";
  }
}

function hasValidOhlc(point: Partial<HeroPricePoint>) {
  return isFiniteNumber(point.open) && isFiniteNumber(point.high) && isFiniteNumber(point.low) && isFiniteNumber(point.close);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseApiTimestampToUtcSeconds(timestamp: string | null | undefined): number | null {
  if (!timestamp) {
    return null;
  }
  const millis = new Date(timestamp).getTime();
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : null;
}

function firstFiniteNumber(...values: Array<number | null | undefined>) {
  return values.find((value): value is number => isFiniteNumber(value)) ?? null;
}
