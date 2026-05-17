# Hero Chart Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add compact, data-aware customization controls to selected hero price charts without changing ordinary Gamma line charts.

**Architecture:** Add a view-model helper that adapts close/volume/OHLC inputs into chart series, then extend `TimeSeriesChart.svelte` with additive candlestick and histogram support. A new `HeroPriceChart.svelte` wrapper owns header settings, persistence, availability labels, and delegates rendering to `TimeSeriesChart`.

**Tech Stack:** Svelte 5, TypeScript, Vitest, `lightweight-charts` 5.1.0, existing Gamma chart tokens and dense panel patterns.

---

## File Structure

- Create `frontend/src/lib/view-models/hero-price-chart.ts`
  - Owns `HeroPricePoint`, `HeroPriceChartSettings`, persistence helpers, availability logic, SMA calculation, and series assembly.
- Create `frontend/src/lib/view-models/hero-price-chart.test.ts`
  - Unit tests for settings normalization, availability, moving averages, and series assembly.
- Modify `frontend/src/components/TimeSeriesChart.svelte`
  - Add `candlestick` and `histogram` series types without changing existing callers.
- Modify `frontend/src/components/TimeSeriesChart.test.ts`
  - Server-render test that proves new series types are accepted by the component contract.
- Create `frontend/src/components/HeroPriceChart.svelte`
  - Hero-only wrapper with compact settings button, dropdown, settings persistence, and disabled labels.
- Create `frontend/src/components/HeroPriceChart.test.ts`
  - Server-render tests for the settings button and disabled state copy.
- Modify `frontend/src/views/FundamentalsView.svelte`
  - Replace overview market-context `TimeSeriesChart` usage with `HeroPriceChart`.
- Modify `frontend/src/views/ResearchView.svelte`
  - Use `HeroPriceChart` only for single-ticker price mode.
- Modify `frontend/src/views/CryptoView.svelte`
  - Use `HeroPriceChart` for token hero history; keep synthetic basket chart on `TimeSeriesChart`.
- Modify existing view tests if markup changes require stable assertions.

---

### Task 1: Add Hero Price Chart View-Model Helpers

**Files:**
- Create: `frontend/src/lib/view-models/hero-price-chart.ts`
- Create: `frontend/src/lib/view-models/hero-price-chart.test.ts`

- [ ] **Step 1: Write failing tests for availability and moving averages**

Create `frontend/src/lib/view-models/hero-price-chart.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  buildHeroPriceChartSeries,
  computeSimpleMovingAverage,
  defaultHeroPriceChartSettings,
  heroPriceChartAvailability,
  normalizeHeroPriceChartSettings,
  type HeroPricePoint
} from "./hero-price-chart";

const closeOnly: HeroPricePoint[] = [
  { time: 1 as never, close: 10 },
  { time: 2 as never, close: 11 },
  { time: 3 as never, close: 12 }
];

const withVolume: HeroPricePoint[] = [
  { time: 1 as never, close: 10, volume: 100 },
  { time: 2 as never, close: 11, volume: 120 },
  { time: 3 as never, close: 12, volume: 90 }
];

const ohlcv: HeroPricePoint[] = [
  { time: 1 as never, open: 9, high: 11, low: 8, close: 10, volume: 100 },
  { time: 2 as never, open: 10, high: 12, low: 9, close: 11, volume: 120 },
  { time: 3 as never, open: 11, high: 13, low: 10, close: 12, volume: 90 }
];

describe("hero price chart view-model", () => {
  it("keeps candles and volume unavailable for close-only history", () => {
    expect(heroPriceChartAvailability(closeOnly)).toEqual({
      hasClose: true,
      hasOhlc: false,
      hasVolume: false
    });
  });

  it("detects volume and full OHLC availability independently", () => {
    expect(heroPriceChartAvailability(withVolume).hasVolume).toBe(true);
    expect(heroPriceChartAvailability(withVolume).hasOhlc).toBe(false);
    expect(heroPriceChartAvailability(ohlcv)).toEqual({
      hasClose: true,
      hasOhlc: true,
      hasVolume: true
    });
  });

  it("computes simple moving averages only after a full window exists", () => {
    expect(computeSimpleMovingAverage(closeOnly, 2)).toEqual([
      { time: 2 as never, value: 10.5 },
      { time: 3 as never, value: 11.5 }
    ]);
  });

  it("normalizes invalid persisted settings to the default contract", () => {
    expect(normalizeHeroPriceChartSettings({ priceStyle: "bad", movingAverages: [20, 13, 200], volumeOverlay: true })).toEqual({
      ...defaultHeroPriceChartSettings,
      volumeOverlay: true,
      movingAverages: [20, 200]
    });
  });

  it("falls back to line rendering when candles are requested without OHLC", () => {
    const series = buildHeroPriceChartSeries(closeOnly, {
      priceStyle: "candles",
      volumeOverlay: true,
      movingAverages: [2]
    });

    expect(series.map((item) => item.id)).toEqual(["price", "ma-2"]);
    expect(series[0]?.type).toBe("line");
    expect(series[1]?.data).toEqual([
      { time: 2 as never, value: 10.5 },
      { time: 3 as never, value: 11.5 }
    ]);
  });

  it("builds candle and volume series when OHLCV is available", () => {
    const series = buildHeroPriceChartSeries(ohlcv, {
      priceStyle: "candles",
      volumeOverlay: true,
      movingAverages: []
    });

    expect(series.map((item) => [item.id, item.type])).toEqual([
      ["price", "candlestick"],
      ["volume", "histogram"]
    ]);
  });
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
npm --prefix frontend test -- src/lib/view-models/hero-price-chart.test.ts
```

