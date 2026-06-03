<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "svelte/store";
  import BarRankChart, { type RankBarItem } from "../components/BarRankChart.svelte";
  import HeroPriceChart from "../components/HeroPriceChart.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    ResearchConstituent,
    ResearchCoverage,
    StrategyLabCompositionResult,
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
    StrategyLabHandoffQueueItem,
    StrategyLabResolvedHandoff,
    TimeSeriesPoint
  } from "../lib/api/types";
  import {
    researchDraft,
    setResearchDraft,
    type ResearchOverviewLoadOptions,
    type ResearchRunOptions,
    type ResearchCompareOptions,
    type SavedResearchCreateOptions,
    type StrategyLabAnalyzeOptions,
    type StrategyLabComposeOptions,
    type StrategyLabPortfolioComposeOptions
  } from "../lib/stores/app";
  import {
    buildResearchCompareOptions,
    buildEquityStrategyHandoff,
    buildStrategyComposerObjects,
    buildStrategyPortfolioLegInputs,
    buildResearchTreemapSections,
    buildPreviewRows,
    classifyResearchSurfaceMode,
    classifySavedResearchSurface,
    defaultStrategyPortfolioDraftLeg,
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
    parseResearchCsvText,
    parseSyntheticText,
    summarizeStrategyPortfolioDraft,
    researchSortMetricLabel,
    hydrateStrategyLabResultFromSaved,
    savedResearchCanReloadScope,
    savedResearchCanReloadStrategy,
    savedResearchHasReturnStream,
    savedResearchScopeDraft,
    strategyResolvedHandoffToDraftLeg,
    treemapDensityClass,
    treemapRectStyle,
    type ResearchCompareOption,
    type ResearchMode,
    type ResearchPreviewRow,
    type ResearchSurface,
    type ResearchSurfaceMode,
    type ResearchSurfaceModeKind,
    type StrategyPortfolioAssetClass,
    type StrategyPortfolioDraftLeg,
    type ResearchTreemapSection,
    type ResearchTreemapTile
  } from "../lib/view-models/research";
  import { heroPricePointFromApiPoint, type HeroPricePoint } from "../lib/view-models/hero-price-chart";

  export let surface: ResearchSurface = "legacy";
  export let mode: ResearchSurfaceMode = "overview";
  export let overview: ResearchOverviewResponse | null = null;
  export let result: ResearchResult | null = null;
  export let strategyResult: StrategyLabResult | null = null;
  export let strategyComposition: StrategyLabCompositionResult | null = null;
  export let compareResult: ResearchCompareResult | null = null;
  export let savedItems: SavedResearchItem[] = [];
  export let loading = false;
  export let overviewLoading = false;
  export let strategyLoading = false;
  export let compareLoading = false;
  export let savedLoading = false;
  export let selectedEquitySymbol: string | null = null;
  export let onLoadOverview: (options?: ResearchOverviewLoadOptions) => Promise<unknown> | void;
  export let onRun: (options: ResearchRunOptions) => void;
  export let onSelectEquity: ((symbol: string, label?: string | null) => void) | undefined = undefined;
  export let onAnalyzeStrategy: (options: StrategyLabAnalyzeOptions) => Promise<StrategyLabResult | null> | void;
  export let onComposeStrategy: (options: StrategyLabComposeOptions) => Promise<StrategyLabCompositionResult | null> | void = async () => null;
  export let onComposePortfolioStrategy: (options: StrategyLabPortfolioComposeOptions) => Promise<StrategyLabCompositionResult | null> | void = async () => null;
  export let onCompare: (options: ResearchCompareOptions) => Promise<ResearchCompareResult | null> | void;
  export let onLoadSaved: () => Promise<SavedResearchItem[]> | void;
  export let onSaveResearch: (options: SavedResearchCreateOptions) => Promise<SavedResearchItem | null> | void;
  export let onDeleteSaved: (itemId: string) => Promise<boolean> | void;
  export let onRestoreStrategy: ((result: StrategyLabResult) => void) | undefined = undefined;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let onOpenIv: (() => void) | undefined = undefined;
  export let onOpenStrategyLab: (() => void) | undefined = undefined;
  export let onSendToStrategyLab:
    | ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void)
    | undefined = undefined;
  export let strategyLabHandoffs: StrategyLabHandoffQueueItem[] = [];
  export let handoffLoading = false;
  export let onResolveStrategyLabHandoffs: (() => Promise<StrategyLabHandoffQueueItem[]> | void) | undefined = undefined;
  export let onDismissStrategyLabHandoff: ((id: string) => void) | undefined = undefined;
  export let onClearStrategyLabHandoffs: (() => void) | undefined = undefined;
  export let onAcceptStrategyLabHandoff: ((id: string) => StrategyLabResolvedHandoff | null | void) | undefined = undefined;

  type ChartMode =
    | "performance"
    | "relative"
    | "price"
    | "drawdown"
    | "rolling_vol"
    | "rolling_beta"
    | "rolling_corr";
  type ResearchTimeframe = "1M" | "3M" | "6M" | "1Y" | "MAX";

  const legacyResearchModes: Array<{ id: ResearchSurfaceMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "scope_analysis", label: "Scope Analysis" },
    { id: "strategy_lab", label: "Strategy Lab" },
    { id: "compare_scenario", label: "Compare / Scenario" },
    { id: "saved_research", label: "Saved Research" }
  ];
  const equityResearchModes: Array<{ id: ResearchSurfaceMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "scope_analysis", label: "Scope" },
    { id: "comparables", label: "Comparables" },
    { id: "scenario_context", label: "Scenario Context" },
    { id: "saved_equity_research", label: "Saved" }
  ];
  const strategyResearchModes: Array<{ id: ResearchSurfaceMode; label: string }> = [
    { id: "composer", label: "Composer" },
    { id: "backtest_analyze", label: "Backtest" },
    { id: "regime_stress", label: "Regime Stress" },
    { id: "imports", label: "Imports" },
    { id: "saved_runs", label: "Saved Runs" }
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
  let overviewUniverseId = "broad_us_market";
  let overviewTimeframe = "DoD";
  let overviewSortBy: ResearchOverviewSortId = "market_cap_desc";
  let overviewMetric: ResearchOverviewMetricId = "return";
  let overviewBenchmarkSymbol = "SPY";
  let selectedOverviewNodeId = "";
  let strategyName = "Imported Strategy";
  let strategyCsvText = `date,return,benchmark
2026-01-02,0.010,0.004
2026-01-05,-0.004,-0.002
2026-01-06,0.006,0.003
2026-01-07,0.002,0.001
2026-01-08,-0.003,-0.004
2026-01-09,0.008,0.005
2026-01-12,0.004,0.002
2026-01-13,0.001,-0.001`;
  let strategyDateColumn = "date";
  let strategyValueColumn = "return";
  let strategyValueKind: "return" | "level" = "return";
  let strategyBenchmarkColumn = "benchmark";
  let strategyBenchmarkValueKind: "return" | "level" = "return";
  let strategyInputWarning = "";
  let compareLeftSource = "";
  let compareRightSource = "";
  let compareWarning = "";
  let composerSelection: Record<string, boolean> = {};
  let composerWeights: Record<string, number> = {};
  let portfolioName = "Strategy Lab Portfolio";
  let portfolioBenchmarkSymbol = "SPY";
  let portfolioLookbackDays = 756;
  let portfolioDraftLegs: StrategyPortfolioDraftLeg[] = [
    { ...defaultStrategyPortfolioDraftLeg(1), label: "Long AI / Growth", assetClass: "etf", identifier: "QQQ", weight: 0.6 },
    { ...defaultStrategyPortfolioDraftLeg(2), label: "Short broad beta", assetClass: "etf", identifier: "SPY", weight: -0.4 },
    {
      ...defaultStrategyPortfolioDraftLeg(3),
      label: "Election contract proxy",
      assetClass: "prediction_contract",
      identifier: "PM-CONTRACT",
      weight: 0.1,
      valueKind: "level",
      historyText: "date,value\n2026-01-02,0.51\n2026-01-05,0.53\n2026-01-06,0.52\n2026-01-07,0.55\n2026-01-08,0.56\n2026-01-09,0.58"
    }
  ];
  let showHandoffReview = true;
  let acceptedHandoffWarnings: string[] = [];
  let savedScopeTitle = "Scope Analysis Run";
  let savedStrategyTitle = "Strategy Lab Run";
  let savedNotes = "";
  const portfolioAssetClasses: Array<{ id: StrategyPortfolioAssetClass; label: string }> = [
    { id: "equity", label: "Equity" },
    { id: "etf", label: "ETF" },
    { id: "commodity", label: "Commodity" },
    { id: "prediction_contract", label: "Prediction" },
    { id: "crypto", label: "Crypto" },
    { id: "custom_stream", label: "Custom" }
  ];
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

  function handleOverviewBenchmarkChange(event: Event) {
    const benchmarkSymbol = (event.currentTarget as HTMLInputElement).value.trim().toUpperCase() || "SPY";
    overviewBenchmarkSymbol = benchmarkSymbol;
    selectedOverviewNodeId = "";
    void loadOverview({ benchmarkSymbol });
  }

  function modeForSurface(target: ResearchMode): ResearchSurfaceMode {
    if (surface === "equity") {
      if (target === "compare_scenario") return "comparables";
      if (target === "saved_research") return "saved_equity_research";
      if (target === "strategy_lab") return "scope_analysis";
    }
    if (surface === "strategy") {
      if (target === "strategy_lab") return "composer";
      if (target === "compare_scenario") return "backtest_analyze";
      if (target === "saved_research") return "saved_runs";
      return "composer";
    }
    return target;
  }

  function selectResearchMode(nextMode: ResearchSurfaceMode) {
    mode = nextMode;
    const nextKind = classifyResearchSurfaceMode(surface, nextMode);
    if (nextKind === "overview" && !overview) {
      void loadOverview();
    }
    if (nextKind === "legacy_saved" || nextKind === "equity_saved" || nextKind === "strategy_saved") {
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
    mode = modeForSurface("scope_analysis");
    inputWarning = "";
  }

  async function analyzeStrategy() {
    const parsed = parseResearchCsvText(strategyCsvText);
    if (!parsed.rows.length) {
      strategyInputWarning = parsed.warnings[0] ?? "CSV rows are required.";
      return;
    }
    if (!parsed.columns.includes(strategyDateColumn) || !parsed.columns.includes(strategyValueColumn)) {
      strategyInputWarning = "Select valid date and return/NAV columns before analyzing.";
      return;
    }
    strategyInputWarning = parsed.warnings.length ? parsed.warnings.join(" ") : "";
    await onAnalyzeStrategy({
      name: strategyName.trim() || "Imported Strategy",
      rows: parsed.rows,
      dateColumn: strategyDateColumn,
      valueColumn: strategyValueColumn,
      valueKind: strategyValueKind,
      benchmarkColumn: strategyBenchmarkColumn && parsed.columns.includes(strategyBenchmarkColumn) ? strategyBenchmarkColumn : null,
      benchmarkValueKind: strategyBenchmarkValueKind,
      minObservations: 5
    });
  }

  async function composeSelectedObjects() {
    if (!selectedComposerLegs.length) {
      strategyInputWarning = "Select at least one return object before composing.";
      return;
    }
    strategyInputWarning = "";
    const result = await onComposeStrategy({
      name: "Strategy Lab Composition",
      legs: selectedComposerLegs,
      lenses: [],
      overlays: [],
      benchmarkObject: null,
      minObservations: 5
    });
    strategyComposition = result ?? null;
  }

  function addPortfolioDraftLeg() {
    portfolioDraftLegs = [...portfolioDraftLegs, defaultStrategyPortfolioDraftLeg(portfolioDraftLegs.length + 1)];
  }

  function removePortfolioDraftLeg(id: string) {
    portfolioDraftLegs = portfolioDraftLegs.length <= 1 ? portfolioDraftLegs : portfolioDraftLegs.filter((leg) => leg.id !== id);
  }

  function addComposerObjectToPortfolio(optionId: string) {
    const option = composerOptions.find((item) => item.id === optionId);
    if (!option) {
      return;
    }
    portfolioDraftLegs = [
      ...portfolioDraftLegs,
      {
        ...defaultStrategyPortfolioDraftLeg(portfolioDraftLegs.length + 1),
        label: option.label,
        assetClass: option.object.object_type.includes("crypto") ? "crypto" : "custom_stream",
        identifier: option.object.symbols[0] ?? "",
        weight: option.defaultWeight,
        objectOptionId: option.id
      }
    ];
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

  function acceptStrategyHandoff(item: StrategyLabHandoffQueueItem) {
    const resolved = item.resolved?.status === "resolved" ? item.resolved : null;
    if (!resolved) {
      strategyInputWarning = item.error ?? "Resolve this handoff before accepting it into the composer.";
      return;
    }
    const draftLeg = strategyResolvedHandoffToDraftLeg(resolved, portfolioDraftLegs.length + 1);
    if (!draftLeg) {
      strategyInputWarning = resolved.unsupported_reason ?? "Resolved handoff did not include a composer-ready leg.";
      return;
    }
    portfolioDraftLegs = [...portfolioDraftLegs, draftLeg];
    acceptedHandoffWarnings = [...resolved.warnings, ...acceptedHandoffWarnings].slice(0, 12);
    onAcceptStrategyLabHandoff?.(item.id);
    strategyInputWarning = "";
  }

  function acceptResolvedStrategyHandoffs() {
    const resolvedItems = strategyLabHandoffs.filter((item) => item.resolved?.status === "resolved");
    if (!resolvedItems.length) {
      strategyInputWarning = "Resolve pending Strategy Lab handoffs before accepting them.";
      return;
    }
    for (const item of resolvedItems) {
      acceptStrategyHandoff(item);
    }
  }

  async function composePortfolioDraft() {
    const built = buildStrategyPortfolioLegInputs(portfolioDraftLegs, composerOptions);
    const summary = summarizeStrategyPortfolioDraft(portfolioDraftLegs);
    const blockingWarnings = [...summary.warnings, ...built.warnings];
    if (!built.legs.length) {
      strategyInputWarning = blockingWarnings[0] ?? "Add at least one portfolio leg with usable history.";
      return;
    }
    strategyInputWarning = blockingWarnings.join(" ");
    const result = await onComposePortfolioStrategy({
      name: portfolioName.trim() || "Strategy Lab Portfolio",
      legs: built.legs,
      benchmarkSymbol: portfolioBenchmarkSymbol.trim().toUpperCase() || null,
      benchmarkObject: null,
      lookbackDays: portfolioLookbackDays,
      minObservations: 5
    });
    strategyComposition = result ?? null;
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
    if (option.source === "strategy" && activeStrategyResult?.returns_points?.length) {
      return {
        label: option.label,
        objectType: option.objectType,
        returnPoints: activeStrategyResult.returns_points
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

  async function saveStrategyRun() {
    if (!activeStrategyResult) {
      return;
    }
    await onSaveResearch({
      objectType: "strategy_lab",
      title: savedStrategyTitle.trim() || activeStrategyResult.name,
      notes: savedNotes,
      payload: { ...activeStrategyResult, saved_from_mode: "strategy_lab" },
      warnings: activeStrategyResult.warnings,
      sourceProvider: "uploaded_csv",
      origin: "frontend.research.strategy_lab.save",
      transformationNote: "Saved normalized uploaded return stream; raw uploaded file is not persisted."
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
    mode = modeForSurface("compare_scenario");
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
    mode = modeForSurface("scope_analysis");
  }

  function loadSavedStrategy(item: SavedResearchItem) {
    const hydrated = hydrateStrategyLabResultFromSaved(item);
    if (!hydrated) {
      return;
    }
    onRestoreStrategy?.(hydrated);
    strategyName = hydrated.name;
    strategyInputWarning = "Loaded normalized saved strategy result. Raw CSV rows were not persisted.";
    mode = modeForSurface("strategy_lab");
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

    const syntheticPositions = parsedSynthetic.filter((item) => Number.isFinite(item.weight) && item.weight > 0);
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

  function normalizeSynthetic() {
    syntheticText = normalizeSyntheticText(syntheticText);
    inputWarning = "";
  }

  function applyPreset(presetId: string) {
    const preset = presetBaskets.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }
    syntheticText = preset.text;
    inputWarning = "";
  }

  function resetBuilder() {
    scopeType = "single_ticker";
    primarySymbol = "AAPL";
    benchmarkSymbol = "SPY";
    lookbackDays = 252;
    syntheticText = presetBaskets[0]?.text ?? defaultPresetText;
    selectedPreset = presetBaskets[0]?.id ?? "index-core";
    inputWarning = "";
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

  let parsedSynthetic = parseSyntheticText(syntheticText);
  let parsedStrategyCsv = parseResearchCsvText(strategyCsvText);
  let previewRows: ResearchPreviewRow[] = [];
  let chartSeries: ChartSeries[] = [];
  let researchHeroPricePoints: HeroPricePoint[] = [];
  let strategyChartSeries: ChartSeries[] = [];
  let compareChartSeries: ChartSeries[] = [];
  let compareRelativeDrawdownSeries: ChartSeries[] = [];
  let stressDrawdownRows: TimeSeriesPoint[] = [];
  let rollingStressRows: StrategyLabResult["rolling_points"] = [];
  let strategyModeTitle = "Imported Return Stream";
  let strategyModeEyebrow = "Strategy Lab";
  let strategyModeSummary = "CSV rows are normalized into returns for analysis only. Gamma does not run strategy code or connect this stream to execution.";
  let compareModeTitle = "Return Stream Comparison";
  let compareModeEyebrow = "Compare / Scenario";
  let compareModeSummary = "Scenario output is normalized historical analytics only. It does not change broker portfolios or rebalance anything.";
  let compareOptions: ResearchCompareOption[] = [];
  let compareMetricRows: Array<{ label: string; left: number | null | undefined; right: number | null | undefined }> = [];
  let surfaceModeKind: ResearchSurfaceModeKind = "overview";
  let overviewModeActive = true;
  let scopeModeActive = false;
  let strategyModeActive = false;
  let compareModeActive = false;
  let savedModeActive = false;
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
  let researchHeadlineKPIs: Array<{
    label: string;
    value: string;
    delta?: string;
    tone?: "positive" | "negative";
  }> = [];

  function formatSignedPct(value: number | null | undefined, digits = 1) {
    if (value == null || !Number.isFinite(value)) {
      return "";
    }
    const scaled = value * 100;
    const sign = scaled > 0 ? "+" : "";
    return `${sign}${scaled.toFixed(digits)}%`;
  }

  function buildResearchHeadlineKPIs(currentOverview: ResearchOverviewResponse | null) {
    if (!currentOverview) {
      return [];
    }
    const kpis: Array<{ label: string; value: string; delta?: string; tone?: "positive" | "negative" }> = [];

    const leader = currentOverview.rankings?.leaders?.[0];
    if (leader && leader.value != null) {
      kpis.push({
        label: "Leader",
        value: leader.symbol ?? leader.label ?? "-",
        delta: formatSignedPct(leader.value),
        tone: leader.value >= 0 ? "positive" : "negative"
      });
    }

    const laggard = currentOverview.rankings?.laggards?.[0];
    if (laggard && laggard.value != null) {
      kpis.push({
        label: "Laggard",
        value: laggard.symbol ?? laggard.label ?? "-",
        delta: formatSignedPct(laggard.value),
        tone: laggard.value >= 0 ? "positive" : "negative"
      });
    }

    const leadingGroup = currentOverview.summary?.leading_group;
    if (leadingGroup && leadingGroup.value != null) {
      kpis.push({
        label: "Leading Group",
        value: leadingGroup.label ?? leadingGroup.group ?? "-",
        delta: formatSignedPct(leadingGroup.value),
        tone: leadingGroup.value >= 0 ? "positive" : "negative"
      });
    }

    const instrumentNodes = (currentOverview.nodes ?? []).filter((node) => node.level === "instrument");
    const pricedNodes = instrumentNodes.filter((node) => node.metrics?.total_return != null);
    if (pricedNodes.length) {
      const upCount = pricedNodes.filter((node) => (node.metrics?.total_return ?? 0) > 0).length;
      const ratio = upCount / pricedNodes.length;
      kpis.push({
        label: "Breadth",
        value: `${upCount}/${pricedNodes.length}`,
        delta: `${(ratio * 100).toFixed(0)}% up`,
        tone: ratio >= 0.5 ? "positive" : "negative"
      });
    }

    return kpis;
  }

  onMount(() => {
    if (classifyResearchSurfaceMode(surface, mode) === "overview" && !overview) {
      void loadOverview();
    }
  });

  $: parsedSynthetic = parseSyntheticText(syntheticText);
  $: parsedStrategyCsv = parseResearchCsvText(strategyCsvText);
  $: {
    if (parsedStrategyCsv.columns.length) {
      if (!parsedStrategyCsv.columns.includes(strategyDateColumn)) {
        strategyDateColumn = parsedStrategyCsv.columns[0] ?? "date";
      }
      if (!parsedStrategyCsv.columns.includes(strategyValueColumn)) {
        strategyValueColumn = parsedStrategyCsv.columns.find((column) => /ret|return|nav|level|equity/i.test(column)) ?? parsedStrategyCsv.columns[1] ?? parsedStrategyCsv.columns[0] ?? "return";
      }
      if (strategyBenchmarkColumn && !parsedStrategyCsv.columns.includes(strategyBenchmarkColumn)) {
        strategyBenchmarkColumn = "";
      }
    }
  }
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
    if (normalizedSelectedEquity && normalizedSelectedEquity !== primarySymbol.trim().toUpperCase()) {
      scopeType = "single_ticker";
      primarySymbol = normalizedSelectedEquity;
      inputWarning = "";
    }
  }
  $: savedResearchList = Array.isArray(savedItems) ? savedItems : [];
  $: activeStrategyResult = strategyComposition ?? strategyResult;
  $: surfaceModeKind = classifyResearchSurfaceMode(surface, mode);
  $: overviewModeActive = surfaceModeKind === "overview";
  $: scopeModeActive = surfaceModeKind === "scope_analysis";
  $: strategyModeActive =
    surfaceModeKind === "legacy_strategy" ||
    surfaceModeKind === "strategy_composer" ||
    surfaceModeKind === "strategy_backtest" ||
    surfaceModeKind === "strategy_regime" ||
    surfaceModeKind === "strategy_imports";
  $: compareModeActive =
    surfaceModeKind === "legacy_compare" ||
    surfaceModeKind === "equity_comparables" ||
    surfaceModeKind === "equity_scenario_context";
  $: savedModeActive = surfaceModeKind === "legacy_saved" || surfaceModeKind === "equity_saved" || surfaceModeKind === "strategy_saved";
  $: compareOptions = buildResearchCompareOptions(result, activeStrategyResult, savedResearchList);
  $: visibleSavedItems = savedResearchList.filter((item) => {
    if (surface === "legacy") {
      return true;
    }
    const classification = classifySavedResearchSurface(item);
    return surface === "equity" ? classification === "equity" : classification === "strategy";
  });
  $: composerOptions = buildStrategyComposerObjects(result, strategyResult, visibleSavedItems);
  $: {
    const knownIds = new Set(composerOptions.map((option) => option.id));
    composerSelection = Object.fromEntries(
      composerOptions.map((option, index) => [
        option.id,
        composerSelection[option.id] ?? index < Math.min(2, composerOptions.length)
      ])
    );
    composerWeights = Object.fromEntries(
      composerOptions.map((option) => [option.id, composerWeights[option.id] ?? option.defaultWeight])
    );
    for (const id of Object.keys(composerSelection)) {
      if (!knownIds.has(id)) {
        delete composerSelection[id];
        delete composerWeights[id];
      }
    }
  }
  $: selectedComposerLegs = composerOptions
    .filter((option) => composerSelection[option.id])
    .map((option) => ({
      object: option.object,
      weight: Number(composerWeights[option.id] ?? option.defaultWeight)
    }))
    .filter((leg) => Number.isFinite(leg.weight) && leg.weight !== 0);
  $: portfolioDraftSummary = summarizeStrategyPortfolioDraft(portfolioDraftLegs);
  $: portfolioDraftBuild = buildStrategyPortfolioLegInputs(portfolioDraftLegs, composerOptions);
  $: visibleResearchModes =
    surface === "equity" ? equityResearchModes : surface === "strategy" ? strategyResearchModes : legacyResearchModes;
  $: surfaceTitle =
    surface === "equity" ? "Equity Research" : surface === "strategy" ? "Strategy Lab" : "Research Workspace";
  $: surfaceSubtitle =
    surface === "equity"
      ? "Market map / scope / scenarios"
      : surface === "strategy"
        ? "Composer / backtests / saved runs"
        : "Strategy backtests / saved screens";
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
  $: researchHeadlineKPIs = buildResearchHeadlineKPIs(overview);
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
    })),
    drawdowns: (overview?.rankings.largest_drawdowns ?? []).map((item) => ({
      label: item.symbol ?? item.label,
      value: item.value ?? 0,
      tone: "negative",
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
              color: "#c49a5a",
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
              color: "#d1645d",
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
              color: "#9bd19f",
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
              color: chartMode === "rolling_beta" ? "#c49a5a" : "#d8c17a",
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
              color: "#ff9f5a",
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
          color: "#7aa6c8",
          type: "area",
          data: cumulativeFromReturns(perf)
        });
      }
      if (benchmark.length) {
        series.push({
          id: "benchmark",
          label: result.benchmark_symbol,
          color: "#c49a5a",
          type: "line",
          lineStyle: "dashed",
          data: cumulativeFromReturns(benchmark)
        });
      }
      chartSeries = series;
    }
  }
  $: strategyChartSeries = activeStrategyResult
    ? [
        ...(activeStrategyResult.equity_curve_points.length
          ? [
              {
                id: "strategy",
                label: activeStrategyResult.name,
                color: "#7aa6c8",
                type: "area" as const,
                data: activeStrategyResult.equity_curve_points.map(toChartPoint)
              }
            ]
          : []),
        ...(activeStrategyResult.benchmark_equity_curve_points.length
          ? [
              {
                id: "benchmark",
                label: activeStrategyResult.benchmark_column ?? "Benchmark",
                color: "#c49a5a",
                type: "line" as const,
                lineStyle: "dashed" as const,
                data: activeStrategyResult.benchmark_equity_curve_points.map(toChartPoint)
              }
            ]
          : [])
      ]
    : [];
  $: stressDrawdownRows = [...(activeStrategyResult?.drawdown_points ?? [])]
    .filter((point) => Number.isFinite(point.value))
    .sort((left, right) => left.value - right.value)
    .slice(0, 8);
  $: rollingStressRows = [...(activeStrategyResult?.rolling_points ?? [])].slice(-12);
  $: strategyModeTitle =
    surfaceModeKind === "strategy_composer"
      ? "Gamma Object Composer"
      : surfaceModeKind === "strategy_imports" || surfaceModeKind === "legacy_strategy"
        ? "Return Stream Import"
        : surfaceModeKind === "strategy_regime"
          ? "Regime / Stress Lens"
          : "Backtest / Analyze";
  $: strategyModeEyebrow =
    surfaceModeKind === "strategy_composer"
      ? "Strategy Composer"
      : surfaceModeKind === "strategy_imports" || surfaceModeKind === "legacy_strategy"
        ? "CSV Import"
        : surfaceModeKind === "strategy_regime"
          ? "Strategy Stress"
          : "Strategy Analytics";
  $: strategyModeSummary =
    surfaceModeKind === "strategy_composer"
      ? "Compose return-bearing Gamma objects into a read-only strategy result. Weights are normalized by the backend."
      : surfaceModeKind === "strategy_imports" || surfaceModeKind === "legacy_strategy"
        ? "Paste or map an external return stream. Gamma validates and normalizes the data without executing strategy code."
        : surfaceModeKind === "strategy_regime"
          ? "Inspect drawdown windows, rolling beta, and rolling correlation to identify where the imported stream is fragile."
          : "Review normalized performance, benchmark-relative behavior, rolling risk, and period returns for the active strategy stream.";
  $: compareChartSeries = compareResult
    ? [
        {
          id: "left",
          label: compareResult.left.label,
          color: "#7aa6c8",
          type: "area" as const,
          data: compareResult.left.normalized_nav_points.map(toChartPoint)
        },
        {
          id: "right",
          label: compareResult.right.label,
          color: "#c49a5a",
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
          color: "#c66b61",
          type: "area" as const,
          invertFilledArea: true,
          data: compareResult.relative_drawdown_points.map(toChartPoint)
        }
      ]
    : [];
  $: compareModeEyebrow =
    surfaceModeKind === "equity_comparables"
      ? "Equity Comparables"
      : surfaceModeKind === "equity_scenario_context"
        ? "Scenario / Context"
        : "Compare / Scenario";
  $: compareModeTitle =
    surfaceModeKind === "equity_comparables"
      ? compareResult
        ? `${compareResult.left.label} vs ${compareResult.right.label}`
        : "Peer And Benchmark Comparison"
      : surfaceModeKind === "equity_scenario_context"
        ? activeHeadline(result)
        : compareResult
          ? `${compareResult.left.label} vs ${compareResult.right.label}`
          : "Return Stream Comparison";
  $: compareModeSummary =
    surfaceModeKind === "equity_comparables"
      ? "Compare the active equity scope against saved scopes, strategy streams, or benchmarks using aligned return windows."
      : surfaceModeKind === "equity_scenario_context"
        ? "Frame the active scope for Risk, Options, Strategy Lab, and saved-object reuse without modifying any portfolio."
        : "Scenario output is normalized historical analytics only. It does not change broker portfolios or rebalance anything.";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">{surfaceTitle}</span>
      <span class="subtitle">{surfaceSubtitle}</span>
      {#if loading || overviewLoading || strategyLoading || compareLoading || savedLoading}<span class="loading-pill">Refreshing</span>{/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label={`${surfaceTitle} modes`}>
        {#each visibleResearchModes as item}
          <button
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

          <div class="treemap-canvas" aria-label={`Research overview treemap sized by ${researchSortMetricLabel(overviewSortBy)} and colored by ${overviewMetricLabels[overviewMetric]}`}>
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
                        aria-label={`${section.label}. ${tile.node.label}. ${overviewMetricLabels[overviewMetric]} ${formatResearchOverviewMetricValue(tile.colorValue, overviewMetric)}. ${researchSortMetricLabel(overviewSortBy)} ${formatResearchOverviewSortValue(tile.metricValue, overviewSortBy)}`}
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
                    <dt>{overviewMetricLabels[overviewMetric]}</dt>
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
          <div class="panel-header"><div><p class="eyebrow">Leaders</p><h3>Leading Names</h3></div></div>
          <BarRankChart items={overviewRankingBars.leaders ?? []} emptyMessage="No leader data." formatValue={(value) => formatResearchOverviewMetricValue(value, "return")} />
        </article>
        <article class="panel">
          <div class="panel-header"><div><p class="eyebrow">Laggards</p><h3>Lagging Names</h3></div></div>
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
            <div class="row"><span>Return</span><strong>{formatResearchOverviewMetricValue(selectedOverviewNode ? getResearchOverviewMetricValue(selectedOverviewNode, "return") : null, "return")}</strong></div>
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

        <div class="kpi-grid">
          <article class="metric">
            <span>Total Return</span>
            <strong class:positive={(result?.summary.total_return ?? 0) > 0} class:negative={(result?.summary.total_return ?? 0) < 0}>{pct(result?.summary.total_return)}</strong>
            <small>{result?.observations_count ?? 0} aligned observations</small>
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
              Shared research return stream against {result.benchmark_symbol}
            {:else}
              Run a scope to seed the chart deck.
            {/if}
          </span>
          <strong>{result?.scope_type === "synthetic_portfolio" ? `${coverageMetrics.available_symbols.length} symbols in scope` : activePrimaryScopeLabel(result)}</strong>
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
        <div class="panel-header">
          <div>
            <p class="eyebrow">Constituents</p>
            <h3>Constituent Detail</h3>
          </div>
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
                  <tr>
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

        <div class="builder-actions">
          <button on:click={submit} disabled={loading}>{loading ? "Running..." : "Run Analysis"}</button>
          <button type="button" class="ghost-button" on:click={resetBuilder}>Reset Builder</button>
          {#if surface === "equity" && scopeType === "single_ticker"}
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
                    <tr>
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
          <button type="button" on:click={() => onOpenRisk?.()} disabled={!result?.snapshot}>Open In Risk</button>
          <button type="button" class="ghost-button" on:click={() => onOpenIv?.()} disabled={result?.scope_type !== "single_ticker"}>Open In Options</button>
          {#if surface === "equity"}
            <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(false)} disabled={!activeEquityHandoffSymbol()}>+ Strategy</button>
            <button type="button" class="ghost-button" on:click={() => sendActiveEquityToStrategyLab(true)} disabled={!activeEquityHandoffSymbol()}>Add &amp; Open</button>
          {/if}
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
  {:else if strategyModeActive}
    <div class="workspace-grid">
      <div class="primary-column">
        {#if surfaceModeKind === "strategy_composer"}
          {#if strategyLabHandoffs.length}
            <article class="panel handoff-panel">
              <div class="handoff-strip">
                <div class="title-block">
                  <p class="eyebrow">Inbound Handoffs</p>
                  <h3>{strategyLabHandoffs.length} pending object{strategyLabHandoffs.length === 1 ? "" : "s"}</h3>
                  <p class="muted">
                    {strategyLabHandoffs.filter((item) => item.status === "resolved").length} resolved /
                    {strategyLabHandoffs.filter((item) => item.status === "pending" || item.status === "error").length} awaiting resolver
                  </p>
                </div>
                <div class="builder-actions compact">
                  <button type="button" class="ghost-button" on:click={() => showHandoffReview = !showHandoffReview}>
                    {showHandoffReview ? "Hide" : "Review"}
                  </button>
                  <button type="button" class="ghost-button" on:click={() => onResolveStrategyLabHandoffs?.()} disabled={handoffLoading}>
                    {handoffLoading ? "Resolving..." : "Resolve"}
                  </button>
                  <button type="button" on:click={acceptResolvedStrategyHandoffs} disabled={handoffLoading}>
                    Accept All
                  </button>
                  <button type="button" class="ghost-button" on:click={() => onClearStrategyLabHandoffs?.()}>
                    Clear
                  </button>
                </div>
              </div>

              {#if showHandoffReview}
                <div class="handoff-list">
                  {#each strategyLabHandoffs as item}
                    <div class="handoff-row">
                      <div>
                        <strong>{item.handoff.selected_entity.label}</strong>
                        <small>
                          {item.handoff.source_tab} / {item.handoff.asset_class} / {item.status}
                          {item.resolved?.date_coverage ? ` / ${item.resolved.date_coverage.start?.slice(0, 10)} - ${item.resolved.date_coverage.end?.slice(0, 10)}` : ""}
                        </small>
                      </div>
                      <div class="handoff-actions">
                        <button type="button" on:click={() => acceptStrategyHandoff(item)} disabled={item.resolved?.status !== "resolved"}>
                          Accept
                        </button>
                        <button type="button" class="ghost-button" on:click={() => onDismissStrategyLabHandoff?.(item.id)}>
                          Dismiss
                        </button>
                      </div>
                      {#if item.resolved?.warnings?.length || item.error}
                        <div class="handoff-warnings">
                          {#each (item.resolved?.warnings ?? [item.error]).filter(Boolean).slice(0, 4) as warning}
                            <span>{warning}</span>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </article>
          {/if}

          <article class="panel table-panel">
            <div class="panel-header top-line">
              <div class="title-block">
                <p class="eyebrow">Strategy Composer</p>
                <h2>Mixed Portfolio Engine</h2>
                <p class="muted">Build signed research books from listed histories, inline contract/commodity histories, and reusable Gamma objects. Gross exposure is normalized by the backend.</p>
              </div>
              <div class="builder-actions compact">
                <button type="button" class="ghost-button" on:click={addPortfolioDraftLeg}>Add Leg</button>
                <button type="button" on:click={composePortfolioDraft} disabled={strategyLoading || !portfolioDraftBuild.legs.length}>
                  {strategyLoading ? "Composing..." : "Compose Portfolio"}
                </button>
              </div>
            </div>

            <div class="field-grid compact-fields">
              <label><span>Name</span><input bind:value={portfolioName} /></label>
              <label><span>Benchmark</span><input bind:value={portfolioBenchmarkSymbol} /></label>
              <label><span>Lookback</span><input type="number" min="20" step="20" bind:value={portfolioLookbackDays} /></label>
            </div>

            <div class="kpi-grid compact-kpis">
              <article class="metric"><span>Gross</span><strong>{fmt(portfolioDraftSummary.grossExposure, 2)}x</strong><small>{portfolioDraftSummary.legCount} active legs</small></article>
              <article class="metric"><span>Net</span><strong class:negative={portfolioDraftSummary.netExposure < 0}>{fmt(portfolioDraftSummary.netExposure, 2)}x</strong><small>{fmt(portfolioDraftSummary.longExposure, 2)} long / {fmt(portfolioDraftSummary.shortExposure, 2)} short</small></article>
              <article class="metric"><span>Listed</span><strong>{portfolioDraftSummary.listedIdentifierLegs}</strong><small>provider-resolved</small></article>
              <article class="metric"><span>Inline</span><strong>{portfolioDraftSummary.inlineHistoryLegs}</strong><small>dated histories</small></article>
              <article class="metric"><span>Objects</span><strong>{portfolioDraftSummary.objectLegs}</strong><small>Gamma streams</small></article>
            </div>

            <div class="table-wrap compact-table">
              <table>
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Class</th>
                    <th>Identifier / Object</th>
                    <th class="num-cell">Weight</th>
                    <th>History</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {#each portfolioDraftLegs as leg}
                    <tr>
                      <td><input class="compact-input wide" bind:value={leg.label} placeholder="Leg label" /></td>
                      <td>
                        <select class="compact-input" bind:value={leg.assetClass}>
                          {#each portfolioAssetClasses as assetClass}
                            <option value={assetClass.id}>{assetClass.label}</option>
                          {/each}
                        </select>
                      </td>
                      <td>
                        <div class="stack tight">
                          <input class="compact-input wide" bind:value={leg.identifier} placeholder="Ticker / contract id" />
                          <select class="compact-input" bind:value={leg.objectOptionId}>
                            <option value="">Provider / inline history</option>
                            {#each composerOptions as option}
                              <option value={option.id}>{option.label}</option>
                            {/each}
                          </select>
                        </div>
                      </td>
                      <td class="num-cell">
                        <input class="compact-input" type="number" step="0.05" bind:value={leg.weight} />
                      </td>
                      <td>
                        <div class="stack tight">
                          <select class="compact-input" bind:value={leg.valueKind}>
                            <option value="return">Returns</option>
                            <option value="level">Level / probability</option>
                          </select>
                          <textarea class="history-input" bind:value={leg.historyText} placeholder="date,value rows for contracts, commodities, custom streams"></textarea>
                        </div>
                      </td>
                      <td class="num-cell"><button type="button" class="ghost-button" on:click={() => removePortfolioDraftLeg(leg.id)}>Remove</button></td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            {#if portfolioDraftSummary.warnings.length || portfolioDraftBuild.warnings.length}
              <div class="warning-list compact-warning-list">
                {#each [...portfolioDraftSummary.warnings, ...portfolioDraftBuild.warnings].slice(0, 5) as warning}
                  <span>{warning}</span>
                {/each}
              </div>
            {/if}
            {#if acceptedHandoffWarnings.length}
              <div class="warning-list compact-warning-list">
                {#each acceptedHandoffWarnings.slice(0, 5) as warning}
                  <span>{warning}</span>
                {/each}
              </div>
            {/if}
          </article>

          <article class="panel table-panel">
            <div class="table-panel-header">Reusable Gamma Objects</div>
            <div class="table-wrap compact-table">
              <table>
                <thead>
                  <tr><th>Use</th><th>Object</th><th>Type</th><th class="num-cell">Weight</th><th></th></tr>
                </thead>
                <tbody>
                  {#if composerOptions.length}
                    {#each composerOptions as option}
                      <tr>
                        <td><input type="checkbox" bind:checked={composerSelection[option.id]} /></td>
                        <td>{option.label}</td>
                        <td>{option.object.object_type}</td>
                        <td class="num-cell">
                          <input class="compact-input" type="number" step="0.05" bind:value={composerWeights[option.id]} />
                        </td>
                        <td class="num-cell"><button type="button" class="ghost-button" on:click={() => addComposerObjectToPortfolio(option.id)}>Add</button></td>
                      </tr>
                    {/each}
                  {:else}
                    <tr><td colspan="5">Run Scope Analysis, import CSV returns, or save a Strategy Lab return stream to compose objects.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
            <div class="builder-actions compact object-compose-actions">
              <button type="button" class="ghost-button" on:click={composeSelectedObjects} disabled={strategyLoading || !selectedComposerLegs.length}>
                {strategyLoading ? "Composing..." : "Compose Selected Objects"}
              </button>
            </div>
          </article>
          {#if strategyComposition}
            <article class="panel">
              <div class="panel-header">
                <div>
                  <p class="eyebrow">Composition Result</p>
                  <h3>{strategyComposition.name}</h3>
                </div>
                <small>{strategyComposition.returns_points.length} return points</small>
              </div>
              <div class="kpi-grid">
                <article class="metric"><span>Total Return</span><strong>{pct(strategyComposition.metrics.total_return)}</strong><small>{strategyComposition.metrics.observation_count} observations</small></article>
                <article class="metric"><span>Annual Vol</span><strong>{pct(strategyComposition.metrics.annual_volatility)}</strong><small>{strategyComposition.metrics.frequency}</small></article>
                <article class="metric"><span>Max Drawdown</span><strong class:negative={(strategyComposition.metrics.max_drawdown ?? 0) < 0}>{pct(strategyComposition.metrics.max_drawdown)}</strong><small>{strategyComposition.metrics.max_drawdown_duration} periods</small></article>
                <article class="metric"><span>Contributions</span><strong>{Object.keys(strategyComposition.leg_contributions).length}</strong><small>weighted legs</small></article>
              </div>
            </article>
          {/if}
        {/if}

        <article class="panel performance-panel">
          <div class="panel-header top-line">
            <div class="title-block">
              <p class="eyebrow">{strategyModeEyebrow}</p>
              <h2>{activeStrategyResult?.name ?? strategyModeTitle}</h2>
              <p class="muted">{strategyModeSummary}</p>
            </div>
            <div class="builder-actions compact">
              <button type="button" on:click={saveStrategyRun} disabled={!activeStrategyResult || savedLoading}>Save Strategy</button>
            </div>
          </div>

          <div class="kpi-grid">
            <article class="metric"><span>Total Return</span><strong>{pct(activeStrategyResult?.metrics.total_return)}</strong><small>{activeStrategyResult?.metrics.observation_count ?? 0} observations</small></article>
            <article class="metric"><span>Annual Return</span><strong>{pct(activeStrategyResult?.metrics.annual_return)}</strong><small>{activeStrategyResult?.metrics.frequency ?? "unknown"} frequency</small></article>
            <article class="metric"><span>Annual Vol</span><strong>{pct(activeStrategyResult?.metrics.annual_volatility)}</strong><small>Inferred periods {fmt(activeStrategyResult?.metrics.periods_per_year, 0)}</small></article>
            <article class="metric"><span>Sharpe</span><strong>{fmt(activeStrategyResult?.metrics.sharpe_ratio, 2)}</strong><small>Zero risk-free assumption</small></article>
            <article class="metric"><span>Sortino</span><strong>{fmt(activeStrategyResult?.metrics.sortino_ratio, 2)}</strong><small>Downside deviation</small></article>
            <article class="metric"><span>Max Drawdown</span><strong class:negative={(activeStrategyResult?.metrics.max_drawdown ?? 0) < 0}>{pct(activeStrategyResult?.metrics.max_drawdown)}</strong><small>{activeStrategyResult?.metrics.max_drawdown_duration ?? 0} periods</small></article>
          </div>

          <TimeSeriesChart series={strategyChartSeries} height={360} emptyMessage="Import CSV returns to populate Strategy Lab." />
          <div class="chart-foot">
            <span>{activeStrategyResult ? `Source ${activeStrategyResult.source_provider} / ${activeStrategyResult.freshness_label}` : "Paste CSV text or map parsed rows from a file outside Gamma."}</span>
            <strong>{activeStrategyResult ? shortDate(activeStrategyResult.retrieved_at) : "No import analyzed"}</strong>
          </div>
        </article>

        {#if surfaceModeKind === "strategy_imports" || surfaceModeKind === "legacy_strategy"}
          <article class="panel table-panel">
            <div class="panel-header top-line">
              <div class="title-block">
                <p class="eyebrow">Import Preview</p>
                <h3>Parsed CSV Rows</h3>
                <p class="muted">Map the date, value, and optional benchmark columns before analysis. Raw uploaded rows are not persisted by default.</p>
              </div>
              <small>{parsedStrategyCsv.rows.length} rows / {parsedStrategyCsv.columns.length} columns</small>
            </div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr>{#each parsedStrategyCsv.columns.slice(0, 5) as column}<th>{column}</th>{/each}</tr></thead>
                <tbody>
                  {#if parsedStrategyCsv.rows.length}
                    {#each parsedStrategyCsv.rows.slice(0, 8) as row}
                      <tr>{#each parsedStrategyCsv.columns.slice(0, 5) as column}<td>{row[column] ?? ""}</td>{/each}</tr>
                    {/each}
                  {:else}
                    <tr><td colspan={Math.max(parsedStrategyCsv.columns.slice(0, 5).length, 1)}>Paste CSV text to inspect parsed rows.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>
        {/if}

        {#if surfaceModeKind === "strategy_regime"}
          <div class="detail-split">
            <article class="panel table-panel">
              <div class="panel-header"><div><p class="eyebrow">Stress Windows</p><h3>Worst Drawdowns</h3></div><small>{stressDrawdownRows.length} points</small></div>
              <div class="table-wrap compact-table">
                <table>
                  <thead><tr><th>Date</th><th>Drawdown</th></tr></thead>
                  <tbody>
                    {#if stressDrawdownRows.length}
                      {#each stressDrawdownRows as point}
                        <tr><td>{shortDate(point.timestamp)}</td><td>{pct(point.value)}</td></tr>
                      {/each}
                    {:else}
                      <tr><td colspan="2">No drawdown series yet.</td></tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </article>

            <article class="panel table-panel">
              <div class="panel-header"><div><p class="eyebrow">Rolling Risk</p><h3>Recent Regime Read</h3></div><small>{rollingStressRows.length} windows</small></div>
              <div class="table-wrap compact-table">
                <table>
                  <thead><tr><th>Date</th><th>Roll Ret</th><th>Vol</th><th>Beta</th><th>Corr</th></tr></thead>
                  <tbody>
                    {#if rollingStressRows.length}
                      {#each rollingStressRows as row}
                        <tr>
                          <td>{shortDate(row.timestamp)}</td>
                          <td>{pct(row.rolling_return)}</td>
                          <td>{pct(row.rolling_volatility)}</td>
                          <td>{fmt(row.rolling_beta, 2)}</td>
                          <td>{fmt(row.rolling_correlation, 2)}</td>
                        </tr>
                      {/each}
                    {:else}
                      <tr><td colspan="5">No rolling windows yet.</td></tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </article>
          </div>
        {:else}
        <div class="detail-split">
          <article class="panel table-panel">
            <div class="panel-header"><div><p class="eyebrow">Monthly</p><h3>Monthly Returns</h3></div><small>{activeStrategyResult?.monthly_returns.length ?? 0} periods</small></div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Period</th><th>Return</th></tr></thead>
                <tbody>
                  {#if activeStrategyResult?.monthly_returns.length}
                    {#each activeStrategyResult.monthly_returns.slice(-18) as row}
                      <tr><td>{row.period}</td><td>{pct(row.value)}</td></tr>
                    {/each}
                  {:else}
                    <tr><td colspan="2">No monthly table yet.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel table-panel">
            <div class="panel-header"><div><p class="eyebrow">Annual</p><h3>Annual Returns</h3></div><small>{activeStrategyResult?.annual_returns.length ?? 0} periods</small></div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Period</th><th>Return</th></tr></thead>
                <tbody>
                  {#if activeStrategyResult?.annual_returns.length}
                    {#each activeStrategyResult.annual_returns as row}
                      <tr><td>{row.period}</td><td>{pct(row.value)}</td></tr>
                    {/each}
                  {:else}
                    <tr><td colspan="2">No annual table yet.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>
        </div>
        {/if}
      </div>

      <aside class="support-column">
        {#if surfaceModeKind === "strategy_imports" || surfaceModeKind === "legacy_strategy"}
        <article class="panel control-panel">
          <div class="rail-header">
            <div><p class="eyebrow">CSV Import</p><h3>Return Stream Mapping</h3></div>
            <strong>{parsedStrategyCsv.rows.length} rows</strong>
          </div>

          <label><span>Name</span><input bind:value={strategyName} /></label>
          <label><span>CSV Text</span><textarea bind:value={strategyCsvText} rows="10" spellcheck="false"></textarea></label>

          <div class="field-grid">
            <label><span>Date</span><select bind:value={strategyDateColumn}>{#each parsedStrategyCsv.columns as column}<option value={column}>{column}</option>{/each}</select></label>
            <label><span>Value</span><select bind:value={strategyValueColumn}>{#each parsedStrategyCsv.columns as column}<option value={column}>{column}</option>{/each}</select></label>
            <label><span>Kind</span><select bind:value={strategyValueKind}><option value="return">Return</option><option value="level">NAV / Level</option></select></label>
          </div>

          <div class="field-grid">
            <label><span>Benchmark</span><select bind:value={strategyBenchmarkColumn}><option value="">None</option>{#each parsedStrategyCsv.columns as column}<option value={column}>{column}</option>{/each}</select></label>
            <label><span>Bench Kind</span><select bind:value={strategyBenchmarkValueKind}><option value="return">Return</option><option value="level">NAV / Level</option></select></label>
            <div class="builder-actions compact"><button type="button" on:click={analyzeStrategy} disabled={strategyLoading}>{strategyLoading ? "Analyzing..." : "Analyze"}</button></div>
          </div>

          {#if strategyInputWarning || parsedStrategyCsv.warnings.length}
            <div class="notes-list">
              {#if strategyInputWarning}<div class="note-row"><span class="note-tag">CSV</span><p>{strategyInputWarning}</p></div>{/if}
              {#each parsedStrategyCsv.warnings as warning}
                <div class="note-row info"><span class="note-tag">Parse</span><p>{warning}</p></div>
              {/each}
            </div>
          {/if}
        </article>
        {:else}
        <article class="panel rail-panel">
          <div class="rail-header"><div><p class="eyebrow">Mode Context</p><h3>{strategyModeTitle}</h3></div></div>
          <div class="stack">
            <div class="row"><span>Active Stream</span><strong>{activeStrategyResult?.name ?? "N/A"}</strong></div>
            <div class="row"><span>Return Points</span><strong>{activeStrategyResult?.returns_points.length ?? 0}</strong></div>
            <div class="row"><span>Benchmark Points</span><strong>{activeStrategyResult?.benchmark_points.length ?? 0}</strong></div>
            <div class="row"><span>Rolling Windows</span><strong>{activeStrategyResult?.rolling_points.length ?? 0}</strong></div>
            <div class="row"><span>Saved Runs</span><strong>{visibleSavedItems.length}</strong></div>
          </div>
          {#if surfaceModeKind === "strategy_composer"}
            <p class="muted">Composer can combine the latest scope, latest imported stream, and saved return streams into a normalized read-only object.</p>
          {:else if surfaceModeKind === "strategy_regime"}
            <p class="muted">Regime/stress uses the current return stream only; macro-aware regime joins can be layered later without changing the import contract.</p>
          {:else}
            <p class="muted">Backtest/analyze uses the latest imported or composed stream and preserves uploaded-source provenance.</p>
          {/if}
        </article>
        {/if}

        <article class="panel rail-panel">
          <div class="rail-header"><div><p class="eyebrow">Source</p><h3>Warnings &amp; Provenance</h3></div></div>
          {#if activeStrategyResult?.warnings.length}
            <div class="notes-list">
              {#each activeStrategyResult.warnings as warning}
                <div class="note-row info"><span class="note-tag">Note</span><p>{warning}</p></div>
              {/each}
            </div>
          {:else}
            <p class="muted">No uploaded return stream has been analyzed yet.</p>
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

        {#if surfaceModeKind === "equity_scenario_context"}
          <article class="panel">
            <div class="panel-header top-line">
              <div class="title-block">
                <p class="eyebrow">Scope Context</p>
                <h3>Forwardable Research State</h3>
              </div>
              <div class="builder-actions compact">
                <button type="button" on:click={() => onOpenRisk?.()} disabled={!result?.snapshot}>Risk</button>
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
          <div class="panel-header"><div><p class="eyebrow">Metrics</p><h3>Side-by-Side</h3></div></div>
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
          <div class="rail-header"><div><p class="eyebrow">{surfaceModeKind === "equity_scenario_context" ? "Scenario Objects" : "Comparable Objects"}</p><h3>Select Streams</h3></div><strong>{compareOptions.length} available</strong></div>
          <label><span>Left</span><select bind:value={compareLeftSource}>{#each compareOptions as option}<option value={option.id}>{option.label}</option>{/each}</select></label>
          <label><span>Right</span><select bind:value={compareRightSource}>{#each compareOptions as option}<option value={option.id}>{option.label}</option>{/each}</select></label>
          <div class="builder-actions"><button type="button" on:click={runComparison} disabled={compareLoading || compareOptions.length < 2}>{compareLoading ? "Comparing..." : "Run Compare"}</button></div>
          {#if compareWarning}<p class="warning">{compareWarning}</p>{/if}
        </article>

        {#if surfaceModeKind === "equity_comparables"}
          <article class="panel table-panel">
            <div class="panel-header"><div><p class="eyebrow">Scope Peers</p><h3>Constituent Comparison</h3></div><small>{constituentRows.length} rows</small></div>
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
          <div class="panel-header top-line">
            <div class="title-block">
              <p class="eyebrow">Saved Research</p>
              <h2>Reusable Research Objects</h2>
              <p class="muted">Saved items store normalized results and metadata. Uploaded raw files are not persisted by default.</p>
            </div>
            <div class="builder-actions compact"><button type="button" class="ghost-button" on:click={() => void onLoadSaved()} disabled={savedLoading}>{savedLoading ? "Loading..." : "Refresh"}</button></div>
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
                          {#if savedResearchCanReloadStrategy(item)}
                            <button type="button" class="ghost-button" on:click={() => loadSavedStrategy(item)}>Load Strategy</button>
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
          <div class="rail-header"><div><p class="eyebrow">Save Current</p><h3>Scope / Strategy</h3></div></div>
          <label><span>Scope Title</span><input bind:value={savedScopeTitle} /></label>
          <div class="builder-actions"><button type="button" on:click={saveScopeRun} disabled={!result || savedLoading}>Save Scope</button></div>
          <label><span>Strategy Title</span><input bind:value={savedStrategyTitle} /></label>
          <div class="builder-actions"><button type="button" on:click={saveStrategyRun} disabled={!activeStrategyResult || savedLoading}>Save Strategy</button></div>
          <label><span>Notes</span><textarea bind:value={savedNotes} rows="5"></textarea></label>
        </article>

        <article class="panel rail-panel">
          <div class="rail-header"><div><p class="eyebrow">Storage</p><h3>Local JSON Layer</h3></div></div>
          <div class="stack">
            <div class="row"><span>Items</span><strong>{visibleSavedItems.length}</strong></div>
            <div class="row"><span>Reusable Streams</span><strong>{visibleSavedItems.filter(savedResearchHasReturnStream).length}</strong></div>
          </div>
          <p class="muted">Saved Research is a first-pass structured layer, not a notebook. It preserves normalized outputs, warnings, timestamps, and provenance fields for reuse.</p>
        </article>
      </aside>
    </div>
  {/if}
</section>

<style>
  /* ── Layout shells ── */
  .view,
  .overview-grid,
  .overview-bottom-grid,
  .ranking-grid,
  .workspace-grid,
  .primary-column,
  .support-column,
  .kpi-grid,
  .detail-split,
  .stack,
  .field-grid,
  .builder-actions,
  .notes-list,
  .mini-groups {
    display: grid;
    gap: 0.5rem;
  }

  .view {
    gap: 0.5rem;
  }

  /* ── Panels ── */
  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel {
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
  }

  .header-panel .title {
    color: var(--text-0);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .header-panel .subtitle {
    color: var(--text-2);
    font-size: 10.5px;
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
    gap: 0.5rem;
  }

  .headline-block {
    display: grid;
    gap: 0.1rem;
    min-width: 0;
  }

  .headline-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    flex-wrap: wrap;
  }

  .loading-pill {
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: 0.2rem 0.5rem;
    white-space: nowrap;
  }

  .mode-kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  /* ── Mode bar (Risk pattern) ── */
  .mode-bar {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.28rem 0.65rem;
    font: inherit;
    font-size: 0.79rem;
    line-height: 1.2;
    display: inline-flex;
    align-items: baseline;
    gap: 0.5rem;
    white-space: nowrap;
    cursor: pointer;
    width: auto;
    min-height: auto;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-bar button:last-child { border-right: 0; }
  .mode-bar button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-bar button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-bar button.selected { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

  /* ── Treemap panel header with inline controls ── */
  .treemap-header {
    align-items: center;
  }

  .treemap-header-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
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
    font-size: 0.75rem;
    padding: 0.3rem 1.6rem 0.3rem 0.65rem;
    cursor: pointer;
    min-width: 0;
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
    width: 5.5rem;
  }

  /* ── Overview grid / treemap ── */
  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }

  .treemap-canvas {
    position: relative;
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
    padding: 0.28rem 0.5rem;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
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
    font-size: 0.62rem;
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
    padding: 0.32rem 0.38rem;
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
    gap: 0.12rem;
  }

  .tile-copy {
    height: 100%;
    align-content: space-between;
  }

  .tile-topline {
    display: flex;
    justify-content: space-between;
    gap: 0.25rem;
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
    font-size: 0.72rem;
    line-height: 1.1;
  }

  .treemap-tile span {
    font-size: 0.68rem;
    color: var(--text-1);
  }

  .treemap-tile em {
    font-style: normal;
    font-weight: 700;
    font-size: 0.72rem;
    line-height: 1.1;
  }

  .treemap-tile small {
    color: var(--text-1);
    font-size: 0.62rem;
    line-height: 1.2;
  }

  .treemap-tile.hero {
    padding: 0.45rem 0.5rem;
  }

  .treemap-tile.hero strong {
    font-size: 0.82rem;
  }

  .treemap-tile.hero em {
    font-size: 0.84rem;
  }

  .treemap-tile.minor {
    padding: 0.28rem 0.32rem;
  }

  .treemap-tile.minor strong,
  .treemap-tile.minor em {
    font-size: 0.6rem;
  }

  .treemap-tile.micro {
    padding: 0.22rem 0.24rem;
  }

  .treemap-tile.micro .tile-copy {
    align-content: start;
  }

  .treemap-tile.micro strong {
    font-size: 0.54rem;
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
    font-size: 0.72rem;
  }

  .treemap-tooltip {
    --tip-offset-x: 14px;
    --tip-offset-y: 14px;
    position: absolute;
    pointer-events: none;
    transform: translate(var(--tip-offset-x), var(--tip-offset-y));
    min-width: 12.5rem;
    max-width: 18rem;
    padding: 0.6rem 0.75rem 0.65rem;
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
    gap: 0.75rem;
  }

  .treemap-tooltip-head strong {
    font-size: 0.92rem;
    letter-spacing: 0.04em;
    color: var(--text-0);
  }

  .treemap-tooltip-chip {
    font-size: 0.74rem;
    font-weight: 700;
    padding: 0.08rem 0.4rem;
    border: 1px solid var(--divider);
    background: color-mix(in srgb, var(--surface-0) 78%, transparent);
  }

  .treemap-tooltip-chip.positive {
    color: #4bb474;
    border-color: color-mix(in srgb, #4bb474 40%, transparent);
    background: color-mix(in srgb, #4bb474 12%, var(--surface-0));
  }

  .treemap-tooltip-chip.negative {
    color: #c66b61;
    border-color: color-mix(in srgb, #c66b61 40%, transparent);
    background: color-mix(in srgb, #c66b61 12%, var(--surface-0));
  }

  .treemap-tooltip-chip.neutral {
    color: var(--text-1);
  }

  .treemap-tooltip-name {
    margin-top: 0.32rem;
    font-size: 0.76rem;
    color: var(--text-1);
    line-height: 1.2;
  }

  .treemap-tooltip-sector {
    margin-top: 0.15rem;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text-2);
  }

  .treemap-tooltip-metrics {
    margin: 0.55rem 0 0;
    padding-top: 0.45rem;
    border-top: 1px solid var(--divider);
    display: grid;
    gap: 0.3rem;
    grid-template-columns: minmax(0, 1fr);
  }

  .treemap-tooltip-metrics > div {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .treemap-tooltip-metrics dt {
    margin: 0;
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .treemap-tooltip-metrics dd {
    margin: 0;
    font-size: 0.8rem;
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
  .workspace-grid {
    grid-template-columns: minmax(0, 1.85fr) minmax(20rem, 0.9fr);
    align-items: start;
  }

  .primary-column,
  .support-column {
    align-content: start;
  }

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  /* ── Panel header rows ── */
  .panel-header,
  .rail-header,
  .chart-foot,
  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.6rem;
    align-items: flex-start;
  }

  .chart-foot {
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
    flex-wrap: wrap;
  }

  .chart-foot span {
    color: var(--text-2);
    font-size: 0.72rem;
    line-height: 1.4;
  }

  .chart-foot strong {
    color: var(--text-1);
    font-size: 0.72rem;
  }

  .top-line {
    align-items: flex-start;
  }

  .title-block {
    min-width: 0;
    max-width: 40rem;
    display: grid;
    gap: 0.12rem;
  }

  .title-block .muted {
    line-height: 1.4;
    font-size: 0.76rem;
  }

  .header-actions {
    display: flex;
    gap: 0.5rem;
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
    padding-block: 0.15rem;
  }

  .metric {
    min-width: 0;
    padding: 0.2rem 0.85rem;
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    text-align: left;
    display: grid;
    gap: 0.1rem;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
  }

  .metric strong {
    display: block;
    margin: 0.1rem 0 0.05rem;
    font-size: 0.95rem;
    line-height: 1.2;
    color: var(--text-0);
  }

  .metric small {
    color: var(--text-2);
    font-size: 0.66rem;
  }

  /* ── Typography ── */
  .eyebrow,
  .group-label,
  .inline-field > span,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  h2 {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-0);
  }

  h3 {
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--text-0);
  }

  h4 {
    font-size: 0.78rem;
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
    gap: 0.6rem;
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: 0.42rem;
  }

  .row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .row span {
    color: var(--text-2);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .row strong {
    font-size: 0.82rem;
    text-align: right;
  }

  /* ── Inputs & buttons ── */
  label,
  .inline-field {
    display: grid;
    gap: 0.22rem;
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
    padding: 0.4rem 0.6rem;
    font: inherit;
    font-size: 0.82rem;
    display: block;
    width: 100%;
    box-sizing: border-box;
    border-radius: 0;
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
    gap: 0.4rem;
    justify-content: flex-end;
  }

  .builder-actions.compact button {
    width: auto;
    padding: 0.35rem 0.75rem;
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

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
    padding: 0.42rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
    white-space: nowrap;
  }

  tbody td {
    padding: 0.45rem 0.55rem;
    border-top: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
    font-size: 0.8rem;
  }

  .num-cell {
    text-align: right;
  }

  .compact-input {
    width: 5.5rem;
    min-height: 1.55rem;
    padding: 0.2rem 0.35rem;
    text-align: right;
  }

  .compact-input.wide {
    width: 100%;
    min-width: 8rem;
    text-align: left;
  }

  .compact-fields {
    grid-template-columns: minmax(12rem, 1fr) minmax(7rem, 0.25fr) minmax(6rem, 0.2fr);
  }

  .compact-kpis {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .tight {
    gap: 0.25rem;
  }

  .history-input {
    min-width: 14rem;
    min-height: 4.4rem;
    max-height: 8rem;
    padding: 0.3rem 0.4rem;
    font-size: 0.74rem;
    line-height: 1.35;
    white-space: pre;
  }

  .table-panel-header {
    padding: 0.35rem 0.65rem;
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.64rem;
    font-weight: 600;
  }

  .compact-warning-list {
    display: grid;
    gap: 0.2rem;
    padding: 0.45rem 0.65rem;
    border-top: 1px solid var(--divider);
    color: var(--warning);
    font-size: 0.72rem;
  }

  .object-compose-actions {
    padding: 0 0.65rem 0.55rem;
    justify-content: flex-end;
  }

  .handoff-panel {
    display: grid;
    gap: 0.5rem;
  }

  .handoff-strip,
  .handoff-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.5rem;
    align-items: start;
  }

  .handoff-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .handoff-row {
    padding: 0.5rem 0;
    border-top: 1px solid var(--divider);
  }

  .handoff-row:first-child {
    border-top: 0;
  }

  .handoff-row strong,
  .handoff-row small {
    display: block;
    overflow-wrap: anywhere;
  }

  .handoff-actions {
    display: flex;
    gap: 0.35rem;
    justify-content: flex-end;
  }

  .handoff-actions button {
    width: auto;
    min-height: 1.65rem;
    padding: 0.25rem 0.45rem;
    font-size: 0.72rem;
  }

  .handoff-warnings {
    grid-column: 1 / -1;
    display: grid;
    gap: 0.2rem;
    color: var(--warning);
    font-size: 0.72rem;
  }

  .table-panel td .stack,
  .table-panel td .compact-input,
  .table-panel td .history-input {
    white-space: normal;
  }

  tbody tr:hover {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .table-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: center;
  }

  .table-actions button {
    width: auto;
    min-height: 1.65rem;
    padding: 0.25rem 0.45rem;
    font-size: 0.72rem;
  }

  /* ── Pills / tags ── */
  .pill-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.35rem;
  }

  .pill-list span {
    border: 1px solid var(--divider);
    background: var(--surface-0);
    color: var(--text-1);
    padding: 0.22rem 0.42rem;
    font-size: 0.7rem;
    text-transform: none;
    letter-spacing: normal;
  }

  /* ── Notes ── */
  .note-row {
    display: grid;
    grid-template-columns: 5rem minmax(0, 1fr);
    gap: 0.6rem;
    padding-top: 0.42rem;
    border-top: 1px solid var(--divider);
    align-items: baseline;
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-row p {
    font-size: 0.76rem;
    line-height: 1.4;
    color: var(--text-1);
  }

  .note-tag {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
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
    font-size: 0.76rem;
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
    .handoff-strip,
    .handoff-row,
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
      padding: 0.45rem 0;
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
      gap: 0.25rem;
    }
  }
</style>
