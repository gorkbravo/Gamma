<script lang="ts">
  import { onMount } from "svelte";
  import { colorWithAlpha, resolveChartColor } from "../lib/chart-colors";
  import { normalizeChartData, splitAtGaps } from "../lib/chart-data";
  import { resolvedTheme } from "../lib/stores/appearance";
  import {
    AreaSeries,
    CandlestickSeries,
    ColorType,
    createChart,
    createSeriesMarkers,
    CrosshairMode,
    HistogramSeries,
    LineSeries,
    LineStyle,
    type IChartApi,
    type ISeriesApi,
    type UTCTimestamp,
    type WhitespaceData
  } from "lightweight-charts";

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

  /** A labelled mark on a series (e.g. where a new tracking segment starts). */
  export interface ChartMarker {
    time: UTCTimestamp;
    text: string;
  }

  export interface ChartSeries {
    id: string;
    label: string;
    color: string;
    type?: "line" | "area" | "candlestick" | "histogram";
    priceScaleId?: string;
    lineStyle?: "solid" | "dashed";
    showPointMarkers?: boolean;
    pointMarkerRadius?: number;
    invertFilledArea?: boolean;
    /**
     * Keep a non-finite value as a break in the line instead of dropping it, so
     * a missing observation is never drawn as continuity (line and area only).
     */
    breakOnGaps?: boolean;
    /** Axis labels as percentages ("2.35%") instead of plain numbers. */
    valueFormat?: "price" | "percent";
    markers?: ChartMarker[];
    data: AnyChartPoint[];
  }

  export let series: ChartSeries[] = [];
  export let height = 320;
  export let emptyMessage = "No chart data";
  export let showLegend = false;

  let container: HTMLDivElement;
  let chart: IChartApi | null = null;
  let seriesMap = new Map<string, ISeriesApi<"Line" | "Area" | "Candlestick" | "Histogram">>();
  let resizeObserver: ResizeObserver | null = null;
  let refreshHandle = 0;
  let pendingRecreate = false;
  let pendingFitContent = false;

  $: seriesWithData = series.filter((item) => item.data.length);

  function buildTickLabelMap() {
    const tickLabels = new Map<number, string>();
    for (const item of series) {
      for (const point of item.data) {
        if (point.tickLabel) {
          tickLabels.set(point.time, point.tickLabel);
        }
      }
    }
    return tickLabels;
  }

  function isValuePoint(point: AnyChartPoint): point is ChartPoint {
    return "value" in point && Number.isFinite(point.time) && Number.isFinite(point.value);
  }

  function isCandlestickPoint(point: AnyChartPoint): point is CandlestickChartPoint {
    return (
      Number.isFinite(point.time) &&
      "open" in point &&
      Number.isFinite(point.open) &&
      Number.isFinite(point.high) &&
      Number.isFinite(point.low) &&
      Number.isFinite(point.close)
    );
  }

  function normalizeValueData(data: readonly AnyChartPoint[]): ChartPoint[] {
    return normalizeChartData(data.filter(isValuePoint));
  }

  /**
   * Tramos continuos de una serie con huecos. lightweight-charts une la línea a
   * través de un punto en blanco, así que cada tramo es su propia serie; el
   * primero lleva los huecos como whitespace para que su fecha siga en el eje.
   */
  function gapRuns(item: ChartSeries): Array<Array<ChartPoint | WhitespaceData<UTCTimestamp>>> {
    const points = item.data.filter((point): point is ChartPoint => "value" in point && Number.isFinite(point.time));
    const { runs, gaps } = splitAtGaps(points);
    const whitespace = gaps.map((time) => ({ time: time as UTCTimestamp }));
    if (!runs.length) return [whitespace];
    return runs.map((run, index) =>
      index === 0 ? [...run, ...whitespace].sort((left, right) => left.time - right.time) : run
    );
  }

  function priceFormatFor(item: ChartSeries, normalizedData: readonly ChartPoint[]) {
    const precision = inferPricePrecision(normalizedData);
    return {
      type: item.valueFormat === "percent" ? ("percent" as const) : ("price" as const),
      precision,
      minMove: 10 ** -precision
    };
  }

  function normalizeCandlestickData(data: readonly AnyChartPoint[]): CandlestickChartPoint[] {
    const sorted = data.filter(isCandlestickPoint).sort((left, right) => left.time - right.time);
    const deduped: CandlestickChartPoint[] = [];
    for (const point of sorted) {
      const previous = deduped.at(-1);
      if (previous && previous.time === point.time) {
        deduped[deduped.length - 1] = point;
        continue;
      }
      deduped.push(point);
    }
    return deduped;
  }

  function inferPricePrecision(data: readonly ChartPoint[]): number {
    const latest = data.at(-1)?.value ?? data[0]?.value ?? 0;
    const magnitude = Math.abs(latest);
    if (magnitude >= 100) return 1;
    if (magnitude >= 1) return 2;
    if (magnitude >= 0.1) return 3;
    if (magnitude >= 0.01) return 4;
    return 6;
  }

  function destroyChart() {
    if (refreshHandle) {
      cancelAnimationFrame(refreshHandle);
      refreshHandle = 0;
    }
    resizeObserver?.disconnect();
    resizeObserver = null;
    chart?.remove();
    chart = null;
    seriesMap = new Map();
  }

  function createOrReplaceChart() {
    const width = Math.max(container.clientWidth, 1);
    const measuredHeight = Math.max(container.clientHeight || height, 1);
    const computedStyle = getComputedStyle(container);
    const divider = resolveChartColor("var(--divider)", computedStyle);
    const baseline = resolveChartColor("var(--panel-strong)", computedStyle);
    const textMuted = resolveChartColor("var(--text-2)", computedStyle);
    // Axis and crosshair labels in the figures font. Canvas text cannot turn
    // on tabular figures, so these are the font's proportional digits.
    const figuresFont = computedStyle.getPropertyValue("--font-num").trim() || undefined;
    const tickLabels = buildTickLabelMap();
    chart?.remove();
    chart = createChart(container, {
      width,
      height: measuredHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: textMuted,
        fontFamily: figuresFont
      },
      // B′: no grid, only the baseline (the time axis edge) below the plot.
      grid: {
        vertLines: { visible: false, color: colorWithAlpha(divider, 0.36) },
        horzLines: { visible: false, color: colorWithAlpha(divider, 0.36) }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: colorWithAlpha(textMuted, 0.25) },
        horzLine: { color: colorWithAlpha(textMuted, 0.18) }
      },
      rightPriceScale: {
        borderVisible: false,
        borderColor: divider,
        minimumWidth: 60,
        entireTextOnly: true,
        scaleMargins: {
          top: 0.08,
          bottom: 0.08
        }
      },
      timeScale: {
        borderColor: baseline,
        timeVisible: true,
        secondsVisible: false,
        ...(tickLabels.size
          ? {
              tickMarkFormatter: (time: unknown) => tickLabels.get(Number(time)) ?? ""
            }
          : {})
      },
      handleScroll: true,
      handleScale: true
    });
    seriesMap = new Map();
  }

  function attachMarkers(api: ISeriesApi<"Line" | "Area">, markers: ChartMarker[], computedStyle: CSSStyleDeclaration) {
    const markerColor = resolveChartColor("var(--text-1)", computedStyle);
    createSeriesMarkers(
      api,
      [...markers]
        .sort((left, right) => left.time - right.time)
        .map((marker) => ({
          time: marker.time,
          position: "aboveBar" as const,
          shape: "circle" as const,
          size: 0.5,
          color: markerColor,
          text: marker.text
        }))
    );
  }

  function syncChart(fitContent = true) {
    if (!chart) {
      return;
    }

    for (const api of seriesMap.values()) {
      chart.removeSeries(api);
    }
    seriesMap = new Map();

    const computedStyle = getComputedStyle(container);

    for (const item of series) {
      const normalizedData = normalizeValueData(item.data);
      const resolvedColor = resolveChartColor(item.color, computedStyle);
      const positiveColor = resolveChartColor("var(--positive)", computedStyle);
      const negativeColor = resolveChartColor("var(--negative)", computedStyle);

      const chartApi = chart;
      const addValueSeries = (): ISeriesApi<"Line" | "Area"> =>
        item.type === "line"
          ? chartApi.addSeries(LineSeries, {
              color: resolvedColor,
              priceScaleId: item.priceScaleId,
              lineWidth: 2,
              lineStyle: item.lineStyle === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
              pointMarkersVisible: item.showPointMarkers ?? false,
              pointMarkersRadius: item.pointMarkerRadius ?? 3,
              priceFormat: priceFormatFor(item, normalizedData),
              lastValueVisible: false,
              priceLineVisible: false
            })
          : chartApi.addSeries(AreaSeries, {
              lineColor: resolvedColor,
              priceScaleId: item.priceScaleId,
              topColor: colorWithAlpha(resolvedColor, 0.09),
              bottomColor: colorWithAlpha(resolvedColor, 0.09),
              invertFilledArea: item.invertFilledArea ?? false,
              lineWidth: 2,
              pointMarkersVisible: item.showPointMarkers ?? false,
              pointMarkersRadius: item.pointMarkerRadius ?? 3,
              priceFormat: priceFormatFor(item, normalizedData),
              lastValueVisible: false,
              priceLineVisible: false
            });

      let api: ISeriesApi<"Line" | "Area" | "Candlestick" | "Histogram">;
      if (item.type !== "candlestick" && item.type !== "histogram") {
        const runs = item.breakOnGaps ? gapRuns(item) : [normalizedData];
        runs.forEach((run, index) => {
          const runApi = addValueSeries();
          runApi.setData(run);
          const valued = run.filter((point): point is ChartPoint => "value" in point);
          const first = valued[0]?.time ?? Number.NEGATIVE_INFINITY;
          const last = valued.at(-1)?.time ?? Number.POSITIVE_INFINITY;
          const markers = (item.markers ?? []).filter((marker) => runs.length === 1 || (marker.time >= first && marker.time <= last));
          if (markers.length) attachMarkers(runApi, markers, computedStyle);
          seriesMap.set(index === 0 ? item.id : `${item.id}#run${index}`, runApi);
        });
        continue;
      }
      if (item.type === "candlestick") {
        const candleData = normalizeCandlestickData(item.data);
        api = chart.addSeries(CandlestickSeries, {
          priceScaleId: item.priceScaleId,
          upColor: positiveColor,
          downColor: negativeColor,
          borderUpColor: positiveColor,
          borderDownColor: negativeColor,
          wickUpColor: positiveColor,
          wickDownColor: negativeColor,
          lastValueVisible: false,
          priceLineVisible: false
        });
        api.setData(candleData);
      } else {
        api = chart.addSeries(HistogramSeries, {
          color: colorWithAlpha(resolvedColor, 0.35),
          priceScaleId: item.priceScaleId,
          priceFormat: {
            type: "volume"
          },
          lastValueVisible: false,
          priceLineVisible: false
        });
        api.setData(normalizedData);
        if (item.priceScaleId) {
          chart.priceScale(item.priceScaleId).applyOptions({
            scaleMargins: { top: 0.78, bottom: 0 }
          });
        }
      }
      seriesMap.set(item.id, api);
    }

    const measuredHeight = Math.max(container.clientHeight || height, 1);
    chart.applyOptions({ height: measuredHeight });
    if (fitContent) {
      chart.timeScale().fitContent();
    }
  }

  function refreshChart(options?: { recreate?: boolean; fitContent?: boolean }) {
    if (!container) {
      return;
    }
    const width = container.clientWidth;
    const measuredHeight = container.clientHeight || height;
    if (width <= 0 || measuredHeight <= 0) {
      return;
    }
    if (!chart || options?.recreate) {
      createOrReplaceChart();
    }
    chart?.resize(width, measuredHeight);
    syncChart(options?.fitContent ?? true);
  }

  function scheduleRefresh(options?: { recreate?: boolean; fitContent?: boolean }) {
    pendingRecreate = pendingRecreate || Boolean(options?.recreate);
    pendingFitContent = pendingFitContent || Boolean(options?.fitContent);
    if (refreshHandle) {
      return;
    }
    refreshHandle = requestAnimationFrame(() => {
      refreshHandle = 0;
      const recreate = pendingRecreate;
      const fitContent = pendingFitContent;
      pendingRecreate = false;
      pendingFitContent = false;
      refreshChart({ recreate, fitContent });
    });
  }

  onMount(() => {
    resizeObserver = new ResizeObserver(() => {
      scheduleRefresh();
    });
    resizeObserver.observe(container);
    scheduleRefresh({ recreate: true, fitContent: true });

    const revealChart = () => scheduleRefresh({ recreate: true, fitContent: true });
    const resizeChart = () => scheduleRefresh();
    window.addEventListener("focus", revealChart);
    window.addEventListener("resize", resizeChart);
    document.addEventListener("visibilitychange", revealChart);

    return () => {
      window.removeEventListener("focus", revealChart);
      window.removeEventListener("resize", resizeChart);
      document.removeEventListener("visibilitychange", revealChart);
      destroyChart();
    };
  });

  $: if (container) {
    const signature = JSON.stringify(
      series.map((item) => [
        item.id,
        item.type ?? "area",
        item.priceScaleId ?? "right",
        item.lineStyle ?? "solid",
        item.showPointMarkers ?? false,
        item.pointMarkerRadius ?? null,
        item.invertFilledArea ?? false,
        item.breakOnGaps ?? false,
        item.valueFormat ?? "price",
        (item.markers ?? []).map((marker) => `${marker.time}:${marker.text}`).join("|"),
        item.data.length,
        item.data.at(0)?.time ?? null,
        item.data.at(-1)?.time ?? null,
        item.data.map((point) => point.tickLabel ?? "").join("|")
      ])
    );
    signature;
    // The chart reads its colours from the tokens, so a theme change rebuilds it.
    $resolvedTheme;
    scheduleRefresh({ recreate: true, fitContent: true });
  }
