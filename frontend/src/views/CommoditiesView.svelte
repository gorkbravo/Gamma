<script lang="ts">
  import { onMount } from "svelte";
  import CompactContextMenu from "../components/CompactContextMenu.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    CommodityCurveSnapshot,
    CommodityInventorySeries,
    CommodityMarketSummary,
    CommodityMode,
    CommodityOverviewRankingItem,
    CommodityPriceBasis,
    CommodityPriceHistory,
    CommoditySpreadSnapshot,
    MacroSeriesHistory,
    StrategyLabHandoffEnvelope,
    CommodityWorkspaceResponse
  } from "../lib/api/types";
  import type { CommodityWorkspaceLoadOptions } from "../lib/stores/app";
  import { buildCommodityStrategyHandoff } from "../lib/view-models/research";

  export let workspace: CommodityWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: CommodityMode = "overview";
  export let onLoadWorkspace: (options?: CommodityWorkspaceLoadOptions) => Promise<unknown> | void;
  export let macroHistories: Record<string, MacroSeriesHistory> = {};
  export let onLoadMacroSeries: (seriesId: string, options?: { region?: string; timeframe?: string; forceRefresh?: boolean }) => Promise<unknown> | void = () => undefined;
  export let onSendToStrategyLab:
    | ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void)
    | undefined = undefined;

  const modes: Array<{ id: CommodityMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "energy", label: "Energy" },
    { id: "metals", label: "Metals" },
    { id: "curves_spreads", label: "Curves & Spreads" },
    { id: "inventories_fundamentals", label: "Inventories & Fundamentals" },
    { id: "events_cross_domain", label: "Events / Cross-Domain" }
  ];

  let selectedInstrumentId = "wti";
  const scatterBounds = { left: 22, right: 342, top: 9, bottom: 92 };
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
  $: selectedReconciliation = findSelectedReconciliation(workspace, selectedInstrumentId);
  $: selectedBasis = selectedSummary?.quote_basis ?? selectedReconciliation?.headline ?? null;
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
  $: providerMixLabel = formatProviderMix(workspace);
  $: basisConflictRows = (workspace?.price_reconciliations ?? []).filter((row) => row.status === "conflict");
  $: termSpreadHeatmapRows = buildTermSpreadHeatmap(selectedCurve);
  $: crackMatrixRows = buildCrackMatrix(workspace?.spreads ?? []);
  $: inventoryCloudRows = buildInventoryCloudRows(visibleInventories);
  $: fundamentalGroups = buildFundamentalGroups(visibleInventories);
  $: fundamentalTapeRows = buildFundamentalTapeRows(visibleInventories);
  $: metalsCorrelationRows = buildMetalsCorrelationRows(workspace, macroHistories);
  $: metalRatioGaugeRows = buildMetalRatioGaugeRows(workspace?.spreads ?? []);
  $: substitutionSpreadRows = buildSubstitutionSpreadRows(workspace?.spreads ?? []);
  $: if (mode === "metals") {
    void ensureMacroDrivers();
  }

  let scatterShellEl: HTMLElement | null = null;
  let tooltipPoint: (typeof scatterState.points)[0] | null = null;
  let tooltipPos = { x: 0, y: 0 };
  let strategyContextMenu = {
    open: false,
    x: 0,
    y: 0,
    summary: null as CommodityMarketSummary | null
  };

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

  function sendSelectedCommodityToStrategyLab(open = false) {
    if (!selectedInstrument || !onSendToStrategyLab) {
      return;
    }
    const handoff = buildCommodityStrategyHandoff(
      {
        instrument: selectedInstrument,
        summary: selectedSummary,
        history: selectedHistory,
        curve: selectedCurve,
        workspace,
        sourceMode: mode
      },
      { sourceMode: mode }
    );
    onSendToStrategyLab(handoff, { open });
  }

  function sendCommodityRowToStrategyLab(summary: CommodityMarketSummary, open = false) {
    if (!onSendToStrategyLab) {
      return;
    }
    const instrumentId = summary.instrument.instrument_id;
    const handoff = buildCommodityStrategyHandoff(
      {
        instrument: summary.instrument,
        summary,
        history: findSelectedHistory(workspace, instrumentId),
        curve: findSelectedCurve(workspace, instrumentId),
        workspace,
        sourceMode: mode
      },
      { sourceMode: mode }
    );
    onSendToStrategyLab(handoff, { open });
  }

  function contextMenuPosition(event: MouseEvent | KeyboardEvent) {
    if (event instanceof MouseEvent && event.type === "contextmenu") {
      return { x: event.clientX, y: event.clientY };
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: rect.left + 12, y: rect.top + Math.min(rect.height, 32) };
  }

  function openCommodityStrategyMenu(event: MouseEvent | KeyboardEvent, summary: CommodityMarketSummary) {
    event.preventDefault();
    selectedInstrumentId = summary.instrument.instrument_id;
    const position = contextMenuPosition(event);
    strategyContextMenu = { open: true, x: position.x, y: position.y, summary };
  }

  function openCommodityOverviewStrategyMenu(
    event: MouseEvent | KeyboardEvent,
    row: { instrumentId: string; symbol: string }
  ) {
    const summary = findSelectedSummary(workspace, row.instrumentId);
    if (!summary) {
      return;
    }
    openCommodityStrategyMenu(event, summary);
  }

  function handleCommodityRowKeydown(event: KeyboardEvent, summary: CommodityMarketSummary) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      openCommodityStrategyMenu(event, summary);
    }
  }

  function handleCommodityOverviewRowKeydown(
    event: KeyboardEvent,
    row: { instrumentId: string; symbol: string }
  ) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      openCommodityOverviewStrategyMenu(event, row);
    }
  }

  function handleStrategyMenuSelect(action: string) {
    const summary = strategyContextMenu.summary;
    if (!summary) {
      return;
    }
    sendCommodityRowToStrategyLab(summary, action === "add-open");
  }

  function closeStrategyMenu() {
    strategyContextMenu = { ...strategyContextMenu, open: false };
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

  function findSelectedReconciliation(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.price_reconciliations ?? []).find((row) => row.instrument_id === instrumentId) ?? null;
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

  function priceHistoryEmptyMessage(history: CommodityPriceHistory | null) {
    return history?.warnings?.[0] ?? "CHART UNAVAILABLE";
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
              label: curve.previous_as_of ? `Previous curve (${formatDate(curve.previous_as_of)})` : "Previous curve",
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
      const median = bandValues.length ? medianOf(bandValues) : null;
      const q1 = bandValues.length ? quantileOf(bandValues, 0.25) : null;
      const q3 = bandValues.length ? quantileOf(bandValues, 0.75) : null;
      const latestValue = series.latest_value ?? latest?.value ?? null;
      const position = min != null && max != null && latestValue != null && max !== min
        ? ((latestValue - min) / (max - min)) * 100
        : null;
      const q1Pos = min != null && max != null && q1 != null && max !== min
        ? ((q1 - min) / (max - min)) * 100
        : null;
      const q3Pos = min != null && max != null && q3 != null && max !== min
        ? ((q3 - min) / (max - min)) * 100
        : null;
      const medianPos = min != null && max != null && median != null && max !== min
        ? ((median - min) / (max - min)) * 100
        : null;
      const pct = series.seasonal_percentile;
      const tone = pct == null
        ? "neutral"
        : pct >= 0.8
          ? "negative"
          : pct <= 0.2
            ? "positive"
            : "neutral";
      return {
        id: series.metadata.series_id,
        label: series.metadata.label,
        unit: series.metadata.unit,
        latest: latestValue,
        change: series.latest_change,
        min,
        max,
        median,
        q1Pos: q1Pos == null ? null : Math.max(0, Math.min(100, q1Pos)),
        q3Pos: q3Pos == null ? null : Math.max(0, Math.min(100, q3Pos)),
        medianPos: medianPos == null ? null : Math.max(0, Math.min(100, medianPos)),
        position: position == null ? null : Math.max(0, Math.min(100, position)),
        percentile: pct,
        tone,
        methodology: series.points.length >= 240 ? "5Y seasonal band" : "Loaded seasonal band",
        interpretation: series.interpretation ?? "N/A"
      };
    });
  }

  function medianOf(values: number[]) {
    return quantileOf(values, 0.5);
  }

  function quantileOf(values: number[], q: number) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  function buildFundamentalGroups(seriesRows: CommodityInventorySeries[]) {
    const buckets: Array<{ id: string; title: string; categories: string[]; color: string }> = [
      { id: "stocks", title: "Stocks", categories: ["inventories", "storage", "warehouse"], color: "var(--chart-primary)" },
      { id: "supply", title: "Supply", categories: ["production", "imports", "refinery"], color: "var(--positive)" },
      { id: "demand", title: "Demand", categories: ["demand", "exports"], color: "var(--warning)" }
    ];
    const colorPalette = ["var(--chart-primary)", "var(--chart-secondary)", "var(--positive)", "var(--warning)", "var(--negative)"];
    return buckets
      .map((bucket) => {
        const inBucket = seriesRows.filter((series) =>
          bucket.categories.includes(series.metadata.category ?? "")
        );
        const series: ChartSeries[] = inBucket
          .filter((s) => s.points.length >= 2)
          .slice(0, 4)
          .map((s, index) => {
            const first = s.points.find((point) => Number.isFinite(point.value) && point.value !== 0)?.value;
            const data = first
              ? s.points
                  .slice(-260)
                  .map((point) => ({
                    time: Math.floor(new Date(point.timestamp).getTime() / 1000),
                    value: (point.value / first) * 100
                  }))
                  .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
              : [];
            return {
              id: `${s.metadata.series_id}-indexed`,
              label: s.metadata.label,
              color: colorPalette[index % colorPalette.length],
              type: "line" as const,
              data
            };
          })
          .filter((s) => s.data.length >= 2);
        return {
          id: bucket.id,
          title: bucket.title,
          count: series.length,
          series
        };
      })
      .filter((group) => group.series.length > 0);
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

  function fundamentalStackTitle(activeMode: CommodityMode) {
    if (activeMode === "energy") return "EIA Fundamental Stack";
    if (activeMode === "metals") return "LME / COMEX Warehouse Stocks";
    return "Fundamental Stack";
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
        const min = values.length ? Math.min(...values) : null;
        const max = values.length ? Math.max(...values) : null;
        const median = values.length ? medianOf(values) : null;
        const q1 = values.length ? quantileOf(values, 0.25) : null;
        const q3 = values.length ? quantileOf(values, 0.75) : null;
        const current = spread.value;
        const distance = current != null && mean ? ((current - mean) / mean) * 100 : null;
        const positionFromRange = min != null && max != null && current != null && max !== min
          ? ((current - min) / (max - min)) * 100
          : null;
        const q1Pos = min != null && max != null && q1 != null && max !== min
          ? ((q1 - min) / (max - min)) * 100
          : null;
        const q3Pos = min != null && max != null && q3 != null && max !== min
          ? ((q3 - min) / (max - min)) * 100
          : null;
        const medianPos = min != null && max != null && median != null && max !== min
          ? ((median - min) / (max - min)) * 100
          : null;
        const pct = spread.percentile;
        const tone = pct == null
          ? "neutral"
          : pct >= 0.8 || pct <= 0.2
            ? "warning"
            : "neutral";
        return {
          id: spread.definition.spread_id,
          label: spread.definition.label,
          current,
          mean,
          distance,
          min,
          max,
          median,
          percentile: pct,
          position: positionFromRange == null
            ? null
            : Math.max(0, Math.min(100, positionFromRange)),
          q1Pos: q1Pos == null ? null : Math.max(0, Math.min(100, q1Pos)),
          q3Pos: q3Pos == null ? null : Math.max(0, Math.min(100, q3Pos)),
          medianPos: medianPos == null ? null : Math.max(0, Math.min(100, medianPos)),
          tone,
          methodology: values.length >= 2400 ? "10Y mean" : "Loaded-history mean"
        };
      });
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
    return value.toLocaleString("en-US", {
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
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  }

  function formatDateTime(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "N/A";
    }
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
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
      return instruments;
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
        quoteBasisLabel: compactBasisLabel(row.quote_basis),
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
        quoteBasisLabel: compactBasisLabel(summary.quote_basis),
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
    if (normalized.includes("unavailable") || normalized.includes("n/a") || !normalized) return "neutral";
    return "warning";
  }

  function compactBasisLabel(
    basis:
      | {
          display_label?: string | null;
          basis_type?: string | null;
          provider?: string | null;
        }
      | null
      | undefined
  ) {
    if (!basis) return "Basis N/A";
    const label = (basis.display_label ?? "").trim();
    if (label) return label;
    return `${providerLabel(basis.provider)} ${humanize(basis.basis_type ?? "basis")}`.trim();
  }

  function providerLabel(value: string | null | undefined) {
    const normalized = (value ?? "").trim().toLowerCase();
    if (normalized === "ibkr" || normalized === "ibkr_cached") return "IBKR";
    if (normalized === "fred") return "FRED";
    if (normalized === "eia") return "EIA";
    if (normalized === "sample_data") return "Sample";
    if (normalized === "gamma") return "Gamma";
    return (value ?? "").trim().toUpperCase() || "N/A";
  }

  function formatProviderMix(data: CommodityWorkspaceResponse | null) {
    if (!data) return "Provider N/A";
    const providers = new Set<string>();
    for (const reconciliation of data.price_reconciliations ?? []) {
      if (reconciliation.headline?.provider) providers.add(providerLabel(reconciliation.headline.provider));
      for (const observation of reconciliation.observations ?? []) {
        if (observation.provider) providers.add(providerLabel(observation.provider));
      }
    }
    if (!providers.size) {
      providers.add(providerLabel(data.coverage.source_provider || data.coverage.provider_id));
    }
    const ordered = [...providers].filter(Boolean).sort();
    return ordered.length <= 1 ? ordered[0] ?? "Provider N/A" : `Mixed: ${ordered.join(" + ")}`;
  }

  function basisTimeLabel(basis: CommodityPriceBasis | null | undefined) {
    return formatDateTime(basis?.source_timestamp ?? basis?.timestamp ?? basis?.retrieved_at ?? null);
  }

  function basisPriorTimeLabel(basis: CommodityPriceBasis | null | undefined) {
    return formatDateTime(basis?.previous_source_timestamp ?? null);
  }