Expected: FAIL because `frontend/src/lib/view-models/hero-price-chart.ts` does not exist.

- [ ] **Step 3: Implement the view-model helper**

Create `frontend/src/lib/view-models/hero-price-chart.ts`:

```ts
import type { UTCTimestamp } from "lightweight-charts";
import type { ChartSeries } from "../../components/TimeSeriesChart.svelte";
import { normalizeChartData } from "../chart-data";

export type HeroPriceStyle = "line" | "candles";
export type MovingAverageWindow = 20 | 50 | 200;

export interface HeroPricePoint {
  time: UTCTimestamp;
  close: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
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

export const movingAverageWindows: MovingAverageWindow[] = [20, 50, 200];

export const defaultHeroPriceChartSettings: HeroPriceChartSettings = {
  priceStyle: "line",
  volumeOverlay: false,
  movingAverages: []
};

const movingAverageColors: Record<MovingAverageWindow, string> = {
  20: "var(--chart-secondary)",
  50: "var(--text-1)",
  200: "var(--chart-negative)"
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function uniqueMovingAverages(values: unknown): MovingAverageWindow[] {
  if (!Array.isArray(values)) return [];
  return movingAverageWindows.filter((window) => values.includes(window));
}

export function normalizeHeroPriceChartSettings(value: unknown): HeroPriceChartSettings {
  if (!value || typeof value !== "object") return { ...defaultHeroPriceChartSettings };
  const candidate = value as Partial<HeroPriceChartSettings>;
  return {
    priceStyle: candidate.priceStyle === "candles" ? "candles" : "line",
    volumeOverlay: candidate.volumeOverlay === true,
    movingAverages: uniqueMovingAverages(candidate.movingAverages)
  };
}

export function heroPriceChartAvailability(points: readonly HeroPricePoint[]): HeroPriceChartAvailability {
  const normalized = normalizeHeroPricePoints(points);
  return {
    hasClose: normalized.some((point) => isFiniteNumber(point.close)),
    hasOhlc: normalized.length > 0 && normalized.every((point) => isFiniteNumber(point.open) && isFiniteNumber(point.high) && isFiniteNumber(point.low) && isFiniteNumber(point.close)),
    hasVolume: normalized.some((point) => isFiniteNumber(point.volume) && point.volume > 0)
  };
}

export function normalizeHeroPricePoints(points: readonly HeroPricePoint[]): HeroPricePoint[] {
  const byTime = new Map<number, HeroPricePoint>();
  for (const point of points) {
    if (!Number.isFinite(point.time) || !isFiniteNumber(point.close)) continue;
    byTime.set(Number(point.time), point);
  }
  return [...byTime.values()].sort((left, right) => left.time - right.time);
}

export function computeSimpleMovingAverage(points: readonly HeroPricePoint[], window: MovingAverageWindow | number) {
  const normalized = normalizeHeroPricePoints(points);
  if (!Number.isFinite(window) || window <= 0) return [];
  const rows: Array<{ time: UTCTimestamp; value: number }> = [];
  for (let index = window - 1; index < normalized.length; index += 1) {
    const slice = normalized.slice(index + 1 - window, index + 1);
    const sum = slice.reduce((total, point) => total + point.close, 0);
    rows.push({ time: normalized[index]!.time, value: sum / window });
  }
  return rows;
}

export function buildHeroPriceChartSeries(points: readonly HeroPricePoint[], settings: HeroPriceChartSettings): ChartSeries[] {
  const normalized = normalizeHeroPricePoints(points);
  const availability = heroPriceChartAvailability(normalized);
  const series: ChartSeries[] = [];

  if (!availability.hasClose) {
    return series;
  }

  if (settings.priceStyle === "candles" && availability.hasOhlc) {
    series.push({
      id: "price",
      label: "Price",
      color: "var(--chart-primary)",
      type: "candlestick",
      data: normalized.map((point) => ({
        time: point.time,
        open: point.open as number,
        high: point.high as number,
        low: point.low as number,
        close: point.close
      }))
    });
  } else {
    series.push({
      id: "price",
      label: "Price",
      color: "var(--chart-primary)",
      type: "line",
      data: normalized.map((point) => ({ time: point.time, value: point.close }))
    });
  }

  for (const window of settings.movingAverages) {
    const data = normalizeChartData(computeSimpleMovingAverage(normalized, window));
    if (!data.length) continue;
    series.push({
      id: `ma-${window}`,
      label: `MA${window}`,
      color: movingAverageColors[window],
      type: "line",
      lineStyle: window === 200 ? "dashed" : "solid",
      data
    });
  }

  if (settings.volumeOverlay && availability.hasVolume) {
    series.push({
      id: "volume",
      label: "Volume",
      color: "var(--text-2)",
      type: "histogram",
      priceScaleId: "volume",
      data: normalized
        .filter((point) => isFiniteNumber(point.volume) && point.volume > 0)
        .map((point) => ({ time: point.time, value: point.volume as number }))
    });
  }

  return series;
}

export function heroPriceSettingsStorageKey(chartKey: string) {
  return `gamma.heroPriceChart.${chartKey}`;
}
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
npm --prefix frontend test -- src/lib/view-models/hero-price-chart.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add frontend/src/lib/view-models/hero-price-chart.ts frontend/src/lib/view-models/hero-price-chart.test.ts
git commit -m "feat: add hero price chart view model"
```

