<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    CommodityCurveSnapshot,
    CommodityInventorySeries,
    CommodityMarketSummary,
    CommodityMode,
    CommodityOverviewRankingItem,
    CommodityPriceHistory,
    CommoditySpreadSnapshot,
    MacroSeriesHistory,
    CommodityWorkspaceResponse
  } from "../lib/api/types";
  import type { CommodityWorkspaceLoadOptions } from "../lib/stores/app";

  export let workspace: CommodityWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: CommodityMode = "overview";
  export let onLoadWorkspace: (options?: CommodityWorkspaceLoadOptions) => Promise<unknown> | void;
  export let macroHistories: Record<string, MacroSeriesHistory> = {};
  export let onLoadMacroSeries: (seriesId: string, options?: { region?: string; timeframe?: string; forceRefresh?: boolean }) => Promise<unknown> | void = () => undefined;

  const modes: Array<{ id: CommodityMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "energy", label: "Energy" },
    { id: "metals", label: "Metals" },
    { id: "curves_spreads", label: "Curves & Spreads" },
    { id: "inventories_fundamentals", label: "Inventories & Fundamentals" },
    { id: "events_cross_domain", label: "Events / Cross-Domain" }
  ];

  let selectedInstrumentId = "wti";
  const scatterBounds = { left: 12, right: 190, top: 10, bottom: 108 };
  const scatterGridFractions = [0.25, 0.5, 0.75];
  const macroDriverSeries = ["us-dollar-broad", "us-real-10y-yield"];
  const requestedMacroDrivers = new Set<string>();

  $: if (workspace?.selected_instrument_id && workspace.selected_instrument_id !== selectedInstrumentId) {
    selectedInstrumentId = workspace.selected_instrument_id;
  }
  $: if (workspace?.mode && modes.some((item) => item.id === workspace?.mode)) {
    mode = workspace.mode as CommodityMode;
  }

  $: selectedSummary = findSelectedSummary(workspace, selectedInstrumentId);
  $: selectedHistory = findSelectedHistory(workspace, selectedInstrumentId);
  $: selectedCurve = findSelectedCurve(workspace, selectedInstrumentId);
  $: selectedInventories = filterInventoriesForInstrument(workspace?.inventories ?? [], selectedInstrumentId);
  $: selectedInventory = selectedInventories[0] ?? findSelectedInventory(workspace, selectedInstrumentId);
  $: selectedInstrument = selectedSummary?.instrument ?? findSelectedInstrument(workspace, selectedInstrumentId);
  $: energySummaries = (workspace?.market_summaries ?? []).filter((summary) => summary.instrument.family === "energy");
  $: metalsSummaries = (workspace?.market_summaries ?? []).filter((summary) => summary.instrument.family === "metals");
  $: visibleSummaries = mode === "metals" ? metalsSummaries : mode === "energy" ? energySummaries : workspace?.market_summaries ?? [];
  $: visibleSpreads = filterSpreads(workspace?.spreads ?? [], mode, workspace?.market_summaries ?? []);
  $: selectedSpreads = filterSpreadsForInstrument(workspace?.spreads ?? [], selectedInstrumentId);
  $: priceSeries = buildPriceSeries(selectedHistory);
  $: curveSeries = buildCurveSeries(selectedCurve);
  $: visibleInventories = mode === "energy" || mode === "metals" || mode === "inventories_fundamentals"
    ? selectedInventories
    : [];
  $: selectedEvents = (workspace?.events ?? []).filter(
    (event) => !selectedInstrumentId || event.linked_instrument_ids.includes(selectedInstrumentId)
  );
  $: selectedCrossDomainLinks = (workspace?.cross_domain_links ?? []).filter(
    (link) => !selectedInstrumentId || link.linked_instrument_ids.includes(selectedInstrumentId)
  );
  $: eventRows = selectedEvents;
  $: coverageNotices = [...(workspace?.coverage.caveats ?? []), ...(workspace?.warnings ?? [])].slice(0, 3);
  $: instrumentGroups = buildInstrumentGroups(workspace?.instruments ?? []);
  $: modeInstrumentOptions = buildModeInstrumentOptions(workspace, mode);
  $: curveInstrumentOptions = buildCurveInstrumentOptions(workspace);
  $: availableModeIds = new Set(workspace?.available_modes ?? modes.map((item) => item.id));
  $: overview = workspace?.overview ?? null;
  $: overviewRows = buildOverviewRows(workspace);
  $: curveBreadth = buildCurveBreadth(workspace);
  $: largestMover = findLargestMover(workspace?.market_summaries ?? []);
  $: strongestRoll = findStrongestRoll(workspace?.curves ?? [], workspace?.market_summaries ?? []);
  $: inventoryOutlier = findInventoryOutlier(workspace?.inventories ?? []);
  $: scatterState = buildScatterState(workspace);
  $: backwardationRows = overview?.rankings
    ? buildRankRowsFromOverview(overview.rankings.strongest_backwardation, "positive")
    : buildBackwardationRows(workspace?.curves ?? [], workspace?.market_summaries ?? []);
  $: contangoRows = overview?.rankings
    ? buildRankRowsFromOverview(overview.rankings.deepest_contango, "negative")
    : buildContangoRows(workspace?.curves ?? [], workspace?.market_summaries ?? []);
  $: inventoryOutlierRows = overview?.rankings
    ? buildRankRowsFromOverview(overview.rankings.inventory_outliers, "warning")
    : buildInventoryOutlierRows(workspace?.inventories ?? []);
  $: spreadZRows = overview?.rankings
    ? buildRankRowsFromOverview(overview.rankings.spread_z_score_outliers, "warning", true)
    : buildSpreadZRows(workspace?.spreads ?? []);
  $: historyPointCount = selectedHistory?.points.length ?? 0;
  $: latestHistoryDate = selectedHistory?.points.at(-1)?.timestamp ?? selectedSummary?.retrieved_at ?? workspace?.retrieved_at ?? null;
  $: termSpreadHeatmapRows = buildTermSpreadHeatmap(selectedCurve);
  $: crackMatrixRows = buildCrackMatrix(workspace?.spreads ?? []);
  $: inventoryCloudRows = buildInventoryCloudRows(visibleInventories);
  $: flowProxyRows = buildFlowProxyRows(workspace, selectedInstrumentId);
  $: fundamentalStackSeries = buildFundamentalStackSeries(visibleInventories);
  $: fundamentalTapeRows = buildFundamentalTapeRows(visibleInventories);
  $: metalsCorrelationRows = buildMetalsCorrelationRows(workspace, macroHistories);
  $: metalRatioGaugeRows = buildMetalRatioGaugeRows(workspace?.spreads ?? []);
  $: warehouseStockRows = buildWarehouseStockRows(mode === "metals" ? workspace?.inventories ?? [] : visibleInventories);
  $: substitutionSpreadRows = buildSubstitutionSpreadRows(workspace?.spreads ?? []);
  $: if (mode === "metals") {
    void ensureMacroDrivers();
  }

  let scatterShellEl: HTMLElement | null = null;
  let tooltipPoint: (typeof scatterState.points)[0] | null = null;
  let tooltipPos = { x: 0, y: 0 };

  function handleScatterMouseMove(event: MouseEvent) {
    if (!scatterShellEl) return;
    const rect = scatterShellEl.getBoundingClientRect();
    tooltipPos = {
      x: event.clientX - rect.left + 14,
      y: event.clientY - rect.top - 56
    };
  }

  onMount(() => {
    if (!workspace) {
      void onLoadWorkspace({ mode, selectedInstrumentId });
    }
  });

  async function refresh(nextMode = mode, forceRefresh = false, instrumentId = selectedInstrumentId) {
    await onLoadWorkspace({ mode: nextMode, selectedInstrumentId: instrumentId, forceRefresh });
  }

  async function selectMode(nextMode: CommodityMode) {
    const nextInstrumentId = instrumentIdForMode(nextMode);
    mode = nextMode;
    selectedInstrumentId = nextInstrumentId;
    await refresh(nextMode, false, nextInstrumentId);
  }

  async function handleInstrumentChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    await selectInstrument(target.value);
  }

  async function selectInstrument(instrumentId: string) {
    if (!instrumentId) {
      return;
    }
    selectedInstrumentId = instrumentId;
    await refresh(mode, false, instrumentId);
  }

  function findSelectedSummary(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.market_summaries ?? []).find((summary) => summary.instrument.instrument_id === instrumentId) ?? null;
  }

  function findSelectedInstrument(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.instruments ?? []).find((instrument) => instrument.instrument_id === instrumentId) ?? null;
  }

  function findSelectedHistory(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.price_histories ?? []).find((history) => history.instrument_id === instrumentId) ?? null;
  }

  function findSelectedCurve(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.curves ?? []).find((curve) => curve.instrument_id === instrumentId) ?? null;
  }

  function findSelectedInventory(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.inventories ?? []).find((series) => series.metadata.instrument_id === instrumentId) ?? null;
  }

  function buildPriceSeries(history: CommodityPriceHistory | null): ChartSeries[] {
    if (!history?.points.length) {
      return [];
    }
    return [
      {
        id: history.instrument_id,
        label: history.label,
        color: "var(--chart-primary)",
        type: "area",
        data: history.points
          .map((point) => ({
            time: Math.floor(new Date(point.timestamp).getTime() / 1000),
            value: point.value
          }))
          .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      }
    ];
  }

  function buildCurveSeries(curve: CommodityCurveSnapshot | null): ChartSeries[] {
    if (!curve?.nodes.length) {
      return [];
    }
    const current = curve.nodes
      .map((node, index) => ({
        time: relativeContractTimestamp(index),
        tickLabel: relativeContractLabel(index),
        value: node.price
      }))
      .filter((point): point is { time: number; value: number } => Number.isFinite(point.time) && point.value != null && Number.isFinite(point.value));
    const previous = curve.nodes
      .map((node, index) => ({
        time: relativeContractTimestamp(index),
        tickLabel: relativeContractLabel(index),
        value: node.previous_price
      }))
      .filter((point): point is { time: number; value: number } => Number.isFinite(point.time) && point.value != null && Number.isFinite(point.value));
    return [
      {
        id: `${curve.instrument_id}-curve-current`,
        label: "Current curve",
        color: "var(--chart-primary)",
        type: "line",
        showPointMarkers: true,
        pointMarkerRadius: 3,
        data: current
      },
      ...(previous.length
        ? [
            {
              id: `${curve.instrument_id}-curve-previous`,
              label: "Previous curve",
              color: "var(--chart-secondary)",
              type: "line" as const,
              lineStyle: "dashed" as const,
              showPointMarkers: true,
              pointMarkerRadius: 3,
              data: previous
            }
          ]
        : [])
    ];
  }

  async function ensureMacroDrivers() {
    for (const seriesId of macroDriverSeries) {
      const key = macroHistoryKey(seriesId);
      if (macroHistories[key] || requestedMacroDrivers.has(key)) {
        continue;
      }
      requestedMacroDrivers.add(key);
      await onLoadMacroSeries(seriesId, { region: "US", timeframe: "3M" });
    }
  }

  function macroHistoryKey(seriesId: string) {
    return `US:3M:${seriesId}`;
  }

  function buildTermSpreadHeatmap(curve: CommodityCurveSnapshot | null) {
    const nodes = curve?.nodes ?? [];
    return nodes.slice(0, -1).map((node, index) => {
      const next = nodes[index + 1];
      const value = node.price != null && next.price != null ? node.price - next.price : null;
      return {
        id: `${curve?.instrument_id ?? "curve"}-${index}`,
        label: `M${index + 1}-M${index + 2}`,
        left: node.contract.symbol,
        right: next.contract.symbol,
        value,
        tone: value == null ? "neutral" : value > 0 ? "positive" : value < 0 ? "negative" : "neutral",
        width: value == null ? 0 : Math.min(100, Math.max(12, Math.abs(value) * 42))
      };
    });
  }

  function buildCrackMatrix(spreads: CommoditySpreadSnapshot[]) {
    const ids = ["gasoline-crack", "heating-oil-crack", "two-one-one-crack", "three-two-one-crack"];
    return ids
      .map((id) => spreads.find((spread) => spread.definition.spread_id === id))
      .filter((spread): spread is CommoditySpreadSnapshot => Boolean(spread))
      .map((spread) => ({
        id: spread.definition.spread_id,
        label: spread.definition.label,
        formula: spread.definition.formula,
        value: spread.value,
        change: spread.change,
        percentile: spread.percentile,
        interpretation: spread.interpretation ?? "N/A",
        tone: spread.change == null ? "" : spread.change > 0 ? "positive" : spread.change < 0 ? "negative" : ""
      }));
  }

  function buildInventoryCloudRows(seriesRows: CommodityInventorySeries[]) {
    return seriesRows.map((series) => {
      const latest = series.points.at(-1);
      const latestDate = latest ? new Date(latest.timestamp) : null;
      const weekKey = latestDate && !Number.isNaN(latestDate.getTime()) ? weekOfYear(latestDate) : null;
      const seasonalPoints = weekKey == null
        ? series.points
        : series.points.filter((point) => weekOfYear(new Date(point.timestamp)) === weekKey);
      const values = seasonalPoints.map((point) => point.value).filter((value) => Number.isFinite(value));
      const allValues = series.points.map((point) => point.value).filter((value) => Number.isFinite(value));
      const bandValues = values.length >= 3 ? values : allValues;
      const min = bandValues.length ? Math.min(...bandValues) : null;
      const max = bandValues.length ? Math.max(...bandValues) : null;
      const latestValue = series.latest_value ?? latest?.value ?? null;
      const position = min != null && max != null && latestValue != null && max !== min
        ? ((latestValue - min) / (max - min)) * 100
        : null;
      return {
        id: series.metadata.series_id,
        label: series.metadata.label,
        unit: series.metadata.unit,
        latest: latestValue,
        change: series.latest_change,
        min,
        max,
        position: position == null ? null : Math.max(0, Math.min(100, position)),
        percentile: series.seasonal_percentile,
        methodology: series.points.length >= 240 ? "5Y seasonal band" : "Loaded seasonal band",
        interpretation: series.interpretation ?? "N/A"
      };
    });
  }

  function buildFlowProxyRows(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    const selectedLinks = (data?.cross_domain_links ?? []).filter((link) => link.linked_instrument_ids.includes(instrumentId));
    const maritimeLink = selectedLinks.find((link) => link.target_domain === "maritime");
    const inventory = findSelectedInventory(data, instrumentId);
    const isEnergy = findSelectedInstrument(data, instrumentId)?.family === "energy";
    return [
      {
        hub: "Cushing",
        metric: inventory ? inventoryValue(inventory) : "Storage N/A",
        signal: inventory?.interpretation ?? "No linked storage series",
        source: inventory?.source_provider ?? "inventory payload"
      },
      {
        hub: "US Gulf",
        metric: isEnergy ? "Maritime handoff" : "N/A",
        signal: maritimeLink?.summary ?? "No vessel-count feed in commodities payload",
        source: maritimeLink?.source_provider ?? "handoff proxy"
      },
      {
        hub: "Rotterdam",
        metric: maritimeLink ? `confidence ${formatNumber(maritimeLink.confidence, 2)}` : "Proxy only",
        signal: maritimeLink ? humanize(maritimeLink.relationship) : "Requires Maritime flow coverage",
        source: maritimeLink?.origin ?? "provider unavailable"
      }
    ];
  }

  function buildFundamentalStackSeries(seriesRows: CommodityInventorySeries[]): ChartSeries[] {
    const colors = [
      "var(--chart-primary)",
      "var(--chart-secondary)",
      "var(--positive)",
      "var(--warning)",
      "var(--negative)"
    ];
    return [...seriesRows]
      .filter((series) => series.points.length >= 2)
      .sort((left, right) => categoryRank(left.metadata.category) - categoryRank(right.metadata.category))
      .slice(0, 5)
      .map((series, index) => {
        const first = series.points.find((point) => Number.isFinite(point.value) && point.value !== 0)?.value;
        const data = first
          ? series.points
              .slice(-260)
              .map((point) => ({
                time: Math.floor(new Date(point.timestamp).getTime() / 1000),
                value: (point.value / first) * 100
              }))
              .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
          : [];
        return {
          id: `${series.metadata.series_id}-indexed`,
          label: `${humanize(series.metadata.category)} | ${series.metadata.label}`,
          color: colors[index % colors.length],
          type: "line" as const,
          data
        };
      })
      .filter((series) => series.data.length >= 2);
  }

  function buildFundamentalTapeRows(seriesRows: CommodityInventorySeries[]) {
    return [...seriesRows]
      .sort((left, right) => categoryRank(left.metadata.category) - categoryRank(right.metadata.category))
      .map((series) => ({
        id: series.metadata.series_id,
        label: series.metadata.label,
        category: humanize(series.metadata.category),
        latest: series.latest_value ?? series.points.at(-1)?.value ?? null,
        change: series.latest_change ?? series.points.at(-1)?.change ?? null,
        unit: series.metadata.unit,
        percentile: series.seasonal_percentile,
        source: series.metadata.provider_series_id ?? series.metadata.source_provider,
        signal: series.interpretation ?? "N/A",
        path: sparklinePath(series.points),
        tone: valueClass(series.latest_change)
      }));
  }

  function buildMetalsCorrelationRows(
    data: CommodityWorkspaceResponse | null,
    histories: Record<string, MacroSeriesHistory>
  ) {
    const drivers = [
      { id: "us-dollar-broad", label: "DXY/Broad USD", history: histories[macroHistoryKey("us-dollar-broad")] },
      { id: "us-real-10y-yield", label: "10Y Real Yield", history: histories[macroHistoryKey("us-real-10y-yield")] }
    ];
    const metals = ["gold", "copper"]
      .map((instrumentId) => findSelectedHistory(data, instrumentId))
      .filter((history): history is CommodityPriceHistory => Boolean(history));
    return metals.flatMap((metal) =>
      drivers.map((driver) => {
        const corr = rollingCorrelation(metal.points, driver.history?.points ?? [], 30);
        return {
          id: `${metal.instrument_id}-${driver.id}`,
          metal: metal.instrument_id === "gold" ? "Gold" : "Copper",
          driver: driver.label,
          value: corr,
          tone: corr == null ? "neutral" : corr > 0.35 ? "positive" : corr < -0.35 ? "negative" : "warning",
          note: corr == null ? "Load Macro US 3M driver history" : correlationNote(metal.instrument_id, driver.id, corr)
        };
      })
    );
  }

  function buildMetalRatioGaugeRows(spreads: CommoditySpreadSnapshot[]) {
    return ["gold-silver-ratio", "gold-platinum-ratio"]
      .map((id) => spreads.find((spread) => spread.definition.spread_id === id))
      .filter((spread): spread is CommoditySpreadSnapshot => Boolean(spread))
      .map((spread) => {
        const values = spread.history.map((point) => point.value).filter((value) => Number.isFinite(value));
        const mean = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
        const current = spread.value;
        const distance = current != null && mean ? ((current - mean) / mean) * 100 : null;
        return {
          id: spread.definition.spread_id,
          label: spread.definition.label,
          current,
          mean,
          distance,
          percentile: spread.percentile,
          position: spread.percentile ?? (distance == null ? null : Math.max(0, Math.min(100, 50 + distance))),
          methodology: values.length >= 2400 ? "10Y mean" : "Loaded-history mean"
        };
      });
  }

  function buildWarehouseStockRows(seriesRows: CommodityInventorySeries[]) {
    return seriesRows
      .filter((series) => series.metadata.category === "warehouse")
      .map((series) => ({
        id: series.metadata.series_id,
        label: series.metadata.label,
        market: findSelectedInstrument(workspace, series.metadata.instrument_id ?? "")?.symbol ?? displayStatus(series.metadata.instrument_id),
        latest: series.latest_value,
        change: series.latest_change,
        percentile: series.seasonal_percentile,
        unit: series.metadata.unit,
        signal: series.interpretation ?? "N/A",
        source: series.metadata.source_provider
      }));
  }

  function buildSubstitutionSpreadRows(spreads: CommoditySpreadSnapshot[]) {
    return spreads
      .filter((spread) => spread.definition.spread_id === "copper-aluminum-spread")
      .map((spread) => ({
        id: spread.definition.spread_id,
        label: spread.definition.label,
        value: spread.value,
        change: spread.change,
        zScore: spread.z_score,
        percentile: spread.percentile,
        interpretation: spread.interpretation ?? "N/A"
      }));
  }

  function weekOfYear(date: Date) {
    const start = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    const day = Math.floor((Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) - start.getTime()) / 86400000);
    return Math.floor(day / 7) + 1;
  }

  function categoryRank(category: string | null | undefined) {
    const order = ["inventories", "storage", "production", "imports", "exports", "refinery", "demand", "warehouse"];
    const index = order.indexOf(category ?? "");
    return index === -1 ? order.length : index;
  }

  function sparklinePath(points: Array<{ timestamp: string; value: number }>, width = 96, height = 28) {
    const values = points
      .slice(-48)
      .map((point) => point.value)
      .filter((value) => Number.isFinite(value));
    if (values.length < 2) {
      return "";
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / Math.max(1, values.length - 1)) * width;
        const y = height - ((value - min) / range) * height;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }

  function rollingCorrelation(
    leftPoints: Array<{ timestamp: string; value: number }>,
    rightPoints: Array<{ timestamp: string; value: number }>,
    windowSize: number
  ) {
    const rightByDate = new Map(rightPoints.map((point) => [dateKey(point.timestamp), point.value]));
    const aligned = leftPoints
      .map((point) => ({ left: point.value, right: rightByDate.get(dateKey(point.timestamp)) }))
      .filter((point): point is { left: number; right: number } => point.right != null && Number.isFinite(point.left) && Number.isFinite(point.right));
    const window = aligned.slice(-windowSize);
    if (window.length < Math.min(18, windowSize)) {
      return null;
    }
    return correlation(window.map((point) => point.left), window.map((point) => point.right));
  }

  function correlation(left: number[], right: number[]) {
    const count = Math.min(left.length, right.length);
    if (count < 2) {
      return null;
    }
    const leftMean = left.slice(0, count).reduce((sum, value) => sum + value, 0) / count;
    const rightMean = right.slice(0, count).reduce((sum, value) => sum + value, 0) / count;
    let numerator = 0;
    let leftDenom = 0;
    let rightDenom = 0;
    for (let index = 0; index < count; index += 1) {
      const leftDiff = left[index] - leftMean;
      const rightDiff = right[index] - rightMean;
      numerator += leftDiff * rightDiff;
      leftDenom += leftDiff * leftDiff;
      rightDenom += rightDiff * rightDiff;
    }
    const denom = Math.sqrt(leftDenom * rightDenom);
    return denom ? numerator / denom : null;
  }

  function dateKey(value: string) {
    return value.slice(0, 10);
  }

  function correlationNote(metalId: string, driverId: string, value: number) {
    if (metalId === "gold" && driverId === "us-real-10y-yield" && value > 0.25) {
      return "Gold and real yields are rising together; macro narrative may be stressed.";
    }
    if (metalId === "gold" && driverId === "us-dollar-broad" && value < -0.25) {
      return "Classic inverse dollar sensitivity is active.";
    }
    if (metalId === "copper" && value > 0.25) {
      return "Industrial metal is moving with the macro driver.";
    }
    return "Near mixed/neutral 30D correlation bucket.";
  }

  function relativeContractTimestamp(index: number) {
    return Math.floor(Date.UTC(2000, index, 1) / 1000);
  }

  function relativeContractLabel(index: number) {
    return `M${index + 1}`;
  }

  function formatNumber(value: number | null | undefined, digits = 2) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    return value.toLocaleString(undefined, {
      maximumFractionDigits: digits,
      minimumFractionDigits: Math.abs(value) < 10 && value !== 0 ? Math.min(digits, 2) : 0
    });
  }

  function formatPct(value: number | null | undefined, fromDecimal = true) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    const pct = fromDecimal ? value * 100 : value;
    return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
  }

  function formatPercentile(value: number | null | undefined) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    return `${value.toFixed(1)}%`;
  }

  function formatDate(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "N/A";
    }
    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  }

  function humanize(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    return value.replace(/_/g, " ");
  }

  function displayStatus(value: string | null | undefined) {
    return humanize(value).toUpperCase();
  }

  function valueClass(value: number | null | undefined) {
    if (value == null) {
      return "";
    }
    if (value > 0) {
      return "positive";
    }
    if (value < 0) {
      return "negative";
    }
    return "";
  }

  function spreadUnit(spread: CommoditySpreadSnapshot) {
    return spread.definition.unit === "ratio" ? "x" : spread.definition.unit;
  }

  function inventoryValue(series: CommodityInventorySeries) {
    return `${formatNumber(series.latest_value, 2)} ${series.metadata.unit}`;
  }

  function coverageTone(status: string | null | undefined) {
    const normalized = (status ?? "").toLowerCase();
    if (normalized === "live") {
      return "positive";
    }
    if (normalized.includes("unavailable") || normalized.includes("missing") || normalized.includes("error")) {
      return "negative";
    }
    return "warning";
  }

  function isModeAvailable(modeId: CommodityMode) {
    return availableModeIds.has(modeId);
  }

  function instrumentIdForMode(nextMode: CommodityMode) {
    const options = buildModeInstrumentOptions(workspace, nextMode);
    if (!options.length || options.some((instrument) => instrument.instrument_id === selectedInstrumentId)) {
      return selectedInstrumentId;
    }
    return options[0].instrument_id;
  }

  function buildInstrumentGroups(instruments: CommodityWorkspaceResponse["instruments"]) {
    const order = ["energy", "metals"];
    const groups = new Map<string, CommodityWorkspaceResponse["instruments"]>();
    for (const instrument of instruments) {
      const family = instrument.family || "other";
      groups.set(family, [...(groups.get(family) ?? []), instrument]);
    }
    return [...groups.entries()]
      .sort(([left], [right]) => {
        const leftIndex = order.indexOf(left);
        const rightIndex = order.indexOf(right);
        if (leftIndex >= 0 || rightIndex >= 0) {
          return (leftIndex >= 0 ? leftIndex : order.length) - (rightIndex >= 0 ? rightIndex : order.length);
        }
        return left.localeCompare(right);
      })
      .map(([family, instruments]) => ({ family, label: displayStatus(family), instruments }));
  }

  function filterSpreads(
    spreads: CommoditySpreadSnapshot[],
    activeMode: CommodityMode,
    summaries: CommodityMarketSummary[]
  ) {
    if (activeMode !== "energy" && activeMode !== "metals") {
      return spreads;
    }
    const familyByInstrument = new Map(
      summaries.map((summary) => [summary.instrument.instrument_id, summary.instrument.family])
    );
    return spreads.filter((spread) => {
      const rawDefinition = [
        spread.definition.spread_id,
        spread.definition.left_leg_id,
        spread.definition.right_leg_id,
        spread.definition.formula
      ].join(" ").toLowerCase();
      for (const [instrumentId, family] of familyByInstrument.entries()) {
        if (family === activeMode && rawDefinition.includes(instrumentId.toLowerCase())) {
          return true;
        }
      }
      return false;
    });
  }

  function filterSpreadsForInstrument(spreads: CommoditySpreadSnapshot[], instrumentId: string) {
    const needle = instrumentId.toLowerCase();
    return spreads.filter((spread) =>
      [
        spread.definition.spread_id,
        spread.definition.left_leg_id,
        spread.definition.right_leg_id,
        spread.definition.formula,
        spread.definition.label
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }

  function filterInventoriesForInstrument(inventories: CommodityInventorySeries[], instrumentId: string) {
    return inventories.filter((series) => series.metadata.instrument_id === instrumentId);
  }

  function buildModeInstrumentOptions(data: CommodityWorkspaceResponse | null, activeMode: CommodityMode) {
    if (!data) {
      return [];
    }
    const instruments = data.instruments ?? [];
    if (activeMode === "energy" || activeMode === "metals") {
      return instruments.filter((instrument) => instrument.family === activeMode);
    }
    if (activeMode === "overview" || activeMode === "curves_spreads") {
      const curveIds = new Set(data.curves.map((curve) => curve.instrument_id));
      return instruments.filter((instrument) => curveIds.has(instrument.instrument_id));
    }
    if (activeMode === "inventories_fundamentals") {
      const inventoryIds = new Set(data.inventories.map((series) => series.metadata.instrument_id).filter(Boolean));
      return instruments.filter((instrument) => inventoryIds.has(instrument.instrument_id));
    }
    if (activeMode === "events_cross_domain") {
      const linkedIds = new Set([
        ...data.events.flatMap((event) => event.linked_instrument_ids),
        ...data.cross_domain_links.flatMap((link) => link.linked_instrument_ids)
      ]);
      return linkedIds.size ? instruments.filter((instrument) => linkedIds.has(instrument.instrument_id)) : instruments;
    }
    return instruments;
  }

  function buildCurveInstrumentOptions(data: CommodityWorkspaceResponse | null) {
    return buildModeInstrumentOptions(data, "overview");
  }

  function buildOverviewRows(data: CommodityWorkspaceResponse | null) {
    const backendRows = data?.overview?.matrix_rows ?? [];
    if (backendRows.length) {
      return prepareOverviewRows(backendRows.map((row) => ({
        instrumentId: row.instrument_id,
        family: row.family,
        symbol: row.symbol,
        name: row.name,
        quoteUnit: row.quote_unit,
        latestPrice: row.latest_price,
        latestChangePct: row.latest_change_pct,
        curveState: row.curve_state,
        frontSpread: row.front_spread,
        inventoryDisplay:
          row.inventory_seasonal_percentile != null
            ? formatPercentile(row.inventory_seasonal_percentile)
            : row.inventory_signal ?? "N/A"
      })));
    }
    const summaries = data?.market_summaries ?? [];
    const curves = data?.curves ?? [];
    const inventories = data?.inventories ?? [];
    const curveByInstrument = new Map(curves.map((curve) => [curve.instrument_id, curve]));
    const inventoryByInstrument = new Map(
      inventories
        .filter((series) => series.metadata.instrument_id)
        .map((series) => [series.metadata.instrument_id as string, series])
    );
    return prepareOverviewRows([...summaries]
      .sort((left, right) => familyRank(left.instrument.family) - familyRank(right.instrument.family) || left.instrument.name.localeCompare(right.instrument.name))
      .map((summary) => ({
        instrumentId: summary.instrument.instrument_id,
        family: summary.instrument.family,
        symbol: summary.instrument.symbol,
        name: summary.instrument.name,
        quoteUnit: summary.instrument.quote_unit,
        latestPrice: summary.latest_price,
        latestChangePct: summary.latest_change_pct,
        curveState: summary.curve_state,
        frontSpread: curveByInstrument.get(summary.instrument.instrument_id)?.front_spread ?? summary.front_spread,
        inventoryDisplay: inventoryByInstrument.get(summary.instrument.instrument_id)
          ? formatPercentile(inventoryByInstrument.get(summary.instrument.instrument_id)?.seasonal_percentile)
          : summary.inventory_signal ?? "N/A"
      })));
  }

  function prepareOverviewRows<T extends { family: string | null | undefined; name: string }>(rows: T[]) {
    const ordered = [...rows].sort(
      (left, right) => familyRank(left.family) - familyRank(right.family) || left.name.localeCompare(right.name)
    );
    const familyCounts = new Map<string, number>();
    for (const row of ordered) {
      const family = row.family || "other";
      familyCounts.set(family, (familyCounts.get(family) ?? 0) + 1);
    }
    const renderedFamilies = new Set<string>();
    return ordered.map((row) => {
      const family = row.family || "other";
      const showFamily = !renderedFamilies.has(family);
      renderedFamilies.add(family);
      return {
        ...row,
        showFamily,
        familyRowspan: showFamily ? familyCounts.get(family) ?? 1 : 0
      };
    });
  }

  function familyRank(family: string | null | undefined) {
    if (family === "energy") return 0;
    if (family === "metals") return 1;
    return 2;
  }

  function buildCurveBreadth(data: CommodityWorkspaceResponse | null) {
    const breadth = data?.overview?.market_breadth;
    if (breadth) {
      return {
        backwardation: breadth.backwardation_count,
        contango: breadth.contango_count
      };
    }
    const summaries = data?.market_summaries ?? [];
    return {
      backwardation: summaries.filter((summary) => summary.curve_state.toLowerCase().includes("backward")).length,
      contango: summaries.filter((summary) => summary.curve_state.toLowerCase().includes("contango")).length
    };
  }

  function findLargestMover(summaries: CommodityMarketSummary[]) {
    return [...summaries]
      .filter((summary) => summary.latest_change_pct != null)
      .sort((left, right) => Math.abs(right.latest_change_pct ?? 0) - Math.abs(left.latest_change_pct ?? 0))[0] ?? null;
  }

  function findStrongestRoll(curves: CommodityCurveSnapshot[], summaries: CommodityMarketSummary[]) {
    const labelById = new Map(summaries.map((summary) => [summary.instrument.instrument_id, summary.instrument.symbol]));
    const curve = [...curves]
      .filter((item) => item.roll_yield_proxy_pct != null)
      .sort((left, right) => Math.abs(right.roll_yield_proxy_pct ?? 0) - Math.abs(left.roll_yield_proxy_pct ?? 0))[0];
    return curve ? { label: labelById.get(curve.instrument_id) ?? curve.instrument_id.toUpperCase(), value: curve.roll_yield_proxy_pct } : null;
  }

  function findInventoryOutlier(inventories: CommodityInventorySeries[]) {
    return [...inventories]
      .filter((series) => series.seasonal_percentile != null)
      .sort((left, right) => Math.abs((right.seasonal_percentile ?? 50) - 50) - Math.abs((left.seasonal_percentile ?? 50) - 50))[0] ?? null;
  }

  function buildScatterState(data: CommodityWorkspaceResponse | null) {
    const backendPoints = data?.overview?.scatter?.points ?? [];
    if (backendPoints.length) {
      return scaleScatterPoints(
        backendPoints.map((point) => ({
          id: point.instrument_id,
          symbol: point.display_label || point.symbol,
          name: point.name,
          family: point.family,
          x: point.x_value,
          y: point.y_value
        }))
      );
    }
    const summaries = data?.market_summaries ?? [];
    const curves = data?.curves ?? [];
    const histories = data?.price_histories ?? [];
    const curveByInstrument = new Map(curves.map((curve) => [curve.instrument_id, curve]));
    const historyByInstrument = new Map(histories.map((history) => [history.instrument_id, history]));
    const raw = summaries
      .map((summary) => {
        const momentum = historyMomentumPct(historyByInstrument.get(summary.instrument.instrument_id))
          ?? (summary.latest_change_pct == null ? null : summary.latest_change_pct * 100);
        const roll = curveByInstrument.get(summary.instrument.instrument_id)?.roll_yield_proxy_pct ?? null;
        if (momentum == null || roll == null || !Number.isFinite(momentum) || !Number.isFinite(roll)) {
          return null;
        }
        return {
          id: summary.instrument.instrument_id,
          symbol: summary.instrument.symbol,
          name: summary.instrument.name,
          family: summary.instrument.family,
          x: momentum,
          y: roll
        };
      })
      .filter((point): point is { id: string; symbol: string; name: string; family: string; x: number; y: number } => point != null);

    return scaleScatterPoints(raw);
  }

  function scaleScatterPoints(raw: Array<{ id: string; symbol: string; name: string; family: string; x: number; y: number }>) {
    if (!raw.length) {
      return { points: [], zeroX: 50, zeroY: 50, xMin: -1, xMax: 1, yMin: -1, yMax: 1 };
    }

    const xValues = raw.map((point) => point.x);
    const yValues = raw.map((point) => point.y);
    const xExtent = Math.max(...xValues.map((value) => Math.abs(value)), 1) * 1.18;
    const yExtent = Math.max(...yValues.map((value) => Math.abs(value)), 1) * 1.18;
    const xMin = -xExtent;
    const xMax = xExtent;
    const yMin = -yExtent;
    const yMax = yExtent;
    const { left, right, top, bottom } = scatterBounds;
    const scaleX = (value: number) => left + ((value - xMin) / (xMax - xMin || 1)) * (right - left);
    const scaleY = (value: number) => bottom - ((value - yMin) / (yMax - yMin || 1)) * (bottom - top);
    return {
      points: raw.map((point) => ({ ...point, cx: scaleX(point.x), cy: scaleY(point.y) })),
      zeroX: scaleX(0),
      zeroY: scaleY(0),
      xMin,
      xMax,
      yMin,
      yMax
    };
  }

  function historyMomentumPct(history: CommodityPriceHistory | undefined) {
    if (!history?.points.length) {
      return null;
    }
    const first = history.points[0]?.value;
    const last = history.points.at(-1)?.value;
    if (!first || last == null) {
      return null;
    }
    return ((last - first) / first) * 100;
  }

  type RankRow = {
    id: string;
    label: string;
    value: number;
    display: string;
    tone: string;
    width: number;
    signed?: boolean;
  };

  function buildRankRowsFromOverview(items: CommodityOverviewRankingItem[], defaultTone: string, signed = false) {
    return normalizeRankRows(
      items.map((item) => {
        const numericValue = item.value ?? 0;
        return {
          id: item.item_id,
          label: item.label,
          value: signed ? numericValue : Math.abs(numericValue),
          display: item.display_value ?? formatNumber(item.value, 2),
          tone: signed ? signedTone(numericValue) : rankingTone(item, defaultTone),
          width: 0,
          signed
        };
      }),
      { signed }
    );
  }

  function signedTone(value: number) {
    return value < 0 ? "negative" : "positive";
  }

  function rankingTone(item: CommodityOverviewRankingItem, fallback: string) {
    const direction = (item.direction ?? "").toLowerCase();
    if (direction.includes("down") || direction.includes("low") || direction.includes("contango")) {
      return "negative";
    }
    if (direction.includes("up") || direction.includes("high") || direction.includes("backward")) {
      return "positive";
    }
    return fallback;
  }

  function buildBackwardationRows(curves: CommodityCurveSnapshot[], summaries: CommodityMarketSummary[]) {
    const labelById = new Map(summaries.map((summary) => [summary.instrument.instrument_id, summary.instrument.symbol]));
    return normalizeRankRows(
      curves
        .filter((curve) => (curve.front_spread ?? 0) > 0)
        .sort((left, right) => (right.front_spread ?? 0) - (left.front_spread ?? 0))
        .slice(0, 5)
        .map((curve) => ({
          id: curve.instrument_id,
          label: labelById.get(curve.instrument_id) ?? curve.instrument_id.toUpperCase(),
          value: Math.abs(curve.front_spread ?? 0),
          display: formatNumber(curve.front_spread, 2),
          tone: "positive",
          width: 0
        }))
    );
  }

  function buildContangoRows(curves: CommodityCurveSnapshot[], summaries: CommodityMarketSummary[]) {
    const labelById = new Map(summaries.map((summary) => [summary.instrument.instrument_id, summary.instrument.symbol]));
    return normalizeRankRows(
      curves
        .filter((curve) => (curve.front_spread ?? 0) < 0)
        .sort((left, right) => (left.front_spread ?? 0) - (right.front_spread ?? 0))
        .slice(0, 5)
        .map((curve) => ({
          id: curve.instrument_id,
          label: labelById.get(curve.instrument_id) ?? curve.instrument_id.toUpperCase(),
          value: Math.abs(curve.front_spread ?? 0),
          display: formatNumber(curve.front_spread, 2),
          tone: "negative",
          width: 0
        }))
    );
  }

  function buildInventoryOutlierRows(inventories: CommodityInventorySeries[]) {
    return normalizeRankRows(
      inventories
        .filter((series) => series.seasonal_percentile != null)
        .sort((left, right) => Math.abs((right.seasonal_percentile ?? 50) - 50) - Math.abs((left.seasonal_percentile ?? 50) - 50))
        .slice(0, 5)
        .map((series) => ({
          id: series.metadata.series_id,
          label: series.metadata.label,
          value: Math.abs((series.seasonal_percentile ?? 50) - 50),
          display: formatPercentile(series.seasonal_percentile),
          tone: (series.seasonal_percentile ?? 50) >= 50 ? "positive" : "negative",
          width: 0
        }))
    );
  }

  function buildSpreadZRows(spreads: CommoditySpreadSnapshot[]) {
    return normalizeRankRows(
      spreads
        .filter((spread) => spread.z_score != null)
        .sort((left, right) => Math.abs(right.z_score ?? 0) - Math.abs(left.z_score ?? 0))
        .slice(0, 5)
        .map((spread) => ({
          id: spread.definition.spread_id,
          label: spread.definition.label,
          value: spread.z_score ?? 0,
          display: formatNumber(spread.z_score, 2),
          tone: (spread.z_score ?? 0) >= 0 ? "positive" : "negative",
          width: 0,
          signed: true
        })),
      { signed: true }
    );
  }

  function normalizeRankRows(rows: RankRow[], options: { signed?: boolean } = {}) {
    const max = Math.max(...rows.map((row) => Math.abs(row.value)), 0);
    return [...rows]
      .sort((left, right) => Math.abs(right.value) - Math.abs(left.value))
      .map((row) => {
        const magnitude = Math.abs(row.value);
        const scaledWidth = options.signed ? (magnitude / max) * 50 : (magnitude / max) * 100;
        return {
          ...row,
          signed: options.signed || row.signed,
          width: max > 0 && magnitude > 0 ? Math.max(options.signed ? 5 : 8, scaledWidth) : 0
        };
      });
  }

  function scatterGridX(fraction: number) {
    return scatterBounds.left + (scatterBounds.right - scatterBounds.left) * fraction;
  }

  function scatterGridY(fraction: number) {
    return scatterBounds.top + (scatterBounds.bottom - scatterBounds.top) * fraction;
  }

  function curveTone(value: string | null | undefined) {
    const normalized = (value ?? "").toLowerCase();
    if (normalized.includes("backward")) return "positive";
    if (normalized.includes("contango")) return "negative";
    return "warning";
  }

  function modeTitle(activeMode: CommodityMode) {
    return modes.find((item) => item.id === activeMode)?.label ?? "Commodities";
  }

</script>

<section class="view">
  <article class="header-panel panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Commodities</p>
        <div class="headline-title-row">
          <h2>Commodities Research</h2>
          {#if loading}<span class="loading-pill">Refreshing</span>{/if}
        </div>
      </div>
      <button type="button" class="refresh-button" on:click={() => refresh(mode, true)} disabled={loading || !workspace}>
        {loading ? "LOADING..." : "Refresh"}
      </button>
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Commodities modes">
        {#each modes as item}
          <button
            type="button"
            role="tab"
            aria-selected={mode === item.id}
            class:selected={mode === item.id}
            on:click={() => selectMode(item.id)}
            disabled={loading || !isModeAvailable(item.id)}
          >
            {item.label}
          </button>
        {/each}
      </div>
      {#if workspace}
        <div class="headline-strip">
          <div class="headline-kpi">
            <span class="headline-kpi-label">Markets</span>
            <strong class="headline-kpi-value">{workspace.market_summaries.length}</strong>
            <small>{workspace.coverage.regions.join(", ") || "Region N/A"}</small>
          </div>
          <div class="headline-kpi">
            <span class="headline-kpi-label">Curves</span>
            <strong class="headline-kpi-value">{curveBreadth.backwardation}/{curveBreadth.contango}</strong>
            <small>Backward / contango</small>
          </div>
          <div class="headline-kpi">
            <span class="headline-kpi-label">Provider</span>
            <strong class="headline-kpi-value {coverageTone(workspace.coverage.coverage_status)}">
              {displayStatus(workspace.coverage.coverage_status)}
            </strong>
            <small>{workspace.coverage.provider_label}</small>
          </div>
        </div>
      {/if}
    </div>

    {#if workspace}
      <p class="coverage-note">
        {workspace.coverage.freshness_label} | as of {formatDate(workspace.coverage.as_of ?? workspace.retrieved_at)} | {workspace.transformation_note}
      </p>
    {/if}
  </article>

  {#if workspace}
    {#if mode !== "overview"}
    <section class="coverage-strip panel" aria-label="Commodities provider coverage">
      <div>
        <span>Provider</span>
        <strong>{workspace.coverage.provider_label}</strong>
        <small>{displayStatus(workspace.coverage.freshness_label)}</small>
      </div>
      <div>
        <span>Status</span>
        <strong class={coverageTone(workspace.coverage.coverage_status)}>
          {displayStatus(workspace.coverage.coverage_status)}
        </strong>
        <small>{formatDate(workspace.coverage.source_timestamp ?? workspace.retrieved_at)}</small>
      </div>
      <div>
        <span>Coverage</span>
        <strong>{workspace.coverage.instruments.length} markets</strong>
        <small>{workspace.coverage.regions.join(", ") || "Region unavailable"}</small>
      </div>
      <div class="notice-cell">
        <span>Warnings</span>
        {#if coverageNotices.length}
          <ul>
            {#each coverageNotices as notice}
              <li>{notice}</li>
            {/each}
          </ul>
        {:else}
          <strong>No active caveats</strong>
        {/if}
      </div>
    </section>
    {/if}

    {#if mode === "overview"}
      <section class="overview-grid">
        <article class="panel chart-panel span-2">
          <div class="section-head control-head">
            <div>
              <h2>Term Structure Stack</h2>
            </div>
            <label>
              Curve Market
              <select bind:value={selectedInstrumentId} on:change={handleInstrumentChange} disabled={loading || !curveInstrumentOptions.length}>
                {#each curveInstrumentOptions as instrument}
                  <option value={instrument.instrument_id}>{instrument.name}</option>
                {/each}
              </select>
            </label>
          </div>
          <div class="inline-stats">
            <div>
              <span>Shape</span>
              <strong>{selectedCurve?.shape_label ?? "N/A"}</strong>
            </div>
            <div>
              <span>M1-M6</span>
              <strong>{formatNumber(selectedCurve?.m1_m6_spread, 3)}</strong>
            </div>
            <div>
              <span>Roll</span>
              <strong>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
            </div>
          </div>
          <TimeSeriesChart series={curveSeries} height={340} emptyMessage="NO CURVE NODES" showLegend={true} />
        </article>

        <article class="panel table-panel matrix-panel span-2">
          <div class="table-panel-hdr">Commodity Matrix</div>
          <div class="table-wrap">
            <table class="matrix-table">
              <colgroup>
                <col class="sector-col" />
                <col class="market-col" />
                <col class="last-col" />
                <col class="change-col" />
                <col class="curve-col" />
                <col class="basis-col" />
                <col class="inventory-col" />
              </colgroup>
              <thead>
                <tr>
                  <th>Sector</th>
                  <th>Market</th>
                  <th>Last</th>
                  <th>% Chg</th>
                  <th>Curve</th>
                  <th>Basis</th>
                  <th>Inventory</th>
                </tr>
              </thead>
              <tbody>
                {#if overviewRows.length}
                  {#each overviewRows as row}
                    <tr>
                      {#if row.showFamily}
                        <td class="sector-cell" rowspan={row.familyRowspan}>{humanize(row.family)}</td>
                      {/if}
                      <td>
                        <strong>{row.name}</strong>
                        <span>{row.symbol} | {row.quoteUnit}</span>
                      </td>
                      <td>{formatNumber(row.latestPrice, 2)}</td>
                      <td class={valueClass(row.latestChangePct)}>{formatPct(row.latestChangePct)}</td>
                      <td><span class="tag {curveTone(row.curveState)}" title={humanize(row.curveState)}>{humanize(row.curveState)}</span></td>
                      <td class={valueClass(row.frontSpread)}>{formatNumber(row.frontSpread, 2)}</td>
                      <td>{row.inventoryDisplay}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row">
                    <td colspan="7">No commodity summaries available.</td>
                  </tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel scatter-panel span-2">
          <div class="section-head">
            <div>
              <h2>Momentum / Roll Scatter</h2>
            </div>
          </div>
          {#if scatterState.points.length}
            <div class="scatter-shell" bind:this={scatterShellEl}
                 role="presentation"
                 on:mousemove={handleScatterMouseMove}
                 on:mouseleave={() => tooltipPoint = null}>
              <svg viewBox="0 0 200 130" role="img" aria-label="Commodity momentum versus roll yield scatter plot">
                {#each scatterGridFractions as fraction}
                  <line class="grid-line" x1={scatterGridX(fraction)} x2={scatterGridX(fraction)} y1={scatterBounds.top} y2={scatterBounds.bottom} />
                  <line class="grid-line" x1={scatterBounds.left} x2={scatterBounds.right} y1={scatterGridY(fraction)} y2={scatterGridY(fraction)} />
                {/each}
                <line class="axis-line" x1={scatterBounds.left} x2={scatterBounds.right} y1={scatterState.zeroY} y2={scatterState.zeroY} />
                <line class="axis-line" x1={scatterState.zeroX} x2={scatterState.zeroX} y1={scatterBounds.top} y2={scatterBounds.bottom} />
                <text class="quadrant-label" x="11" y="17">Carry / weak momentum</text>
                <text class="quadrant-label" x="189" y="17" text-anchor="end">Backwardation + momentum</text>
                <text class="quadrant-label" x="11" y="105">Contango / weak</text>
                <text class="quadrant-label" x="189" y="105" text-anchor="end">Momentum / carry drag</text>
                <text class="axis-label" x="100" y="127">{overview?.scatter?.x_methodology_label ?? "Loaded-history momentum"}</text>
                <text class="axis-label vertical" x="-59" y="5">{overview?.scatter?.y_methodology_label ?? "Roll proxy"}</text>
                {#each scatterState.points as point}
                  {@const hovered = tooltipPoint?.id === point.id}
                  <g class="scatter-point {point.family}"
                     role="img"
                     aria-label={`${point.name}: momentum ${formatNumber(point.x, 2)}%, roll proxy ${formatNumber(point.y, 2)}%`}
                     class:hovered
                     transform={`translate(${point.cx}, ${point.cy})`}
                     on:mouseenter={() => tooltipPoint = point}
                     on:mouseleave={() => tooltipPoint = null}>
                    <circle r={hovered ? 4.6 : 3.2} />
                    <text x="4.5" y="-4">{point.symbol}</text>
                  </g>
                {/each}
              </svg>
              {#if tooltipPoint}
                <div class="scatter-tooltip" style={`left:${tooltipPos.x}px;top:${tooltipPos.y}px`}>
                  <strong>{tooltipPoint.name}</strong>
                  <div class="tip-row"><span>Momentum</span><span class={valueClass(tooltipPoint.x)}>{formatNumber(tooltipPoint.x, 2)}%</span></div>
                  <div class="tip-row"><span>Roll proxy</span><span class={valueClass(tooltipPoint.y)}>{formatNumber(tooltipPoint.y, 2)}%</span></div>
                  <div class="tip-row"><span>Family</span><span>{tooltipPoint.family}</span></div>
                </div>
              {/if}
            </div>
          {:else}
            <p class="empty-hint">No overlapping price-history and curve-roll data for a scatter view.</p>
          {/if}
        </article>

        <article class="panel event-panel span-2">
          <div class="section-head">
            <div>
              <h2>Event Tape</h2>
            </div>
          </div>
          <div class="table-wrap">
            {#if workspace.events.length}
              <table class="event-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Event</th>
                    <th>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {#each workspace.events.slice(0, 6) as event}
                    <tr>
                      <td>{formatDate(event.scheduled_at)}</td>
                      <td><strong>{event.title}</strong></td>
                      <td>
                        <span>{event.relative_label ?? humanize(event.category)}</span>
                        <span>{displayStatus(event.importance)}</span>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {:else}
              <p class="empty-hint">No event rows are linked to the selected commodity.</p>
            {/if}
          </div>
        </article>

        <article class="panel rankers-panel span-4">
          <div class="section-head">
            <div>
              <h2>Market Regime Ranks</h2>
            </div>
          </div>
          <div class="rank-grid">
            <div class="rank-block">
              <h3>Strongest Backwardation</h3>
              {#if backwardationRows.length}
                <ol class="rank-list">
                  {#each backwardationRows as row}
                    <li>
                      <span class="rank-label">{row.label}</span>
                      <div class="rank-bar-shell" class:signed={row.signed}>
                        <span
                          class="rank-bar {row.tone}"
                          class:signed={row.signed}
                          class:negative-side={row.signed && row.value < 0}
                          class:positive-side={row.signed && row.value >= 0}
                          style={`width:${row.width}%`}
                        ></span>
                      </div>
                      <span class="rank-value {row.tone}">{row.display}</span>
                    </li>
                  {/each}
                </ol>
              {:else}
                <p class="empty-hint">No backwardation rows.</p>
              {/if}
            </div>
            <div class="rank-block">
              <h3>Deepest Contango</h3>
              {#if contangoRows.length}
                <ol class="rank-list">
                  {#each contangoRows as row}
                    <li>
                      <span class="rank-label">{row.label}</span>
                      <div class="rank-bar-shell" class:signed={row.signed}>
                        <span
                          class="rank-bar {row.tone}"
                          class:signed={row.signed}
                          class:negative-side={row.signed && row.value < 0}
                          class:positive-side={row.signed && row.value >= 0}
                          style={`width:${row.width}%`}
                        ></span>
                      </div>
                      <span class="rank-value {row.tone}">{row.display}</span>
                    </li>
                  {/each}
                </ol>
              {:else}
                <p class="empty-hint">No contango rows.</p>
              {/if}
            </div>
            <div class="rank-block">
              <h3>Inventory Outliers</h3>
              {#if inventoryOutlierRows.length}
                <ol class="rank-list">
                  {#each inventoryOutlierRows as row}
                    <li>
                      <span class="rank-label">{row.label}</span>
                      <div class="rank-bar-shell" class:signed={row.signed}>
                        <span
                          class="rank-bar {row.tone}"
                          class:signed={row.signed}
                          class:negative-side={row.signed && row.value < 0}
                          class:positive-side={row.signed && row.value >= 0}
                          style={`width:${row.width}%`}
                        ></span>
                      </div>
                      <span class="rank-value {row.tone}">{row.display}</span>
                    </li>
                  {/each}
                </ol>
              {:else}
                <p class="empty-hint">No inventory percentile rows.</p>
              {/if}
            </div>
            <div class="rank-block">
              <h3>Spread Z-Score</h3>
              {#if spreadZRows.length}
                <ol class="rank-list">
                  {#each spreadZRows as row}
                    <li>
                      <span class="rank-label">{row.label}</span>
                      <div class="rank-bar-shell" class:signed={row.signed}>
                        <span
                          class="rank-bar {row.tone}"
                          class:signed={row.signed}
                          class:negative-side={row.signed && row.value < 0}
                          class:positive-side={row.signed && row.value >= 0}
                          style={`width:${row.width}%`}
                        ></span>
                      </div>
                      <span class="rank-value {row.tone}">{row.display}</span>
                    </li>
                  {/each}
                </ol>
              {:else}
                <p class="empty-hint">No spread z-scores.</p>
              {/if}
            </div>
          </div>
        </article>

        <article class="panel span-4">
          <div class="section-head">
            <div>
              <h2>Cross-Domain Notes</h2>
            </div>
          </div>
          <div class="note-list compact-notes four-col-notes">
            {#if workspace.cross_domain_links.length}
              {#each workspace.cross_domain_links.slice(0, 8) as link}
                <div class="note-row">
                  <strong>{link.target_label}</strong>
                  <span>{humanize(link.target_domain)} | confidence {formatNumber(link.confidence, 2)}</span>
                </div>
              {/each}
            {:else}
              <p class="empty-hint">No cross-domain links are available for this payload.</p>
            {/if}
          </div>
        </article>
      </section>
    {:else}
      <section class="mode-context panel">
        <div>
          <p class="eyebrow">{modeTitle(mode)}</p>
          <h2>{selectedInstrument?.name ?? "Select a commodity"}</h2>
        </div>
        <label>
          Mode Market
          <select bind:value={selectedInstrumentId} on:change={handleInstrumentChange} disabled={loading || !modeInstrumentOptions.length}>
            {#each modeInstrumentOptions as instrument}
              <option value={instrument.instrument_id}>{instrument.name}</option>
            {/each}
          </select>
        </label>
      </section>

      <section class="kpi-strip panel" aria-label="Selected commodity metrics">
        <div class="metric">
          <span>Selected</span>
          <strong>{selectedSummary?.instrument.symbol ?? selectedInstrumentId.toUpperCase()}</strong>
          <small>{selectedSummary?.instrument.quote_unit ?? "unit unavailable"}</small>
        </div>
        <div class="metric">
          <span>Last</span>
          <strong>{formatNumber(selectedSummary?.latest_price, 2)}</strong>
          <small class={valueClass(selectedSummary?.latest_change)}>
            {formatNumber(selectedSummary?.latest_change, 2)} | {formatPct(selectedSummary?.latest_change_pct)}
          </small>
        </div>
        <div class="metric">
          <span>Curve</span>
          <strong>{selectedCurve?.shape_label ?? selectedSummary?.curve_state ?? "unavailable"}</strong>
          <small>Front {formatNumber(selectedCurve?.front_spread, 3)}</small>
        </div>
        <div class="metric">
          <span>Roll Proxy</span>
          <strong>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
          <small>Front-spread heuristic</small>
        </div>
        <div class="metric">
          <span>Inventory</span>
          <strong>{selectedInventory ? formatPercentile(selectedInventory.seasonal_percentile) : "N/A"}</strong>
          <small>{selectedInventory ? inventoryValue(selectedInventory) : "no linked series"}</small>
        </div>
        <div class="metric">
          <span>As Of</span>
          <strong>{formatDate(workspace.coverage.as_of ?? workspace.retrieved_at)}</strong>
          <small>{workspace.source_provider}</small>
        </div>
      </section>
    {/if}

    {#if mode === "energy" || mode === "metals"}
      <section class="split">
        <article class="panel chart-panel">
          <div class="section-head">
            <div>
              <h2>Price History</h2>
              {#if historyPointCount}
                <p>{historyPointCount} observations | latest {formatDate(latestHistoryDate)}</p>
              {:else}
                <p>No price history loaded for the selected market.</p>
              {/if}
            </div>
          </div>
          <TimeSeriesChart series={priceSeries} height={270} emptyMessage="CHART UNAVAILABLE" />
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">{mode === "metals" ? "Metals Snapshot" : mode === "energy" ? "Energy Snapshot" : "Market Snapshot"}</div>
          <div class="table-wrap">
            <table class="market-table">
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Last</th>
                  <th>Chg</th>
                  <th>Curve</th>
                  <th>Inventory</th>
                </tr>
              </thead>
              <tbody>
                {#if visibleSummaries.length}
                  {#each visibleSummaries as summary}
                    <tr class:selected={summary.instrument.instrument_id === selectedInstrumentId}>
                      <td>
                        <button
                          class="market-button"
                          class:active-market={summary.instrument.instrument_id === selectedInstrumentId}
                          type="button"
                          on:click={() => selectInstrument(summary.instrument.instrument_id)}
                          disabled={loading}
                        >
                          <strong>{summary.instrument.name}</strong>
                          <span>{summary.instrument.symbol} | {summary.instrument.quote_unit}</span>
                        </button>
                      </td>
                      <td>{formatNumber(summary.latest_price, 2)}</td>
                      <td class={valueClass(summary.latest_change)}>{formatPct(summary.latest_change_pct)}</td>
                      <td>{humanize(summary.curve_state)}</td>
                      <td>{summary.inventory_signal ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row">
                    <td colspan="5">No commodity summaries available for this mode.</td>
                  </tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "energy"}
      <section class="deep-grid">
        <article class="panel table-panel">
          <div class="table-panel-hdr">Crack Spread Matrix</div>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Spread</th>
                  <th>Value</th>
                  <th>Chg</th>
                  <th>Pctl</th>
                </tr>
              </thead>
              <tbody>
                {#if crackMatrixRows.length}
                  {#each crackMatrixRows as row}
                    <tr>
                      <td>
                        <strong>{row.label}</strong>
                        <span>{row.formula}</span>
                      </td>
                      <td>{formatNumber(row.value, 2)} USD/bbl</td>
                      <td class={row.tone}>{formatNumber(row.change, 2)}</td>
                      <td>{formatPercentile(row.percentile)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No crack-spread rows are available.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Term Structure Heatmap</h2>
            </div>
          </div>
          {#if termSpreadHeatmapRows.length}
            <div class="heatmap-list">
              {#each termSpreadHeatmapRows as row}
                <div class="heatmap-row">
                  <span>{row.label}</span>
                  <div class="heatmap-track">
                    <span class="heatmap-bar {row.tone}" style={`width:${row.width}%`}></span>
                  </div>
                  <strong class={row.tone}>{formatNumber(row.value, 3)}</strong>
                  <small>{row.left} / {row.right}</small>
                </div>
              {/each}
            </div>
          {:else}
            <p class="empty-hint">No adjacent curve nodes for calendar-spread heatmap.</p>
          {/if}
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Inventory vs Seasonality Cloud</h2>
            </div>
          </div>
          <div class="seasonality-list">
            {#if inventoryCloudRows.length}
              {#each inventoryCloudRows as row}
                <div class="seasonality-row">
                  <div>
                    <strong>{row.label}</strong>
                    <span>{row.methodology}</span>
                  </div>
                  <div class="seasonality-band">
                    {#if row.position != null}
                      <span class="seasonality-dot" style={`left:${row.position}%`}></span>
                    {/if}
                  </div>
                  <small>{formatNumber(row.min, 1)} / {formatNumber(row.latest, 1)} / {formatNumber(row.max, 1)} {row.unit}</small>
                </div>
              {/each}
            {:else}
              <p class="empty-hint">No inventory series for the selected energy market.</p>
            {/if}
          </div>
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">Vessel / Flow Proxy</div>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Hub</th>
                  <th>Metric</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {#each flowProxyRows as row}
                  <tr>
                    <td>{row.hub}</td>
                    <td>{row.metric}</td>
                    <td>{row.source}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "metals"}
      <section class="deep-grid">
        <article class="panel table-panel">
          <div class="table-panel-hdr">Macro Driver Correlation</div>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Metal</th>
                  <th>Driver</th>
                  <th>Corr</th>
                  <th>Read</th>
                </tr>
              </thead>
              <tbody>
                {#if metalsCorrelationRows.length}
                  {#each metalsCorrelationRows as row}
                    <tr>
                      <td>{row.metal}</td>
                      <td>{row.driver}</td>
                      <td><span class="tag {row.tone}">{formatNumber(row.value, 2)}</span></td>
                      <td>{row.note}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No gold/copper histories are available for macro correlation.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Precious Ratio Gauges</h2>
            </div>
          </div>
          <div class="ratio-gauge-list">
            {#if metalRatioGaugeRows.length}
              {#each metalRatioGaugeRows as row}
                <div class="ratio-gauge-row">
                  <div>
                    <strong>{row.label}</strong>
                    <span>{row.methodology} | mean {formatNumber(row.mean, 2)}</span>
                  </div>
                  <div class="gauge-track">
                    {#if row.position != null}
                      <span class="gauge-marker" style={`left:${row.position}%`}></span>
                    {/if}
                  </div>
                  <small>{formatNumber(row.current, 2)}x | {formatPercentile(row.percentile)}</small>
                </div>
              {/each}
            {:else}
              <p class="empty-hint">No precious-metal ratio rows are available.</p>
            {/if}
          </div>
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">LME / COMEX Warehouse Stocks</div>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Series</th>
                  <th>Market</th>
                  <th>Latest</th>
                  <th>Chg</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {#if warehouseStockRows.length}
                  {#each warehouseStockRows as row}
                    <tr>
                      <td>
                        <strong>{row.label}</strong>
                        <span>{row.source}</span>
                      </td>
                      <td>{row.market}</td>
                      <td>{formatNumber(row.latest, 1)} {row.unit}</td>
                      <td class={valueClass(row.change)}>{formatNumber(row.change, 1)}</td>
                      <td>{row.signal}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="5">No exchange warehouse rows are available.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">Substitution Spreads</div>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Spread</th>
                  <th>Value</th>
                  <th>Chg</th>
                  <th>Z</th>
                  <th>Read</th>
                </tr>
              </thead>
              <tbody>
                {#if substitutionSpreadRows.length}
                  {#each substitutionSpreadRows as row}
                    <tr>
                      <td>{row.label}</td>
                      <td>{formatNumber(row.value, 1)} USD/mt</td>
                      <td class={valueClass(row.change)}>{formatNumber(row.change, 1)}</td>
                      <td class={valueClass(row.zScore)}>{formatNumber(row.zScore, 2)}</td>
                      <td>{row.interpretation}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="5">No copper/aluminum spread row is available.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if (mode === "energy" || mode === "inventories_fundamentals") && fundamentalTapeRows.length}
      <section class="split">
        <article class="panel chart-panel">
          <div class="section-head">
            <div>
              <h2>EIA Fundamental Stack</h2>
            </div>
          </div>
          <TimeSeriesChart series={fundamentalStackSeries} height={260} emptyMessage="NO FUNDAMENTAL HISTORY" showLegend={true} />
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">Fundamental Tape</div>
          <div class="table-wrap">
            <table class="compact-table fundamental-table">
              <thead>
                <tr>
                  <th>Series</th>
                  <th>Type</th>
                  <th>Latest</th>
                  <th>Chg</th>
                  <th>Path</th>
                </tr>
              </thead>
              <tbody>
                {#each fundamentalTapeRows as row}
                  <tr>
                    <td>
                      <strong>{row.label}</strong>
                      <span>{row.source}</span>
                    </td>
                    <td>{row.category}</td>
                    <td>{formatNumber(row.latest, 2)} {row.unit}</td>
                    <td class={row.tone}>{formatNumber(row.change, 2)}</td>
                    <td class="sparkline-cell">
                      {#if row.path}
                        <svg class="sparkline" viewBox="0 0 96 28" aria-label={`${row.label} recent path`}>
                          <path d={row.path}></path>
                        </svg>
                      {:else}
                        <span class="sparkline-empty">N/A</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "energy" || mode === "metals" || mode === "curves_spreads"}
      <section class="split">
        <article class="panel chart-panel">
          <div class="section-head">
            <div>
              <h2>Curve</h2>
            </div>
          </div>
          <div class="inline-stats">
            <div>
              <span>Shape</span>
              <strong>{selectedCurve?.shape_label ?? "N/A"}</strong>
            </div>
            <div>
              <span>M1-M6</span>
              <strong>{formatNumber(selectedCurve?.m1_m6_spread, 3)}</strong>
            </div>
            <div>
              <span>Slope</span>
              <strong>{formatNumber(selectedCurve?.curve_slope, 3)}</strong>
            </div>
          </div>
          <TimeSeriesChart series={curveSeries} height={285} emptyMessage="NO CURVE NODES" showLegend={true} />
        </article>

        <article class="panel table-panel">
          <div class="table-panel-hdr">Curve Nodes</div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Month</th>
                  <th>DTE</th>
                  <th>Price</th>
                  <th>Chg</th>
                </tr>
              </thead>
              <tbody>
                {#if selectedCurve?.nodes.length}
                  {#each selectedCurve.nodes as node}
                    <tr>
                      <td>{node.contract.symbol}</td>
                      <td>{node.contract.contract_month}</td>
                      <td>{node.days_to_expiry == null ? "N/A" : `${node.days_to_expiry}d`}</td>
                      <td>{formatNumber(node.price, 3)}</td>
                      <td class={valueClass(node.change)}>{formatNumber(node.change, 3)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row">
                    <td colspan="5">No curve nodes available for the selected market.</td>
                  </tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "curves_spreads" || mode === "metals" || mode === "energy"}
      <section class="panel table-panel">
        <div class="table-panel-hdr">Spreads</div>
        <div class="table-wrap">
          <table class="spread-table">
            <thead>
              <tr>
                <th>Spread</th>
                <th>Value</th>
                <th>Change</th>
                <th>Z</th>
                <th>Percentile</th>
              </tr>
            </thead>
            <tbody>
              {#if selectedSpreads.length}
                {#each selectedSpreads as spread}
                  <tr>
                    <td>
                      <strong>{spread.definition.label}</strong>
                      <span>{spread.definition.formula}</span>
                    </td>
                    <td>{formatNumber(spread.value, 3)} {spreadUnit(spread)}</td>
                    <td class={valueClass(spread.change)}>{formatNumber(spread.change, 3)}</td>
                    <td class={valueClass(spread.z_score)}>{formatNumber(spread.z_score, 2)}</td>
                    <td>{formatPercentile(spread.percentile)}</td>
                  </tr>
                {/each}
              {:else}
                <tr class="empty-row">
                  <td colspan="5">No spread rows are linked to the selected market.</td>
                </tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    {#if mode === "energy" || mode === "metals" || mode === "inventories_fundamentals"}
      <section class="inventory-grid">
        {#if visibleInventories.length}
          {#each visibleInventories as series}
            <article class="panel inventory-panel">
              <div>
                <h2>{series.metadata.label}</h2>
                <p>{series.metadata.source_provider} | {series.metadata.frequency}</p>
              </div>
              <dl>
                <div>
                  <dt>Latest</dt>
                  <dd>{inventoryValue(series)}</dd>
                </div>
                <div>
                  <dt>Change</dt>
                  <dd class={valueClass(series.latest_change)}>{formatNumber(series.latest_change, 2)}</dd>
                </div>
                <div>
                  <dt>Percentile</dt>
                  <dd>{formatPercentile(series.seasonal_percentile)}</dd>
                </div>
                <div>
                  <dt>Signal</dt>
                  <dd>{series.interpretation ?? "N/A"}</dd>
                </div>
              </dl>
              {#if sparklinePath(series.points, 120, 32)}
                <svg class="inventory-sparkline" viewBox="0 0 120 32" aria-label={`${series.metadata.label} recent history`}>
                  <path d={sparklinePath(series.points, 120, 32)}></path>
                </svg>
              {:else}
                <p class="sparkline-empty">No loaded history path</p>
              {/if}
            </article>
          {/each}
        {:else}
          <article class="panel inventory-panel empty-state">
            <h2>No Inventory Series</h2>
            <p>No linked inventory or fundamental series is available for the selected market and provider payload.</p>
          </article>
        {/if}
      </section>
    {/if}

    {#if mode === "events_cross_domain"}
      <section class="split">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Events</h2>
            </div>
          </div>
          <div class="note-list">
            {#if eventRows.length}
              {#each eventRows as event}
                <div class="note-row">
                  <strong>{event.title}</strong>
                  <span>{event.relative_label ?? humanize(event.category)} | {formatDate(event.scheduled_at)}</span>
                  <p>{event.summary ?? "No event summary available."}</p>
                </div>
              {/each}
            {:else}
              <p class="empty-hint">No event rows are linked to the selected commodity.</p>
            {/if}
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Cross-Domain</h2>
            </div>
          </div>
          <div class="note-list">
            {#if selectedCrossDomainLinks.length}
              {#each selectedCrossDomainLinks as link}
                <div class="note-row">
                  <strong>{link.target_label}</strong>
                  <span>{humanize(link.target_domain)} | confidence {formatNumber(link.confidence, 2)}</span>
                  <p>{link.summary ?? "No cross-domain note available."}</p>
                </div>
              {/each}
            {:else}
              <p class="empty-hint">No cross-domain links are available for the selected commodity.</p>
            {/if}
          </div>
        </article>
      </section>
    {/if}

    <footer class="panel provenance">
      <div class="provenance-head">
        <strong>Source & Method</strong>
        <span>{workspace.source_provider} | {workspace.origin}</span>
      </div>
      <span>{workspace.transformation_note}</span>
      {#if workspace.coverage.caveats.length}
        <ul>
          {#each workspace.coverage.caveats.slice(0, 6) as caveat}
            <li>{caveat}</li>
          {/each}
        </ul>
      {/if}
    </footer>
  {:else}
    <article class="panel empty-state">
      <h2>{loading ? "LOADING COMMODITIES" : "Commodities unavailable"}</h2>
      <p>{loading ? "Gamma is preparing the commodities workspace." : "No commodities payload is loaded yet."}</p>
    </article>
  {/if}
</section>

<style>
  .view {
    display: grid;
    gap: 0.5rem;
    padding-bottom: 1rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    min-width: 0;
  }

  .header-panel {
    display: grid;
    gap: 0.5rem;
  }

  .header-top,
  .mode-kpi-row,
  .headline-title-row,
  .section-head,
  .control-head {
    display: flex;
    gap: 0.5rem;
  }

  .header-top,
  .mode-kpi-row,
  .section-head,
  .control-head {
    justify-content: space-between;
  }

  .header-top,
  .mode-kpi-row {
    align-items: flex-start;
  }

  .headline-title-row {
    align-items: baseline;
  }

  .headline-block,
  .section-head > div,
  .control-head > div,
  .mode-context > div {
    min-width: 0;
  }

  .header-panel h2,
  .mode-context h2,
  .section-head h2,
  .inventory-panel h2,
  .empty-state h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 650;
    letter-spacing: 0;
    color: var(--text-0);
  }

  .header-panel h2,
  .mode-context h2,
  .metric strong,
  .coverage-strip strong,
  .note-row strong {
    overflow-wrap: anywhere;
  }

  .eyebrow,
  .subtle,
  .coverage-note,
  .mode-context p,
  .section-head p,
  .inventory-panel p,
  .note-row span,
  .provenance span,
  td span,
  small {
    color: var(--text-2);
  }

  .eyebrow,
  .subtle,
  .coverage-note,
  .mode-context p,
  .section-head p,
  .inventory-panel p {
    margin: 0.25rem 0 0;
  }

  .eyebrow {
    margin: 0;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.68rem;
  }

  .subtle,
  .section-head p,
  .inventory-panel p,
  .note-row p,
  .empty-hint,
  .empty-state p {
    line-height: 1.45;
  }

  .loading-pill {
    color: var(--accent);
    border: 1px solid var(--panel-strong);
    padding: 0.15rem 0.45rem;
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .refresh-button {
    flex: 0 0 auto;
    min-height: 25px;
    padding: 4px 9px;
    font-size: 0.72rem;
  }

  label {
    display: grid;
    gap: 0.25rem;
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  select,
  button {
    min-height: 2rem;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0.35rem 0.55rem;
  }

  button {
    cursor: pointer;
  }

  button:not(:disabled):hover,
  select:not(:disabled):hover {
    border-color: var(--accent);
  }

  button:disabled,
  select:disabled {
    cursor: default;
    color: var(--text-2);
  }

  .mode-bar {
    display: inline-flex;
    width: auto;
    max-width: 100%;
    overflow-x: auto;
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    border-radius: 0;
    background: transparent;
    min-height: 27px;
    padding: 0.3rem 0.75rem;
    white-space: nowrap;
    color: var(--text-1);
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button.selected {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .headline-strip {
    display: flex;
    gap: 0;
    justify-content: flex-end;
    min-width: 0;
  }

  .headline-kpi {
    display: grid;
    gap: 0.08rem;
    min-width: 6.5rem;
    padding: 0.1rem 0.65rem;
    border-left: 1px solid var(--divider);
    text-align: right;
  }

  .headline-kpi-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
  }

  .headline-kpi-value {
    color: var(--text-0);
    font-weight: 650;
    line-height: 1.2;
    overflow-wrap: anywhere;
  }

  .coverage-strip {
    display: grid;
    grid-template-columns: minmax(8rem, 0.8fr) minmax(8rem, 0.7fr) minmax(8rem, 0.7fr) minmax(0, 2fr);
    gap: 0;
    padding: 0;
  }

  .coverage-strip > div,
  .metric {
    display: grid;
    gap: 0.22rem;
    min-width: 0;
    padding: 0.65rem 0.75rem;
    border-right: 1px solid var(--divider);
  }

  .coverage-strip > div:last-child,
  .metric:last-child {
    border-right: 0;
  }

  .coverage-strip span,
  .metric span,
  dt {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.66rem;
  }

  .coverage-strip strong,
  .metric strong {
    color: var(--text-0);
    font-weight: 650;
    line-height: 1.25;
  }

  .coverage-strip small,
  .metric small {
    line-height: 1.35;
  }

  .notice-cell ul {
    display: grid;
    gap: 0.16rem;
    margin: 0.1rem 0 0;
    padding-left: 1rem;
    color: var(--text-2);
    line-height: 1.35;
  }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
    padding: 0;
  }

  .metric strong {
    font-size: 1rem;
  }

  .mode-context {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(12rem, auto);
    align-items: end;
    gap: 0.5rem;
  }

  .overview-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .span-2 {
    grid-column: span 2;
  }

  .split {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(21rem, 0.8fr);
    gap: 0.5rem;
  }

  .chart-panel {
    min-height: 24rem;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .section-head > div {
    min-width: 0;
  }

  .inline-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0;
    margin-bottom: 0.5rem;
    border-top: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
  }

  .inline-stats > div {
    display: grid;
    gap: 0.12rem;
    min-width: 0;
    padding: 0.45rem 0.6rem;
    border-right: 1px solid var(--divider);
  }

  .inline-stats > div:last-child {
    border-right: 0;
  }

  .inline-stats span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
  }

  .inline-stats strong {
    color: var(--text-0);
    font-weight: 650;
    overflow-wrap: anywhere;
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-panel-hdr {
    display: flex;
    align-items: center;
    padding: 0.3rem 0.75rem;
    min-height: 26px;
    border-bottom: 1px solid var(--divider);
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-2);
  }

  .table-wrap {
    overflow: auto;
    max-width: 100%;
  }

  table {
    width: 100%;
    min-width: 42rem;
    border-collapse: collapse;
  }

  .market-table,
  .matrix-table {
    table-layout: fixed;
  }

  .market-table {
    min-width: 100%;
  }

  .matrix-table {
    min-width: 42rem;
  }

  .market-table th:nth-child(1),
  .market-table td:nth-child(1) {
    width: 28%;
  }

  .market-table th:nth-child(2),
  .market-table td:nth-child(2),
  .market-table th:nth-child(3),
  .market-table td:nth-child(3) {
    width: 13%;
  }

  .market-table th:nth-child(4),
  .market-table td:nth-child(4) {
    width: 18%;
  }

  .matrix-table .sector-col {
    width: 10%;
  }

  .matrix-table .market-col {
    width: 23%;
  }

  .matrix-table .last-col {
    width: 11%;
  }

  .matrix-table .change-col {
    width: 10%;
  }

  .matrix-table .curve-col {
    width: 17%;
  }

  .matrix-table .basis-col {
    width: 11%;
  }

  .matrix-table .inventory-col {
    width: 18%;
  }

  .spread-table {
    min-width: 40rem;
  }

  th,
  td {
    padding: 0.42rem 0.45rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
    line-height: 1.35;
  }

  th {
    color: var(--text-2);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.66rem;
  }

  td strong,
  td span {
    display: block;
  }

  .matrix-table td {
    overflow-wrap: anywhere;
  }

  .sector-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.66rem;
  }

  tr.selected {
    background: color-mix(in srgb, var(--accent) 7%, transparent);
  }

  .matrix-table tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 5%, transparent);
    cursor: default;
  }

  .market-button {
    display: grid;
    gap: 0.1rem;
    width: 100%;
    min-height: 0;
    padding: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    color: inherit;
    text-align: left;
  }

  .market-button strong {
    color: var(--text-0);
  }

  .market-button span {
    color: var(--text-2);
    font-size: 0.72rem;
  }

  .market-button.active-market strong,
  .market-button:not(:disabled):hover strong {
    color: var(--accent);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .warning {
    color: var(--warning);
  }

  .tag {
    display: inline-block;
    max-width: 100%;
    border: 1px solid var(--divider);
    padding: 0.05rem 0.3rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.62rem;
  }

  .tag.positive {
    border-color: color-mix(in srgb, var(--positive) 55%, var(--divider));
  }

  .tag.negative {
    border-color: color-mix(in srgb, var(--negative) 55%, var(--divider));
  }

  .tag.warning {
    border-color: color-mix(in srgb, var(--warning) 55%, var(--divider));
  }

  .span-4 {
    grid-column: span 4;
  }

  .scatter-shell {
    position: relative;
    border: 1px solid var(--divider);
    background: var(--bg-0);
  }

  .scatter-shell svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .axis-line {
    stroke: var(--panel-strong);
    stroke-width: 0.5;
  }

  .grid-line {
    stroke: var(--divider);
    stroke-width: 0.35;
    opacity: 0.5;
  }

  .axis-label,
  .quadrant-label {
    fill: var(--text-2);
    font-size: 4.5px;
    letter-spacing: 0;
  }

  .axis-label {
    text-anchor: middle;
  }

  .vertical {
    transform: rotate(-90deg);
  }

  .scatter-point {
    cursor: pointer;
  }

  .scatter-point circle {
    fill: var(--chart-primary);
    transition: r 0.1s ease;
  }

  .scatter-point.metals circle {
    fill: var(--chart-secondary);
  }

  .scatter-point.hovered circle {
    stroke: var(--text-0);
    stroke-width: 0.6;
  }

  .scatter-point text {
    fill: var(--text-1);
    font-size: 4.6px;
    letter-spacing: 0;
    pointer-events: none;
  }

  .scatter-tooltip {
    position: absolute;
    pointer-events: none;
    z-index: 20;
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    padding: 0.5rem 0.65rem;
    font-size: 0.72rem;
    min-width: 11rem;
  }

  .scatter-tooltip strong {
    display: block;
    color: var(--text-0);
    font-weight: 650;
    margin-bottom: 0.3rem;
  }

  .tip-row {
    display: flex;
    justify-content: space-between;
    gap: 1.5rem;
    line-height: 1.55;
  }

  .tip-row span:first-child {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.64rem;
  }

  .tip-row span:last-child {
    color: var(--text-1);
  }

  .event-table {
    min-width: 100%;
    table-layout: fixed;
  }

  .event-table th:nth-child(1),
  .event-table td:nth-child(1) {
    width: 25%;
  }

  .event-table th:nth-child(2),
  .event-table td:nth-child(2) {
    width: 50%;
  }

  .event-table th:nth-child(3),
  .event-table td:nth-child(3) {
    width: 25%;
  }

  .event-table td {
    overflow-wrap: anywhere;
  }

  .rank-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
    border-top: 1px solid var(--divider);
    margin-top: 0.25rem;
  }

  .rank-block {
    min-width: 0;
    padding: 0.75rem 1rem 0.5rem 0.75rem;
    border-right: 1px solid var(--divider);
  }

  .rank-block:last-child {
    border-right: 0;
    padding-right: 0;
  }

  .rank-block:first-child {
    padding-left: 0;
  }

  .rank-block h3 {
    margin: 0 0 0.45rem;
    color: var(--text-2);
    font-size: 0.66rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .rank-list {
    display: grid;
    gap: 0.5rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .rank-list li {
    display: grid;
    grid-template-columns: minmax(2.5rem, 0.7fr) minmax(0, 2fr) minmax(3rem, auto);
    align-items: center;
    gap: 0.45rem;
    min-width: 0;
  }

  .rank-label,
  .rank-value {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8rem;
  }

  .rank-label {
    color: var(--text-1);
  }

  .rank-bar-shell {
    position: relative;
    height: 0.7rem;
    border-left: 1px solid var(--divider);
    background: var(--surface-soft);
    min-width: 0;
    overflow: hidden;
  }

  .rank-bar {
    display: block;
    height: 100%;
    background: var(--text-2);
    opacity: 0.75;
  }

  .rank-bar-shell.signed {
    border-left: 0;
  }

  .rank-bar-shell.signed::before {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    left: 50%;
    z-index: 1;
    border-left: 1px solid var(--divider);
  }

  .rank-bar.signed {
    position: absolute;
    top: 0;
    bottom: 0;
  }

  .rank-bar.positive-side {
    left: 50%;
  }

  .rank-bar.negative-side {
    right: 50%;
  }

  .rank-bar.positive {
    background: var(--positive);
    opacity: 0.8;
  }

  .rank-bar.negative {
    background: var(--negative);
    opacity: 0.8;
  }

  .inventory-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .deep-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .compact-table {
    min-width: 100%;
    table-layout: fixed;
  }

  .fundamental-table {
    min-width: 38rem;
  }

  .sparkline-cell {
    width: 7rem;
  }

  .sparkline,
  .inventory-sparkline {
    display: block;
    width: 100%;
    height: 2rem;
    border: 1px solid var(--divider);
    background: var(--bg-0);
  }

  .sparkline path,
  .inventory-sparkline path {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.6;
    vector-effect: non-scaling-stroke;
  }

  .sparkline-empty {
    margin: 0;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.68rem;
  }

  .heatmap-list,
  .seasonality-list,
  .ratio-gauge-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .heatmap-row,
  .seasonality-row,
  .ratio-gauge-row {
    display: grid;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    padding: 0.48rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .heatmap-row {
    grid-template-columns: 4.5rem minmax(0, 1fr) 4.5rem 6.5rem;
  }

  .seasonality-row,
  .ratio-gauge-row {
    grid-template-columns: minmax(0, 1.1fr) minmax(8rem, 1fr) minmax(8rem, auto);
  }

  .seasonality-row strong,
  .seasonality-row span,
  .ratio-gauge-row strong,
  .ratio-gauge-row span {
    display: block;
    overflow-wrap: anywhere;
  }

  .seasonality-row span,
  .ratio-gauge-row span {
    color: var(--text-2);
    font-size: 0.72rem;
  }

  .heatmap-track,
  .seasonality-band,
  .gauge-track {
    position: relative;
    height: 0.75rem;
    background: var(--surface-soft);
    border-left: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
    overflow: hidden;
  }

  .heatmap-track::before,
  .gauge-track::before {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    left: 50%;
    border-left: 1px solid var(--divider);
  }

  .heatmap-bar {
    display: block;
    height: 100%;
    opacity: 0.78;
  }

  .heatmap-bar.positive {
    background: var(--positive);
  }

  .heatmap-bar.negative {
    background: var(--negative);
  }

  .heatmap-bar.neutral {
    background: var(--text-2);
  }

  .seasonality-dot,
  .gauge-marker {
    position: absolute;
    top: -0.15rem;
    width: 2px;
    height: 1.05rem;
    background: var(--accent);
  }

  .seasonality-dot::after,
  .gauge-marker::after {
    content: "";
    position: absolute;
    top: 0.28rem;
    left: -0.2rem;
    width: 0.42rem;
    height: 0.42rem;
    border: 1px solid var(--accent);
    background: var(--bg-0);
  }

  .inventory-panel {
    display: grid;
    gap: 0.5rem;
    align-content: start;
  }

  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0;
    margin: 0;
    border-top: 1px solid var(--divider);
  }

  dt,
  dd {
    margin: 0;
  }

  dd {
    margin-top: 0.2rem;
    color: var(--text-0);
    overflow-wrap: anywhere;
  }

  dl > div {
    min-width: 0;
    padding: 0.45rem 0.5rem 0.45rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .note-list {
    display: grid;
    gap: 0;
  }

  .note-row {
    border-top: 1px solid var(--divider);
    padding: 0.55rem 0;
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .compact-notes .note-row {
    padding: 0.45rem 0;
  }

  .four-col-notes {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
  }

  .four-col-notes .note-row {
    border-top: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
    padding: 0.45rem 0.65rem 0.45rem 0;
  }

  .four-col-notes .note-row:nth-child(4n) {
    border-right: 0;
  }

  .four-col-notes .note-row:nth-child(-n+4) {
    border-top: 0;
  }

  .four-col-notes .note-row:nth-child(n+2) {
    padding-left: 0.65rem;
  }

  .four-col-notes .note-row:nth-child(4n+1) {
    padding-left: 0;
  }

  .note-row strong,
  .note-row span {
    display: block;
  }

  .note-row p {
    margin: 0.3rem 0 0;
    color: var(--text-1);
  }

  .empty-row td,
  .empty-hint {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
  }

  .empty-hint {
    margin: 0;
    padding: 0.45rem 0;
  }

  .provenance {
    display: grid;
    gap: 0.35rem;
  }

  .provenance-head {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    align-items: baseline;
  }

  .provenance ul {
    margin: 0.25rem 0 0;
    padding-left: 1.1rem;
    color: var(--text-2);
    line-height: 1.4;
  }

  .empty-state {
    min-height: 8rem;
    align-content: center;
  }

  @media (max-width: 1200px) {
    .headline-strip {
      display: none;
    }

    .coverage-strip,
    .kpi-strip {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .coverage-strip > div:nth-child(3n),
    .metric:nth-child(3n) {
      border-right: 0;
    }

    .overview-grid,
    .rank-grid,
    .inventory-grid,
    .deep-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .span-2 {
      grid-column: span 2;
    }

    .span-4 {
      grid-column: span 2;
    }

    .rank-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .four-col-notes {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 1100px) {
    .split {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  @media (max-width: 720px) {
    .header-top,
    .mode-kpi-row,
    .mode-context,
    .control-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      align-items: stretch;
    }

    .mode-bar {
      width: 100%;
    }

    .mode-bar button {
      border-right: 1px solid var(--panel-strong);
      border-bottom: 0;
      white-space: nowrap;
      text-align: center;
    }

    .mode-bar button:last-child {
      border-right: 0;
    }

    .coverage-strip,
    .kpi-strip {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .overview-grid,
    .rank-grid,
    .inventory-grid,
    .deep-grid,
    dl {
      grid-template-columns: minmax(0, 1fr);
    }

    .heatmap-row,
    .seasonality-row,
    .ratio-gauge-row {
      grid-template-columns: minmax(0, 1fr);
      align-items: stretch;
    }

    .span-2 {
      grid-column: span 1;
    }

    .span-4 {
      grid-column: span 1;
    }

    .four-col-notes {
      grid-template-columns: minmax(0, 1fr);
    }

    .coverage-strip > div,
    .coverage-strip > div:nth-child(3n),
    .metric,
    .inline-stats > div {
      border-right: 0;
    }

    .coverage-strip > div:nth-child(odd),
    .metric:nth-child(odd) {
      border-right: 1px solid var(--divider);
    }

    .coverage-strip > div.notice-cell {
      grid-column: 1 / -1;
      border-right: 0;
    }

    .coverage-strip > div,
    .metric {
      border-bottom: 1px solid var(--divider);
    }

    .coverage-strip > div:last-child,
    .metric:nth-last-child(-n + 2) {
      border-bottom: 0;
    }

    .inline-stats {
      grid-template-columns: minmax(0, 1fr);
    }

    .inline-stats > div {
      border-bottom: 1px solid var(--divider);
    }

    .inline-stats > div:last-child {
      border-bottom: 0;
    }

    .provenance-head {
      display: grid;
    }
  }
</style>