</script>

<div class="chart-shell" style={`height:${height}px`}>
  <div class="chart" bind:this={container}></div>
  {#if showLegend && seriesWithData.length}
    <div class="legend" aria-label="Chart legend">
      {#each seriesWithData as item}
        <span class="legend-item">
          <span class:dash={item.lineStyle === "dashed"} style={`--legend-color:${item.color}`}></span>
          {item.label}
        </span>
      {/each}
    </div>
  {/if}
  {#if !series.length || !series.some((item) => item.data.length)}
    <div class="empty">{emptyMessage}</div>
  {/if}
</div>

<style>
  .chart-shell {
    position: relative;
    width: 100%;
    border: 0;
    background: transparent;
    overflow: hidden;
  }

  .chart {
    position: absolute;
    inset: 0;
  }

  .legend {
    position: absolute;
    top: 0.45rem;
    left: 0.55rem;
    z-index: 2;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3) var(--space-5);
    max-width: calc(100% - 1.1rem);
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: 1.2;
    pointer-events: none;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    white-space: nowrap;
  }

  .legend-item span {
    width: 1rem;
    border-top: 2px solid var(--legend-color);
  }

  .legend-item span.dash {
    border-top-style: dashed;
  }

  .empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--text-2);
    background: var(--bg-0);
    text-transform: var(--label-case);
    letter-spacing: 0;
    font-size: var(--text-sm);
  }
</style>