Expected: commit succeeds.

---

### Task 2: Extend TimeSeriesChart With Candles and Volume Histograms

**Files:**
- Modify: `frontend/src/components/TimeSeriesChart.svelte`
- Create: `frontend/src/components/TimeSeriesChart.test.ts`

- [ ] **Step 1: Write failing component contract test**

Create `frontend/src/components/TimeSeriesChart.test.ts`:

```ts
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";

describe("TimeSeriesChart", () => {
  it("accepts additive candle and histogram series contracts", () => {
    const series: ChartSeries[] = [
      {
        id: "price",
        label: "Price",
        color: "var(--chart-primary)",
        type: "candlestick",
        data: [
          { time: 1 as never, open: 10, high: 12, low: 9, close: 11 },
          { time: 2 as never, open: 11, high: 13, low: 10, close: 12 }
        ]
      },
      {
        id: "volume",
        label: "Volume",
        color: "var(--text-2)",
        type: "histogram",
        priceScaleId: "volume",
        data: [
          { time: 1 as never, value: 100 },
          { time: 2 as never, value: 120 }
        ]
      }
    ];

    const { body } = render(TimeSeriesChart, {
      props: {
        series,
        showLegend: true,
        height: 180
      }
    });

    expect(body).toContain("Price");
    expect(body).toContain("Volume");
    expect(body).toContain("height:180px");
  });
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
npm --prefix frontend test -- src/components/TimeSeriesChart.test.ts
```

Expected: FAIL with TypeScript errors because `ChartSeries.type` does not allow `candlestick` or `histogram`.

- [ ] **Step 3: Update the chart component types and imports**

In `frontend/src/components/TimeSeriesChart.svelte`, update the import from `lightweight-charts`:

```ts
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp
} from "lightweight-charts";
```

Replace the chart point and series interfaces with:

```ts
export interface ChartPoint {
  time: UTCTimestamp;
  value: number;
  tickLabel?: string;
}

export interface CandlestickChartPoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  tickLabel?: string;
}

export type AnyChartPoint = ChartPoint | CandlestickChartPoint;

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  type?: "line" | "area" | "candlestick" | "histogram";
  lineStyle?: "solid" | "dashed";
  showPointMarkers?: boolean;
  pointMarkerRadius?: number;
  invertFilledArea?: boolean;
  priceScaleId?: string;
  data: AnyChartPoint[];
}
```

Change `seriesMap` to:

```ts
let seriesMap = new Map<string, ISeriesApi<"Line" | "Area" | "Candlestick" | "Histogram">>();
```

Add helper type guards near `inferPricePrecision`:

```ts
function isValuePoint(point: AnyChartPoint): point is ChartPoint {
  return "value" in point && Number.isFinite(point.value);
}

function isCandlestickPoint(point: AnyChartPoint): point is CandlestickChartPoint {
  return (
    "open" in point &&
    Number.isFinite(point.open) &&
    Number.isFinite(point.high) &&
    Number.isFinite(point.low) &&
    Number.isFinite(point.close)
  );
}

function inferSeriesPrecision(data: AnyChartPoint[]): number {
  const latestValuePoint = data.findLast(isValuePoint);
  if (latestValuePoint) return inferPricePrecision([latestValuePoint]);
  const latestCandle = data.findLast(isCandlestickPoint);
  if (!latestCandle) return 2;
  return inferPricePrecision([{ time: latestCandle.time, value: latestCandle.close }]);
}
```

- [ ] **Step 4: Update series creation logic**

Inside `syncChart`, replace the current `const api = item.type === "line" ? ... : ...` block with this branch:

```ts
let api: ISeriesApi<"Line" | "Area" | "Candlestick" | "Histogram">;
const priceFormat = {
  type: "price" as const,
  precision: inferSeriesPrecision(item.data),
  minMove: 10 ** -inferSeriesPrecision(item.data)
};

if (item.type === "candlestick") {
  api = chart.addSeries(CandlestickSeries, {
    upColor: resolveChartColor("var(--positive)", computedStyle),
    downColor: resolveChartColor("var(--negative)", computedStyle),
    borderUpColor: resolveChartColor("var(--positive)", computedStyle),
    borderDownColor: resolveChartColor("var(--negative)", computedStyle),
    wickUpColor: resolveChartColor("var(--positive)", computedStyle),
    wickDownColor: resolveChartColor("var(--negative)", computedStyle),
    priceFormat,
    lastValueVisible: false,
    priceLineVisible: false
  });
  api.setData(item.data.filter(isCandlestickPoint));
} else if (item.type === "histogram") {
  api = chart.addSeries(HistogramSeries, {
    color: colorWithAlpha(resolvedColor, 0.42),
    priceScaleId: item.priceScaleId ?? "",
    priceFormat: {
      type: "volume"
    },
    lastValueVisible: false,
    priceLineVisible: false
  });
  chart.priceScale(item.priceScaleId ?? "").applyOptions({
    scaleMargins: {
      top: 0.78,
      bottom: 0
    }
  });
  api.setData(item.data.filter(isValuePoint));
} else if (item.type === "line") {
  const normalizedData = normalizeChartData(item.data.filter(isValuePoint));
  api = chart.addSeries(LineSeries, {
    color: resolvedColor,
    lineWidth: 2,
    lineStyle: item.lineStyle === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
    pointMarkersVisible: item.showPointMarkers ?? false,
    pointMarkersRadius: item.pointMarkerRadius ?? 3,
    priceFormat,
    lastValueVisible: false,
    priceLineVisible: false
  });
  api.setData(normalizedData);
} else {
  const normalizedData = normalizeChartData(item.data.filter(isValuePoint));
  api = chart.addSeries(AreaSeries, {
    lineColor: resolvedColor,
    topColor: item.invertFilledArea ? colorWithAlpha(resolvedColor, 0.012) : colorWithAlpha(resolvedColor, 0.2),
    bottomColor: item.invertFilledArea ? colorWithAlpha(resolvedColor, 0.2) : colorWithAlpha(resolvedColor, 0.012),
    invertFilledArea: item.invertFilledArea ?? false,
    lineWidth: 2,
    pointMarkersVisible: item.showPointMarkers ?? false,
    pointMarkersRadius: item.pointMarkerRadius ?? 3,
    priceFormat,
    lastValueVisible: false,
    priceLineVisible: false
  });
  api.setData(normalizedData);
}
seriesMap.set(item.id, api);
```

