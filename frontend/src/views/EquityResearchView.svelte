<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import CompactContextMenu from "../components/CompactContextMenu.svelte";
  import HeroPriceChart from "../components/HeroPriceChart.svelte";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { toProvenanceBadge } from "../lib/provenance";
  import type {
    ResearchConstituent,
    ResearchCoverage,
    ResearchOverviewMetricId,
    ResearchOverviewNode,
    ResearchOverviewRankItem,
    ResearchOverviewResponse,
    ResearchOverviewSortId,
    ResearchCompareResult,
    ResearchResult,
    SavedResearchItem,
    StrategyLabResult,
    ResearchStructure,
    StrategyLabHandoffEnvelope,
    TimeSeriesPoint
  } from "../lib/api/types";
  import {
    researchDraft,
    setResearchDraft,
    type ResearchOverviewLoadOptions,
    type ResearchRunOptions,
    type ResearchCompareOptions,
    type SavedResearchCreateOptions
  } from "../lib/stores/app";
  import {
    buildResearchCompareOptions,
    buildEquityStrategyHandoff,
    buildResearchTreemapSections,
    buildPreviewRows,
    classifySavedResearchSurface,
    deriveConstituentsFromResearchResult,
    deriveCoverageFromResearchResult,
    deriveStructureFromWeights,
    doesResearchDraftMatchResult,
    formatResearchOverviewMetricValue,
    formatResearchOverviewSortValue,
    getResearchOverviewMetricValue,
    hasPopulatedCoverage,
    hasPopulatedStructure,
    normalizeSyntheticText,
    parseSyntheticText,
    researchSortMetricLabel,
    savedResearchCanReloadScope,
    savedResearchHasReturnStream,
    savedResearchScopeDraft,
    treemapDensityClass,
    treemapRectStyle,
    type ResearchCompareOption,
    type EquityResearchMode,
    type ResearchPreviewRow,
    type ResearchTreemapSection,
    type ResearchTreemapTile
  } from "../lib/view-models/research";
  import { heroPricePointFromApiPoint, type HeroPricePoint } from "../lib/view-models/hero-price-chart";

  export let mode: EquityResearchMode = "overview";
  export let overview: ResearchOverviewResponse | null = null;
  export let result: ResearchResult | null = null;
  export let strategyResult: StrategyLabResult | null = null;
  export let compareResult: ResearchCompareResult | null = null;
  export let savedItems: SavedResearchItem[] = [];
  export let loading = false;
  export let overviewLoading = false;
  export let compareLoading = false;
  export let savedLoading = false;
  export let riskHandoffLoading = false;
  export let selectedEquitySymbol: string | null = null;
  export let onLoadOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void;
  export let onRun: (options: ResearchRunOptions) => void;
  export let onSelectEquity: ((symbol: string, label?: string | null) => void) | undefined = undefined;
  export let onCompare: (options: ResearchCompareOptions) => Promise<ResearchCompareResult | null> | void;
  export let onLoadSaved: () => Promise<SavedResearchItem[]> | void;
  export let onSaveResearch: (options: SavedResearchCreateOptions) => Promise<SavedResearchItem | null> | void;
  export let onDeleteSaved: (itemId: string) => Promise<boolean> | void;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let onOpenIv: (() => void) | undefined = undefined;
  export let onOpenStrategyLab: (() => void) | undefined = undefined;
  export let onSendToStrategyLab:
    | ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void)
    | undefined = undefined;

  type ChartMode =
    | "performance"
    | "relative"
    | "price"
    | "drawdown"
    | "rolling_vol"
    | "rolling_beta"
    | "rolling_corr";
  type ResearchTimeframe = "1M" | "3M" | "6M" | "1Y" | "MAX";

  const equityResearchModes: Array<{ id: EquityResearchMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "scope_analysis", label: "Scope" },
    { id: "comparables", label: "Comparables" },
    { id: "scenario_context", label: "Scenario Context" },
    { id: "saved_equity_research", label: "Saved" }
  ];
  const chartModeLabels: Record<ChartMode, string> = {
    performance: "Performance",
    relative: "Relative",
    price: "Price",
    drawdown: "Drawdown",
    rolling_vol: "Rolling Vol",
    rolling_beta: "Rolling Beta",
    rolling_corr: "Rolling Corr"
  };
  const timeframes: ResearchTimeframe[] = ["1M", "3M", "6M", "1Y", "MAX"];
  const defaultPresetText = [
    "SPY 0.20",
    "QQQ 0.14",
    "IWM 0.08",
    "EFA 0.07",
    "EEM 0.06",
    "XLV 0.08",
    "XLF 0.07",
    "XLE 0.06",
    "GLD 0.08",
    "TLT 0.08",
    "HYG 0.04",
    "DBC 0.04"
  ].join("\n");
  const presetBaskets: Array<{ id: string; label: string; text: string }> = [
    { id: "index-core", label: "Cross-Asset Core", text: defaultPresetText },
    {
      id: "ai-infra",
      label: "AI Infrastructure",
      text: [
        "NVDA 0.18",
        "MSFT 0.14",
        "AVGO 0.11",
        "AMD 0.09",
        "TSM 0.08",
        "ASML 0.07",
        "AMZN 0.09",
        "GOOGL 0.08",
        "ANET 0.06",
        "MU 0.05",
        "SMH 0.05"
      ].join("\n")
    },
    {
      id: "defensive",
      label: "Defensive Compounders",
      text: [
        "XLV 0.12",
        "XLP 0.10",
        "XLU 0.08",
        "LLY 0.10",
        "JNJ 0.08",
        "PG 0.08",
        "COST 0.08",
        "MCD 0.07",
        "KO 0.07",
        "PEP 0.07",
        "NEE 0.06",
        "SO 0.05",
        "WM 0.04"
      ].join("\n")
    }
  ];

  const initialDraft = get(researchDraft);
  let scopeType: "single_ticker" | "synthetic_portfolio" = initialDraft.scopeType;
  let primarySymbol = initialDraft.primarySymbol;
  let benchmarkSymbol = initialDraft.benchmarkSymbol;
  let lookbackDays = initialDraft.lookbackDays;
  let syntheticText = initialDraft.syntheticText;
  let chartMode: ChartMode = "performance";
  let timeframe: ResearchTimeframe = "1Y";
  let selectedPreset = initialDraft.selectedPreset;
  let inputWarning = "";
  let signedBookRows: Array<{ symbol: string; weight: number }> = [];
  let overviewUniverseId = "broad_us_market";
  let overviewTimeframe = "DoD";
  let overviewSortBy: ResearchOverviewSortId = "market_cap_desc";
  let overviewMetric: ResearchOverviewMetricId = "return";
  let overviewBenchmarkSymbol = "SPY";
  let selectedOverviewNodeId = "";
  let compareLeftSource = "";
  let compareRightSource = "";
  let compareWarning = "";
  type EquityStrategyRow = {
    symbol: string;
    label: string;
    defaultWeight: number;
    sourceProvider: string | null;
    origin?: string | null;
    retrievedAt?: string | null;
  };
  let equityStrategyContextMenu = {
    open: false,
    x: 0,
    y: 0,
    row: null as EquityStrategyRow | null
  };
  let savedScopeTitle = "Scope Analysis Run";
  let savedNotes = "";
  const emptyStructure: ResearchStructure = {
    total_weight: null,
    top_weight: null,
    top5_weight: null,
    concentration_hhi: null,
    effective_positions: null,
    aligned_symbol_count: 0
  };
  const emptyCoverage: ResearchCoverage = {
    available_symbols: [],
    missing_symbols: [],
    benchmark_overlap_count: 0
  };

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";

  const overviewMetricLabels: Record<ResearchOverviewMetricId, string> = {
    return: "Return",
    volatility: "Volatility",
    beta: "Beta",
    drawdown: "Drawdown",
    relative_return: "Relative"
  };
  const overviewSortLabels: Record<ResearchOverviewSortId, string> = {
    market_cap_desc: "Market Cap",
    universe_weight_desc: "Universe Weight",
    return_desc: "Return",
    volatility_desc: "Volatility",
    beta_desc: "Beta",
    drawdown_desc: "Drawdown"
  };
  const overviewSortToMetric: Record<ResearchOverviewSortId, ResearchOverviewMetricId> = {
    market_cap_desc: "return",
    universe_weight_desc: "return",
    return_desc: "return",
    volatility_desc: "volatility",
    beta_desc: "beta",
    drawdown_desc: "drawdown"
  };
  const overviewTimeframeLabels: Record<string, string> = {
    DoD: "Day over day",
    "1M": "1M",
    "3M": "3M",
    "6M": "6M",
    "1Y": "1Y"
  };
  const hiddenOverviewUniverseIds = new Set<string>(["sample_equities"]);

  function overviewReturnPeriodLabel(currentOverview: ResearchOverviewResponse | null) {
    const timeframe = currentOverview?.timeframe ?? overviewTimeframe;
    return timeframe === "DoD" ? "Latest Day" : `${timeframe} Return`;
  }

  function overviewMetricLabel(metricId: ResearchOverviewMetricId, currentOverview: ResearchOverviewResponse | null = overview) {
    return metricId === "return" ? overviewReturnPeriodLabel(currentOverview) : overviewMetricLabels[metricId];
  }

  function overviewSortOptions(currentOverview: ResearchOverviewResponse | null) {
    const options = currentOverview?.sort_options?.length
      ? currentOverview.sort_options
      : ([
          { sort_id: "market_cap_desc", label: "Market Cap", description: "Size by market cap." },
          { sort_id: "universe_weight_desc", label: "Universe Weight", description: "Size by universe weight." },
          { sort_id: "return_desc", label: "Return", description: "Size by return." },
          { sort_id: "volatility_desc", label: "Volatility", description: "Size by volatility." },
          { sort_id: "beta_desc", label: "Beta", description: "Size by beta." },
          { sort_id: "drawdown_desc", label: "Drawdown", description: "Size by drawdown." }
        ] as const);
    return options.filter((option) => option.sort_id in overviewSortLabels);
  }

  async function loadOverview(options: ResearchOverviewLoadOptions = {}) {
    await onLoadOverview({
      universeId: options.universeId ?? overviewUniverseId,
      timeframe: options.timeframe ?? overviewTimeframe,
      benchmarkSymbol: (options.benchmarkSymbol ?? overviewBenchmarkSymbol).trim().toUpperCase() || "SPY",
      forceRefresh: options.forceRefresh ?? false
    });
  }

  function handleOverviewUniverseChange(event: Event) {
    const universeId = (event.currentTarget as HTMLSelectElement).value;
    overviewUniverseId = universeId;
    selectedOverviewNodeId = "";
    void loadOverview({ universeId });
  }

  function handleOverviewTimeframeChange(event: Event) {
    const timeframe = (event.currentTarget as HTMLSelectElement).value;
    overviewTimeframe = timeframe;
    selectedOverviewNodeId = "";
    void loadOverview({ timeframe });
  }

  function selectResearchMode(nextMode: EquityResearchMode) {
    mode = nextMode;
    if (nextMode === "overview" && !overview) {
      void loadOverview();
    }
    if (nextMode === "saved_equity_research") {
      void onLoadSaved();
    }
  }

  function selectOverviewNode(nodeId: string) {
    selectedOverviewNodeId = nodeId;
    const node = overview?.nodes.find((item) => item.node_id === nodeId) ?? null;
    if (node?.symbol) {
      onSelectEquity?.(node.symbol, node.label);
    }
  }

  function inspectOverviewNodeInScope(node: ResearchOverviewNode | null) {
    if (!node?.symbol) {
      return;
    }
    onSelectEquity?.(node.symbol, node.label);
    scopeType = "single_ticker";
    primarySymbol = node.symbol;
    benchmarkSymbol = overview?.benchmark_symbol ?? overviewBenchmarkSymbol;
    mode = "scope_analysis";
    inputWarning = "";
  }

  function activeEquityHandoffSymbol() {
    const resultSymbol =
      result?.scope_type === "single_ticker" ? String(result.primary_symbol ?? "").trim().toUpperCase() : "";
    const draftSymbol = scopeType === "single_ticker" ? primarySymbol.trim().toUpperCase() : "";
    return resultSymbol || draftSymbol || String(selectedEquitySymbol ?? "").trim().toUpperCase();
  }

  function activeEquityHandoffLabel() {
    const symbol = activeEquityHandoffSymbol();
    if (result?.scope_type === "single_ticker" && result.primary_symbol === symbol) {
      return result.primary_symbol;
    }
    return symbol;
  }

  function sendActiveEquityToStrategyLab(open = false) {
    const symbol = activeEquityHandoffSymbol();
    if (!symbol) {
      inputWarning = "Select or enter a ticker before sending it to Strategy Lab.";
      return;
    }
    if (!onSendToStrategyLab) {
      onOpenStrategyLab?.();
      return;
    }
    const handoff = buildEquityStrategyHandoff(
      {
        symbol,
        label: activeEquityHandoffLabel(),
        sourceProvider: result?.source_provider ?? null
      },
      { sourceMode: String(mode), defaultWeight: 0.1 }
    );
    onSendToStrategyLab(handoff, { open });
    inputWarning = "";
  }

  function sendEquityRowToStrategyLab(row: EquityStrategyRow, open = false) {
    if (!onSendToStrategyLab) {
      onOpenStrategyLab?.();
      return;
    }
    const handoff = buildEquityStrategyHandoff(
      {
        symbol: row.symbol,
        label: row.label,
        sourceProvider: row.sourceProvider,
        origin: row.origin,
        retrievedAt: row.retrievedAt
      },
      { sourceMode: String(mode), defaultWeight: row.defaultWeight }
    );
    onSendToStrategyLab(handoff, { open });
    inputWarning = "";
  }

  function equityRowFromPreview(row: ResearchPreviewRow): EquityStrategyRow {
    return {
      symbol: row.symbol,
      label: row.symbol,
      defaultWeight: row.normalizedWeight,
      sourceProvider: result?.source_provider ?? null
    };
  }

  function equityRowFromConstituent(row: ResearchConstituent): EquityStrategyRow {
    const symbol = String(row.display_symbol ?? row.symbol ?? "").trim().toUpperCase();
    return {
      symbol,
      label: symbol,
      defaultWeight: row.weight,
      sourceProvider: result?.source_provider ?? null
    };
  }

  function contextMenuPosition(event: MouseEvent | KeyboardEvent) {
    if (event instanceof MouseEvent && event.type === "contextmenu") {
      return { x: event.clientX, y: event.clientY };
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: rect.left + 12, y: rect.top + Math.min(rect.height, 32) };
  }

  function openEquityStrategyMenu(event: MouseEvent | KeyboardEvent, row: EquityStrategyRow) {
    if (!row.symbol) {
      return;
    }
    event.preventDefault();
    onSelectEquity?.(row.symbol, row.label);
    const position = contextMenuPosition(event);
    equityStrategyContextMenu = { open: true, x: position.x, y: position.y, row };
  }

  function handleEquityRowKeydown(event: KeyboardEvent, row: EquityStrategyRow) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      openEquityStrategyMenu(event, row);
    }
  }

  function handleEquityStrategyMenuSelect(action: string) {
    const row = equityStrategyContextMenu.row;
    if (!row) {
      return;
    }
    sendEquityRowToStrategyLab(row, action === "add-open");
  }

  function closeEquityStrategyMenu() {
    equityStrategyContextMenu = { ...equityStrategyContextMenu, open: false };
  }

  function compareLegForSource(sourceId: string) {
    const option = compareOptions.find((item) => item.id === sourceId);
    if (!option) {
      return null;
    }
    if (option.source === "scope" && result?.performance_points?.length) {
      return {
        label: option.label,
        objectType: option.objectType,
        returnPoints: result.performance_points
      };
    }
    if (option.source === "strategy" && strategyResult?.returns_points?.length) {
      return {
        label: option.label,
        objectType: option.objectType,
        returnPoints: strategyResult.returns_points
      };
    }
    if (option.source === "saved") {
      return {
        label: option.label,
        objectType: option.objectType,
        savedResearchId: sourceId.replace(/^saved:/, "")
      };
    }
    return null;
  }

  async function runComparison() {
    compareWarning = "";
    if (!compareLeftSource || !compareRightSource) {
      compareWarning = "Select two research objects with return streams.";
      return;
    }
    if (compareLeftSource === compareRightSource) {
      compareWarning = "Select two different objects for comparison.";
      return;
    }
    const left = compareLegForSource(compareLeftSource);
    const right = compareLegForSource(compareRightSource);
    if (!left || !right) {
      compareWarning = "Selected objects do not have reusable return streams.";
      return;
    }
    await onCompare({ left, right });
  }

  async function saveScopeRun() {
    if (!result) {
      return;
    }
    await onSaveResearch({
      objectType: "scope_analysis",
      title: savedScopeTitle.trim() || "Scope Analysis Run",
      notes: savedNotes,
      payload: {
        ...result,
        saved_from_mode: "scope_analysis",
        builder_state: {
          scope_type: scopeType,
          primary_symbol: primarySymbol.trim().toUpperCase(),
          benchmark_symbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
          lookback_days: lookbackDays,
          synthetic_text: syntheticText
        }
      },
      warnings: result.warnings,
      sourceProvider: "gamma_research",
      origin: "frontend.research.scope_analysis.save",
      transformationNote: "Saved normalized Scope Analysis result for reuse in Research Compare / Scenario."
    });
    void onLoadSaved();
  }

  function useSavedInCompare(item: SavedResearchItem) {
    const sourceId = `saved:${item.id}`;
    if (!compareLeftSource) {
      compareLeftSource = sourceId;
    } else {
      compareRightSource = sourceId;
    }
    mode = "comparables";
  }

  function loadSavedScope(item: SavedResearchItem) {
    const draft = savedResearchScopeDraft(item);
    if (!draft) {
      return;
    }
    scopeType = draft.scopeType;
    primarySymbol = draft.scopeType === "single_ticker" ? draft.primarySymbol : "";
    benchmarkSymbol = draft.benchmarkSymbol;
    lookbackDays = draft.lookbackDays;
    if (draft.scopeType === "synthetic_portfolio") {
      syntheticText = draft.syntheticText;
    }
    inputWarning = "Loaded saved scope into the builder. Run analysis to refresh provider-backed history.";
    mode = "scope_analysis";
  }

  function rankingMeta(item: ResearchOverviewRankItem) {
    return item.group ?? item.symbol ?? "";
  }

  function tileMetricAbsMax(sections: ResearchTreemapSection[]) {
    return Math.max(
      ...sections
        .flatMap((section) => section.tiles)
        .map((tile) => Math.abs(tile.colorValue ?? 0))
        .filter((value) => Number.isFinite(value) && value > 0),
      0.01
    );
  }

  function overviewTileColor(value: number | null, metricId: ResearchOverviewMetricId, maxAbs: number) {
    // RGB values below match design tokens exactly:
    //   --accent   #7aa6c8 = 122,166,200
    //   --warning  #c49a5a = 196,154, 90
    //   --positive #4bb474 =  75,180,116
    //   --negative #c66b61 = 198,107, 97
    //   --text-2   #8a919a = 138,145,154
    if (value == null || !Number.isFinite(value)) {
      return "rgba(138, 145, 154, 0.14)";
    }
    const intensity = Math.min(0.78, 0.22 + Math.abs(value) / Math.max(maxAbs, 1e-6) * 0.56);
    if (metricId === "volatility" || metricId === "beta") {
      return value >= 1 && metricId === "beta"
        ? `rgba(196, 154, 90, ${intensity})`
        : `rgba(122, 166, 200, ${Math.max(0.24, intensity - 0.08)})`;
    }
    if (metricId === "drawdown") {
      return value < 0 ? `rgba(198, 107, 97, ${intensity})` : `rgba(75, 180, 116, ${intensity})`;
    }
    return value >= 0 ? `rgba(75, 180, 116, ${intensity})` : `rgba(198, 107, 97, ${intensity})`;
  }

  function overviewTileStyle(tile: ResearchTreemapTile, metricId: ResearchOverviewMetricId, maxAbs: number) {
    return `${treemapRectStyle(tile.rect)} background:${overviewTileColor(tile.colorValue, metricId, maxAbs)};`;
  }

  function submit() {
    if (scopeType === "single_ticker") {
      inputWarning = primarySymbol.trim() ? "" : "Ticker is required.";
      if (inputWarning) {
        return;
      }
      onSelectEquity?.(primarySymbol, null);
      onRun({
        scopeType,
        primarySymbol: primarySymbol.trim().toUpperCase(),
        benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
        lookbackDays
      });
      return;
    }

    const parsedRows = parsedSynthetic.filter((item) => item.symbol && Number.isFinite(item.weight) && item.weight !== 0);
    const shortRows = parsedRows.filter((item) => item.weight < 0);
    if (shortRows.length) {
      signedBookRows = parsedRows;
      inputWarning =
        `Scope Analysis is long-only. ${shortRows.length} short leg(s) detected: ` +
        `${shortRows.map((item) => item.symbol).join(", ")}. ` +
        "Nothing was dropped or analyzed. Send the signed book to Strategy Lab to analyze long/short.";
      return;
    }
    signedBookRows = [];

    const syntheticPositions = parsedRows;
    if (!syntheticPositions.length) {
      inputWarning = "Synthetic portfolio needs valid positive weights.";
      return;
    }

    inputWarning = "";
    onRun({
      scopeType,
      syntheticPositions,
      benchmarkSymbol: benchmarkSymbol.trim().toUpperCase() || "SPY",
      lookbackDays
    });
  }

  function sendSignedBookToStrategyLab(open = false) {
    if (!signedBookRows.length) {
      return;
    }
    if (!onSendToStrategyLab) {
      onOpenStrategyLab?.();
      return;
    }
    signedBookRows.forEach((row, index) => {
      const handoff = buildEquityStrategyHandoff(
        {
          symbol: row.symbol,
          label: row.symbol,
          sourceProvider: result?.source_provider ?? null
        },
        { sourceMode: String(mode), defaultWeight: row.weight }
      );
      void onSendToStrategyLab?.(handoff, { open: open && index === signedBookRows.length - 1 });
    });
    inputWarning = `Sent ${signedBookRows.length} signed leg(s) to Strategy Lab with weights preserved.`;
    signedBookRows = [];
  }

  function normalizeSynthetic() {
    syntheticText = normalizeSyntheticText(syntheticText);
    inputWarning = "";
    signedBookRows = [];
  }

  function applyPreset(presetId: string) {
    const preset = presetBaskets.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }
    syntheticText = preset.text;
    inputWarning = "";
    signedBookRows = [];
  }

  function resetBuilder() {
    scopeType = "single_ticker";
    primarySymbol = "AAPL";
    benchmarkSymbol = "SPY";
    lookbackDays = 252;
    syntheticText = presetBaskets[0]?.text ?? defaultPresetText;
    selectedPreset = presetBaskets[0]?.id ?? "index-core";
    inputWarning = "";
    signedBookRows = [];
  }

  function slicePoints(points: TimeSeriesPoint[]) {
    if (timeframe === "MAX" || !points.length) {
      return points;
    }
    const latest = new Date(points[points.length - 1].timestamp).getTime();
    const days = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 }[timeframe];
    const cutoff = latest - days * 24 * 60 * 60 * 1000;
    return points.filter((point) => new Date(point.timestamp).getTime() >= cutoff);
  }

  function toChartPoint(point: TimeSeriesPoint) {
    return {
      time: Math.floor(new Date(point.timestamp).getTime() / 1000),
      value: point.value
    };
  }

  function cumulativeFromReturns(points: TimeSeriesPoint[]) {
    let cumulative = 1;
    return points.map((point) => {
      cumulative *= 1 + point.value;
      return {
        time: Math.floor(new Date(point.timestamp).getTime() / 1000),
        value: cumulative
      };
    });
  }

  function rollingStd(points: TimeSeriesPoint[], window = 21) {
    return points
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = points.slice(index + 1 - window, index + 1).map((item) => item.value);
        const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
        const variance = slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(slice.length - 1, 1);
        return {
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: Math.sqrt(variance) * Math.sqrt(252)
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function rollingBetaLike(
    perfPoints: TimeSeriesPoint[],
    benchmarkPoints: TimeSeriesPoint[],
    mode: "beta" | "corr",
    window = 63
  ) {
    const benchmarkByTs = new Map(benchmarkPoints.map((point) => [new Date(point.timestamp).getTime(), point.value]));
    const aligned = perfPoints
      .map((point) => {
        const ts = new Date(point.timestamp).getTime();
        const benchmark = benchmarkByTs.get(ts);
        if (benchmark == null) {
          return null;
        }
        return { ts, perf: point.value, benchmark };
      })
      .filter((point): point is { ts: number; perf: number; benchmark: number } => point !== null);

    return aligned
      .map((point, index) => {
        if (index + 1 < window) {
          return null;
        }
        const slice = aligned.slice(index + 1 - window, index + 1);
        const perfMean = slice.reduce((sum, item) => sum + item.perf, 0) / slice.length;
        const benchmarkMean = slice.reduce((sum, item) => sum + item.benchmark, 0) / slice.length;
        const covariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) * (item.benchmark - benchmarkMean), 0) /
          Math.max(slice.length - 1, 1);
        const perfVariance =
          slice.reduce((sum, item) => sum + (item.perf - perfMean) ** 2, 0) / Math.max(slice.length - 1, 1);
        const benchmarkVariance =
          slice.reduce((sum, item) => sum + (item.benchmark - benchmarkMean) ** 2, 0) /
          Math.max(slice.length - 1, 1);
        if (benchmarkVariance <= 0) {
          return null;
        }
        const value =
          mode === "beta"
            ? covariance / benchmarkVariance
            : covariance / Math.sqrt(Math.max(perfVariance, 0) * benchmarkVariance || 1);
        return {
          time: Math.floor(point.ts / 1000),
          value
        };
      })
      .filter((point): point is { time: number; value: number } => point !== null);
  }

  function chartEmptyMessage(modeId: ChartMode, currentResult: ResearchResult | null) {
    if (modeId === "price" && currentResult?.scope_type === "synthetic_portfolio") {
      return "Price mode is only available for single-ticker research.";
    }
    if (modeId === "rolling_beta" || modeId === "rolling_corr") {
      return "Rolling beta/correlation needs benchmark overlap after a run.";
    }
    return "Run analysis to populate the research canvas.";
  }

  function buildNotes(
    currentResult: ResearchResult | null,
    structure: ResearchStructure,
    coverage: ResearchCoverage,
    draftScopeType: "single_ticker" | "synthetic_portfolio",
    previewCount: number
  ) {
    const notes: string[] = [];
    if (!currentResult) {
      if (draftScopeType === "synthetic_portfolio") {
        notes.push(previewCount ? `Draft basket has ${previewCount} parsed names before normalization.` : "Build a basket to inspect concentration and benchmark sensitivity.");
      } else {
        notes.push("Single-name research is best for isolating benchmark sensitivity before sending the name to Options or Risk.");
      }
      return notes;
    }

    if ((structure.top_weight ?? 0) >= 0.5) {
      notes.push(`Scope is concentrated: top weight is ${pct(structure.top_weight)}.`);
    } else if ((structure.effective_positions ?? 0) >= 4) {
      notes.push(`Scope is reasonably spread: effective positions are ${fmt(structure.effective_positions, 2)}.`);
    } else {
      notes.push(`Scope remains fairly tight with ${fmt(structure.effective_positions, 2)} effective positions.`);
    }

    if ((currentResult.summary.correlation ?? 0) >= 0.8) {
      notes.push(`Benchmark sensitivity is high at ${fmt(currentResult.summary.correlation, 3)} correlation to ${currentResult.benchmark_symbol}.`);
    } else if ((currentResult.summary.beta ?? 0) >= 1.2) {
      notes.push(`Beta is elevated at ${fmt(currentResult.summary.beta, 3)} versus ${currentResult.benchmark_symbol}.`);
    } else {
      notes.push(`Benchmark dependence looks moderate against ${currentResult.benchmark_symbol}.`);
    }

    if (coverage.missing_symbols.length) {
      notes.push(`Coverage is partial: missing ${coverage.missing_symbols.join(", ")}.`);
    } else {
      notes.push(`Coverage is clean across ${coverage.available_symbols.length} aligned symbols.`);
    }

    if (coverage.benchmark_overlap_count > 0) {
      notes.push(`${coverage.benchmark_overlap_count} aligned benchmark observations support the run.`);
    }

    return notes.slice(0, 4);
  }

  function formatScopeLabel(scopeType: ResearchResult["scope_type"] | "none" | null | undefined) {
    if (scopeType === "single_ticker") {
      return "Single Ticker";
    }
    if (scopeType === "synthetic_portfolio") {
      return "Synthetic Portfolio";
    }
    return "No Active Run";
  }

  function activeHeadline(currentResult: ResearchResult | null) {
    if (!currentResult) {
      return "No Active Analysis";
    }
    if (currentResult.scope_type === "single_ticker") {
      return currentResult.primary_symbol ?? "Single Ticker";
    }
    return "Synthetic Basket";
  }

  function activePrimaryScopeLabel(currentResult: ResearchResult | null) {
    if (!currentResult) {
      return "No active run";
    }
    if (currentResult.scope_type === "single_ticker") {
      return currentResult.primary_symbol ?? "N/A";
    }
    return "Basket";
  }

  function formatScopeAsOf(value: string | null | undefined) {
    if (!value) {
      return "as of N/A";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return `as of ${value.slice(0, 10)}`;
    }
    return `as of ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  }

  function latestDailySubLabel(currentResult: ResearchResult | null) {
    if (!currentResult) {
      return "No daily observation";
    }
    return formatScopeAsOf(currentResult.latest_daily_return_at);
  }

  let parsedSynthetic = parseSyntheticText(syntheticText);
  let previewRows: ResearchPreviewRow[] = [];
  let chartSeries: ChartSeries[] = [];
  let researchHeroPricePoints: HeroPricePoint[] = [];
  let compareChartSeries: ChartSeries[] = [];
  let compareRelativeDrawdownSeries: ChartSeries[] = [];
  let compareOptions: ResearchCompareOption[] = [];
  let compareMetricRows: Array<{ label: string; left: number | null | undefined; right: number | null | undefined }> = [];
  let weightBars: RankBarItem[] = [];
  let structureMetrics: ResearchStructure = emptyStructure;
  let coverageMetrics: ResearchCoverage = emptyCoverage;
  let constituentRows: ResearchConstituent[] = [];
  let bestConstituent: ResearchConstituent | null = null;
  let worstConstituent: ResearchConstituent | null = null;
  let weightedLeader: ResearchConstituent | null = null;
  let researchNotes: string[] = [];
  let draftMatchesResult = false;
  let overviewTreemapSections: ResearchTreemapSection[] = [];
  let overviewMetricMaxAbs = 0.01;
  let selectedOverviewNode: ResearchOverviewNode | null = null;
  let treemapTooltip: {
    section: string;
    tile: ResearchTreemapTile;
    x: number;
    y: number;
    flipX: boolean;
    flipY: boolean;
  } | null = null;
  const treemapTooltipOffset = 14;
  const treemapTooltipEstWidth = 240;
  const treemapTooltipEstHeight = 160;

  function handleTileHover(event: MouseEvent, section: ResearchTreemapSection, tile: ResearchTreemapTile) {
    const canvas = (event.currentTarget as HTMLElement).closest(".treemap-canvas") as HTMLElement | null;
    const bounds = canvas?.getBoundingClientRect();
    if (!bounds) {
      return;
    }
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    treemapTooltip = {
      section: section.label,
      tile,
      x,
      y,
      flipX: x + treemapTooltipOffset + treemapTooltipEstWidth > bounds.width,
      flipY: y + treemapTooltipOffset + treemapTooltipEstHeight > bounds.height
    };
  }

  function handleTileLeave() {
    treemapTooltip = null;
  }
  let overviewRankingBars: Record<string, RankBarItem[]> = {};

  onMount(() => {
    if (mode === "overview" && !overview) {
      void loadOverview();
    }
  });

  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: setResearchDraft({
    scopeType,
    primarySymbol,
    benchmarkSymbol,
    lookbackDays,
    syntheticText,
    selectedPreset
  });
  $: {
    const normalizedSelectedEquity = selectedEquitySymbol?.trim().toUpperCase() ?? "";
    if (
      normalizedSelectedEquity &&
      scopeType === "single_ticker" &&
      normalizedSelectedEquity !== primarySymbol.trim().toUpperCase()
    ) {
      primarySymbol = normalizedSelectedEquity;
      inputWarning = "";
    }
  }
  $: focalScopeSuggestion =
    scopeType === "synthetic_portfolio" && selectedEquitySymbol?.trim()
      ? selectedEquitySymbol.trim().toUpperCase()
      : "";

  function loadFocalSingleTickerScope() {
    if (!focalScopeSuggestion) {
      return;
    }
    scopeType = "single_ticker";
    primarySymbol = focalScopeSuggestion;
    inputWarning = "";
    signedBookRows = [];
  }
  $: savedResearchList = Array.isArray(savedItems) ? savedItems : [];
  $: overviewModeActive = mode === "overview";
  $: scopeModeActive = mode === "scope_analysis";
  $: compareModeActive = mode === "comparables" || mode === "scenario_context";
  $: savedModeActive = mode === "saved_equity_research";
  $: compareOptions = buildResearchCompareOptions(result, strategyResult, savedResearchList);
  $: visibleSavedItems = savedResearchList.filter((item) => classifySavedResearchSurface(item) === "equity");
  $: compareMetricRows = [
    { label: "Total Return", left: compareResult?.left.metrics.total_return, right: compareResult?.right.metrics.total_return },
    { label: "Annual Return", left: compareResult?.left.metrics.annual_return, right: compareResult?.right.metrics.annual_return },
    { label: "Annual Vol", left: compareResult?.left.metrics.annual_volatility, right: compareResult?.right.metrics.annual_volatility },
    { label: "Max Drawdown", left: compareResult?.left.metrics.max_drawdown, right: compareResult?.right.metrics.max_drawdown }
  ];
  $: {
    if (!compareLeftSource && compareOptions[0]) {
      compareLeftSource = compareOptions[0].id;
    }
    if ((!compareRightSource || compareRightSource === compareLeftSource) && compareOptions.length > 1) {
      compareRightSource = compareOptions.find((item) => item.id !== compareLeftSource)?.id ?? "";
    }
  }
  $: previewRows = buildPreviewRows(scopeType, primarySymbol, parsedSynthetic);
  $: draftMatchesResult = doesResearchDraftMatchResult(
    result,
    {
      scopeType,
      primarySymbol,
      benchmarkSymbol
    },
    previewRows
  );
  $: structureMetrics = hasPopulatedStructure(result?.structure)
    ? (result?.structure ?? emptyStructure)
    : result?.weights?.length
      ? deriveStructureFromWeights(result.weights)
      : emptyStructure;
  $: coverageMetrics = hasPopulatedCoverage(result?.coverage)
    ? (result?.coverage ?? emptyCoverage)
    : deriveCoverageFromResearchResult(result);
  $: scopeBadge = result ? toProvenanceBadge(result) : null;
  $: overviewBadge = overview ? toProvenanceBadge(overview) : null;
  $: weightBars = (result?.weights ?? []).map((weight) => ({
    label: weight.display_symbol ?? weight.symbol,
    value: weight.weight,
    tone: "positive"
  }));
  $: constituentRows = result?.constituents?.length ? result.constituents : deriveConstituentsFromResearchResult(result);
  $: {
    const ranked = [...(result?.constituents ?? [])].filter((item) => item.total_return != null);
    bestConstituent = ranked.length ? [...ranked].sort((left, right) => (right.total_return ?? -Infinity) - (left.total_return ?? -Infinity))[0] : null;
    worstConstituent = ranked.length ? [...ranked].sort((left, right) => (left.total_return ?? Infinity) - (right.total_return ?? Infinity))[0] : null;
    weightedLeader = [...(result?.constituents ?? [])]
      .filter((item) => item.weighted_return != null)
      .sort((left, right) => (right.weighted_return ?? -Infinity) - (left.weighted_return ?? -Infinity))[0] ?? null;
  }
  $: researchNotes = buildNotes(result, structureMetrics, coverageMetrics, scopeType, previewRows.length);
  $: {
    if (overview && overview.universe_id !== overviewUniverseId) {
      overviewUniverseId = overview.universe_id;
    }
    if (overview && overview.timeframe !== overviewTimeframe) {
      overviewTimeframe = overview.timeframe;
    }
    if (overview && overview.benchmark_symbol !== overviewBenchmarkSymbol) {
      overviewBenchmarkSymbol = overview.benchmark_symbol;
    }
  }
  $: overviewMetric = overviewSortToMetric[overviewSortBy] ?? "return";
  $: overviewTreemapSections = buildResearchTreemapSections(overview, overviewMetric, overviewSortBy);
  $: overviewMetricMaxAbs = tileMetricAbsMax(overviewTreemapSections);
  $: selectedOverviewNode =
    overview?.nodes.find((node) => node.node_id === selectedOverviewNodeId) ??
    overviewTreemapSections[0]?.tiles[0]?.node ??
    null;
  $: overviewRankingBars = {
    leaders: (overview?.rankings.leaders ?? []).map((item) => ({
      label: item.symbol ?? item.label,
      value: item.value ?? 0,
      tone: (item.value ?? 0) >= 0 ? "positive" : "negative",
      meta: rankingMeta(item)
    })),
    laggards: (overview?.rankings.laggards ?? []).map((item) => ({
      label: item.symbol ?? item.label,
      value: item.value ?? 0,
      tone: (item.value ?? 0) >= 0 ? "positive" : "negative",
      meta: rankingMeta(item)
    })),
    volatility: (overview?.rankings.highest_volatility ?? []).map((item) => ({
      label: item.symbol ?? item.label,
      value: item.value ?? 0,
      tone: "neutral",
      meta: rankingMeta(item)
    })),
    beta: (overview?.rankings.highest_beta ?? []).map((item) => ({
      label: item.symbol ?? item.label,
      value: item.value ?? 0,
      tone: "neutral",
      meta: rankingMeta(item)
    }))
  };
  $: {
    const perf = slicePoints(result?.performance_points ?? []);
    const benchmark = slicePoints(result?.benchmark_points ?? []);
    const prices = slicePoints(result?.primary_price_points ?? []);
    researchHeroPricePoints = prices
      .map((point) => heroPricePointFromApiPoint(point))
      .filter((point): point is HeroPricePoint => point !== null);

    if (!result) {
      chartSeries = [];
    } else if (chartMode === "price") {
      chartSeries = prices.length
        ? [
            {
              id: "price",
              label: result.primary_symbol ?? "Price",
              color: "var(--chart-secondary)",
              type: "line",
              data: prices.map(toChartPoint)
            }
          ]
        : [];
    } else if (chartMode === "drawdown") {
      let cumulative = 1;
      let peak = 1;
      chartSeries = perf.length
        ? [
            {
              id: "drawdown",
              label: "Drawdown",
              color: "var(--chart-negative)",
              type: "area",
              invertFilledArea: true,
              data: perf.map((point) => {
                cumulative *= 1 + point.value;
                peak = Math.max(peak, cumulative);
                return {
                  time: Math.floor(new Date(point.timestamp).getTime() / 1000),
                  value: cumulative / peak - 1
                };
              })
            }
          ]
        : [];
    } else if (chartMode === "rolling_vol") {
      const volSeries = rollingStd(perf);
      chartSeries = volSeries.length
        ? [
            {
              id: "rolling_vol",
              label: "Rolling Vol",
              color: "var(--chart-primary)",
              type: "line",
              data: volSeries
            }
          ]
        : [];
    } else if (chartMode === "rolling_beta" || chartMode === "rolling_corr") {
      const betaSeries = rollingBetaLike(perf, benchmark, chartMode === "rolling_beta" ? "beta" : "corr");
      chartSeries = betaSeries.length
        ? [
            {
              id: chartMode,
              label: chartMode === "rolling_beta" ? "Rolling Beta" : "Rolling Corr",
              color: "var(--chart-secondary)",
              type: "line",
              data: betaSeries
            }
          ]
        : [];
    } else if (chartMode === "relative") {
      const perfSeries = cumulativeFromReturns(perf);
      const benchmarkSeries = cumulativeFromReturns(benchmark);
      const benchmarkByTime = new Map(benchmarkSeries.map((point) => [point.time, point.value]));
      const relative = perfSeries
        .map((point) => {
          const benchmarkValue = benchmarkByTime.get(point.time);
          if (benchmarkValue == null || benchmarkValue === 0) {
            return null;
          }
          return {
            time: point.time,
            value: point.value / benchmarkValue - 1
          };
        })
        .filter((point): point is { time: number; value: number } => point !== null);
      chartSeries = relative.length
        ? [
            {
              id: "relative",
              label: "Relative Return",
              color: "var(--chart-primary)",
              type: "line",
              data: relative
            }
          ]
        : [];
    } else {
      const series: ChartSeries[] = [];
      if (perf.length) {
        series.push({
          id: "research",
          label: result.primary_symbol ?? (result.scope_type === "single_ticker" ? "Research" : "Scope"),
          color: "var(--chart-primary)",
          type: "area",
          data: cumulativeFromReturns(perf)
        });
      }
      if (benchmark.length) {
        series.push({
          id: "benchmark",
          label: result.benchmark_symbol,
          color: "var(--chart-secondary)",
          type: "line",
          lineStyle: "dashed",
          data: cumulativeFromReturns(benchmark)
        });
      }
      chartSeries = series;
    }
  }
  $: compareChartSeries = compareResult
    ? [
        {
          id: "left",
          label: compareResult.left.label,
          color: "var(--chart-primary)",
          type: "area" as const,
          data: compareResult.left.normalized_nav_points.map(toChartPoint)
        },
        {
          id: "right",
          label: compareResult.right.label,
          color: "var(--chart-secondary)",
          type: "line" as const,
          lineStyle: "dashed" as const,
          data: compareResult.right.normalized_nav_points.map(toChartPoint)
        }
      ]
    : [];
  $: compareRelativeDrawdownSeries = compareResult?.relative_drawdown_points?.length
    ? [
        {
          id: "relative_drawdown",
          label: "Relative Drawdown",
          color: "var(--chart-negative)",
          type: "area" as const,
          invertFilledArea: true,
          data: compareResult.relative_drawdown_points.map(toChartPoint)
        }
      ]
    : [];
  $: compareModeEyebrow = mode === "scenario_context" ? "Scenario / Context" : "Equity Comparables";
  $: compareModeTitle =
    mode === "scenario_context"
      ? activeHeadline(result)
      : compareResult
        ? `${compareResult.left.label} vs ${compareResult.right.label}`
        : "Peer And Benchmark Comparison";
  $: compareModeSummary =
    mode === "scenario_context"
      ? "Frame the active scope for Risk, Options, Strategy Lab, and saved-object reuse without modifying any portfolio."
      : "Compare the active equity scope against saved scopes, strategy streams, or benchmarks using aligned return windows.";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Equity Research</span>
      <span class="subtitle">Market map / scope / scenarios</span>
      {#if loading || overviewLoading || compareLoading || savedLoading}<span class="loading-pill">Refreshing</span>{/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Equity Research modes">
        {#each equityResearchModes as item}
          <button
            class="mode-btn"
            type="button"
            class:selected={mode === item.id}
            on:click={() => selectResearchMode(item.id)}
            role="tab"
            aria-selected={mode === item.id}
          >
            {item.label}
          </button>
        {/each}
      </div>
    </div>
  </article>

  {#if overviewModeActive}
      <div class="overview-grid">
        <article class="panel treemap-panel">
          <div class="panel-header treemap-header">
            <div class="title-block">
              <p class="eyebrow">Market Map</p>
              <h3>{overview?.universe_label ?? "Overview"}</h3>
            </div>
            <div class="treemap-header-right">
              <div class="ctrl-group">
                <select class="ctrl-select" bind:value={overviewUniverseId} on:change={handleOverviewUniverseChange} title="Universe">
                  {#each (overview?.available_universes ?? [{
                    universe_id: "broad_us_market",
                    label: "Broad US Market",
                    description: "Static proxy universe.",
                    instruments: [],
                    limitations: [],
                    metadata_source_label: "Static S&P 500-derived proxy metadata",
                    coverage_label: "Static large-cap US seed, partial coverage",
                    is_complete_universe: false
                  }]).filter((item) => !hiddenOverviewUniverseIds.has(item.universe_id)) as item}
                    <option value={item.universe_id}>{item.label}</option>
                  {/each}
                </select>
                <select class="ctrl-select" bind:value={overviewSortBy} title="Size by">
                  {#each overviewSortOptions(overview) as item}
                    <option value={item.sort_id}>{item.label}</option>
                  {/each}
                </select>
                <select class="ctrl-select ctrl-select--short" bind:value={overviewTimeframe} on:change={handleOverviewTimeframeChange} title="Timeframe">
                  {#each overview?.available_timeframes ?? ["DoD", "1M", "3M", "6M", "1Y"] as item}
                    <option value={item}>{overviewTimeframeLabels[item] ?? item}</option>
                  {/each}
                </select>
              </div>
              <div class="builder-actions compact">
                <button type="button" class="ghost-button" on:click={() => void loadOverview({ forceRefresh: true })} disabled={overviewLoading}>
                  {overviewLoading ? "Loading..." : "Refresh"}
                </button>
                <button type="button" on:click={() => inspectOverviewNodeInScope(selectedOverviewNode)} disabled={!selectedOverviewNode?.symbol}>
                  Inspect Scope
                </button>
              </div>
            </div>
          </div>

          <div class="treemap-canvas" aria-label={`Research overview treemap sized by ${researchSortMetricLabel(overviewSortBy)} and colored by ${overviewMetricLabel(overviewMetric)}`}>
            {#if overviewTreemapSections.length}
              {#each overviewTreemapSections as section}
                <section class="treemap-section" style={treemapRectStyle(section.rect)}>
                  <div class="treemap-section-head">
                    <span>{section.label}</span>
                    <small>{section.nodeCount} names</small>
                  </div>
                  <div class="treemap-section-body">
                    {#each section.tiles as tile}
                      {@const density = treemapDensityClass(tile.rect, section.rect)}
                      <button
                        type="button"
                        class={`treemap-tile ${density}`}
                        class:selected={selectedOverviewNode?.node_id === tile.node.node_id}
                        style={overviewTileStyle(tile, overviewMetric, overviewMetricMaxAbs)}
                        aria-label={`${section.label}. ${tile.node.label}. ${overviewMetricLabel(overviewMetric)} ${formatResearchOverviewMetricValue(tile.colorValue, overviewMetric)}. ${researchSortMetricLabel(overviewSortBy)} ${formatResearchOverviewSortValue(tile.metricValue, overviewSortBy)}`}
                        on:click={() => selectOverviewNode(tile.node.node_id)}
                        on:mouseenter={(event) => handleTileHover(event, section, tile)}
                        on:mousemove={(event) => handleTileHover(event, section, tile)}
                        on:mouseleave={handleTileLeave}
                        on:focus={(event) => handleTileHover(event as unknown as MouseEvent, section, tile)}
                        on:blur={handleTileLeave}
                      >
                        <div class="tile-copy">
                          <div class="tile-topline">
                            <strong>{tile.node.symbol ?? tile.node.label}</strong>
                            {#if density !== "micro"}
                              <em>{formatResearchOverviewMetricValue(tile.colorValue, overviewMetric)}</em>
                            {/if}
                          </div>
                          {#if density === "hero"}
                            <div class="tile-bottomline">
                              <span>{tile.node.label}</span>
                              <small>{researchSortMetricLabel(overviewSortBy)}: {formatResearchOverviewSortValue(tile.metricValue, overviewSortBy)}</small>
                            </div>
                          {:else if density === "major"}
                            <div class="tile-bottomline">
                              <small>{formatResearchOverviewSortValue(tile.metricValue, overviewSortBy)}</small>
                            </div>
                          {/if}
                        </div>
                      </button>
                    {/each}
                  </div>
                </section>
              {/each}
            {:else}
              <div class="treemap-empty">{overviewLoading ? "Loading overview..." : "No overview history available."}</div>
            {/if}
            {#if treemapTooltip}
              {@const tipColorValue = treemapTooltip.tile.colorValue}
              {@const tipColorTone = tipColorValue == null ? "neutral" : tipColorValue > 0 ? "positive" : tipColorValue < 0 ? "negative" : "neutral"}
              <div
                class="treemap-tooltip"
                class:flip-x={treemapTooltip.flipX}
                class:flip-y={treemapTooltip.flipY}
                role="presentation"
                style={`left:${treemapTooltip.x}px; top:${treemapTooltip.y}px;`}
              >
                <div class="treemap-tooltip-head">
                  <strong>{treemapTooltip.tile.node.symbol ?? treemapTooltip.tile.node.label}</strong>
                  <span class={`treemap-tooltip-chip ${tipColorTone}`}>
                    {formatResearchOverviewMetricValue(tipColorValue, overviewMetric)}
                  </span>
                </div>
                <div class="treemap-tooltip-name">{treemapTooltip.tile.node.label}</div>
                <div class="treemap-tooltip-sector">{treemapTooltip.section}</div>
                <dl class="treemap-tooltip-metrics">
                  <div>
                    <dt>{overviewMetricLabel(overviewMetric)}</dt>
                    <dd>{formatResearchOverviewMetricValue(tipColorValue, overviewMetric)}</dd>
                  </div>
                  <div>
                    <dt>{researchSortMetricLabel(overviewSortBy)}</dt>
                    <dd>{formatResearchOverviewSortValue(treemapTooltip.tile.metricValue, overviewSortBy)}</dd>
                  </div>
                </dl>
              </div>
            {/if}
          </div>

        </article>

      </div>

      <div class="ranking-grid">
        <article class="panel">
          <div class="panel-header"><div><p class="eyebrow">Leaders</p><h3>{overviewReturnPeriodLabel(overview)} Leaders</h3></div></div>
          <BarRankChart items={overviewRankingBars.leaders ?? []} emptyMessage="No leader data." formatValue={(value) => formatResearchOverviewMetricValue(value, "return")} />
        </article>
        <article class="panel">
          <div class="panel-header"><div><p class="eyebrow">Laggards</p><h3>{overviewReturnPeriodLabel(overview)} Laggards</h3></div></div>
          <BarRankChart items={overviewRankingBars.laggards ?? []} emptyMessage="No laggard data." formatValue={(value) => formatResearchOverviewMetricValue(value, "return")} />
        </article>
        <article class="panel">
          <div class="panel-header"><div><p class="eyebrow">Risk</p><h3>Highest Volatility</h3></div></div>
          <BarRankChart items={overviewRankingBars.volatility ?? []} emptyMessage="No volatility data." formatValue={(value) => formatResearchOverviewMetricValue(value, "volatility")} />
        </article>
        <article class="panel">
          <div class="panel-header"><div><p class="eyebrow">Benchmark</p><h3>Highest Beta</h3></div></div>
          <BarRankChart items={overviewRankingBars.beta ?? []} emptyMessage="No beta data." formatValue={(value) => formatResearchOverviewMetricValue(value, "beta")} />
        </article>
      </div>

      <div class="overview-bottom-grid">
        <article class="panel rail-panel">
          <div class="rail-header">
            <div>
              <p class="eyebrow">Selection</p>
              <h3>{selectedOverviewNode?.symbol ?? selectedOverviewNode?.label ?? "No Selection"}</h3>
            </div>
          </div>
          <div class="stack">
            <div class="row"><span>Group</span><strong>{selectedOverviewNode?.group ?? "N/A"}</strong></div>
            <div class="row"><span>Market Cap</span><strong>{formatResearchOverviewSortValue(selectedOverviewNode?.market_cap_usd, "market_cap_desc")}</strong></div>
            <div class="row"><span>History Obs</span><strong>{selectedOverviewNode?.metrics.observation_count ?? 0}</strong></div>
            <div class="row"><span>{overviewReturnPeriodLabel(overview)}</span><strong>{formatResearchOverviewMetricValue(selectedOverviewNode ? getResearchOverviewMetricValue(selectedOverviewNode, "return") : null, "return")}</strong></div>
            <div class="row"><span>Volatility</span><strong>{formatResearchOverviewMetricValue(selectedOverviewNode ? getResearchOverviewMetricValue(selectedOverviewNode, "volatility") : null, "volatility")}</strong></div>
            <div class="row"><span>Beta</span><strong>{formatResearchOverviewMetricValue(selectedOverviewNode ? getResearchOverviewMetricValue(selectedOverviewNode, "beta") : null, "beta")}</strong></div>
            <div class="row"><span>Drawdown</span><strong>{formatResearchOverviewMetricValue(selectedOverviewNode ? getResearchOverviewMetricValue(selectedOverviewNode, "drawdown") : null, "drawdown")}</strong></div>
          </div>
        </article>

        <article class="panel rail-panel">
          <div class="rail-header">
            <div>
              <p class="eyebrow">Warnings</p>
              <h3>Coverage Notes</h3>
            </div>
          </div>
          <div class="stack">
            <div class="row"><span>Source</span><ProvenanceBadge data={overviewBadge} /></div>
            <div class="row"><span>Coverage Type</span><strong>{overview?.coverage_label ?? "N/A"}</strong></div>
            <div class="row"><span>Missing / Thin</span><strong>{overview?.coverage?.missing_count ?? 0} / {overview?.coverage?.thin_history_symbols?.length ?? 0}</strong></div>
            <div class="row"><span>Observation Range</span><strong>{overview?.coverage?.min_observation_count ?? 0}-{overview?.coverage?.max_observation_count ?? 0}</strong></div>
          </div>
          {#if overview?.warnings.length || selectedOverviewNode?.warnings.length}
            <div class="notes-list">
              {#each overview?.warnings ?? [] as warning}
                <div class="note-row info">
                  <span class="note-tag">Note</span>
                  <p>{warning}</p>
                </div>
              {/each}
              {#each selectedOverviewNode?.warnings ?? [] as warning}
                <div class="note-row">
                  <span class="note-tag">Node</span>
                  <p>{warning}</p>
                </div>
              {/each}
            </div>
          {:else}
            <p class="muted">No overview warnings for the loaded universe.</p>
          {/if}
        </article>
      </div>
  {:else if scopeModeActive}
      <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel performance-panel">
        <div class="panel-header top-line">
          <div class="title-block">
            <p class="eyebrow">Research Workspace</p>
            <h2>{activeHeadline(result)}</h2>
            <p class="muted">
              {#if result}
                Analysis cards and handoff actions are pinned to the last completed research run.
              {:else}
                Build a scope in the builder, then run analysis to create an active research context.
              {/if}
            </p>
          </div>
          <div class="header-actions">
            <label class="inline-field timeframe-field">
              <span>Timeframe</span>
              <select bind:value={timeframe}>
                {#each timeframes as option}
                  <option value={option}>{option}</option>
                {/each}
              </select>
            </label>
            <label class="inline-field view-field">
              <span>View</span>
              <select bind:value={chartMode}>
                {#each Object.entries(chartModeLabels) as [value, label]}
                  <option value={value}>{label}</option>
                {/each}
              </select>
            </label>
          </div>
        </div>

        <div class="kpi-grid summary-kpis">
          <article class="metric">
            <span>Lookback Return</span>
            <strong class:positive={(result?.summary.total_return ?? 0) > 0} class:negative={(result?.summary.total_return ?? 0) < 0}>{pct(result?.summary.total_return)}</strong>
            <small>{result?.observations_count ?? 0} obs / {lookbackDays}D</small>
          </article>
          <article class="metric">
            <span>Latest Day</span>
            <strong class:positive={(result?.latest_daily_return ?? 0) > 0} class:negative={(result?.latest_daily_return ?? 0) < 0}>{pct(result?.latest_daily_return)}</strong>
            <small>{latestDailySubLabel(result)}</small>
          </article>
          <article class="metric">
            <span>Annual Return</span>
            <strong>{pct(result?.summary.annual_return)}</strong>
            <small>{result?.benchmark_symbol ?? "N/A"} benchmark</small>
          </article>
          <article class="metric">
            <span>Annual Vol</span>
            <strong>{pct(result?.summary.annual_vol)}</strong>
            <small>{fmt(structureMetrics.aligned_symbol_count, 0)} aligned names</small>
          </article>
          <article class="metric">
            <span>Max Drawdown</span>
            <strong class:negative={(result?.summary.max_drawdown ?? 0) < 0}>{pct(result?.summary.max_drawdown)}</strong>
            <small>{pct(structureMetrics.top_weight)} top weight</small>
          </article>
          <article class="metric">
            <span>Beta</span>
            <strong class:elevated={(result?.summary.beta ?? 0) > 1.2}>{fmt(result?.summary.beta, 3)}</strong>
            <small>{coverageMetrics.benchmark_overlap_count} overlap obs</small>
          </article>
          <article class="metric">
            <span>Correlation</span>
            <strong>{fmt(result?.summary.correlation, 3)}</strong>
            <small>{pct(structureMetrics.top5_weight)} top-5 weight</small>
          </article>
        </div>

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

        <div class="chart-foot">
          <span>
            {#if coverageMetrics.missing_symbols.length}
              Missing history: {coverageMetrics.missing_symbols.join(", ")}
            {:else if result}
              Shared return stream against {result.benchmark_symbol}; daily move {latestDailySubLabel(result)}
            {:else}
              Run a scope to seed the chart deck.
            {/if}
          </span>
          <strong>
            {#if result?.scope_type === "single_ticker" && result.latest_price_at}
              {activePrimaryScopeLabel(result)} price {formatScopeAsOf(result.latest_price_at)}
            {:else}
              {result?.scope_type === "synthetic_portfolio" ? `${coverageMetrics.available_symbols.length} symbols in scope` : activePrimaryScopeLabel(result)}
            {/if}
          </strong>
        </div>
      </article>

      <div class="detail-split">
        <article class="panel composition-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Composition</p>
              <h3>Weights &amp; Structure</h3>
            </div>
            <small>{structureMetrics.aligned_symbol_count} aligned names</small>
          </div>

          <BarRankChart items={weightBars} emptyMessage="Weights will appear after running analysis." formatValue={(value) => pct(value)} />

          <div class="stack">
            <div class="row"><span>Top Weight</span><strong>{pct(structureMetrics.top_weight)}</strong></div>
            <div class="row"><span>Top-5 Weight</span><strong>{pct(structureMetrics.top5_weight)}</strong></div>
            <div class="row"><span>HHI</span><strong>{fmt(structureMetrics.concentration_hhi, 3)}</strong></div>
            <div class="row"><span>Effective Positions</span><strong>{fmt(structureMetrics.effective_positions, 2)}</strong></div>
          </div>
        </article>

        <article class="panel insight-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Research Readout</p>
              <h3>Interpretation</h3>
            </div>
          </div>

          <div class="stack">
            <div class="row"><span>Best Constituent</span><strong>{bestConstituent ? `${bestConstituent.display_symbol ?? bestConstituent.symbol} | ${pct(bestConstituent.total_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Worst Constituent</span><strong>{worstConstituent ? `${worstConstituent.display_symbol ?? worstConstituent.symbol} | ${pct(worstConstituent.total_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Weighted Leader</span><strong>{weightedLeader ? `${weightedLeader.display_symbol ?? weightedLeader.symbol} | ${pct(weightedLeader.weighted_return)}` : "N/A"}</strong></div>
            <div class="row"><span>Benchmark Overlap</span><strong>{coverageMetrics.benchmark_overlap_count}</strong></div>
          </div>

          <div class="notes-list">
            {#each researchNotes as note}
              <div class="note-row">
                <span class="note-tag">Note</span>
                <p>{note}</p>
              </div>
            {/each}
          </div>
        </article>
      </div>

      <article class="panel table-panel">
        <div class="panel-header tight-head">
          <h3>Constituent Detail</h3>
          <small>{constituentRows.length} rows</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Weight</th>
                <th>Total Return</th>
                <th>Annual Vol</th>
                <th>Max DD</th>
                <th>Weighted Return</th>
              </tr>
            </thead>
            <tbody>
              {#if constituentRows.length}
                {#each constituentRows as constituent}
                  {@const equityRow = equityRowFromConstituent(constituent)}
                  <tr
                    tabindex="0"
                    aria-label={`Strategy actions for ${equityRow.label}`}
                    on:contextmenu={(event) => openEquityStrategyMenu(event, equityRow)}
                    on:keydown={(event) => handleEquityRowKeydown(event, equityRow)}
                  >
                    <td>{constituent.display_symbol ?? constituent.symbol}</td>
                    <td>{pct(constituent.weight)}</td>
                    <td>{pct(constituent.total_return)}</td>
                    <td>{pct(constituent.annual_vol)}</td>
                    <td>{pct(constituent.max_drawdown)}</td>
                    <td>{pct(constituent.weighted_return)}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="6">No constituent rows yet.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>

    <aside class="support-column">
      <article class="panel control-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Scope Builder</p>
            <h3>Build Research Scope</h3>
          </div>
          <strong>{scopeType === "single_ticker" ? "Single Ticker" : "Synthetic Basket"}</strong>
        </div>

        <div class="field-grid">
          <label>
            <span>Scope</span>
            <select bind:value={scopeType}>
              <option value="single_ticker">Single Ticker</option>
              <option value="synthetic_portfolio">Synthetic Portfolio</option>
            </select>
          </label>
          <label>
            <span>Benchmark</span>
            <input bind:value={benchmarkSymbol} placeholder="SPY" />
          </label>
          <label>
            <span>Lookback</span>
            <select bind:value={lookbackDays}>
              <option value={126}>126D</option>
              <option value={252}>252D</option>
              <option value={504}>504D</option>
            </select>
          </label>
        </div>

        {#if scopeType === "single_ticker"}
          <label>
            <span>Ticker</span>
            <input bind:value={primarySymbol} placeholder="AAPL" />
          </label>
        {:else}
          <div class="subsection">
            <div class="section-head">
              <h4>Basket Input</h4>
              <small>One line per name, example: `SPY 0.60`</small>
            </div>

            <label>
              <span>Preset</span>
              <select bind:value={selectedPreset} on:change={() => applyPreset(selectedPreset)}>
                {#each presetBaskets as preset}
                  <option value={preset.id}>{preset.label}</option>
                {/each}
              </select>
            </label>

            <label>
              <span>Synthetic Portfolio</span>
              <textarea bind:value={syntheticText} rows="7" spellcheck="false"></textarea>
            </label>

            <div class="builder-actions compact">
              <button type="button" on:click={normalizeSynthetic}>Normalize</button>
              <button type="button" class="ghost-button" on:click={() => applyPreset(selectedPreset)}>Load Preset</button>
            </div>
          </div>
        {/if}

        {#if inputWarning}
          <p class="warning">{inputWarning}</p>
        {/if}

        {#if signedBookRows.length && scopeType === "synthetic_portfolio"}
          <div class="signed-book">
            <div class="section-head">
              <h4>Signed Book Detected</h4>
              <small>{signedBookRows.filter((row) => row.weight > 0).length} long / {signedBookRows.filter((row) => row.weight < 0).length} short</small>
            </div>
            <div class="pill-list">
              {#each signedBookRows as row}
                <span class={row.weight < 0 ? "short-pill" : ""}>{row.symbol} {fmt(row.weight, 2)}</span>
              {/each}
            </div>
            <div class="builder-actions compact">
              <button type="button" on:click={() => sendSignedBookToStrategyLab(false)}>Send Signed Book to Strategy Lab</button>
              <button type="button" class="ghost-button" on:click={() => sendSignedBookToStrategyLab(true)}>Send &amp; Open</button>
            </div>
          </div>
        {/if}

        {#if focalScopeSuggestion}
          <p class="muted focal-hint">
            Focus {focalScopeSuggestion} is available but not loaded; the active basket is preserved.
            <button type="button" class="ghost-button" on:click={loadFocalSingleTickerScope}>Load {focalScopeSuggestion} scope</button>
          </p>
        {/if}

        <div class="builder-actions">
          <button on:click={submit} disabled={loading}>{loading ? "Running..." : "Run Analysis"}</button>
          <button type="button" class="ghost-button" on:click={resetBuilder}>Reset Builder</button>
          {#if scopeType === "single_ticker"}
            <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(false)} disabled={!activeEquityHandoffSymbol()}>
              + Strategy
            </button>
            <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(true)} disabled={!activeEquityHandoffSymbol()}>
              Add &amp; Open
            </button>
          {/if}
        </div>

        {#if result && !draftMatchesResult}
          <p class="muted">Draft differs from the active analysis. Rerun to replace the current research context.</p>
        {/if}

        <div class="subsection">
          <div class="section-head">
            <h4>Scope Preview</h4>
            <small>{previewRows.length} parsed names</small>
          </div>

          <div class="table-wrap preview-table">
            <table>
              <thead>
                <tr><th>Symbol</th><th>Input</th><th>Normalized</th></tr>
              </thead>
              <tbody>
                {#if previewRows.length}
                  {#each previewRows as row}
                    {@const equityRow = equityRowFromPreview(row)}
                    <tr
                      tabindex="0"
                      aria-label={`Strategy actions for ${equityRow.label}`}
                      on:contextmenu={(event) => openEquityStrategyMenu(event, equityRow)}
                      on:keydown={(event) => handleEquityRowKeydown(event, equityRow)}
                    >
                      <td>{row.symbol}</td>
                      <td>{fmt(row.inputWeight, 4)}</td>
                      <td>{pct(row.normalizedWeight)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="3">No parsed scope yet.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Structure</p>
            <h3>Active Scope Summary</h3>
          </div>
        </div>

        <div class="stack">
          <div class="row"><span>Scope Type</span><strong>{formatScopeLabel(result?.scope_type)}</strong></div>
          <div class="row"><span>Primary Symbol</span><strong>{activePrimaryScopeLabel(result)}</strong></div>
          <div class="row"><span>Aligned Symbols</span><strong>{structureMetrics.aligned_symbol_count}</strong></div>
          <div class="row"><span>Total Weight</span><strong>{fmt(structureMetrics.total_weight, 4)}</strong></div>
          <div class="row"><span>Effective Positions</span><strong>{fmt(structureMetrics.effective_positions, 2)}</strong></div>
          <div class="row"><span>HHI / Top-5</span><strong>{fmt(structureMetrics.concentration_hhi, 3)} / {pct(structureMetrics.top5_weight)}</strong></div>
        </div>

        <div class="mini-groups">
          <div>
            <small class="group-label">Available Symbols</small>
            <div class="pill-list">
              {#if coverageMetrics.available_symbols.length}
                {#each coverageMetrics.available_symbols as symbol}
                  <span>{symbol}</span>
                {/each}
              {:else}
                <span>Waiting for active run</span>
              {/if}
            </div>
          </div>
        </div>
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Research Context</p>
            <h3>Data Quality &amp; Coverage</h3>
          </div>
        </div>

        <div class="stack">
          <div class="row"><span>Source</span><ProvenanceBadge data={scopeBadge} /></div>
          <div class="row"><span>Observations</span><strong>{result?.observations_count ?? 0}</strong></div>
          <div class="row"><span>Benchmark Overlap</span><strong>{coverageMetrics.benchmark_overlap_count}</strong></div>
          <div class="row"><span>Missing Symbols</span><strong>{coverageMetrics.missing_symbols.length}</strong></div>
          <div class="row"><span>Benchmark</span><strong>{result?.benchmark_symbol ?? "N/A"}</strong></div>
        </div>

        {#if result?.warnings?.length || coverageMetrics.missing_symbols.length}
          <div class="notes-list">
            {#each coverageMetrics.missing_symbols as symbol}
              <div class="note-row">
                <span class="note-tag">{symbol}</span>
                <p>History is missing for this symbol in the current run.</p>
              </div>
            {/each}
            {#each result?.warnings ?? [] as warning}
              <div class="note-row info">
                <span class="note-tag">Warning</span>
                <p>{warning}</p>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">No active coverage issues or warnings.</p>
        {/if}
      </article>

      <article class="panel rail-panel">
        <div class="rail-header">
          <div>
            <p class="eyebrow">Forward Actions</p>
            <h3>Handoff &amp; Snapshot</h3>
          </div>
        </div>

        <div class="builder-actions">
          <button type="button" on:click={() => onOpenRisk?.()} disabled={riskHandoffLoading || !result?.snapshot}>
            {riskHandoffLoading ? "Opening..." : "Open In Risk"}
          </button>
          <button type="button" class="ghost-button" on:click={() => onOpenIv?.()} disabled={result?.scope_type !== "single_ticker"}>Open In Options</button>
          <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(false)} disabled={!activeEquityHandoffSymbol()}>+ Strategy</button>
          <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(true)} disabled={!activeEquityHandoffSymbol()}>Add &amp; Open</button>
        </div>

        {#if result?.snapshot}
          <div class="stack">
            <div class="row"><span>Base Currency</span><strong>{result.snapshot.base_currency}</strong></div>
            <div class="row"><span>Positions</span><strong>{result.snapshot.positions.length}</strong></div>
            <div class="row"><span>Portfolio Value</span><strong>{fmt(result.snapshot.net_liquidation)}</strong></div>
            <div class="row"><span>Snapshot Time</span><strong>{new Date(result.snapshot.timestamp).toLocaleString("en-US")}</strong></div>
          </div>
        {:else}
          <p class="muted">Run research to create the forwarded snapshot for Risk or Options.</p>
        {/if}
      </article>
      </aside>
    </div>
  {:else if compareModeActive}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel performance-panel">
          <div class="panel-header top-line">
            <div class="title-block">
              <p class="eyebrow">{compareModeEyebrow}</p>
              <h2>{compareModeTitle}</h2>
              <p class="muted">{compareModeSummary}</p>
            </div>
          </div>

          <div class="kpi-grid">
            <article class="metric"><span>Aligned Obs</span><strong>{compareResult?.aligned_observation_count ?? 0}</strong><small>Common return calendar</small></article>
            <article class="metric"><span>Relative Return</span><strong>{pct(compareResult?.relative_return)}</strong><small>Left minus right</small></article>
            <article class="metric"><span>Vol Difference</span><strong>{pct(compareResult?.volatility_difference)}</strong><small>Annualized</small></article>
            <article class="metric"><span>Drawdown Gap</span><strong>{pct(compareResult?.max_drawdown_difference)}</strong><small>Max drawdown delta</small></article>
            <article class="metric"><span>Correlation</span><strong>{fmt(compareResult?.correlation, 3)}</strong><small>Left vs right</small></article>
            <article class="metric"><span>Beta</span><strong>{fmt(compareResult?.beta, 3)}</strong><small>Left to right</small></article>
          </div>

          <TimeSeriesChart series={compareChartSeries} height={380} emptyMessage="Select two loaded or saved return streams to compare." />
        </article>

        {#if mode === "scenario_context"}
          <article class="panel">
            <div class="panel-header top-line">
              <div class="title-block">
                <p class="eyebrow">Scope Context</p>
                <h3>Forwardable Research State</h3>
              </div>
              <div class="builder-actions compact">
                <button type="button" on:click={() => onOpenRisk?.()} disabled={riskHandoffLoading || !result?.snapshot}>
                  {riskHandoffLoading ? "Opening..." : "Risk"}
                </button>
                <button type="button" class="ghost-button" on:click={() => onOpenIv?.()} disabled={result?.scope_type !== "single_ticker"}>Options</button>
                <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(true)} disabled={!activeEquityHandoffSymbol()}>Add &amp; Open</button>
              </div>
            </div>
            <div class="kpi-grid">
              <article class="metric"><span>Scope</span><strong>{formatScopeLabel(result?.scope_type)}</strong><small>{activePrimaryScopeLabel(result)}</small></article>
              <article class="metric"><span>Benchmark</span><strong>{result?.benchmark_symbol ?? benchmarkSymbol}</strong><small>{coverageMetrics.benchmark_overlap_count} overlap obs</small></article>
              <article class="metric"><span>Available Names</span><strong>{coverageMetrics.available_symbols.length}</strong><small>{coverageMetrics.missing_symbols.length} missing</small></article>
              <article class="metric"><span>Effective Positions</span><strong>{fmt(structureMetrics.effective_positions, 2)}</strong><small>{pct(structureMetrics.top5_weight)} top-5</small></article>
            </div>
          </article>
        {/if}

        <div class="detail-split">
          <article class="panel rail-panel">
            <div class="rail-header"><div><p class="eyebrow">Alignment</p><h3>Common Window</h3></div></div>
            <div class="stack">
              <div class="row"><span>Left Obs</span><strong>{compareResult?.left_observation_count ?? 0}</strong></div>
              <div class="row"><span>Right Obs</span><strong>{compareResult?.right_observation_count ?? 0}</strong></div>
              <div class="row"><span>Overlap</span><strong>{compareResult ? `${shortDate(compareResult.overlap_start)} - ${shortDate(compareResult.overlap_end)}` : "N/A"}</strong></div>
              <div class="row"><span>Relative DD Points</span><strong>{compareResult?.relative_drawdown_points.length ?? 0}</strong></div>
            </div>
          </article>

          <article class="panel">
            <div class="panel-header"><div><p class="eyebrow">Relative Risk</p><h3>Relative Drawdown</h3></div></div>
            <TimeSeriesChart series={compareRelativeDrawdownSeries} height={210} emptyMessage="Relative drawdown appears after comparison." />
          </article>
        </div>

        <article class="panel table-panel">
          <div class="panel-header tight-head"><h3>Side-by-Side Metrics</h3></div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Metric</th><th>{compareResult?.left.label ?? "Left"}</th><th>{compareResult?.right.label ?? "Right"}</th></tr></thead>
              <tbody>
                {#each compareMetricRows as row}
                  <tr><td>{row.label}</td><td>{pct(row.left)}</td><td>{pct(row.right)}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel control-panel">
          <div class="rail-header"><div><p class="eyebrow">{mode === "scenario_context" ? "Scenario Objects" : "Comparable Objects"}</p><h3>Select Streams</h3></div><strong>{compareOptions.length} available</strong></div>
          <label><span>Left</span><select bind:value={compareLeftSource}>{#each compareOptions as option}<option value={option.id}>{option.label}</option>{/each}</select></label>
          <label><span>Right</span><select bind:value={compareRightSource}>{#each compareOptions as option}<option value={option.id}>{option.label}</option>{/each}</select></label>
          <div class="builder-actions"><button type="button" on:click={runComparison} disabled={compareLoading || compareOptions.length < 2}>{compareLoading ? "Comparing..." : "Run Compare"}</button></div>
          {#if compareWarning}<p class="warning">{compareWarning}</p>{/if}
        </article>

        {#if mode === "comparables"}
          <article class="panel table-panel">
            <div class="panel-header tight-head"><h3>Constituent Comparison</h3><small>{constituentRows.length} rows</small></div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Symbol</th><th>Weight</th><th>Return</th><th>Vol</th></tr></thead>
                <tbody>
                  {#if constituentRows.length}
                    {#each constituentRows.slice(0, 10) as constituent}
                      <tr>
                        <td>{constituent.display_symbol ?? constituent.symbol}</td>
                        <td>{pct(constituent.weight)}</td>
                        <td>{pct(constituent.total_return)}</td>
                        <td>{pct(constituent.annual_vol)}</td>
                      </tr>
                    {/each}
                  {:else}
                    <tr><td colspan="4">Run Scope Analysis to seed comparable constituents.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>
        {/if}

        <article class="panel rail-panel">
          <div class="rail-header"><div><p class="eyebrow">Warnings</p><h3>Scenario Notes</h3></div></div>
          {#if compareResult?.warnings.length}
            <div class="notes-list">
              {#each compareResult.warnings as warning}
                <div class="note-row info"><span class="note-tag">Note</span><p>{warning}</p></div>
              {/each}
            </div>
          {:else}
            <p class="muted">Run a comparison to see alignment and scenario warnings.</p>
          {/if}
        </article>
      </aside>
    </div>
  {:else if savedModeActive}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel table-panel">
          <div class="panel-header tight-head">
            <h3>Saved Research Objects</h3>
            <button type="button" class="ghost-button inline-refresh" on:click={() => void onLoadSaved()} disabled={savedLoading}>{savedLoading ? "Loading..." : "Refresh"}</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Title</th><th>Type</th><th>Updated</th><th>Warnings</th><th>Actions</th></tr></thead>
              <tbody>
                {#if visibleSavedItems.length}
                  {#each visibleSavedItems as item}
                    <tr>
                      <td>{item.title}</td>
                      <td>{item.object_type}</td>
                      <td>{shortDate(item.updated_at)}</td>
                      <td>{item.warnings.length}</td>
                      <td>
                        <div class="table-actions">
                          {#if savedResearchCanReloadScope(item)}
                            <button type="button" class="ghost-button" on:click={() => loadSavedScope(item)}>Load Scope</button>
                          {/if}
                          <button type="button" class="ghost-button" on:click={() => useSavedInCompare(item)} disabled={!savedResearchHasReturnStream(item)}>Compare</button>
                          <button type="button" class="ghost-button" on:click={() => void onDeleteSaved(item.id)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="5">No saved research yet.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel control-panel">
          <div class="rail-header"><div><p class="eyebrow">Save Current</p><h3>Scope Analysis</h3></div></div>
          <label><span>Scope Title</span><input bind:value={savedScopeTitle} /></label>
          <div class="builder-actions"><button type="button" on:click={saveScopeRun} disabled={!result || savedLoading}>Save Scope</button></div>
          <label><span>Notes</span><textarea bind:value={savedNotes} rows="5"></textarea></label>
        </article>

        <article class="panel rail-panel">
          <div class="rail-header"><div><p class="eyebrow">Storage</p><h3>Local JSON Layer</h3></div></div>
          <div class="stack">
            <div class="row"><span>Items</span><strong>{visibleSavedItems.length}</strong></div>
            <div class="row"><span>Reusable Streams</span><strong>{visibleSavedItems.filter(savedResearchHasReturnStream).length}</strong></div>
          </div>
        </article>
      </aside>
    </div>
  {/if}

  <CompactContextMenu
    open={equityStrategyContextMenu.open}
    x={equityStrategyContextMenu.x}
    y={equityStrategyContextMenu.y}
    label="Equity Research Strategy Lab actions"
    items={[
      { id: "add", label: "Add to Strategy", disabled: !onSendToStrategyLab },
      { id: "add-open", label: "Add and Open", disabled: !onSendToStrategyLab }
    ]}
    onSelect={handleEquityStrategyMenuSelect}
    onClose={closeEquityStrategyMenu}
  />
</section>

<style>
  /* ── Layout shells ── */
  .view,
  .overview-grid,
  .overview-bottom-grid,
  .ranking-grid,
  .kpi-grid,
  .detail-split,
  .stack,
  .field-grid,
  .builder-actions,
  .notes-list,
  .mini-groups {
    display: grid;
    gap: var(--space-4);
  }

  .view {
    gap: var(--space-4);
  }

  /* ── Panels ── */

  .header-panel {
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
  }

  .header-panel .title {
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .header-panel .subtitle {
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
  }

  .performance-panel,
  .treemap-panel,
  .composition-panel,
  .insight-panel,
  .table-panel,
  .control-panel,
  .rail-panel,
  .subsection {
    align-content: start;
  }

  /* ── Header panel internals ── */
  .header-top {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
  }

  .loading-pill {
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: var(--space-2) var(--space-4);
    white-space: nowrap;
  }

  .mode-kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  /* ── Mode bar (Risk pattern) ── */

  /* ── Treemap panel header with inline controls ── */
  .treemap-header {
    align-items: center;
  }

  .treemap-header-right {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .ctrl-group {
    display: flex;
    align-items: center;
    border: 1px solid var(--panel-border);
    background: var(--surface-0);
  }

  .ctrl-select {
    appearance: none;
    border: 0;
    border-right: 1px solid var(--panel-border);
    background-color: var(--surface-0);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23718096'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.5rem center;
    background-size: 8px 5px;
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-7) var(--space-2) var(--space-5);
    cursor: pointer;
    min-width: 8rem;
    white-space: nowrap;
  }

  .ctrl-select:last-child {
    border-right: 0;
  }

  .ctrl-select:hover {
    background-color: color-mix(in srgb, var(--accent) 8%, var(--surface-0));
    color: var(--text-0);
  }

  .ctrl-select:focus,
  .ctrl-select:focus-visible {
    background-color: var(--surface-0);
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .ctrl-select option {
    background-color: var(--surface-0);
    color: var(--text-0);
  }

  .ctrl-select--short {
    width: 7rem;
    min-width: 7rem;
    flex-shrink: 0;
  }

  /* ── Overview grid / treemap ── */
  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }

  /* minmax(0,1fr) instead of the implicit auto track: the canvas's
     aspect-ratio + min-height would otherwise floor the track width */
  .treemap-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .treemap-canvas {
    position: relative;
    /* explicit width + min-width: 0 keep aspect-ratio from transferring
       min-height into a forced inline size that overflows narrow panels */
    width: 100%;
    min-width: 0;
    min-height: 42rem;
    aspect-ratio: 16 / 9;
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: hidden;
  }

  .treemap-section {
    position: absolute;
    border: 1px solid color-mix(in srgb, var(--panel-strong) 72%, var(--divider));
    background: color-mix(in srgb, var(--surface-0) 76%, transparent);
    min-width: 0;
    overflow: hidden;
  }

  .treemap-section-head {
    position: absolute;
    inset: 0 0 auto 0;
    min-height: 1.5rem;
    padding: var(--space-2) var(--space-4);
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: center;
    background: color-mix(in srgb, var(--bg-1) 86%, transparent);
    border-bottom: 1px solid var(--divider);
    z-index: 1;
    pointer-events: none;
  }

  .treemap-section-head span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .treemap-section-head small {
    color: var(--text-2);
    white-space: nowrap;
  }

  .treemap-section-body {
    position: absolute;
    inset: 1.55rem 0.12rem 0.12rem 0.12rem;
  }

  .treemap-tile {
    position: absolute;
    min-height: 0;
    min-width: 0;
    padding: var(--space-3) var(--space-3);
    border: 1px solid var(--divider);
    color: var(--text-0);
    text-align: left;
    overflow: hidden;
    width: auto;
    transition: border-color 120ms ease, filter 120ms ease;
  }

  .treemap-tile:hover,
  .treemap-tile.selected {
    border-color: var(--accent);
    filter: brightness(1.08);
  }

  .tile-copy,
  .tile-bottomline {
    display: grid;
    gap: var(--space-1);
  }

  .tile-copy {
    height: 100%;
    align-content: space-between;
  }

  .tile-topline {
    display: flex;
    justify-content: space-between;
    gap: var(--space-2);
    align-items: start;
  }

  .treemap-tile strong,
  .treemap-tile span,
  .treemap-tile em,
  .treemap-tile small {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text-0);
  }

  .treemap-tile strong {
    font-size: var(--text-sm);
    line-height: 1.1;
  }

  .treemap-tile span {
    font-size: var(--text-xs);
    color: var(--text-1);
  }

  .treemap-tile em {
    font-style: normal;
    font-weight: 700;
    font-size: var(--text-sm);
    line-height: 1.1;
  }

  .treemap-tile small {
    color: var(--text-1);
    font-size: var(--text-2xs);
    line-height: 1.2;
  }

  .treemap-tile.hero {
    padding: var(--space-4) var(--space-4);
  }

  .treemap-tile.hero strong {
    font-size: var(--text-base);
  }

  .treemap-tile.hero em {
    font-size: var(--text-base);
  }

  .treemap-tile.minor {
    padding: var(--space-2) var(--space-3);
  }

  .treemap-tile.minor strong,
  .treemap-tile.minor em {
    font-size: var(--text-2xs);
  }

  .treemap-tile.micro {
    padding: var(--space-2) var(--space-2);
  }

  .treemap-tile.micro .tile-copy {
    align-content: start;
  }

  .treemap-tile.micro strong {
    font-size: var(--text-2xs);
    letter-spacing: 0.02em;
  }

  .treemap-empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-sm);
  }

  .treemap-tooltip {
    --tip-offset-x: 14px;
    --tip-offset-y: 14px;
    position: absolute;
    pointer-events: none;
    transform: translate(var(--tip-offset-x), var(--tip-offset-y));
    min-width: 12.5rem;
    max-width: 18rem;
    padding: var(--space-4) var(--space-5) var(--space-5);
    background: color-mix(in srgb, var(--bg-1) 96%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
    box-shadow:
      0 1px 0 color-mix(in srgb, var(--accent) 20%, transparent) inset,
      0 12px 28px rgba(0, 0, 0, 0.55),
      0 2px 6px rgba(0, 0, 0, 0.4);
    color: var(--text-0);
    z-index: 20;
    backdrop-filter: blur(6px);
  }

  .treemap-tooltip-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .treemap-tooltip-head strong {
    font-size: var(--text-md);
    letter-spacing: 0.04em;
    color: var(--text-0);
  }

  .treemap-tooltip-chip {
    font-size: var(--text-sm);
    font-weight: 700;
    padding: 0.08rem var(--space-3);
    border: 1px solid var(--divider);
    background: color-mix(in srgb, var(--surface-0) 78%, transparent);
  }

  .treemap-tooltip-chip.positive {
    color: var(--positive);
    border-color: color-mix(in srgb, var(--positive) 40%, transparent);
    background: color-mix(in srgb, var(--positive) 12%, var(--surface-0));
  }

  .treemap-tooltip-chip.negative {
    color: var(--negative);
    border-color: color-mix(in srgb, var(--negative) 40%, transparent);
    background: color-mix(in srgb, var(--negative) 12%, var(--surface-0));
  }

  .treemap-tooltip-chip.neutral {
    color: var(--text-1);
  }

  .treemap-tooltip-name {
    margin-top: var(--space-3);
    font-size: var(--text-sm);
    color: var(--text-1);
    line-height: 1.2;
  }

  .treemap-tooltip-sector {
    margin-top: var(--space-1);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text-2);
  }

  .treemap-tooltip-metrics {
    margin: var(--space-4) 0 0;
    padding-top: var(--space-4);
    border-top: 1px solid var(--divider);
    display: grid;
    gap: var(--space-2);
    grid-template-columns: minmax(0, 1fr);
  }

  .treemap-tooltip-metrics > div {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .treemap-tooltip-metrics dt {
    margin: 0;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .treemap-tooltip-metrics dd {
    margin: 0;
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--text-0);
    white-space: nowrap;
  }

  .treemap-tooltip.flip-x {
    --tip-offset-x: calc(-100% - 14px);
  }

  .treemap-tooltip.flip-y {
    --tip-offset-y: calc(-100% - 14px);
  }

  /* ── Rankings grid ── */
  .ranking-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    align-items: start;
  }

  .overview-bottom-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
  }

  /* ── Scope-analysis workspace ── */

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  /* ── Panel header rows ── */
  .rail-header,
  .chart-foot,
  .section-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: flex-start;
  }

  .chart-foot {
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
    flex-wrap: wrap;
  }

  .chart-foot span {
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .chart-foot strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .top-line {
    align-items: flex-start;
  }

  .tight-head {
    align-items: center;
  }

  .tight-head small {
    color: var(--text-2);
    font-size: var(--text-xs);
    white-space: nowrap;
  }

  .inline-refresh {
    width: auto;
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
  }

  .title-block {
    min-width: 0;
    max-width: 40rem;
    display: grid;
    gap: var(--space-1);
  }

  .title-block .muted {
    line-height: 1.4;
    font-size: var(--text-sm);
  }

  .header-actions {
    display: flex;
    gap: var(--space-4);
    align-items: end;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .view-field {
    min-width: 0;
    width: 9rem;
  }

  /* ── KPI strip ── */
  .kpi-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
    padding-block: var(--space-1);
  }

  .summary-kpis {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }

  .metric {
    min-width: 0;
    padding: var(--space-2) var(--space-5);
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    text-align: left;
    display: grid;
    gap: var(--space-1);
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .metric strong {
    display: block;
    margin: var(--space-1) 0 0.05rem;
    font-size: var(--text-md);
    line-height: 1.2;
    color: var(--text-0);
  }

  .metric small {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  /* ── Typography ── */
  .group-label,
  .inline-field > span,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  h2 {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-0);
  }

  h3 {
    font-size: var(--text-base);
    font-weight: 700;
    color: var(--text-0);
  }

  h4 {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-0);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  h2,
  h3,
  h4,
  p,
  small {
    margin: 0;
  }

  .muted {
    color: var(--text-2);
  }

  strong {
    color: var(--text-0);
  }

  .muted,
  .row span,
  .row strong,
  .note-row p {
    overflow-wrap: anywhere;
  }

  /* ── Rows (label/value pairs) ── */
  .row {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .row span {
    color: var(--text-2);
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .row strong {
    font-size: var(--text-base);
    text-align: right;
  }

  /* ── Inputs & buttons ── */
  label,
  .inline-field {
    display: grid;
    gap: var(--space-2);
  }

  .inline-field {
    min-width: 8rem;
  }

  .inline-field.timeframe-field {
    min-width: 6.5rem;
    width: 6.5rem;
  }

  .field-grid {
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.72fr) minmax(0, 0.58fr);
  }

  .field-grid > label {
    min-width: 0;
  }

  input,
  select,
  textarea,
  button {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-3) var(--space-4);
    font: inherit;
    font-size: var(--text-base);
    display: block;
    width: 100%;
    box-sizing: border-box;
    border-radius: var(--radius-sm);
  }

  textarea {
    min-height: 7rem;
    resize: vertical;
  }

  input,
  select,
  button {
    min-height: 2rem;
    line-height: 1.2;
  }

  input:hover,
  select:hover,
  textarea:hover {
    border-color: color-mix(in srgb, var(--accent) 32%, var(--panel-strong));
  }

  input:focus-visible,
  select:focus-visible,
  textarea:focus-visible,
  button:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  button {
    cursor: pointer;
  }

  button:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
    border-color: var(--panel-border);
    background: var(--bg-1);
  }

  .ghost-button {
    background: transparent;
    color: var(--text-1);
  }

  .builder-actions {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .builder-actions.compact {
    display: flex;
    gap: var(--space-3);
    justify-content: flex-end;
  }

  .builder-actions.compact button {
    width: auto;
    padding: var(--space-3) var(--space-5);
  }

  /* ── Tables ── */
  .table-wrap {
    overflow: auto;
    border: 1px solid var(--divider);
    background: var(--bg-0);
    max-height: 28rem;
  }

  .preview-table {
    max-height: 16rem;
  }

  .compact-table {
    max-height: 20rem;
  }

  /* Table panels: the panel is the table — zero padding, each section
     carries its own inset so the table itself runs edge-to-edge. */
  .table-panel {
    padding: 0;
    gap: 0;
    overflow: hidden;
  }

  .table-panel > .panel-header {
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
    align-items: center;
  }

  .table-panel > .table-wrap {
    border: 0;
    background: transparent;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
    white-space: nowrap;
  }

  tbody td {
    padding: var(--space-4) var(--space-4);
    border-top: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    font-size: var(--text-base);
  }

  tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .table-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: center;
  }

  .table-actions button {
    width: auto;
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
  }

  /* ── Pills / tags ── */
  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin-top: var(--space-3);
  }

  .pill-list span {
    border: 1px solid var(--divider);
    background: var(--surface-0);
    color: var(--text-1);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-xs);
    text-transform: none;
    letter-spacing: normal;
  }

  .pill-list span.short-pill {
    border-color: var(--negative);
    color: var(--negative);
  }

  .signed-book {
    border: 1px solid var(--divider);
    background: var(--surface-0);
    padding: var(--space-4) var(--space-4);
    margin-top: var(--space-4);
  }

  .focal-hint {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
    font-size: var(--text-sm);
    margin-top: var(--space-4);
  }

  /* ── Notes ── */
  .note-row {
    display: grid;
    grid-template-columns: 5rem minmax(0, 1fr);
    gap: var(--space-4);
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
    align-items: baseline;
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-row p {
    font-size: var(--text-sm);
    line-height: 1.4;
    color: var(--text-1);
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .note-row.info .note-tag,
  .note-row.info p {
    color: var(--accent);
  }

  /* ── Signal tints ── */
  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  .elevated { color: var(--data-warm); }

  .warning {
    color: var(--warning);
    font-size: var(--text-sm);
  }

  /* ── Responsive ── */
  @media (max-width: 1240px) {
    .workspace-grid,
    .detail-split,
    .overview-grid {
      grid-template-columns: 1fr;
    }

    .ranking-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .support-column {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .kpi-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  @media (max-width: 980px) {
    .support-column,
    .field-grid,
    .overview-bottom-grid,
    .ranking-grid,
    .builder-actions,
    .kpi-grid {
      grid-template-columns: 1fr;
    }

    .mode-bar {
      flex-wrap: wrap;
    }

    .treemap-canvas {
      min-height: 26rem;
    }

    .treemap-header {
      flex-direction: column;
      align-items: flex-start;
    }

    .treemap-header-right {
      justify-content: flex-start;
    }

    .metric {
      padding: var(--space-4) 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
    }

    .metric:first-child {
      padding-top: 0;
      border-top: 0;
    }

    .panel-header,
    .rail-header,
    .chart-foot,
    .section-head {
      flex-direction: column;
      align-items: stretch;
    }

    .header-actions {
      justify-content: stretch;
    }

    .header-actions > * {
      width: 100%;
    }

    .note-row {
      grid-template-columns: 1fr;
      gap: var(--space-2);
    }
  }
</style>
