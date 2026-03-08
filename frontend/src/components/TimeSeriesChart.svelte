<script lang="ts">
  import { onMount } from "svelte";
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
        textColor: "#8ea1b5"
      },
      grid: {
        vertLines: { color: "rgba(19, 32, 44, 0.35)" },
        horzLines: { color: "rgba(19, 32, 44, 0.35)" }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(106, 168, 255, 0.35)" },
        horzLine: { color: "rgba(106, 168, 255, 0.25)" }
      },
      rightPriceScale: {
        borderColor: "rgba(30, 46, 60, 0.7)"
      },
      timeScale: {
        borderColor: "rgba(30, 46, 60, 0.7)",
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

    for (const item of series) {
      const api =
        item.type === "line"
          ? chart.addSeries(LineSeries, {
              color: item.color,
              lineWidth: 2,
              lineStyle: item.lineStyle === "dashed" ? LineStyle.Dashed : LineStyle.Solid,
              lastValueVisible: false,
              priceLineVisible: false
            })
          : chart.addSeries(AreaSeries, {
              lineColor: item.color,
              topColor: `${item.color}55`,
              bottomColor: `${item.color}08`,
              lineWidth: 2,
              lastValueVisible: false,
              priceLineVisible: false
            });
      api.setData(item.data);
      seriesMap.set(item.id, api);
    }

    chart.applyOptions({ height });
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
        item.data.length,
        item.data.at(0)?.time ?? null,
        item.data.at(-1)?.time ?? null
      ])
    );
    signature;
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
    min-height: 16rem;
    border: 1px solid rgba(22, 32, 43, 0.85);
    background:
      linear-gradient(180deg, rgba(9, 14, 20, 0.98), rgba(5, 8, 11, 0.98)),
      radial-gradient(circle at top, rgba(106, 168, 255, 0.08), transparent 55%);
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
    background: linear-gradient(180deg, rgba(4, 6, 8, 0.3), rgba(4, 6, 8, 0.55));
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.78rem;
  }
</style>