Remove the old `api.setData(normalizedData); seriesMap.set(...)` lines from the previous block so data is set once in each branch.

- [ ] **Step 5: Run tests**

Run:

```powershell
npm --prefix frontend test -- src/components/TimeSeriesChart.test.ts src/lib/view-models/hero-price-chart.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add frontend/src/components/TimeSeriesChart.svelte frontend/src/components/TimeSeriesChart.test.ts
git commit -m "feat: support hero chart candle and volume series"
```

Expected: commit succeeds.

---

### Task 3: Create the HeroPriceChart Wrapper

**Files:**
- Create: `frontend/src/components/HeroPriceChart.svelte`
- Create: `frontend/src/components/HeroPriceChart.test.ts`

- [ ] **Step 1: Write failing render tests**

Create `frontend/src/components/HeroPriceChart.test.ts`:

```ts
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import HeroPriceChart from "./HeroPriceChart.svelte";
import type { HeroPricePoint } from "../lib/view-models/hero-price-chart";

describe("HeroPriceChart", () => {
  it("renders compact settings controls for a hero chart", () => {
    const points: HeroPricePoint[] = [
      { time: 1 as never, close: 10 },
      { time: 2 as never, close: 11 }
    ];

    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "test:close",
        points,
        height: 180,
        emptyMessage: "No data"
      }
    });

    expect(body).toContain("aria-label=\"Hero chart settings\"");
    expect(body).toContain("Chart Settings");
    expect(body).toContain("Candles unavailable");
    expect(body).toContain("Volume unavailable");
  });

  it("shows volume as available when points include volume", () => {
    const points: HeroPricePoint[] = [
      { time: 1 as never, close: 10, volume: 100 },
      { time: 2 as never, close: 11, volume: 120 }
    ];

    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "test:volume",
        points,
        height: 180,
        emptyMessage: "No data"
      }
    });

    expect(body).toContain("Volume overlay");
    expect(body).not.toContain("Volume unavailable");
  });
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
npm --prefix frontend test -- src/components/HeroPriceChart.test.ts
```

Expected: FAIL because `HeroPriceChart.svelte` does not exist.

- [ ] **Step 3: Implement the wrapper component**

Create `frontend/src/components/HeroPriceChart.svelte`:

