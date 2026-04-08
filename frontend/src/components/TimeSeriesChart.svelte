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
  }

  export interface ChartSeries {
    id: string;
    label: string;
    color: string;
    type?: "line" | "area";
    lineStyle?: "solid" | "dashed";
    invertFilledArea?: boolean;
    data: ChartPoint[];
  }

  export let series: ChartSeries[] = [];
  export let height = 320;
  export let emptyMessage = "No chart data";

  let container: HTMLDivElement;
  let chart: IChartApi | null = null;
  let seriesMap = new Map<string, ISeriesApi<"Line" | "Area">>();
  let resizeObserver: ResizeObserver | null = null;
  let refreshHandle = 0;
  let pendingRecreate = false;
  let pendingFitContent = false;

  let currentTheme = "blue";
  $: currentTheme = $chartTheme;

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
    chart?.remove();
    chart = createChart(container, {
      width,
      height: measuredHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8a919a"
      },
      grid: {
        vertLines: { color: "rgba(48, 54, 62, 0.24)" },
        horzLines: { color: "rgba(48, 54, 62, 0.24)" }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(140, 145, 154, 0.25)" },
        horzLine: { color: "rgba(140, 145, 154, 0.18)" }
      },
      rightPriceScale: {
        borderColor: "rgba(50, 56, 64, 0.55)",
        minimumWidth: 60,
        entireTextOnly: true,
        scaleMargins: {
          top: 0.08,
          bottom: 0.08
        }
      },
      timeScale: {
        borderColor: "rgba(50, 56, 64, 0.55)",
        timeVisible: true,
        secondsVisible: false
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
        item.invertFilledArea ?? false,
        item.data.length,
        item.data.at(0)?.time ?? null,
        item.data.at(-1)?.time ?? null
      ])
    );
    signature;
    currentTheme;
    scheduleRefresh({ recreate: true, fitContent: true });
  }
</script>

<div class="chart-shell" style={`height:${height}px`}>
  <div class="chart" bind:this={container}></div>
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
