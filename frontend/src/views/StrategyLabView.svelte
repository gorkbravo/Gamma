<script lang="ts">
  import { get } from "svelte/store";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import StrategyScriptWorkspace from "../components/StrategyScriptWorkspace.svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { toProvenanceBadge } from "../lib/provenance";
  import type {
    GammaResearchObject,
    ResearchResult,
    SavedResearchItem,
    StrategyLabBookValidation,
    StrategyLabCompositionResult,
    StrategyLabHandoffQueueItem,
    StrategyLabResolvedHandoff,
    StrategyLabResult,
    TimeSeriesPoint
  } from "../lib/api/types";
  import { strategyComposerDraft } from "../lib/stores/app";
  import type {
    SavedResearchCreateOptions,
    StrategyLabAnalyzeOptions,
    StrategyLabComposeOptions,
    StrategyLabPortfolioComposeOptions
  } from "../lib/stores/app";
  import {
    buildStrategyComposerObjects,
    buildStrategyPortfolioLegInputs,
    classifySavedResearchSurface,
    defaultStrategyPortfolioDraftLeg,
    parseResearchCsvText,
    parseStrategyPortfolioHistoryText,
    summarizeStrategyPortfolioDraft,
    hydrateStrategyLabResultFromSaved,
    savedResearchCanReloadStrategy,
    savedResearchHasReturnStream,
    strategyResolvedHandoffToDraftLeg,
    type StrategyLabMode,
    type StrategyPortfolioAssetClass,
    type StrategyPortfolioDraftLeg
  } from "../lib/view-models/research";

  export let mode: StrategyLabMode = "composer";
  export let result: ResearchResult | null = null;
  export let strategyResult: StrategyLabResult | null = null;
  export let strategyComposition: StrategyLabCompositionResult | null = null;
  export let savedItems: SavedResearchItem[] = [];
  export let strategyLoading = false;
  export let savedLoading = false;
  export let riskHandoffLoading = false;
  export let onAnalyzeStrategy: (options: StrategyLabAnalyzeOptions) => Promise<StrategyLabResult | null> | void;
  export let onComposeStrategy: (options: StrategyLabComposeOptions) => Promise<StrategyLabCompositionResult | null> | void = async () => null;
  export let onComposePortfolioStrategy: (options: StrategyLabPortfolioComposeOptions) => Promise<StrategyLabCompositionResult | null> | void = async () => null;
  export let onValidatePortfolioStrategy: (options: StrategyLabPortfolioComposeOptions) => Promise<StrategyLabBookValidation | null> | void = async () => null;
  export let onLoadSaved: () => Promise<SavedResearchItem[]> | void;
  export let onSaveResearch: (options: SavedResearchCreateOptions) => Promise<SavedResearchItem | null> | void;
  export let onDeleteSaved: (itemId: string) => Promise<boolean> | void;
  export let onRestoreStrategy: ((result: StrategyLabResult) => void) | undefined = undefined;
  export let onOpenRisk: (() => void) | undefined = undefined;
  export let strategyLabHandoffs: StrategyLabHandoffQueueItem[] = [];
  export let handoffLoading = false;
  export let onResolveStrategyLabHandoffs: (() => Promise<StrategyLabHandoffQueueItem[]> | void) | undefined = undefined;
  export let onDismissStrategyLabHandoff: ((id: string) => void) | undefined = undefined;
  export let onClearStrategyLabHandoffs: (() => void) | undefined = undefined;
  export let onAcceptStrategyLabHandoff: ((id: string) => StrategyLabResolvedHandoff | null | void) | undefined = undefined;
  export let onReviveStrategyLabHandoff: ((id: string) => void) | undefined = undefined;
  export let onClearStaleStrategyLabHandoffs: (() => void) | undefined = undefined;

  const strategyResearchModes: Array<{ id: StrategyLabMode; label: string }> = [
    { id: "composer", label: "Composer" },
    { id: "script", label: "Script" },
    { id: "backtest_analyze", label: "Backtest" },
    { id: "regime_stress", label: "Regime Stress" },
    { id: "imports", label: "Imports" },
    { id: "saved_runs", label: "Saved Runs" }
  ];

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
  // Seeded from the store so the draft survives leaving the tab, and written back
  // on every edit (GUA-20260903-9).
  const restoredDraft = get(strategyComposerDraft);
  let composerSelection: Record<string, boolean> = { ...restoredDraft.selection };
  let composerWeights: Record<string, number> = { ...restoredDraft.weights };
  let expandedDraftLegs: Record<string, boolean> = {};
  let portfolioName = restoredDraft.name;
  let portfolioBenchmarkSymbol = restoredDraft.benchmarkSymbol;
  let portfolioLookbackDays = restoredDraft.lookbackDays;
  let portfolioDraftLegs: StrategyPortfolioDraftLeg[] = restoredDraft.legs.map((leg) => ({ ...leg }));
  let showHandoffReview = true;
  let bookValidation: StrategyLabBookValidation | null = null;
  let bookValidationLoading = false;
  let bookValidationFingerprint = "";
  let acceptedStrategyLenses: GammaResearchObject[] = [];
  let acceptedStrategyOverlays: GammaResearchObject[] = [];
  let acceptedHandoffWarnings: string[] = [];
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

  const pct = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";
  const signClass = (value: number | null | undefined) =>
    value == null || !Number.isFinite(value) || value === 0 ? "" : value > 0 ? "positive" : "negative";

  function selectResearchMode(nextMode: StrategyLabMode) {
    mode = nextMode;
    if (nextMode === "saved_runs") {
      void onLoadSaved();
    }
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
      lenses: acceptedStrategyLenses,
      overlays: acceptedStrategyOverlays,
      benchmarkObject: null,
      minObservations: 5
    });
    strategyComposition = result ?? null;
  }

  function addPortfolioDraftLeg() {
    portfolioDraftLegs = [...portfolioDraftLegs, defaultStrategyPortfolioDraftLeg(portfolioDraftLegs.length + 1)];
  }

  function toggleDraftLegDetail(id: string) {
    expandedDraftLegs = { ...expandedDraftLegs, [id]: !expandedDraftLegs[id] };
  }

  function removePortfolioDraftLeg(id: string) {
    portfolioDraftLegs =
      portfolioDraftLegs.length <= 1
        ? portfolioDraftLegs.map((leg, index) => (leg.id === id ? defaultStrategyPortfolioDraftLeg(index + 1) : leg))
        : portfolioDraftLegs.filter((leg) => leg.id !== id);
  }

  function resetPortfolioDraftLeg(id: string) {
    portfolioDraftLegs = portfolioDraftLegs.map((leg, index) =>
      leg.id === id ? defaultStrategyPortfolioDraftLeg(index + 1) : leg
    );
  }

  function normalizePortfolioDraftLegSource(id: string, source: "object" | "identifier" | "history") {
    portfolioDraftLegs = portfolioDraftLegs.map((leg) => {
      if (leg.id !== id) {
        return leg;
      }
      if (source === "object" && leg.objectOptionId) {
        return { ...leg, identifier: "", historyText: "" };
      }
      if (source === "identifier" && leg.identifier.trim()) {
        return { ...leg, objectOptionId: "", historyText: "" };
      }
      if (source === "history" && leg.historyText.trim()) {
        return { ...leg, objectOptionId: "", identifier: "" };
      }
      return { ...leg };
    });
  }

  function portfolioDraftSourceLabel(leg: StrategyPortfolioDraftLeg) {
    if (leg.objectOptionId) return "Object";
    if (leg.historyText.trim()) return "Inline";
    if (leg.identifier.trim()) return "Provider";
    return "Unset";
  }

  function portfolioDraftSourceDetail(leg: StrategyPortfolioDraftLeg) {
    if (leg.objectOptionId) {
      return composerOptions.find((option) => option.id === leg.objectOptionId)?.label ?? "Gamma object";
    }
    if (leg.historyText.trim()) {
      const parsed = parseStrategyPortfolioHistoryText(leg.historyText);
      return `${parsed.points.length} dated points`;
    }
    if (leg.identifier.trim()) {
      return `${leg.assetClass} / ${leg.identifier.trim().toUpperCase()}`;
    }
    return "reset or fill source";
  }

  function diagnosticValue(item: Record<string, unknown>, key: string) {
    const value = item[key];
    return value == null || value === "" ? "N/A" : String(value);
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

  function acceptStrategyHandoff(item: StrategyLabHandoffQueueItem) {
    const resolved = item.resolved?.status === "resolved" ? item.resolved : null;
    if (!resolved) {
      strategyInputWarning = item.error ?? "Resolve this handoff before accepting it into the composer.";
      return;
    }
    if (resolved.lens) {
      acceptedStrategyLenses = [
        resolved.lens,
        ...acceptedStrategyLenses.filter((lens) => lens.object_id !== resolved.lens?.object_id)
      ].slice(0, 12);
      acceptedHandoffWarnings = [...resolved.warnings, ...acceptedHandoffWarnings].slice(0, 12);
      onAcceptStrategyLabHandoff?.(item.id);
      strategyInputWarning = "";
      return;
    }
    if (resolved.overlay) {
      acceptedStrategyOverlays = [
        resolved.overlay,
        ...acceptedStrategyOverlays.filter((overlay) => overlay.object_id !== resolved.overlay?.object_id)
      ].slice(0, 12);
      acceptedHandoffWarnings = [...resolved.warnings, ...acceptedHandoffWarnings].slice(0, 12);
      onAcceptStrategyLabHandoff?.(item.id);
      strategyInputWarning = "";
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
    const resolvedItems = strategyLabHandoffs.filter((item) => !item.stale && item.resolved?.status === "resolved");
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
    if (!bookValidation?.valid || bookValidationStale) {
      strategyInputWarning = "Validate the current signed book before composing it for Risk.";
      return;
    }
    strategyInputWarning = blockingWarnings.join(" ");
    const result = await onComposePortfolioStrategy({
      name: portfolioName.trim() || "Strategy Lab Portfolio",
      legs: built.legs,
      lenses: acceptedStrategyLenses,
      overlays: acceptedStrategyOverlays,
      benchmarkSymbol: portfolioBenchmarkSymbol.trim().toUpperCase() || null,
      benchmarkObject: null,
      lookbackDays: portfolioLookbackDays,
      minObservations: 5,
      validation: bookValidation
    });
    strategyComposition = result ?? null;
  }

  async function validatePortfolioDraft() {
    const built = buildStrategyPortfolioLegInputs(portfolioDraftLegs, composerOptions);
    const summary = summarizeStrategyPortfolioDraft(portfolioDraftLegs);
    const blockingWarnings = [...summary.warnings, ...built.warnings];
    if (!built.legs.length) {
      strategyInputWarning = blockingWarnings[0] ?? "Add at least one portfolio leg with usable history.";
      bookValidation = null;
      return;
    }
    strategyInputWarning = blockingWarnings.join(" ");
    bookValidationLoading = true;
    try {
      const result = await onValidatePortfolioStrategy({
        name: portfolioName.trim() || "Strategy Lab Portfolio",
        legs: built.legs,
        lenses: acceptedStrategyLenses,
        overlays: acceptedStrategyOverlays,
        benchmarkSymbol: portfolioBenchmarkSymbol.trim().toUpperCase() || null,
        benchmarkObject: null,
        lookbackDays: portfolioLookbackDays,
        minObservations: 5
      });
      bookValidation = result ?? null;
      bookValidationFingerprint = JSON.stringify(built.legs);
    } finally {
      bookValidationLoading = false;
    }
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

  function loadSavedStrategy(item: SavedResearchItem) {
    const hydrated = hydrateStrategyLabResultFromSaved(item);
    if (!hydrated) {
      return;
    }
    onRestoreStrategy?.(hydrated);
    strategyName = hydrated.name;
    strategyInputWarning = "Loaded normalized saved strategy result. Raw CSV rows were not persisted.";
    mode = "composer";
  }

  function toChartPoint(point: TimeSeriesPoint) {
    return {
      time: Math.floor(new Date(point.timestamp).getTime() / 1000),
      value: point.value
    };
  }

  let parsedStrategyCsv = parseResearchCsvText(strategyCsvText);
  let strategyChartSeries: ChartSeries[] = [];
  let strategyDrawdownSeries: ChartSeries[] = [];
  let rollingRiskSeries: ChartSeries[] = [];
  let stressDrawdownRows: TimeSeriesPoint[] = [];
  let rollingStressRows: StrategyLabResult["rolling_points"] = [];

  $: strategyComposerDraft.set({
    name: portfolioName,
    benchmarkSymbol: portfolioBenchmarkSymbol,
    lookbackDays: portfolioLookbackDays,
    legs: portfolioDraftLegs,
    selection: composerSelection,
    weights: composerWeights
  });
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
  $: savedResearchList = Array.isArray(savedItems) ? savedItems : [];
  $: activeStrategyResult = strategyComposition ?? strategyResult;
  $: scriptModeActive = mode === "script";
  $: strategyModeActive = mode !== "saved_runs" && mode !== "script";
  $: savedModeActive = mode === "saved_runs";
  $: visibleSavedItems = savedResearchList.filter((item) => classifySavedResearchSurface(item) === "strategy");
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
  $: compositionDiagnostics = (strategyComposition?.alignment_diagnostics ?? {}) as Record<string, unknown>;
  $: compositionDiagnosticLegs = Array.isArray(compositionDiagnostics.legs)
    ? (compositionDiagnostics.legs as Array<Record<string, unknown>>)
    : [];
  $: bookValidationStale =
    bookValidation != null && bookValidationFingerprint !== JSON.stringify(portfolioDraftBuild.legs);
  $: currentStrategyHandoffs = strategyLabHandoffs.filter((item) => !item.stale);
  $: staleStrategyHandoffs = strategyLabHandoffs.filter((item) => item.stale);
  $: bookValidationDiagnostics = (bookValidation?.alignment_diagnostics ?? {}) as Record<string, unknown>;
  $: bookValidationLegs = Array.isArray(bookValidationDiagnostics.legs)
    ? (bookValidationDiagnostics.legs as Array<Record<string, unknown>>)
    : [];
  $: strategyBadge = activeStrategyResult ? toProvenanceBadge(activeStrategyResult) : null;
  $: strategyChartSeries = activeStrategyResult
    ? [
        ...(activeStrategyResult.equity_curve_points.length
          ? [
              {
                id: "strategy",
                label: activeStrategyResult.name,
                color: "var(--chart-primary)",
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
                color: "var(--chart-secondary)",
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
  $: strategyDrawdownSeries = activeStrategyResult?.drawdown_points?.length
    ? [
        {
          id: "drawdown",
          label: "Drawdown",
          color: "var(--chart-negative)",
          type: "area" as const,
          invertFilledArea: true,
          data: activeStrategyResult.drawdown_points
            .filter((point) => Number.isFinite(point.value))
            .map(toChartPoint)
        }
      ]
    : [];
  $: rollingRiskSeries = (() => {
    const points = activeStrategyResult?.rolling_points ?? [];
    const betaData = points
      .filter((point) => point.rolling_beta != null && Number.isFinite(point.rolling_beta))
      .map((point) => ({ time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: point.rolling_beta as number }));
    const corrData = points
      .filter((point) => point.rolling_correlation != null && Number.isFinite(point.rolling_correlation))
      .map((point) => ({ time: Math.floor(new Date(point.timestamp).getTime() / 1000), value: point.rolling_correlation as number }));
    const series: ChartSeries[] = [];
    if (betaData.length) {
      series.push({ id: "rolling_beta", label: "Rolling Beta", color: "var(--chart-primary)", type: "line" as const, data: betaData });
    }
    if (corrData.length) {
      series.push({ id: "rolling_corr", label: "Rolling Corr", color: "var(--chart-secondary)", type: "line" as const, lineStyle: "dashed" as const, data: corrData });
    }
    return series;
  })();
  $: strategyModeTitle =
    mode === "composer"
      ? "Gamma Object Composer"
      : mode === "imports"
        ? "Return Stream Import"
        : mode === "regime_stress"
          ? "Regime / Stress Lens"
          : "Backtest / Analyze";
  $: strategyModeEyebrow =
    mode === "composer"
      ? "Strategy Composer"
      : mode === "imports"
        ? "CSV Import"
        : mode === "regime_stress"
          ? "Strategy Stress"
          : "Strategy Analytics";
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Strategy Lab</span>
      <span class="subtitle">Composer / scripts / backtests / saved runs</span>
      {#if strategyLoading || savedLoading || handoffLoading}<span class="loading-pill">Refreshing</span>{/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Strategy Lab modes">
        {#each strategyResearchModes as item}
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

  {#if scriptModeActive}
    <StrategyScriptWorkspace />
  {:else if strategyModeActive}
    <div class="workspace-grid">
      <div class="primary-column">
        {#if mode === "composer"}
          {#if strategyLabHandoffs.length}
            <article class="panel handoff-panel">
              <div class="handoff-strip">
                <div class="handoff-summary">
                  <span class="handoff-label">Inbound Handoffs</span>
                  <strong>{currentStrategyHandoffs.length} pending</strong>
                  <small>
                    {currentStrategyHandoffs.filter((item) => item.status === "resolved").length} resolved /
                    {currentStrategyHandoffs.filter((item) => item.status === "pending" || item.status === "error").length} awaiting{staleStrategyHandoffs.length ? ` / ${staleStrategyHandoffs.length} stale` : ""}
                  </small>
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
                  {#each currentStrategyHandoffs as item}
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

                  {#if staleStrategyHandoffs.length}
                    <div class="stale-handoff-head">
                      <div>
                        <strong>Earlier Sessions</strong>
                        <small>Expired handoffs are excluded from Resolve and Accept All. Revive one to re-resolve it with fresh data, or re-send it from the source tab.</small>
                      </div>
                      <button type="button" class="ghost-button" on:click={() => onClearStaleStrategyLabHandoffs?.()}>
                        Clear Earlier
                      </button>
                    </div>
                    {#each staleStrategyHandoffs as item}
                      <div class="handoff-row stale-handoff-row">
                        <div>
                          <strong>{item.handoff.selected_entity.label}</strong>
                          <small>
                            {item.handoff.source_tab} / {item.handoff.asset_class} / enqueued {item.enqueued_at.slice(0, 10)}
                          </small>
                        </div>
                        <div class="handoff-actions">
                          <button type="button" class="ghost-button" on:click={() => onReviveStrategyLabHandoff?.(item.id)}>
                            Revive
                          </button>
                          <button type="button" class="ghost-button" on:click={() => onDismissStrategyLabHandoff?.(item.id)}>
                            Dismiss
                          </button>
                        </div>
                      </div>
                    {/each}
                  {/if}
                </div>
              {/if}
            </article>
          {/if}

          <article class="panel table-panel">
            <div class="panel-header tight-head">
              <h3>Portfolio Composer</h3>
              <div class="builder-actions compact">
                <button type="button" class="ghost-button" on:click={addPortfolioDraftLeg}>Add Leg</button>
                <button type="button" class="ghost-button" on:click={validatePortfolioDraft} disabled={bookValidationLoading || strategyLoading || !portfolioDraftBuild.legs.length}>
                  {bookValidationLoading ? "Validating..." : "Validate Book"}
                </button>
                <button type="button" on:click={composePortfolioDraft} disabled={strategyLoading || !portfolioDraftBuild.legs.length || !bookValidation?.valid || bookValidationStale}>
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
              <article class="metric"><span>Net</span><strong class={signClass(portfolioDraftSummary.netExposure)}>{fmt(portfolioDraftSummary.netExposure, 2)}x</strong><small>{fmt(portfolioDraftSummary.longExposure, 2)} long / {fmt(portfolioDraftSummary.shortExposure, 2)} short</small></article>
              <article class="metric"><span>Listed</span><strong>{portfolioDraftSummary.listedIdentifierLegs}</strong><small>provider-resolved</small></article>
              <article class="metric"><span>Inline</span><strong>{portfolioDraftSummary.inlineHistoryLegs}</strong><small>dated histories</small></article>
              <article class="metric"><span>Objects</span><strong>{portfolioDraftSummary.objectLegs}</strong><small>Gamma streams</small></article>
              <article class="metric"><span>Context</span><strong>{acceptedStrategyLenses.length + acceptedStrategyOverlays.length}</strong><small>lenses / overlays</small></article>
            </div>

            {#if acceptedStrategyLenses.length || acceptedStrategyOverlays.length}
              <div class="attached-context-list" aria-label="Attached Strategy Lab context">
                {#each acceptedStrategyLenses as lens}
                  <div class="attached-context-row">
                    <span>Lens</span>
                    <strong>{lens.display_name}</strong>
                    <small>{lens.source_tab} / {lens.source_mode ?? "context"} / {lens.provider_summary ?? "Gamma"}</small>
                  </div>
                {/each}
                {#each acceptedStrategyOverlays as overlay}
                  <div class="attached-context-row">
                    <span>Overlay</span>
                    <strong>{overlay.display_name}</strong>
                    <small>{overlay.source_tab} / {overlay.source_mode ?? "context"} / {overlay.provider_summary ?? "Gamma"}</small>
                  </div>
                {/each}
              </div>
            {/if}

            <div class="table-wrap compact-table">
              <table class="composer-table">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Class</th>
                    <th>Source</th>
                    <th>Identifier</th>
                    <th class="num-cell">Weight</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {#each portfolioDraftLegs as leg (leg.id)}
                    <tr>
                      <td><input class="compact-input wide" bind:value={leg.label} placeholder="Leg label" /></td>
                      <td>
                        <select class="compact-input class-select" bind:value={leg.assetClass}>
                          {#each portfolioAssetClasses as assetClass}
                            <option value={assetClass.id}>{assetClass.label}</option>
                          {/each}
                        </select>
                      </td>
                      <td>
                        <div class="source-cell" title={portfolioDraftSourceDetail(leg)}>
                          <span class:warning={portfolioDraftSourceLabel(leg) === "Unset"}>{portfolioDraftSourceLabel(leg)}</span>
                          <small>{portfolioDraftSourceDetail(leg)}</small>
                        </div>
                      </td>
                      <td>
                        <input
                          class="compact-input wide"
                          bind:value={leg.identifier}
                          placeholder="Ticker / contract id"
                          on:input={() => normalizePortfolioDraftLegSource(leg.id, "identifier")}
                        />
                      </td>
                      <td class="num-cell">
                        <input class="compact-input" type="number" step="0.05" bind:value={leg.weight} />
                      </td>
                      <td class="num-cell">
                        <div class="row-actions">
                          <button
                            type="button"
                            class="ghost-button icon-button"
                            aria-expanded={Boolean(expandedDraftLegs[leg.id])}
                            title="Object / inline history source"
                            on:click={() => toggleDraftLegDetail(leg.id)}
                          >{expandedDraftLegs[leg.id] ? "▾" : "▸"}</button>
                          <button
                            type="button"
                            class="ghost-button icon-button"
                            title="Remove leg"
                            aria-label="Remove leg"
                            on:click={() => removePortfolioDraftLeg(leg.id)}
                          >✕</button>
                        </div>
                      </td>
                    </tr>
                    {#if expandedDraftLegs[leg.id]}
                      <tr class="leg-detail-row">
                        <td colspan="6">
                          <div class="leg-detail">
                            <label>
                              <span>Gamma Object</span>
                              <select
                                class="compact-input wide"
                                bind:value={leg.objectOptionId}
                                on:change={() => normalizePortfolioDraftLegSource(leg.id, "object")}
                              >
                                <option value="">Provider / inline history</option>
                                {#each composerOptions as option}
                                  <option value={option.id}>{option.label}</option>
                                {/each}
                              </select>
                            </label>
                            <label>
                              <span>Value Kind</span>
                              <select class="compact-input wide" bind:value={leg.valueKind}>
                                <option value="return">Returns</option>
                                <option value="level">Level / probability</option>
                              </select>
                            </label>
                            <label class="history-field">
                              <span>Inline History (date,value)</span>
                              <textarea
                                class="history-input"
                                bind:value={leg.historyText}
                                placeholder="date,value rows for contracts, commodities, custom streams"
                                on:input={() => normalizePortfolioDraftLegSource(leg.id, "history")}
                              ></textarea>
                            </label>
                            <button type="button" class="ghost-button leg-reset" on:click={() => resetPortfolioDraftLeg(leg.id)}>Reset</button>
                          </div>
                        </td>
                      </tr>
                    {/if}
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

            {#if bookValidation}
              <div class="book-validation" class:invalid={!bookValidation.valid}>
                <div class="row">
                  <span>Book Validation</span>
                  <strong class={bookValidation.valid ? "positive" : "negative"}>
                    {bookValidation.valid ? "VALID" : "INVALID"}{bookValidationStale ? " (STALE - draft changed, revalidate)" : ""}
                  </strong>
                </div>
                <div class="row">
                  <span>Usable Legs</span>
                  <strong>{bookValidation.usable_leg_count} / {bookValidation.requested_leg_count}</strong>
                </div>
                <div class="row">
                  <span>Aligned Obs</span>
                  <strong>{bookValidation.aligned_observation_count} / min {bookValidation.min_observations}</strong>
                </div>
                {#if bookValidationLegs.length}
                  <div class="table-wrap compact-table">
                    <table>
                      <thead>
                        <tr><th>Leg</th><th>Source</th><th>Window</th><th class="num-cell">Obs</th><th class="num-cell">Norm Wt</th></tr>
                      </thead>
                      <tbody>
                        {#each bookValidationLegs as diagnostic}
                          <tr>
                            <td class:absent={diagnosticValue(diagnostic, "label") === "N/A"}>{diagnosticValue(diagnostic, "label")}</td>
                            <td class:absent={diagnosticValue(diagnostic, "source_provider") === "N/A"}>{diagnosticValue(diagnostic, "source_provider")}</td>
                            <td>{diagnosticValue(diagnostic, "available_start").slice(0, 10)} - {diagnosticValue(diagnostic, "available_end").slice(0, 10)}</td>
                            <td class="num-cell" class:absent={diagnosticValue(diagnostic, "observation_count") === "N/A"}>{diagnosticValue(diagnostic, "observation_count")}</td>
                            <td class="num-cell" class:absent={fmt(Number(diagnostic.normalized_weight ?? 0), 3) === "N/A"}>{fmt(Number(diagnostic.normalized_weight ?? 0), 3)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {/if}
                {#if bookValidation.errors.length}
                  <div class="warning-list compact-warning-list">
                    {#each bookValidation.errors.slice(0, 6) as error}
                      <span>{error}</span>
                    {/each}
                  </div>
                {/if}
                {#if bookValidation.warnings.length}
                  <div class="warning-list compact-warning-list muted-warnings">
                    {#each bookValidation.warnings.slice(0, 4) as warning}
                      <span>{warning}</span>
                    {/each}
                  </div>
                {/if}
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
                <div class="builder-actions compact">
                  <small>{strategyComposition.returns_points.length} return points</small>
                  <button type="button" class="ghost-button" on:click={() => onOpenRisk?.()} disabled={riskHandoffLoading}>
                    {riskHandoffLoading ? "Opening..." : "Open In Risk"}
                  </button>
                </div>
              </div>
              {#if compositionDiagnosticLegs.length}
                <div class="alignment-diagnostics">
                  <div class="row">
                    <span>Shared Window</span>
                    <strong>
                      {diagnosticValue(compositionDiagnostics, "aligned_start").slice(0, 10)} -
                      {diagnosticValue(compositionDiagnostics, "aligned_end").slice(0, 10)}
                    </strong>
                  </div>
                  <div class="row">
                    <span>Aligned Obs</span>
                    <strong>{diagnosticValue(compositionDiagnostics, "aligned_observation_count")} / min {diagnosticValue(compositionDiagnostics, "min_observations")}</strong>
                  </div>
                  <div class="table-wrap compact-table">
                    <table>
                      <thead>
                        <tr><th>Leg</th><th>Source</th><th>Window</th><th class="num-cell">Obs</th><th class="num-cell">Norm Wt</th></tr>
                      </thead>
                      <tbody>
                        {#each compositionDiagnosticLegs as diagnostic}
                          <tr>
                            <td class:absent={diagnosticValue(diagnostic, "label") === "N/A"}>{diagnosticValue(diagnostic, "label")}</td>
                            <td class:absent={diagnosticValue(diagnostic, "source_provider") === "N/A"}>{diagnosticValue(diagnostic, "source_provider")}</td>
                            <td>{diagnosticValue(diagnostic, "available_start").slice(0, 10)} - {diagnosticValue(diagnostic, "available_end").slice(0, 10)}</td>
                            <td class="num-cell" class:absent={diagnosticValue(diagnostic, "observation_count") === "N/A"}>{diagnosticValue(diagnostic, "observation_count")}</td>
                            <td class="num-cell" class:absent={fmt(Number(diagnostic.normalized_weight ?? 0), 3) === "N/A"}>{fmt(Number(diagnostic.normalized_weight ?? 0), 3)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                </div>
              {/if}
              <div class="kpi-grid">
                <article class="metric"><span>Total Return</span><strong class={signClass(strategyComposition.metrics.total_return)} class:absent={pct(strategyComposition.metrics.total_return) === "N/A"}>{pct(strategyComposition.metrics.total_return)}</strong><small>{strategyComposition.metrics.observation_count} observations</small></article>
                <article class="metric"><span>Annual Vol</span><strong class:absent={pct(strategyComposition.metrics.annual_volatility) === "N/A"}>{pct(strategyComposition.metrics.annual_volatility)}</strong><small>{strategyComposition.metrics.frequency}</small></article>
                <article class="metric"><span>Max Drawdown</span><strong class:negative={(strategyComposition.metrics.max_drawdown ?? 0) < 0}>{pct(strategyComposition.metrics.max_drawdown)}</strong><small>{strategyComposition.metrics.max_drawdown_duration} periods</small></article>
                <article class="metric"><span>Contributions</span><strong>{Object.keys(strategyComposition.leg_contributions).length}</strong><small>weighted legs</small></article>
                <article class="metric"><span>Lenses</span><strong>{strategyComposition.lenses.length}</strong><small>{strategyComposition.overlays.length} overlays</small></article>
              </div>
              {#if strategyComposition.lenses.length || strategyComposition.overlays.length}
                <div class="attached-context-list">
                  {#each strategyComposition.lenses as lens}
                    <div class="attached-context-row">
                      <span>Lens</span>
                      <strong>{lens.display_name}</strong>
                      <small>{lens.provider_summary ?? lens.source_tab}</small>
                    </div>
                  {/each}
                  {#each strategyComposition.overlays as overlay}
                    <div class="attached-context-row">
                      <span>Overlay</span>
                      <strong>{overlay.display_name}</strong>
                      <small>{overlay.provider_summary ?? overlay.source_tab}</small>
                    </div>
                  {/each}
                </div>
              {/if}
            </article>
          {/if}
        {/if}

        <article class="panel performance-panel">
          <div class="panel-header top-line">
            <div class="title-block">
              <p class="eyebrow">{strategyModeEyebrow}</p>
              <h2>{activeStrategyResult?.name ?? strategyModeTitle}</h2>
            </div>
            <div class="builder-actions compact">
              <button type="button" on:click={saveStrategyRun} disabled={!activeStrategyResult || savedLoading}>Save Strategy</button>
            </div>
          </div>

          <div class="kpi-grid">
            <article class="metric"><span>Total Return</span><strong class={signClass(activeStrategyResult?.metrics.total_return)} class:absent={pct(activeStrategyResult?.metrics.total_return) === "N/A"}>{pct(activeStrategyResult?.metrics.total_return)}</strong><small>{activeStrategyResult?.metrics.observation_count ?? 0} observations</small></article>
            <article class="metric"><span>Annual Return</span><strong class={signClass(activeStrategyResult?.metrics.annual_return)} class:absent={pct(activeStrategyResult?.metrics.annual_return) === "N/A"}>{pct(activeStrategyResult?.metrics.annual_return)}</strong><small>{activeStrategyResult?.metrics.frequency ?? "unknown"} frequency</small></article>
            <article class="metric"><span>Annual Vol</span><strong class:absent={pct(activeStrategyResult?.metrics.annual_volatility) === "N/A"}>{pct(activeStrategyResult?.metrics.annual_volatility)}</strong><small>Inferred periods {fmt(activeStrategyResult?.metrics.periods_per_year, 0)}</small></article>
            <article class="metric"><span>Sharpe</span><strong class={signClass(activeStrategyResult?.metrics.sharpe_ratio)} class:absent={fmt(activeStrategyResult?.metrics.sharpe_ratio, 2) === "N/A"}>{fmt(activeStrategyResult?.metrics.sharpe_ratio, 2)}</strong><small>Zero risk-free assumption</small></article>
            <article class="metric"><span>Sortino</span><strong class={signClass(activeStrategyResult?.metrics.sortino_ratio)} class:absent={fmt(activeStrategyResult?.metrics.sortino_ratio, 2) === "N/A"}>{fmt(activeStrategyResult?.metrics.sortino_ratio, 2)}</strong><small>Downside deviation</small></article>
            <article class="metric"><span>Max Drawdown</span><strong class:negative={(activeStrategyResult?.metrics.max_drawdown ?? 0) < 0}>{pct(activeStrategyResult?.metrics.max_drawdown)}</strong><small>{activeStrategyResult?.metrics.max_drawdown_duration ?? 0} periods</small></article>
          </div>

          <TimeSeriesChart series={strategyChartSeries} height={320} emptyMessage="Import CSV returns to populate Strategy Lab." />
          {#if strategyDrawdownSeries.length}
            <div class="subchart-label">Underwater Drawdown</div>
            <TimeSeriesChart series={strategyDrawdownSeries} height={140} />
          {/if}
          {#if activeStrategyResult}
            <div class="chart-foot">
              <ProvenanceBadge data={strategyBadge} label="Source" />
            </div>
          {/if}
        </article>

        {#if mode === "imports"}
          <article class="panel table-panel">
            <div class="panel-header tight-head">
              <h3>Parsed CSV Rows</h3>
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

        {#if mode === "regime_stress"}
          {#if rollingRiskSeries.length}
            <article class="panel">
              <div class="table-panel-header">Rolling Beta &amp; Correlation</div>
              <TimeSeriesChart series={rollingRiskSeries} height={200} showLegend emptyMessage="Analyze a benchmarked stream to populate rolling regime risk." />
            </article>
          {/if}
          <div class="detail-split">
            <article class="panel table-panel">
              <div class="panel-header tight-head"><h3>Worst Drawdowns</h3><small>{stressDrawdownRows.length} points</small></div>
              <div class="table-wrap compact-table">
                <table>
                  <thead><tr><th>Date</th><th class="num-cell">Drawdown</th></tr></thead>
                  <tbody>
                    {#if stressDrawdownRows.length}
                      {#each stressDrawdownRows as point}
                        <tr><td class:absent={shortDate(point.timestamp) === "N/A"}>{shortDate(point.timestamp)}</td><td class="num-cell {signClass(point.value)}" class:absent={pct(point.value) === "N/A"}>{pct(point.value)}</td></tr>
                      {/each}
                    {:else}
                      <tr><td colspan="2">No drawdown series yet.</td></tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </article>

            <article class="panel table-panel">
              <div class="panel-header tight-head"><h3>Recent Regime Read</h3><small>{rollingStressRows.length} windows</small></div>
              <div class="table-wrap compact-table">
                <table>
                  <thead><tr><th>Date</th><th class="num-cell">Roll Ret</th><th class="num-cell">Vol</th><th class="num-cell">Beta</th><th class="num-cell">Corr</th></tr></thead>
                  <tbody>
                    {#if rollingStressRows.length}
                      {#each rollingStressRows as row}
                        <tr>
                          <td class:absent={shortDate(row.timestamp) === "N/A"}>{shortDate(row.timestamp)}</td>
                          <td class="num-cell {signClass(row.rolling_return)}" class:absent={pct(row.rolling_return) === "N/A"}>{pct(row.rolling_return)}</td>
                          <td class="num-cell" class:absent={pct(row.rolling_volatility) === "N/A"}>{pct(row.rolling_volatility)}</td>
                          <td class="num-cell" class:absent={fmt(row.rolling_beta, 2) === "N/A"}>{fmt(row.rolling_beta, 2)}</td>
                          <td class="num-cell" class:absent={fmt(row.rolling_correlation, 2) === "N/A"}>{fmt(row.rolling_correlation, 2)}</td>
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
            <div class="panel-header tight-head"><h3>Monthly Returns</h3><small>{activeStrategyResult?.monthly_returns.length ?? 0} periods</small></div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Period</th><th class="num-cell">Return</th></tr></thead>
                <tbody>
                  {#if activeStrategyResult?.monthly_returns.length}
                    {#each activeStrategyResult.monthly_returns.slice(-18) as row}
                      <tr><td>{row.period}</td><td class="num-cell {signClass(row.value)}" class:absent={pct(row.value) === "N/A"}>{pct(row.value)}</td></tr>
                    {/each}
                  {:else}
                    <tr><td colspan="2">No monthly table yet.</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel table-panel">
            <div class="panel-header tight-head"><h3>Annual Returns</h3><small>{activeStrategyResult?.annual_returns.length ?? 0} periods</small></div>
            <div class="table-wrap compact-table">
              <table>
                <thead><tr><th>Period</th><th class="num-cell">Return</th></tr></thead>
                <tbody>
                  {#if activeStrategyResult?.annual_returns.length}
                    {#each activeStrategyResult.annual_returns as row}
                      <tr><td>{row.period}</td><td class="num-cell {signClass(row.value)}" class:absent={pct(row.value) === "N/A"}>{pct(row.value)}</td></tr>
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
        {#if mode === "imports"}
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
            <div class="row"><span>Active Stream</span><strong class:absent={activeStrategyResult?.name == null}>{activeStrategyResult?.name ?? "N/A"}</strong></div>
            <div class="row"><span>Return Points</span><strong>{activeStrategyResult?.returns_points.length ?? 0}</strong></div>
            <div class="row"><span>Benchmark Points</span><strong>{activeStrategyResult?.benchmark_points.length ?? 0}</strong></div>
            <div class="row"><span>Rolling Windows</span><strong>{activeStrategyResult?.rolling_points.length ?? 0}</strong></div>
            <div class="row"><span>Saved Runs</span><strong>{visibleSavedItems.length}</strong></div>
          </div>
          {#if strategyInputWarning}
            <p class="warning">{strategyInputWarning}</p>
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
  {:else if savedModeActive}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel table-panel">
          <div class="panel-header tight-head">
            <h3>Saved Strategy Runs</h3>
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
                      <td class:absent={shortDate(item.updated_at) === "N/A"}>{shortDate(item.updated_at)}</td>
                      <td>{item.warnings.length}</td>
                      <td>
                        <div class="table-actions">
                          {#if savedResearchCanReloadStrategy(item)}
                            <button type="button" class="ghost-button" on:click={() => loadSavedStrategy(item)}>Load Strategy</button>
                          {/if}
                          <button type="button" class="ghost-button" on:click={() => void onDeleteSaved(item.id)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="5">No saved strategy runs yet.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel control-panel">
          <div class="rail-header"><div><p class="eyebrow">Save Current</p><h3>Strategy Run</h3></div></div>
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
        </article>
      </aside>
    </div>
  {/if}
</section>

<style>
  /* ── Layout shells ── */
  .view,
  .kpi-grid,
  .detail-split,
  .stack,
  .field-grid,
  .builder-actions,
  .notes-list {
    display: grid;
    gap: var(--space-4);
  }

  .view {
    gap: var(--space-4);
  }

  /* ── Panels ── */

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
  .table-panel,
  .control-panel,
  .rail-panel {
    align-content: start;
  }

  /* ── Header panel internals ── */

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

  /* ── Mode bar (Risk pattern) ── */

  /* ── Workspace ── */

  .detail-split {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  /* ── Panel header rows ── */
  .rail-header,
  .chart-foot {
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

  .subchart-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    margin-top: var(--space-1);
  }

  .title-block {
    min-width: 0;
    max-width: 40rem;
    display: grid;
    gap: var(--space-1);
  }

  /* ── KPI strip ── */
  .kpi-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0;
    padding-block: var(--space-1);
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

  h2,
  h3,
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
  label {
    display: grid;
    gap: var(--space-2);
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

  .table-panel > :not(.panel-header):not(.table-panel-header) + .table-wrap {
    border-top: 1px solid var(--divider);
  }

  .table-panel > .field-grid {
    padding: var(--space-4) var(--space-5) var(--space-2);
  }

  .table-panel > .kpi-grid {
    padding: var(--space-2) var(--space-5) var(--space-3);
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

  .num-cell {
    text-align: right;
  }

  .compact-input {
    width: 5.5rem;
    min-height: 1.55rem;
    padding: var(--space-2) var(--space-3);
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
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .history-input {
    min-width: 14rem;
    min-height: 4.4rem;
    max-height: 8rem;
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
    line-height: 1.35;
    white-space: pre;
  }

  .source-cell {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    min-width: 8rem;
    max-width: 16rem;
  }

  .source-cell span {
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-xs);
    flex-shrink: 0;
  }

  .source-cell span.warning {
    color: var(--warning);
  }

  .source-cell small {
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.25;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  .row-actions {
    display: inline-flex;
    gap: var(--space-2);
    align-items: center;
    justify-content: flex-end;
  }

  .icon-button {
    width: 1.55rem;
    min-height: 1.55rem;
    padding: 0;
    display: inline-grid;
    place-items: center;
    font-size: var(--text-xs);
    color: var(--text-2);
  }

  .icon-button[aria-expanded="true"] {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 32%, var(--panel-strong));
  }

  .composer-table tbody td {
    padding: var(--space-2) var(--space-3);
  }

  .composer-table .class-select {
    width: auto;
    min-width: 7.5rem;
    text-align: left;
  }

  .leg-detail-row td {
    padding: 0;
    background: var(--surface-soft);
  }

  .leg-detail {
    display: grid;
    grid-template-columns: minmax(12rem, 0.9fr) minmax(9rem, 0.5fr) minmax(16rem, 1.6fr) auto;
    gap: var(--space-4);
    align-items: start;
    padding: var(--space-3) var(--space-4);
  }

  .leg-detail label {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .leg-detail .compact-input.wide {
    min-width: 0;
  }

  .leg-detail .history-input {
    width: 100%;
    min-width: 0;
    min-height: 3.2rem;
  }

  .leg-detail .leg-reset {
    align-self: end;
    width: auto;
    min-height: 1.55rem;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
  }

  .alignment-diagnostics {
    display: grid;
    gap: var(--space-4);
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
  }

  .book-validation {
    display: grid;
    gap: var(--space-4);
    border-top: 1px solid var(--divider);
    padding: var(--space-4) var(--space-5) var(--space-4);
  }

  .book-validation.invalid {
    border-left: 2px solid var(--negative);
  }

  .book-validation strong.positive {
    color: var(--positive);
  }

  .book-validation strong.negative {
    color: var(--negative);
  }

  .muted-warnings span {
    color: var(--text-2);
  }

  .table-panel-header {
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    font-weight: 600;
  }

  .compact-warning-list {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-4) var(--space-5);
    border-top: 1px solid var(--divider);
    color: var(--warning);
    font-size: var(--text-sm);
  }

  .attached-context-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .attached-context-row {
    display: grid;
    grid-template-columns: 4.5rem minmax(0, 1fr) minmax(8rem, auto);
    gap: var(--space-4);
    align-items: center;
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
    font-size: var(--text-sm);
  }

  .attached-context-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-xs);
  }

  .attached-context-row strong,
  .attached-context-row small {
    overflow-wrap: anywhere;
  }

  .attached-context-row small {
    color: var(--text-2);
    text-align: right;
  }

  .object-compose-actions {
    padding: 0 var(--space-5) var(--space-4);
    justify-content: flex-end;
  }

  .handoff-panel {
    display: grid;
    gap: var(--space-4);
  }

  .handoff-strip,
  .handoff-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-4);
    align-items: start;
  }

  .handoff-strip {
    align-items: center;
  }

  .handoff-summary {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
    min-width: 0;
    flex-wrap: wrap;
  }

  .handoff-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  .handoff-summary small {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .handoff-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .handoff-row {
    padding: var(--space-4) 0;
    border-top: 1px solid var(--divider);
  }

  .handoff-row:first-child {
    border-top: 0;
  }

  .stale-handoff-head {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-4);
    align-items: start;
    padding: var(--space-4) 0 var(--space-2);
    border-top: 1px solid var(--divider);
  }

  .stale-handoff-head strong {
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-2);
  }

  .stale-handoff-head small {
    display: block;
    color: var(--text-2);
    overflow-wrap: anywhere;
  }

  .stale-handoff-row {
    opacity: 0.75;
  }

  .handoff-row strong,
  .handoff-row small {
    display: block;
    overflow-wrap: anywhere;
  }

  .handoff-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: flex-end;
  }

  .handoff-actions button {
    width: auto;
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
  }

  .handoff-warnings {
    grid-column: 1 / -1;
    display: grid;
    gap: var(--space-2);
    color: var(--warning);
    font-size: var(--text-sm);
  }

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
    gap: var(--space-3);
    align-items: center;
  }

  .table-actions button {
    width: auto;
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
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

  .warning {
    color: var(--warning);
    font-size: var(--text-sm);
  }

  /* ── Responsive ── */
  @media (max-width: 1240px) {
    .workspace-grid,
    .detail-split {
      grid-template-columns: 1fr;
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
    .attached-context-row,
    .builder-actions,
    .leg-detail,
    .kpi-grid {
      grid-template-columns: 1fr;
    }

    .mode-bar {
      flex-wrap: wrap;
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
    .chart-foot {
      flex-direction: column;
      align-items: stretch;
    }

    .attached-context-row small {
      text-align: left;
    }

    .note-row {
      grid-template-columns: 1fr;
      gap: var(--space-2);
    }
  }
</style>