```svelte
<script lang="ts">
  import TimeSeriesChart from "./TimeSeriesChart.svelte";
  import {
    buildHeroPriceChartSeries,
    defaultHeroPriceChartSettings,
    heroPriceChartAvailability,
    heroPriceSettingsStorageKey,
    movingAverageWindows,
    normalizeHeroPriceChartSettings,
    type HeroPriceChartSettings,
    type HeroPricePoint,
    type HeroPriceStyle,
    type MovingAverageWindow
  } from "../lib/view-models/hero-price-chart";

  export let chartKey: string;
  export let points: HeroPricePoint[] = [];
  export let height = 320;
  export let emptyMessage = "CHART UNAVAILABLE";
  export let showLegend = true;

  let open = false;
  let settings: HeroPriceChartSettings = { ...defaultHeroPriceChartSettings };
  let loadedKey = "";

  function readStoredSettings(key: string): HeroPriceChartSettings {
    if (typeof localStorage === "undefined") return { ...defaultHeroPriceChartSettings };
    try {
      return normalizeHeroPriceChartSettings(JSON.parse(localStorage.getItem(heroPriceSettingsStorageKey(key)) ?? "null"));
    } catch {
      return { ...defaultHeroPriceChartSettings };
    }
  }

  function persistSettings(nextSettings: HeroPriceChartSettings) {
    settings = normalizeHeroPriceChartSettings(nextSettings);
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(heroPriceSettingsStorageKey(chartKey), JSON.stringify(settings));
  }

  function setPriceStyle(priceStyle: HeroPriceStyle) {
    persistSettings({ ...settings, priceStyle });
  }

  function toggleVolume() {
    persistSettings({ ...settings, volumeOverlay: !settings.volumeOverlay });
  }

  function toggleMovingAverage(window: MovingAverageWindow) {
    const next = settings.movingAverages.includes(window)
      ? settings.movingAverages.filter((item) => item !== window)
      : [...settings.movingAverages, window].sort((left, right) => left - right);
    persistSettings({ ...settings, movingAverages: next });
  }

  $: if (chartKey && chartKey !== loadedKey) {
    loadedKey = chartKey;
    settings = readStoredSettings(chartKey);
  }

  $: availability = heroPriceChartAvailability(points);
  $: effectiveSettings = {
    ...settings,
    priceStyle: settings.priceStyle === "candles" && !availability.hasOhlc ? "line" : settings.priceStyle,
    volumeOverlay: settings.volumeOverlay && availability.hasVolume
  } satisfies HeroPriceChartSettings;
  $: chartSeries = buildHeroPriceChartSeries(points, effectiveSettings);
</script>

<div class="hero-price-chart">
  <div class="hero-chart-toolbar">
    <button type="button" class="settings-button" aria-label="Hero chart settings" aria-expanded={open} on:click={() => (open = !open)}>
      <span aria-hidden="true">⚙</span>
    </button>

    <div class:open class="settings-popover">
      <div class="settings-title">Chart Settings</div>

      <div class="settings-row">
        <span>Price</span>
        <div class="segmented">
          <button type="button" class:selected={settings.priceStyle === "line"} on:click={() => setPriceStyle("line")}>Line</button>
          <button type="button" class:selected={settings.priceStyle === "candles"} disabled={!availability.hasOhlc} on:click={() => setPriceStyle("candles")}>
            {availability.hasOhlc ? "Candles" : "Candles unavailable"}
          </button>
        </div>
      </div>

      <div class="settings-row">
        <span>Volume</span>
        <button type="button" class="toggle-button" disabled={!availability.hasVolume} class:selected={settings.volumeOverlay && availability.hasVolume} on:click={toggleVolume}>
          {availability.hasVolume ? "Volume overlay" : "Volume unavailable"}
        </button>
      </div>

      <div class="settings-row">
        <span>Moving averages</span>
        <div class="ma-options">
          {#each movingAverageWindows as window}
            <button type="button" class:selected={settings.movingAverages.includes(window)} disabled={!availability.hasClose} on:click={() => toggleMovingAverage(window)}>MA{window}</button>
          {/each}
        </div>
      </div>
    </div>
  </div>

  <TimeSeriesChart series={chartSeries} {height} {emptyMessage} {showLegend} />
</div>

<style>
  .hero-price-chart {
    position: relative;
    display: grid;
    gap: 0.35rem;
  }

  .hero-chart-toolbar {
    position: absolute;
    top: -2.45rem;
    right: 0;
    z-index: 5;
  }

  .settings-button {
    width: 25px;
    height: 25px;
    display: grid;
    place-items: center;
    padding: 0;
    color: var(--text-1);
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    cursor: pointer;
  }

  .settings-button:hover,
  .settings-button[aria-expanded="true"] {
    color: var(--text-0);
    border-color: var(--accent);
  }

  .settings-popover {
    position: absolute;
    top: 1.85rem;
    right: 0;
    width: min(320px, calc(100vw - 2rem));
    display: none;
    gap: 0.55rem;
    padding: 0.65rem;
    color: var(--text-1);
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
    z-index: 10;
  }

  .settings-popover.open {
    display: grid;
  }

  .settings-title {
    color: var(--text-0);
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .settings-row {
    display: grid;
    grid-template-columns: 6.8rem 1fr;
    align-items: center;
    gap: 0.5rem;
    min-height: 28px;
    font-size: 0.74rem;
  }

  .settings-row > span {
    color: var(--text-2);
  }

  .segmented,
  .ma-options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }

  .segmented button,
  .ma-options button,
  .toggle-button {
    min-height: 25px;
    padding: 0.22rem 0.5rem;
    color: var(--text-1);
    background: transparent;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    cursor: pointer;
    font-size: 0.72rem;
  }

  .segmented button.selected,
  .ma-options button.selected,
  .toggle-button.selected {
    color: var(--text-0);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-strong));
  }

  .segmented button:disabled,
  .ma-options button:disabled,
  .toggle-button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
</style>
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
npm --prefix frontend test -- src/components/HeroPriceChart.test.ts src/lib/view-models/hero-price-chart.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add frontend/src/components/HeroPriceChart.svelte frontend/src/components/HeroPriceChart.test.ts
git commit -m "feat: add hero price chart settings control"
```

Expected: commit succeeds.

---

### Task 4: Integrate Fundamentals Overview Hero Chart

