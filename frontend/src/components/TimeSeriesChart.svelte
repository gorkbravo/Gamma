<script lang="ts">
  import { onMount } from "svelte";
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

    const resolvedPrimary = getComputedStyle(container).getPropertyValue("--chart-primary").trim() || "#7aa6c8";
    const resolvedSecondary = getComputedStyle(container).getPropertyValue("--chart-secondary").trim() || "#c49a5a";
    const resolvedNegative = getComputedStyle(container).getPropertyValue("--chart-negative").trim() || "#b65d54";

    for (const item of series) {
      let resolvedColor = item.color;
      if (item.color === "#7aa6c8") resolvedColor = resolvedPrimary;
      else if (item.color === "#c49a5a") resolvedColor = resolvedSecondary;
      else if (item.color === "#b65d54" || item.color === "#d1645d") resolvedColor = resolvedNegative;

      const api =
        item.type === "line"
          ? chart.addSeries(LineSeries, {
              color: resolvedColor,
              lineWidth: 2,
              lineStyle: item.lineStyle === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
              priceFormat: {
                type: "price",
                precision: inferPricePrecision(item.data),
                minMove: 10 ** -inferPricePrecision(item.data)
              },
              lastValueVisible: false,
              priceLineVisible: false
            })
          : chart.addSeries(AreaSeries, {
              lineColor: resolvedColor,
              topColor: item.invertFilledArea ? `${resolvedColor}03` : `${resolvedColor}33`,
              bottomColor: item.invertFilledArea ? `${resolvedColor}33` : `${resolvedColor}03`,
              invertFilledArea: item.invertFilledArea ?? false,
              lineWidth: 2,
              priceFormat: {
                type: "price",
                precision: inferPricePrecision(item.data),
                minMove: 10 ** -inferPricePrecision(item.data)
              },
              lastValueVisible: false,
              priceLineVisible: false
            });
      api.setData(item.data);
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
    background: rgba(7, 11, 16, 0.88);
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
    background:
      linear-gradient(90deg, transparent 25%, rgba(122, 166, 200, 0.04) 50%, transparent 75%),
      linear-gradient(180deg, rgba(5, 8, 11, 0.28), rgba(5, 8, 11, 0.5));
    background-size: 200% 100%, 100% 100%;
    animation: shimmer 2.4s ease-in-out infinite;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.74rem;
  }

  @keyframes shimmer {
    0% { background-position: 200% 0, 0 0; }
    100% { background-position: -200% 0, 0 0; }
  }
</style>