</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Commodities</span>
      {#if workspace}
        <span class="subtitle">{workspace.coverage.provider_label} | {providerMixLabel} | as of {formatDate(workspace.coverage.as_of ?? workspace.retrieved_at)}</span>
      {/if}
      {#if loading}<span class="loading-pill">Refreshing</span>{/if}
      {#if workspace && selectedInstrument}
        <div class="handoff-actions" aria-label="Strategy Lab commodity handoff actions">
          <button
            type="button"
            class="ghost-action"
            on:click={() => sendSelectedCommodityToStrategyLab(false)}
            disabled={loading || !onSendToStrategyLab}
          >
            + Strategy
          </button>
          <button
            type="button"
            on:click={() => sendSelectedCommodityToStrategyLab(true)}
            disabled={loading || !onSendToStrategyLab}
          >
            Add & Open
          </button>
        </div>
      {/if}
      <button type="button" class="refresh-button" on:click={() => refresh(mode, true)} disabled={loading || !workspace}>
        {loading ? "LOADING..." : "Refresh"}
      </button>
    </div>

    {#if workspace && selectedBasis}
      <div class="basis-strip" aria-label="Selected commodity source and basis">
        <span><em>Headline</em> {compactBasisLabel(selectedBasis)}</span>
        <span><em>Provider</em> {providerLabel(selectedBasis.provider)}</span>
        {#if selectedBasis.contract_symbol}
          <span><em>Contract</em> {selectedBasis.contract_symbol}{selectedBasis.contract_month ? ` / ${selectedBasis.contract_month}` : ""}</span>
        {/if}
        <span><em>Time</em> {basisTimeLabel(selectedBasis)}</span>
        <span><em>Prior</em> {basisPriorTimeLabel(selectedBasis)}</span>
        {#if selectedReconciliation?.status === "conflict"}<strong>Basis conflict</strong>{/if}
      </div>
    {/if}

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
        <div class="header-kpis">
          <div class="header-kpi">
            <span>Markets</span>
            <strong>{workspace.market_summaries.length}</strong>
          </div>
          <div class="header-kpi">
            <span>Back/Cont</span>
            <strong>{curveBreadth.backwardation}/{curveBreadth.contango}</strong>
          </div>
          <div class="header-kpi">
            <span>Status</span>
            <strong class={coverageTone(workspace.coverage.coverage_status)}>
              {displayStatus(workspace.coverage.coverage_status)}
            </strong>
          </div>
          <div class="header-kpi">
            <span>Region</span>
            <strong>{workspace.coverage.regions[0] ?? "N/A"}</strong>
          </div>
        </div>
      {/if}
    </div>
  </article>

  {#if workspace}

    {#if mode === "overview"}
      <section class="overview-grid">
        <div class="overview-top">
        <article class="panel table-panel matrix-panel matrix-cell">
          <header class="panel-title">
            <span>Commodity Matrix</span>
            <span class="header-meta">{overviewRows.length} markets · click row to drill</span>
          </header>
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
                    <tr
                      tabindex="0"
                      aria-label={`Strategy actions for ${row.symbol}`}
                      class:selected={row.instrumentId === selectedInstrumentId}
                      on:click={() => selectInstrument(row.instrumentId)}
                      on:contextmenu={(event) => openCommodityOverviewStrategyMenu(event, row)}
                      on:keydown={(event) => handleCommodityOverviewRowKeydown(event, row)}
                    >
                      {#if row.showFamily}
                        <td class="sector-cell" rowspan={row.familyRowspan}>{humanize(row.family)}</td>
                      {/if}
                      <td>
                        <strong>{row.name}</strong>
                        <span>{row.symbol} | {row.quoteUnit} | {row.quoteBasisLabel}</span>
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

        <div class="left-stack">
        <article class="panel chart-panel term-cell">
          <header class="panel-title">
            <span>Term Structure Stack</span>
            <span class="header-meta">
              <select class="inline-select" bind:value={selectedInstrumentId} on:change={handleInstrumentChange} disabled={loading || !curveInstrumentOptions.length}>
                {#each curveInstrumentOptions as instrument}
                  <option value={instrument.instrument_id}>{instrument.name}</option>
                {/each}
              </select>
            </span>
          </header>
          <div class="inline-stats">
            <div>
              <span>Shape</span>
              <strong class={curveTone(selectedCurve?.shape_label ?? selectedSummary?.curve_state)}>{selectedCurve?.shape_label ?? "N/A"}</strong>
            </div>
            <div>
              <span>M1-M6</span>
              <strong class={valueClass(selectedCurve?.m1_m6_spread)}>{formatNumber(selectedCurve?.m1_m6_spread, 3)}</strong>
            </div>
            <div>
              <span>Roll</span>
              <strong class={valueClass(selectedCurve?.roll_yield_proxy_pct)}>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
            </div>
          </div>
          <TimeSeriesChart series={curveSeries} height={220} emptyMessage="NO CURVE NODES" showLegend={true} />
        </article>

        <article class="panel scatter-panel scatter-cell">
          <header class="panel-title">
            <span>Momentum / Roll Scatter</span>
          </header>
          {#if scatterState.points.length}
            <div class="scatter-shell" bind:this={scatterShellEl}
                 role="presentation"
                 on:mousemove={handleScatterMouseMove}
                 on:mouseleave={() => tooltipPoint = null}>
              <svg viewBox="0 0 360 110" preserveAspectRatio="none" role="img" aria-label="Commodity momentum versus roll yield scatter plot">
                {#each scatterGridFractions as fraction}
                  <line class="grid-line" x1={scatterGridX(fraction)} x2={scatterGridX(fraction)} y1={scatterBounds.top} y2={scatterBounds.bottom} />
                  <line class="grid-line" x1={scatterBounds.left} x2={scatterBounds.right} y1={scatterGridY(fraction)} y2={scatterGridY(fraction)} />
                {/each}
                <line class="axis-line" x1={scatterBounds.left} x2={scatterBounds.right} y1={scatterState.zeroY} y2={scatterState.zeroY} />
                <line class="axis-line" x1={scatterState.zeroX} x2={scatterState.zeroX} y1={scatterBounds.top} y2={scatterBounds.bottom} />
                <text class="quadrant-label" x="20" y="14">Carry / weak momentum</text>
                <text class="quadrant-label" x="340" y="14" text-anchor="end">Backwardation + momentum</text>
                <text class="quadrant-label" x="20" y="89">Contango / weak</text>
                <text class="quadrant-label" x="340" y="89" text-anchor="end">Momentum / carry drag</text>
                <text class="axis-label" x="180" y="107">{overview?.scatter?.x_methodology_label ?? "Loaded-history momentum"}</text>
                <text class="axis-label vertical" x="-55" y="6">{overview?.scatter?.y_methodology_label ?? "Roll proxy"}</text>
                {#each scatterState.points as point}
                  {@const hovered = tooltipPoint?.id === point.id}
                  <g class="scatter-point {point.family}"
                     role="img"
                     aria-label={`${point.name}: momentum ${formatNumber(point.x, 2)}%, roll proxy ${formatNumber(point.y, 2)}%`}
                     class:hovered
                     transform={`translate(${point.cx}, ${point.cy})`}
                     on:mouseenter={() => tooltipPoint = point}
                     on:mouseleave={() => tooltipPoint = null}>
                    <circle r={hovered ? 4.5 : 3} />
                    <text x="6" y="-5">{point.symbol}</text>
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
        </div>
        </div>

        <article class="panel table-panel rankers-panel span-4">
          <header class="panel-title">
            <span>Market Regime Ranks</span>
          </header>
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

        <article class="panel table-panel span-2">
          <header class="panel-title">
            <span>Event Tape</span>
            <span class="header-meta">{workspace.events.length} events</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table event-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Event</th>
                  <th class="num">Type</th>
                </tr>
              </thead>
              <tbody>
                {#if workspace.events.length}
                  {#each workspace.events.slice(0, 8) as event}
                    <tr>
                      <td class="mono">{formatDate(event.scheduled_at)}</td>
                      <td><strong>{event.title}</strong></td>
                      <td class="num"><span class="tag">{displayStatus(event.importance)}</span></td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="3">No event rows linked.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel table-panel span-2">
          <header class="panel-title">
            <span>Cross-Domain Links</span>
            <span class="header-meta">{workspace.cross_domain_links.length} links</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Domain</th>
                  <th class="num">Conf</th>
                </tr>
              </thead>
              <tbody>
                {#if workspace.cross_domain_links.length}
                  {#each workspace.cross_domain_links.slice(0, 8) as link}
                    <tr>
                      <td><strong>{link.target_label}</strong></td>
                      <td>{humanize(link.target_domain)}</td>
                      <td class="num">{formatNumber(link.confidence, 2)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="3">No cross-domain links.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {:else}
      <article class="panel controls-card">
        <div class="controls-bar">
          <label class="control"><span>Market</span>
            <select bind:value={selectedInstrumentId} on:change={handleInstrumentChange} disabled={loading || !modeInstrumentOptions.length}>
              {#each modeInstrumentOptions as instrument}
                <option value={instrument.instrument_id}>{instrument.name}</option>
              {/each}
            </select>
          </label>
          <div class="ctx-kpis">
            <div class="ctx-kpi">
              <span>Symbol</span>
              <strong>{selectedSummary?.instrument.symbol ?? selectedInstrumentId.toUpperCase()}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Last</span>
              <strong>{formatNumber(selectedSummary?.latest_price, 2)}</strong>
            </div>
            <div class="ctx-kpi wide">
              <span>Basis</span>
              <strong>{compactBasisLabel(selectedBasis)}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Chg</span>
              <strong class={valueClass(selectedSummary?.latest_change)}>{formatPct(selectedSummary?.latest_change_pct)}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Curve</span>
              <strong class={curveTone(selectedSummary?.curve_state)}>{selectedCurve?.shape_label ?? selectedSummary?.curve_state ?? "N/A"}</strong>
            </div>
            <div class="ctx-kpi">
              <span>M1-M2</span>
              <strong class={valueClass(selectedCurve?.front_spread)}>{formatNumber(selectedCurve?.front_spread, 3)}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Roll</span>
              <strong class={valueClass(selectedCurve?.roll_yield_proxy_pct)}>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Inv Pctl</span>
              <strong>{selectedInventory ? formatPercentile(selectedInventory.seasonal_percentile) : "N/A"}</strong>
            </div>
            <div class="ctx-kpi">
              <span>Unit</span>
              <strong>{selectedSummary?.instrument.quote_unit ?? "N/A"}</strong>
            </div>
          </div>
        </div>
      </article>
    {/if}

    {#if selectedReconciliation?.status === "conflict"}
      <article class="panel reconciliation-panel">
        <header class="panel-title">
          <span>Basis Reconciliation</span>
          <span class="header-meta">{selectedReconciliation.observations.length} quote references</span>
        </header>
        <div class="reconciliation-line">
          <strong>{selectedReconciliation.summary}</strong>
          <span>{selectedReconciliation.warnings[0]}</span>
        </div>
      </article>
    {:else if basisConflictRows.length && mode === "overview"}
      <article class="panel reconciliation-panel">
        <header class="panel-title">
          <span>Basis Reconciliation</span>
          <span class="header-meta">{basisConflictRows.length} conflicts</span>
        </header>
        <div class="reconciliation-list">
          {#each basisConflictRows.slice(0, 3) as row}
            <span>{row.warnings[0] ?? row.summary}</span>
          {/each}
        </div>
      </article>
    {/if}

    {#if mode === "energy" || mode === "metals"}
      <section class="split">
        <article class="panel chart-panel">
          <header class="panel-title">
            <span>{selectedInstrument?.name ?? "Price"} · Price History</span>
            <span class="header-meta">{historyPointCount ? `${historyPointCount} obs · ${formatDate(latestHistoryDate)}` : "—"}</span>
          </header>
          <TimeSeriesChart series={priceSeries} height={260} emptyMessage={priceHistoryEmptyMessage(selectedHistory)} />
          {#if !historyPointCount && selectedHistory?.warnings?.length}
            <p class="empty-hint">{selectedHistory.warnings[0]}</p>
          {/if}
        </article>

        <article class="panel table-panel snapshot-panel">
          <header class="panel-title">
            <span>{mode === "metals" ? "Metals Snapshot" : "Energy Snapshot"}</span>
            <span class="header-meta">{visibleSummaries.length} markets</span>
          </header>
          <div class="table-wrap snapshot-wrap">
            <table class="compact-table market-table">
              <thead>
                <tr>
                  <th>Market</th>
                  <th class="num">Last</th>
                  <th class="num">Chg</th>
                  <th>Curve</th>
                </tr>
              </thead>
              <tbody>
                {#if visibleSummaries.length}
                  {#each visibleSummaries as summary}
                    <tr
                      tabindex="0"
                      aria-label={`Strategy actions for ${summary.instrument.symbol}`}
                      class:selected={summary.instrument.instrument_id === selectedInstrumentId}
                      on:contextmenu={(event) => openCommodityStrategyMenu(event, summary)}
                      on:keydown={(event) => handleCommodityRowKeydown(event, summary)}
                    >
                      <td>
                        <button
                          class="market-button"
                          class:active-market={summary.instrument.instrument_id === selectedInstrumentId}
                          type="button"
                          on:click={() => selectInstrument(summary.instrument.instrument_id)}
                          disabled={loading}
                        >
                          <strong>{summary.instrument.symbol}</strong>
                          <span>{summary.instrument.name}</span>
                        </button>
                      </td>
                      <td class="num">{formatNumber(summary.latest_price, 2)}</td>
                      <td class="num {valueClass(summary.latest_change)}">{formatPct(summary.latest_change_pct)}</td>
                      <td><span class="tag {curveTone(summary.curve_state)}">{humanize(summary.curve_state)}</span></td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row">
                    <td colspan="4">No commodity summaries available.</td>
                  </tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    <!-- 1. Forward curve + curve nodes (top of curve-bearing modes) -->
    {#if mode === "energy" || mode === "metals" || mode === "curves_spreads"}
      <section class="split">
        <article class="panel chart-panel">
          <header class="panel-title">
            <span>{selectedInstrument?.symbol ?? "Curve"} · Forward Curve</span>
            <span class="header-meta">{selectedCurve?.shape_label ?? "N/A"}</span>
          </header>
          <div class="inline-stats">
            <div>
              <span>M1-M6</span>
              <strong class={valueClass(selectedCurve?.m1_m6_spread)}>{formatNumber(selectedCurve?.m1_m6_spread, 3)}</strong>
            </div>
            <div>
              <span>Slope</span>
              <strong class={valueClass(selectedCurve?.curve_slope)}>{formatNumber(selectedCurve?.curve_slope, 3)}</strong>
            </div>
            <div>
              <span>Roll</span>
              <strong class={valueClass(selectedCurve?.roll_yield_proxy_pct)}>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
            </div>
          </div>
          <TimeSeriesChart series={curveSeries} height={260} emptyMessage="NO CURVE NODES" showLegend={true} />
        </article>

        <article class="panel table-panel curve-nodes-panel">
          <header class="panel-title">
            <span>Curve Nodes</span>
            <span class="header-meta">{selectedCurve?.nodes.length ?? 0} contracts</span>
          </header>
          <div class="table-wrap curve-nodes-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Month</th>
                  <th class="num">DTE</th>
                  <th class="num">Price</th>
                  <th class="num">Chg</th>
                </tr>
              </thead>
              <tbody>
                {#if selectedCurve?.nodes.length}
                  {#each selectedCurve.nodes as node}
                    <tr>
                      <td><strong>{node.contract.symbol}</strong></td>
                      <td>{node.contract.contract_month}</td>
                      <td class="num">{node.days_to_expiry == null ? "N/A" : `${node.days_to_expiry}d`}</td>
                      <td class="num">{formatNumber(node.price, 3)}</td>
                      <td class="num {valueClass(node.change)}">{formatNumber(node.change, 3)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="5">No curve nodes.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    <!-- 2. Energy curve-support: Crack Spread Matrix + Term Structure Heatmap -->
    {#if mode === "energy"}
      <section class="curve-support-grid">
        <article class="panel table-panel">
          <header class="panel-title">
            <span>Crack Spread Matrix</span>
            <span class="header-meta">{crackMatrixRows.length} rows</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Spread</th>
                  <th class="num">Value</th>
                  <th class="num">Chg</th>
                  <th class="num">Pctl</th>
                </tr>
              </thead>
              <tbody>
                {#if crackMatrixRows.length}
                  {#each crackMatrixRows as row}
                    <tr>
                      <td><strong>{row.label}</strong><span class="meta">{row.formula}</span></td>
                      <td class="num">{formatNumber(row.value, 2)}</td>
                      <td class="num {row.tone}">{formatNumber(row.change, 2)}</td>
                      <td class="num">{formatPercentile(row.percentile)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No crack-spread rows.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel rows-panel">
          <header class="panel-title">
            <span>Term Structure Heatmap</span>
            <span class="header-meta">{termSpreadHeatmapRows.length} legs</span>
          </header>
          {#if termSpreadHeatmapRows.length}
            <div class="heatmap-list">
              {#each termSpreadHeatmapRows as row}
                <div class="heatmap-row">
                  <span class="row-label">{row.label}</span>
                  <div class="heatmap-track">
                    <span class="heatmap-bar {row.tone}" style={`width:${row.width}%`}></span>
                  </div>
                  <strong class="num {row.tone}">{formatNumber(row.value, 3)}</strong>
                </div>
              {/each}
            </div>
          {:else}
            <div class="empty-state-inline">No adjacent curve nodes.</div>
          {/if}
        </article>
      </section>

      <section class="panel table-panel">
        <header class="panel-title">
          <span>Vessel / Flow Proxy</span>
          <span class="header-meta">{selectedCrossDomainLinks.length} links</span>
        </header>
        <div class="table-wrap">
          <table class="compact-table">
            <thead>
              <tr>
                <th>Target</th>
                <th>Domain</th>
                <th>Relationship</th>
                <th class="num">Conf</th>
              </tr>
            </thead>
            <tbody>
              {#if selectedCrossDomainLinks.length}
                {#each selectedCrossDomainLinks as link}
                  <tr>
                    <td><strong>{link.target_label}</strong></td>
                    <td>{humanize(link.target_domain)}</td>
                    <td>{humanize(link.relationship)}</td>
                    <td class="num">{formatNumber(link.confidence, 2)}</td>
                  </tr>
                {/each}
              {:else}
                <tr class="empty-row"><td colspan="4">No vessel-flow proxy linked.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    <!-- 2b. Metals curve-support: Substitution Spreads + Term Structure Heatmap -->
    {#if mode === "metals"}
      <section class="curve-support-grid">
        <article class="panel table-panel">
          <header class="panel-title">
            <span>Substitution Spreads</span>
            <span class="header-meta">{substitutionSpreadRows.length} rows</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Spread</th>
                  <th class="num">Value</th>
                  <th class="num">Chg</th>
                  <th class="num">Z</th>
                  <th class="num">Pctl</th>
                </tr>
              </thead>
              <tbody>
                {#if substitutionSpreadRows.length}
                  {#each substitutionSpreadRows as row}
                    <tr>
                      <td><strong>{row.label}</strong></td>
                      <td class="num">{formatNumber(row.value, 1)}</td>
                      <td class="num {valueClass(row.change)}">{formatNumber(row.change, 1)}</td>
                      <td class="num {valueClass(row.zScore)}">{formatNumber(row.zScore, 2)}</td>
                      <td class="num">{formatPercentile(row.percentile)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="5">No substitution spreads.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel rows-panel">
          <header class="panel-title">
            <span>Term Structure Heatmap</span>
            <span class="header-meta">{termSpreadHeatmapRows.length} legs</span>
          </header>
          {#if termSpreadHeatmapRows.length}
            <div class="heatmap-list">
              {#each termSpreadHeatmapRows as row}
                <div class="heatmap-row">
                  <span class="row-label">{row.label}</span>
                  <div class="heatmap-track">
                    <span class="heatmap-bar {row.tone}" style={`width:${row.width}%`}></span>
                  </div>
                  <strong class="num {row.tone}">{formatNumber(row.value, 3)}</strong>
                </div>
              {/each}
            </div>
          {:else}
            <div class="empty-state-inline">No adjacent curve nodes.</div>
          {/if}
        </article>
      </section>
    {/if}

    <!-- Standalone curves-spreads term structure heatmap (kept for curves_spreads mode) -->
    {#if mode === "curves_spreads"}
      <section class="panel rows-panel">
        <header class="panel-title"><span>Term Structure Heatmap</span></header>
        {#if termSpreadHeatmapRows.length}
          <div class="heatmap-list">
            {#each termSpreadHeatmapRows as row}
              <div class="heatmap-row">
                <span class="row-label">{row.label}</span>
                <div class="heatmap-track">
                  <span class="heatmap-bar {row.tone}" style={`width:${row.width}%`}></span>
                </div>
                <strong class="num {row.tone}">{formatNumber(row.value, 3)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <div class="empty-state-inline">No adjacent curve nodes.</div>
        {/if}
      </section>
    {/if}

    <!-- 3. Spreads table -->
    {#if mode === "curves_spreads" || mode === "metals" || mode === "energy"}
      <section class="panel table-panel">
        <header class="panel-title">
          <span>Spreads</span>
          <span class="header-meta">{selectedSpreads.length} linked</span>
        </header>
        <div class="table-wrap">
          <table class="compact-table spread-table">
            <thead>
              <tr>
                <th>Spread</th>
                <th class="num">Value</th>
                <th class="num">Chg</th>
                <th class="num">Z</th>
                <th class="num">Pctl</th>
              </tr>
            </thead>
            <tbody>
              {#if selectedSpreads.length}
                {#each selectedSpreads as spread}
                  <tr>
                    <td><strong>{spread.definition.label}</strong><span class="meta">{spread.definition.formula}</span></td>
                    <td class="num">{formatNumber(spread.value, 3)} {spreadUnit(spread)}</td>
                    <td class="num {valueClass(spread.change)}">{formatNumber(spread.change, 3)}</td>
                    <td class="num {valueClass(spread.z_score)}">{formatNumber(spread.z_score, 2)}</td>
                    <td class="num">{formatPercentile(spread.percentile)}</td>
                  </tr>
                {/each}
              {:else}
                <tr class="empty-row"><td colspan="5">No spread rows linked.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    <!-- 4. Metals macro context (parallel to where Energy's fundamentals charts go) -->
    {#if mode === "metals"}
      <section class="curve-support-grid">
        <article class="panel table-panel">
          <header class="panel-title">
            <span>Macro Driver Correlation</span>
            <span class="header-meta">{metalsCorrelationRows.length} pairs</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Metal</th>
                  <th>Driver</th>
                  <th class="num">30D Corr</th>
                </tr>
              </thead>
              <tbody>
                {#if metalsCorrelationRows.length}
                  {#each metalsCorrelationRows as row}
                    <tr>
                      <td><strong>{row.metal}</strong></td>
                      <td>{row.driver}</td>
                      <td class="num"><span class="tag {row.tone}">{formatNumber(row.value, 2)}</span></td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="3">No gold/copper macro histories.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel rows-panel">
          <header class="panel-title">
            <span>Precious Ratio Gauges</span>
            <span class="header-meta">{metalRatioGaugeRows.length} · loaded-history band</span>
          </header>
          <div class="seasonality-list">
            {#if metalRatioGaugeRows.length}
              {#each metalRatioGaugeRows as row}
                <div class="seasonality-row">
                  <span class="row-label" title={row.label}>{row.label}</span>
                  <span class="num meta range-min">{formatNumber(row.min, 2)}</span>
                  <div class="seasonality-band">
                    <span class="band-whisker"></span>
                    {#if row.q1Pos != null && row.q3Pos != null}
                      <span class="band-box" style={`left:${row.q1Pos}%;width:${Math.max(0.5, row.q3Pos - row.q1Pos)}%`}></span>
                    {/if}
                    {#if row.medianPos != null}
                      <span class="band-median" style={`left:${row.medianPos}%`}></span>
                    {/if}
                    {#if row.position != null}
                      <span class="band-marker {row.tone}" style={`left:${row.position}%`}></span>
                    {/if}
                  </div>
                  <span class="num meta range-max">{formatNumber(row.max, 2)}</span>
                  <strong class="num {row.tone}">{formatNumber(row.current, 2)}x</strong>
                  <span class="num meta pctl-cell">{formatPercentile(row.percentile)}</span>
                </div>
              {/each}
            {:else}
              <div class="empty-state-inline">No precious-metal ratios.</div>
            {/if}
          </div>
        </article>
      </section>
    {/if}

    <!-- 5. Fundamentals charts (split by category group) -->
    {#if mode === "energy" || mode === "metals" || mode === "inventories_fundamentals"}
      <section class="fundamental-grid">
        <article class="panel table-panel">
          <header class="panel-title">
            <span>{fundamentalStackTitle(mode)}</span>
            <span class="header-meta">{fundamentalTapeRows.length} series</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Series</th>
                  <th>Type</th>
                  <th class="num">Latest</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {#if fundamentalTapeRows.length}
                  {#each fundamentalTapeRows as row}
                    <tr>
                      <td><strong>{row.label}</strong></td>
                      <td>{row.category}</td>
                      <td class="num">{formatNumber(row.latest, 2)} {row.unit}</td>
                      <td>{row.signal}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No fundamental series linked.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        {#each fundamentalGroups as group}
          <article class="panel chart-panel">
            <header class="panel-title">
              <span>{group.title}</span>
              <span class="header-meta">{group.count} · idx 100</span>
            </header>
            <TimeSeriesChart series={group.series} height={180} emptyMessage="NO HISTORY" showLegend={true} />
          </article>
        {/each}
      </section>
    {/if}

    <!-- 6. Fundamental Tape (full width, room to breathe) -->
    {#if mode === "energy" || mode === "metals" || mode === "inventories_fundamentals"}
      <section class="panel table-panel">
        <header class="panel-title">
          <span>Fundamental Tape</span>
          <span class="header-meta">{fundamentalTapeRows.length} series</span>
        </header>
        <div class="table-wrap">
          <table class="compact-table fundamental-table wide">
            <thead>
              <tr>
                <th>Series</th>
                <th>Type</th>
                <th class="num">Latest</th>
                <th class="num">Chg</th>
                <th class="num">Pctl</th>
                <th class="num">Path</th>
              </tr>
            </thead>
            <tbody>
              {#if fundamentalTapeRows.length}
                {#each fundamentalTapeRows as row}
                  <tr>
                    <td><strong>{row.label}</strong><span class="meta">{row.source}</span></td>
                    <td>{row.category}</td>
                    <td class="num">{formatNumber(row.latest, 2)} {row.unit}</td>
                    <td class="num {row.tone}">{formatNumber(row.change, 2)}</td>
                    <td class="num">{formatPercentile(row.percentile)}</td>
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
              {:else}
                <tr class="empty-row"><td colspan="6">No fundamental tape rows.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    <!-- 7. Inventory vs Seasonality (energy only, box-plot redesign) -->
    {#if mode === "energy" || mode === "metals"}
      <section class="panel rows-panel">
        <header class="panel-title">
          <span>Inventory vs Seasonality</span>
          <span class="header-meta">5Y · same week-of-year band</span>
        </header>
        <div class="seasonality-list">
          {#if inventoryCloudRows.length}
            {#each inventoryCloudRows as row}
              <div class="seasonality-row">
                <span class="row-label" title={row.label}>{row.label}</span>
                <span class="num meta range-min">{formatNumber(row.min, 1)}</span>
                <div class="seasonality-band">
                  <span class="band-whisker"></span>
                  {#if row.q1Pos != null && row.q3Pos != null}
                    <span class="band-box" style={`left:${row.q1Pos}%;width:${Math.max(0.5, row.q3Pos - row.q1Pos)}%`}></span>
                  {/if}
                  {#if row.medianPos != null}
                    <span class="band-median" style={`left:${row.medianPos}%`}></span>
                  {/if}
                  {#if row.position != null}
                    <span class="band-marker {row.tone}" style={`left:${row.position}%`}></span>
                  {/if}
                </div>
                <span class="num meta range-max">{formatNumber(row.max, 1)}</span>
                <strong class="num {row.tone}">{formatNumber(row.latest, 1)}</strong>
                <span class="num meta pctl-cell">{formatPercentile(row.percentile)}</span>
              </div>
            {/each}
          {:else}
            <div class="empty-state-inline">No inventory seasonality history.</div>
          {/if}
        </div>
      </section>
    {/if}

    {#if mode === "energy" || mode === "metals" || mode === "inventories_fundamentals"}
      <section class="panel table-panel">
        <header class="panel-title">
          <span>Inventory Series</span>
          <span class="header-meta">{visibleInventories.length} series</span>
        </header>
        <div class="table-wrap">
          <table class="compact-table inventory-table">
            <thead>
              <tr>
                <th>Series</th>
                <th>Frequency</th>
                <th class="num">Latest</th>
                <th class="num">Chg</th>
                <th class="num">Pctl</th>
                <th class="num">Path</th>
              </tr>
            </thead>
            <tbody>
              {#if visibleInventories.length}
                {#each visibleInventories as series}
                  <tr>
                    <td><strong>{series.metadata.label}</strong><span class="meta">{series.metadata.source_provider}</span></td>
                    <td>{series.metadata.frequency}</td>
                    <td class="num">{formatNumber(series.latest_value, 2)} {series.metadata.unit}</td>
                    <td class="num {valueClass(series.latest_change)}">{formatNumber(series.latest_change, 2)}</td>
                    <td class="num">{formatPercentile(series.seasonal_percentile)}</td>
                    <td class="sparkline-cell">
                      {#if sparklinePath(series.points, 96, 28)}
                        <svg class="sparkline" viewBox="0 0 96 28" aria-label={`${series.metadata.label} recent history`}>
                          <path d={sparklinePath(series.points, 96, 28)}></path>
                        </svg>
                      {:else}
                        <span class="sparkline-empty">N/A</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              {:else}
                <tr class="empty-row"><td colspan="6">No inventory series linked.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    {#if mode === "events_cross_domain"}
      <section class="split">
        <article class="panel table-panel">
          <header class="panel-title">
            <span>Linked Events</span>
            <span class="header-meta">{eventRows.length} events</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Event</th>
                  <th>Category</th>
                  <th class="num">Importance</th>
                </tr>
              </thead>
              <tbody>
                {#if eventRows.length}
                  {#each eventRows as event}
                    <tr>
                      <td class="mono">{formatDate(event.scheduled_at)}</td>
                      <td><strong>{event.title}</strong><span class="meta">{event.relative_label ?? ""}</span></td>
                      <td>{humanize(event.category)}</td>
                      <td class="num"><span class="tag">{displayStatus(event.importance)}</span></td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No event rows linked.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel table-panel">
          <header class="panel-title">
            <span>Cross-Domain Links</span>
            <span class="header-meta">{selectedCrossDomainLinks.length} links</span>
          </header>
          <div class="table-wrap">
            <table class="compact-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Domain</th>
                  <th>Relationship</th>
                  <th class="num">Conf</th>
                </tr>
              </thead>
              <tbody>
                {#if selectedCrossDomainLinks.length}
                  {#each selectedCrossDomainLinks as link}
                    <tr>
                      <td><strong>{link.target_label}</strong></td>
                      <td>{humanize(link.target_domain)}</td>
                      <td>{humanize(link.relationship)}</td>
                      <td class="num">{formatNumber(link.confidence, 2)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr class="empty-row"><td colspan="4">No cross-domain links.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    <footer class="panel provenance">
      <span class="prov-label">Source</span>
      <span>{workspace.source_provider} · {workspace.origin}</span>
      <span class="prov-sep">|</span>
      <span class="meta">{workspace.transformation_note}</span>
      {#if workspace.coverage.caveats.length}
        <span class="prov-sep">|</span>
        <span class="prov-label">Caveats</span>
        <span class="meta">{workspace.coverage.caveats.slice(0, 3).join(" · ")}</span>
      {/if}
    </footer>
  {:else}
    <article class="panel empty-state">
      <h2>{loading ? "LOADING COMMODITIES" : "Commodities unavailable"}</h2>
      <p>{loading ? "Gamma is preparing the commodities workspace." : "No commodities payload is loaded yet."}</p>
    </article>
  {/if}

  <CompactContextMenu
    open={strategyContextMenu.open}
    x={strategyContextMenu.x}
    y={strategyContextMenu.y}
    label="Commodity Strategy Lab actions"
    items={[
      { id: "add", label: "Add to Strategy", disabled: !onSendToStrategyLab },
      { id: "add-open", label: "Add and Open", disabled: !onSendToStrategyLab }
    ]}
    onSelect={handleStrategyMenuSelect}
    onClose={closeStrategyMenu}
  />
</section>

<style>
  .view {
    display: grid;
    gap: var(--space-4);
    padding-bottom: var(--space-5);
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
    min-width: 0;
  }

  /* ── Header panel ── */
  .header-panel {
    display: grid;
    gap: var(--space-4);
    padding: var(--space-4) var(--space-5);
  }

  .header-top {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
  }

  .title {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .subtitle {
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .loading-pill {
    color: var(--accent);
    border: 1px solid var(--panel-strong);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .basis-strip {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4) var(--space-5);
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: 1.25;
  }

  .basis-strip em {
    color: var(--text-2);
    font-style: normal;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-right: var(--space-2);
  }

  .basis-strip strong {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .handoff-actions {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    flex: 0 0 auto;
  }

  .handoff-actions button {
    min-height: 25px;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .handoff-actions .ghost-action {
    background: transparent;
  }

  .refresh-button {
    flex: 0 0 auto;
    min-height: 25px;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-xs);
  }

  .mode-kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    flex-wrap: wrap;
  }

  /* ── Mode bar (Risk pattern) ── */
  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(6, auto);
    border: 1px solid var(--panel-strong);
    width: fit-content;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-2) var(--space-5);
    font: inherit;
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover:not(:disabled) { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }
  .mode-bar button:disabled { opacity: 0.45; cursor: not-allowed; }

  /* ── Header KPIs (Risk pattern) ── */
  .header-kpis {
    display: flex;
    gap: 0;
    flex-wrap: wrap;
    border-left: 1px solid var(--divider);
  }

  .header-kpi {
    display: grid;
    gap: 0.05rem;
    padding: var(--space-1) var(--space-5);
    border-right: 1px solid var(--divider);
    min-width: 5rem;
  }

  .header-kpi span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    line-height: 1.1;
  }

  .header-kpi strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
    line-height: 1.15;
    white-space: nowrap;
  }

  .header-kpi strong.warning { color: var(--warning); }
  .header-kpi strong.positive { color: var(--positive); }
  .header-kpi strong.negative { color: var(--negative); }

  /* ── Controls card (non-overview) ── */
  .controls-card { padding: var(--space-4) var(--space-5); }

  .controls-bar {
    display: flex;
    gap: var(--space-4);
    align-items: stretch;
    flex-wrap: wrap;
  }

  .control {
    display: grid;
    gap: var(--space-1);
    min-width: 8rem;
  }

  .control > span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    line-height: 1.1;
  }

  .ctx-kpis {
    display: flex;
    gap: 0;
    margin-left: auto;
    border-left: 1px solid var(--divider);
    flex-wrap: wrap;
  }

  .ctx-kpi {
    display: grid;
    gap: 0.05rem;
    padding: var(--space-1) var(--space-5);
    border-right: 1px solid var(--divider);
    min-width: 4.5rem;
  }

  .ctx-kpi.wide {
    min-width: 11rem;
  }

  .ctx-kpi span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    line-height: 1.1;
  }

  .ctx-kpi strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
    line-height: 1.15;
    white-space: nowrap;
  }

  .ctx-kpi.wide strong {
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 13rem;
  }

  .ctx-kpi strong.positive { color: var(--positive); }
  .ctx-kpi strong.negative { color: var(--negative); }
  .ctx-kpi strong.warning { color: var(--warning); }

  /* ── Form controls (default) ── */
  select {
    height: 28px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0 var(--space-4);
    font: inherit;
    font-size: var(--text-sm);
  }

  select:hover:not(:disabled) { border-color: var(--accent); }
  select:disabled { color: var(--text-2); cursor: default; }

  button {
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    cursor: pointer;
  }

  button:hover:not(:disabled) { border-color: var(--accent); }
  button:disabled { cursor: default; color: var(--text-2); }

  .inline-select {
    height: 22px;
    padding: 0 var(--space-3);
    border-color: var(--divider);
    background: transparent;
    font-size: var(--text-xs);
    color: var(--text-1);
  }

  /* ── Panel title (single 26px header, Risk pattern) ── */
  .panel-title {
    min-height: 26px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    color: var(--text-1);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-xs);
    font-weight: 600;
  }

  .panel-title .header-meta {
    color: var(--text-2);
    font-weight: 400;
    font-size: var(--text-2xs);
    text-transform: none;
    letter-spacing: 0;
  }

  /* Edge-to-edge panels */
  .table-panel,
  .chart-panel,
  .rows-panel,
  .scatter-panel { padding: 0; }

  .chart-panel { display: flex; flex-direction: column; gap: 0; }

  /* ── Layout grids ── */
  .overview-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .span-2 { grid-column: span 2; }
  .span-4 { grid-column: span 4; }

  /* Overview top block: term structure + scatter stacked left, matrix right */
  .overview-top {
    grid-column: 1 / span 4;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    min-height: 0;
  }
  .overview-top .left-stack {
    grid-column: 1;
    grid-row: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-height: 0;
  }
  .overview-top .left-stack > .term-cell,
  .overview-top .left-stack > .scatter-cell {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .overview-top .matrix-cell {
    grid-column: 2;
    grid-row: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .overview-top .matrix-cell .table-wrap {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
  }
  .overview-top .term-cell :global(.chart-shell) {
    flex: 1 1 auto;
    height: auto !important;
    min-height: 0;
  }
  .overview-top .scatter-cell .scatter-shell {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
  }
  .overview-top .scatter-cell .scatter-shell svg {
    width: 100%;
    height: 100%;
  }

  .split {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(20rem, 0.6fr);
    gap: var(--space-4);
  }

  .deep-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* Energy curve-support grid: Crack Spread Matrix + Term Structure Heatmap */
  .curve-support-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
  }

  /* Fundamentals charts grid: one chart per category bucket (stocks / supply / demand) */
  .fundamental-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* ── Inline stats strip (under chart panel headers) ── */
  .inline-stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0;
    border-bottom: 1px solid var(--divider);
  }

  .inline-stats > div {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    min-width: 0;
    padding: var(--space-3) var(--space-5);
    border-right: 1px solid var(--divider);
  }

  .inline-stats > div:last-child { border-right: 0; }

  .inline-stats span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .inline-stats strong {
    color: var(--text-0);
    font-weight: 600;
    font-size: var(--text-sm);
    line-height: 1.15;
  }

  /* ── Tables ── */
  .table-panel { overflow: hidden; }
  .table-wrap { overflow: auto; max-width: 100%; }

  /* Curve Nodes scrolls so the paired Forward Curve chart sets the row height */
  .curve-nodes-panel { display: flex; flex-direction: column; min-height: 0; }
  .curve-nodes-wrap {
    flex: 1 1 auto;
    min-height: 0;
    max-height: 18.25rem;
    overflow-y: auto;
  }

  /* Snapshot table scrolls so the paired Price History chart sets the row height */
  .snapshot-panel { display: flex; flex-direction: column; min-height: 0; }
  .snapshot-wrap {
    flex: 1 1 auto;
    min-height: 0;
    max-height: 16.25rem;
    overflow-y: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  .compact-table { min-width: 100%; }
  .matrix-table { min-width: 42rem; table-layout: fixed; }
  .market-table { table-layout: fixed; }
  .spread-table { min-width: 36rem; }
  .fundamental-table { min-width: 36rem; }
  .inventory-table { min-width: 38rem; }
  .event-table { min-width: 100%; }

  th, td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: middle;
    line-height: 1.3;
    font-size: var(--text-sm);
    color: var(--text-1);
  }

  th {
    color: var(--text-2);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  td.mono { font-variant-numeric: tabular-nums; color: var(--text-2); white-space: nowrap; }

  td strong { color: var(--text-0); font-weight: 600; }
  td .meta { display: block; color: var(--text-2); font-size: var(--text-2xs); line-height: 1.25; margin-top: 1px; }

  tbody tr:hover { background: rgba(122, 166, 200, 0.06); }
  tr.selected { background: rgba(122, 166, 200, 0.12); }

  .empty-row td { color: var(--text-2); text-align: center; padding: var(--space-5); text-transform: none; letter-spacing: 0; font-size: var(--text-xs); }

  /* Matrix-specific column hints */
  .matrix-table .sector-col { width: 9%; }
  .matrix-table .market-col { width: 24%; }
  .matrix-table .last-col { width: 10%; }
  .matrix-table .change-col { width: 9%; }
  .matrix-table .curve-col { width: 17%; }
  .matrix-table .basis-col { width: 11%; }
  .matrix-table .inventory-col { width: 14%; }
  .sector-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
    font-weight: 600;
    border-right: 1px solid var(--divider);
    background: rgba(122, 166, 200, 0.03);
  }

  /* Market button (used inside snapshot table) */
  .market-button {
    display: grid;
    gap: 0;
    width: 100%;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .market-button strong { color: var(--text-0); font-size: var(--text-sm); }
  .market-button span { color: var(--text-2); font-size: var(--text-2xs); line-height: 1.2; }
  .market-button.active-market strong,
  .market-button:not(:disabled):hover strong { color: var(--accent); }

  /* ── Semantic colors ── */
  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  .warning { color: var(--warning); }

  /* ── Tag chip ── */
  .tag {
    display: inline-block;
    max-width: 100%;
    border: 1px solid var(--divider);
    padding: 0.04rem var(--space-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
    color: var(--text-1);
  }

  .tag.positive { border-color: color-mix(in srgb, var(--positive) 55%, var(--divider)); color: var(--positive); }
  .tag.negative { border-color: color-mix(in srgb, var(--negative) 55%, var(--divider)); color: var(--negative); }
  .tag.warning { border-color: color-mix(in srgb, var(--warning) 55%, var(--divider)); color: var(--warning); }
  .tag.neutral { border-color: var(--divider); color: var(--text-2); background: rgba(122, 166, 200, 0.05); }

  .reconciliation-panel {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
  }

  .reconciliation-line,
  .reconciliation-list {
    display: grid;
    gap: var(--space-2);
    color: var(--text-1);
    font-size: var(--text-xs);
  }

  .reconciliation-line strong {
    color: var(--warning);
    font-size: var(--text-xs);
  }

  .reconciliation-line span,
  .reconciliation-list span {
    color: var(--text-2);
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
    font-size: var(--text-2xs);
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
    font-size: var(--text-2xs);
    letter-spacing: 0;
    pointer-events: none;
  }

  .scatter-tooltip {
    position: absolute;
    pointer-events: none;
    z-index: 20;
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    padding: var(--space-4) var(--space-5);
    font-size: var(--text-sm);
    min-width: 11rem;
  }

  .scatter-tooltip strong {
    display: block;
    color: var(--text-0);
    font-weight: 650;
    margin-bottom: var(--space-2);
  }

  .tip-row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-7);
    line-height: 1.55;
  }

  .tip-row span:first-child {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  .tip-row span:last-child {
    color: var(--text-1);
  }

  /* ── Rank panel grid ── */
  .rank-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0;
  }

  .rank-block {
    min-width: 0;
    padding: var(--space-4) var(--space-5);
    border-right: 1px solid var(--divider);
  }

  .rank-block:last-child { border-right: 0; }

  .rank-block h3 {
    margin: 0 0 var(--space-3);
    color: var(--text-2);
    font-size: var(--text-2xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .rank-list {
    display: grid;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .rank-list li {
    display: grid;
    grid-template-columns: minmax(2.5rem, 0.7fr) minmax(0, 2fr) minmax(2.8rem, auto);
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
  }

  .rank-label,
  .rank-value {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }

  .rank-label { color: var(--text-1); }
  .rank-value { color: var(--text-0); text-align: right; }

  .rank-bar-shell {
    position: relative;
    height: 0.55rem;
    border-left: 1px solid var(--divider);
    background: rgba(39, 53, 68, 0.6);
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

  /* ── Sparkline ── */
  .sparkline-cell { width: 7rem; padding: var(--space-2) var(--space-4); }

  .sparkline {
    display: block;
    width: 100%;
    height: 1.6rem;
  }

  .sparkline path {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.4;
    vector-effect: non-scaling-stroke;
  }

  .sparkline-empty {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  /* ── Heatmap / seasonality / ratio rows ── */
  .heatmap-list,
  .seasonality-list,
  .ratio-gauge-list {
    display: grid;
    gap: 0;
  }

  .heatmap-row,
  .seasonality-row {
    display: grid;
    grid-template-columns: 4.5rem minmax(0, 1fr) 4.5rem 5rem;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  /* Inventory vs Seasonality: label | min | track | max | latest | pctl */
  .seasonality-list .seasonality-row {
    grid-template-columns: minmax(8rem, 11rem) 3.5rem minmax(0, 1fr) 3.5rem 4rem 3.2rem;
    padding: var(--space-3) var(--space-5);
  }

  .heatmap-row { grid-template-columns: 4.5rem minmax(0, 1fr) 5.5rem; }

  .heatmap-row:last-child,
  .seasonality-row:last-child { border-bottom: 0; }

  .row-label {
    color: var(--text-1);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .heatmap-row strong,
  .seasonality-row strong {
    font-size: var(--text-sm);
    font-weight: 600;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .seasonality-row .meta { color: var(--text-2); font-size: var(--text-2xs); text-align: right; }
  .seasonality-row .range-min { text-align: right; }
  .seasonality-row .range-max { text-align: left; }
  .seasonality-row .pctl-cell { text-align: right; color: var(--text-2); font-size: var(--text-xs); }

  .heatmap-track,
  .gauge-track {
    position: relative;
    height: 0.6rem;
    background: rgba(39, 53, 68, 0.6);
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

  .heatmap-bar.positive { background: var(--positive); }
  .heatmap-bar.negative { background: var(--negative); }
  .heatmap-bar.neutral { background: var(--text-2); }

  .gauge-marker {
    position: absolute;
    top: -0.15rem;
    width: 2px;
    height: 0.9rem;
    background: var(--accent);
  }

  .gauge-marker::after {
    content: "";
    position: absolute;
    top: 0.22rem;
    left: -0.2rem;
    width: 0.42rem;
    height: 0.42rem;
    border: 1px solid var(--accent);
    background: var(--bg-0);
  }

  /* ── Seasonality box-plot ── */
  .seasonality-band {
    position: relative;
    height: 1.3rem;
    background: rgba(39, 53, 68, 0.35);
    border-left: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
  }

  .band-whisker {
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1px;
    background: var(--text-2);
    opacity: 0.45;
  }

  .band-box {
    position: absolute;
    top: 22%;
    bottom: 22%;
    background: rgba(122, 166, 200, 0.18);
    border: 1px solid color-mix(in srgb, var(--chart-primary) 45%, var(--divider));
  }

  .band-median {
    position: absolute;
    top: 22%;
    bottom: 22%;
    width: 1px;
    background: var(--text-1);
    opacity: 0.85;
  }

  .band-marker {
    position: absolute;
    top: -2px;
    bottom: -2px;
    width: 2px;
    background: var(--accent);
    box-shadow: 0 0 0 1px var(--bg-0);
    transform: translateX(-1px);
  }

  .band-marker::after {
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0.55rem;
    height: 0.55rem;
    transform: translate(-50%, -50%);
    border: 1.5px solid var(--accent);
    background: var(--bg-0);
    border-radius: 50%;
  }

  .band-marker.positive { background: var(--positive); }
  .band-marker.positive::after { border-color: var(--positive); }
  .band-marker.negative { background: var(--negative); }
  .band-marker.negative::after { border-color: var(--negative); }
  .band-marker.warning { background: var(--warning); }
  .band-marker.warning::after { border-color: var(--warning); }

  /* ── Empty state ── */
  .empty-state-inline,
  .empty-hint {
    color: var(--text-2);
    font-size: var(--text-xs);
    padding: var(--space-5) var(--space-5);
    margin: 0;
  }

  .empty-state {
    min-height: 7rem;
    align-content: center;
    text-align: center;
  }

  .empty-state h2 {
    margin: 0;
    font-size: var(--text-base);
    color: var(--text-1);
    font-weight: 600;
  }

  .empty-state p {
    margin: var(--space-2) 0 0;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  /* ── Provenance footer ── */
  .provenance {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-5);
    color: var(--text-1);
    font-size: var(--text-xs);
  }

  .provenance .prov-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .provenance .prov-sep { color: var(--divider); }
  .provenance .meta { color: var(--text-2); }

  /* ── Responsive ── */
  @media (max-width: 1280px) {
    .fundamental-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 1200px) {
    .overview-grid,
    .rank-grid,
    .deep-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .span-4 { grid-column: span 2; }
    .header-kpi:nth-child(n+3) { display: none; }
  }

  @media (max-width: 1100px) {
    .split {
      grid-template-columns: minmax(0, 1fr);
    }
    .curve-support-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  @media (max-width: 900px) {
    .fundamental-grid { grid-template-columns: minmax(0, 1fr); }
    .seasonality-list .seasonality-row {
      grid-template-columns: 1fr;
      gap: var(--space-2);
    }
  }

  @media (max-width: 720px) {
    .header-top,
    .mode-kpi-row {
      flex-direction: column;
      align-items: stretch;
    }

    .mode-bar {
      width: 100%;
      grid-template-columns: repeat(3, 1fr);
    }

    .mode-bar button:nth-child(3) { border-right: 0; }
    .mode-bar button:nth-child(-n+3) { border-bottom: 1px solid var(--panel-strong); }

    .header-kpis { width: 100%; border-left: 0; border-top: 1px solid var(--divider); padding-top: var(--space-3); }

    .overview-grid,
    .rank-grid,
    .deep-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .heatmap-row,
    .seasonality-row {
      grid-template-columns: minmax(0, 1fr);
      align-items: stretch;
      gap: var(--space-2);
    }

    .span-2, .span-4 { grid-column: span 1; }

    .inline-stats { grid-template-columns: minmax(0, 1fr); }
    .inline-stats > div { border-right: 0; border-bottom: 1px solid var(--divider); }
    .inline-stats > div:last-child { border-bottom: 0; }

    .ctx-kpis { margin-left: 0; border-left: 0; border-top: 1px solid var(--divider); width: 100%; padding-top: var(--space-3); }
  }
</style>