**Files:**
- Modify: `frontend/src/views/FundamentalsView.svelte`
- Modify: `frontend/src/views/FundamentalsView.test.ts` if needed

- [ ] **Step 1: Replace imports and point mapping**

In `frontend/src/views/FundamentalsView.svelte`, replace:

```ts
import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
```

with:

```ts
import HeroPriceChart from "../components/HeroPriceChart.svelte";
```

Add:

```ts
import type { HeroPricePoint } from "../lib/view-models/hero-price-chart";
```

Replace the `priceSeries` reactive block with:

```ts
$: heroPricePoints = overview?.price_history?.length
  ? overview.price_history
      .map((point) => ({
        time: parseApiTimestampToUtcSeconds(point.timestamp),
        close: point.price
      }))
      .filter((point): point is HeroPricePoint => point.time != null && Number.isFinite(point.close))
  : [];
```

- [ ] **Step 2: Replace the chart markup**

Replace:

```svelte
{#if priceSeries.length}
  <div class="chart-panel">
    <TimeSeriesChart series={priceSeries} height={240} emptyMessage="No price history available." />
  </div>
{:else}
  <div class="empty-panel">No price history</div>
{/if}
```

with:

```svelte
{#if heroPricePoints.length}
  <div class="chart-panel">
    <HeroPriceChart chartKey="fundamentals:equity" points={heroPricePoints} height={240} emptyMessage="No price history available." />
  </div>
{:else}
  <div class="empty-panel">No price history</div>
{/if}
```

- [ ] **Step 3: Run type and relevant tests**

Run:

```powershell
npm --prefix frontend test -- src/components/HeroPriceChart.test.ts src/lib/view-models/hero-price-chart.test.ts
npm --prefix frontend run build
```

Expected: tests PASS and build succeeds.

- [ ] **Step 4: Commit Task 4**

Run:

```powershell
git add frontend/src/views/FundamentalsView.svelte
git commit -m "feat: add settings to fundamentals hero chart"
```

Expected: commit succeeds.

---

### Task 5: Integrate Research Single-Ticker Price Hero Chart

**Files:**
- Modify: `frontend/src/views/ResearchView.svelte`

- [ ] **Step 1: Add imports**

In `frontend/src/views/ResearchView.svelte`, keep the existing `TimeSeriesChart` import for other chart modes and add:

```ts
import HeroPriceChart from "../components/HeroPriceChart.svelte";
import type { HeroPricePoint } from "../lib/view-models/hero-price-chart";
```

- [ ] **Step 2: Add hero price point derivation**

Near the existing `chartSeries` declarations, add:

```ts
let researchHeroPricePoints: HeroPricePoint[] = [];
```

Inside the reactive chart block after `const prices = slicePoints(result?.primary_price_points ?? []);`, add:

```ts
researchHeroPricePoints = prices
  .map((point) => ({
    time: Math.floor(new Date(point.timestamp).getTime() / 1000) as never,
    close: point.value
  }))
  .filter((point): point is HeroPricePoint => Number.isFinite(point.time) && Number.isFinite(point.close));
```

- [ ] **Step 3: Render HeroPriceChart only in price mode**

Replace:

```svelte
<TimeSeriesChart series={chartSeries} height={380} emptyMessage={chartEmptyMessage(chartMode, result)} />
```

with:

```svelte
{#if chartMode === "price" && result?.scope_type === "single_ticker"}
  <HeroPriceChart
    chartKey="research:single-ticker"
    points={researchHeroPricePoints}
    height={380}
    emptyMessage={chartEmptyMessage(chartMode, result)}
  />
{:else}
  <TimeSeriesChart series={chartSeries} height={380} emptyMessage={chartEmptyMessage(chartMode, result)} />
{/if}
```

- [ ] **Step 4: Run validation**

Run:

```powershell
npm --prefix frontend test -- src/components/HeroPriceChart.test.ts src/lib/view-models/hero-price-chart.test.ts
npm --prefix frontend run build
```

