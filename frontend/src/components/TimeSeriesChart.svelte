<script lang="ts">
  import { onMount } from "svelte";
  import { colorWithAlpha, resolveChartColor } from "../lib/chart-colors";
  import { normalizeChartData } from "../lib/chart-data";
  import { chartTheme } from "../lib/stores/app";
  import {
    AreaSeries,
    ColorType,
    createChart,
    CrosshairMode,
    LineSeries,
    LineStyle,
    type IChartApi,
    type ISeriesApi,
    type UTCTimestamp
  } from "lightweight-charts";

  export interface ChartPoint {
    time: UTCTimestamp;
    value: number;
    tickLabel?: string;
  }

  export interface ChartSeries {
    id: string;
    label: string;
    color: string;
    type?: "line" | "area";
    lineStyle?: "solid" | "dashed";
    showPointMarkers?: boolean;
    pointMarkerRadius?: number;
    invertFilledArea?: boolean;
    data: ChartPoint[];
  }

  export let series: ChartSeries[] = [];
  export let height = 320;
  export let emptyMessage = "No chart data";
  export let showLegend = false;

  let container: HTMLDivElement;
  let chart: IChartApi | null = null;
  let seriesMap = new Map<string, ISeriesApi<"Line" | "Area">>();
  let resizeObserver: ResizeObserver | null = null;
  let refreshHandle = 0;
  let pendingRecreate = false;
  let pendingFitContent = false;

  let currentTheme = "blue";
  $: currentTheme = $chartTheme;
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

  function inferPricePrecision(data: ChartPoint[]): number {
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
    const textMuted = resolveChartColor("var(--text-2)", computedStyle);
    const tickLabels = buildTickLabelMap();
    chart?.remove();
    chart = createChart(container, {
      width,
      height: measuredHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: textMuted
      },
      grid: {
        vertLines: { color: colorWithAlpha(divider, 0.36) },
        horzLines: { color: colorWithAlpha(divider, 0.36) }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: colorWithAlpha(textMuted, 0.25) },
        horzLine: { color: colorWithAlpha(textMuted, 0.18) }
      },
      rightPriceScale: {
        borderColor: divider,
        minimumWidth: 60,
        entireTextOnly: true,
        scaleMargins: {
          top: 0.08,
          bottom: 0.08
        }
      },
      timeScale: {
        borderColor: divider,
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
      const normalizedData = normalizeChartData(item.data);
      const resolvedColor = resolveChartColor(item.color, computedStyle);

      const api =
        item.type === "line"
          ? chart.addSeries(LineSeries, {
              color: resolvedColor,
              lineWidth: 2,
              lineStyle: item.lineStyle === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
              pointMarkersVisible: item.showPointMarkers ?? false,
              pointMarkersRadius: item.pointMarkerRadius ?? 3,
              priceFormat: {
                type: "price",
                precision: inferPricePrecision(normalizedData),
                minMove: 10 ** -inferPricePrecision(normalizedData)
              },
              lastValueVisible: false,
              priceLineVisible: false
            })
          : chart.addSeries(AreaSeries, {
              lineColor: resolvedColor,
              topColor: item.invertFilledArea ? colorWithAlpha(resolvedColor, 0.012) : colorWithAlpha(resolvedColor, 0.2),
              bottomColor: item.invertFilledArea ? colorWithAlpha(resolvedColor, 0.2) : colorWithAlpha(resolvedColor, 0.012),
              invertFilledArea: item.invertFilledArea ?? false,
              lineWidth: 2,
              pointMarkersVisible: item.showPointMarkers ?? false,
              pointMarkersRadius: item.pointMarkerRadius ?? 3,
              priceFormat: {
                type: "price",
                precision: inferPricePrecision(normalizedData),
                minMove: 10 ** -inferPricePrecision(normalizedData)
              },
              lastValueVisible: false,
              priceLineVisible: false
            });
      api.setData(normalizedData);
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
        item.lineStyle ?? "solid",
        item.showPointMarkers ?? false,
        item.pointMarkerRadius ?? null,
        item.invertFilledArea ?? false,
        item.data.length,
        item.data.at(0)?.time ?? null,
        item.data.at(-1)?.time ?? null,
        item.data.map((point) => point.tickLabel ?? "").join("|")
      ])
    );
    signature;
    currentTheme;
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
    border: 1px solid var(--divider);
    background: var(--bg-0);
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
    gap: 0.35rem 0.65rem;
    max-width: calc(100% - 1.1rem);
    color: var(--text-1);
    font-size: 0.66rem;
    line-height: 1.2;
    pointer-events: none;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
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
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.74rem;
  }
</style>