Expected: tests PASS and build succeeds.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add frontend/src/views/ResearchView.svelte
git commit -m "feat: add settings to research price hero chart"
```

Expected: commit succeeds.

---

### Task 6: Integrate Crypto Token Hero Chart

**Files:**
- Modify: `frontend/src/views/CryptoView.svelte`

- [ ] **Step 1: Add imports and derive token hero points**

In `frontend/src/views/CryptoView.svelte`, add:

```ts
import HeroPriceChart from "../components/HeroPriceChart.svelte";
import type { HeroPricePoint } from "../lib/view-models/hero-price-chart";
```

Keep `TimeSeriesChart` for synthetic basket charts.

Add a reactive block near `tokenChartSeries`:

```ts
$: tokenHeroPricePoints = history?.points?.length
  ? history.points
      .map((point) => ({
        time: parseApiTimestampToUtcSeconds(point.timestamp),
        close: point.price,
        volume: point.total_volume
      }))
      .filter((point): point is HeroPricePoint => point.time != null && Number.isFinite(point.close))
  : [];
```

- [ ] **Step 2: Keep synthetic basket on TimeSeriesChart and token on HeroPriceChart**

Replace the single hero chart markup:

```svelte
<TimeSeriesChart
  series={activeHeroSeries}
  height={360}
  emptyMessage={heroCanvas === "basket" ? "Build a synthetic basket to promote it into the hero canvas." : "Select a token to load price history."}
/>
```

with:

```svelte
{#if heroCanvas === "basket"}
  <TimeSeriesChart
    series={activeHeroSeries}
    height={360}
    emptyMessage="Build a synthetic basket to promote it into the hero canvas."
  />
{:else}
  <HeroPriceChart
    chartKey="crypto:token"
    points={tokenHeroPricePoints}
    height={360}
    emptyMessage="Select a token to load price history."
  />
{/if}
```

- [ ] **Step 3: Run validation**

Run:

```powershell
npm --prefix frontend test -- src/views/CryptoView.test.ts src/components/HeroPriceChart.test.ts src/lib/view-models/hero-price-chart.test.ts
npm --prefix frontend run build
```

Expected: tests PASS and build succeeds.

- [ ] **Step 4: Commit Task 6**

Run:

```powershell
git add frontend/src/views/CryptoView.svelte
git commit -m "feat: add settings to crypto token hero chart"
```

Expected: commit succeeds.

---

### Task 7: Final UI and Regression Verification

**Files:**
- Review: `frontend/src/components/HeroPriceChart.svelte`
- Review: `frontend/src/components/TimeSeriesChart.svelte`
- Review: `frontend/src/views/FundamentalsView.svelte`
- Review: `frontend/src/views/ResearchView.svelte`
- Review: `frontend/src/views/CryptoView.svelte`

- [ ] **Step 1: Run full frontend tests**

Run:

```powershell
npm --prefix frontend test
```

Expected: PASS.

- [ ] **Step 2: Run frontend production build**

Run:

```powershell
npm --prefix frontend run build
```

Expected: build succeeds.

- [ ] **Step 3: Inspect changed code for non-hero chart leakage**

Run:

```powershell
rg -n "HeroPriceChart|heroPriceChart|gamma.heroPriceChart" frontend/src
```

Expected: matches only in the helper, helper tests, `HeroPriceChart` component/tests, and the three approved views.

- [ ] **Step 4: Commit verification-only adjustments if any were needed**

If Step 1 or Step 2 required a small fix, stage and commit the exact changed files:

```powershell
git add frontend/src
git commit -m "fix: stabilize hero chart settings"
```

Expected: commit succeeds only if files changed. If no files changed, skip this step.

---

## Self-Review

Spec coverage:

- Header settings button: Task 3 implements the button, Tasks 4-6 place it only on hero charts.
- Price style line/candles: Tasks 1-3 implement settings and data-aware fallback; Task 2 adds renderer support.
- Volume overlay: Tasks 1-3 implement availability and histogram output; Task 6 wires crypto volume now.
- Moving averages: Task 1 implements Gamma-owned SMA logic and tests; Task 3 exposes controls.
- Scope control: Tasks 4-6 integrate only Fundamentals, Research price mode, and Crypto token hero.
- No fake candles: Task 1 availability and fallback tests enforce close-only data rendering as line.
- Validation: Task 7 runs full tests/build and checks for non-hero leakage.

Placeholder scan:

- This plan contains no unresolved markers and no unspecified test steps.

Type consistency:

- `HeroPricePoint`, `HeroPriceChartSettings`, `MovingAverageWindow`, and `ChartSeries` are defined before use.
- `priceStyle`, `volumeOverlay`, and `movingAverages` names are consistent across helper, wrapper, and tests.
