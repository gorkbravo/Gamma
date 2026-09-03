<script lang="ts">
  import CompactContextMenu from "../components/CompactContextMenu.svelte";
  import CopilotOptionsWorkingAnalysis from "../components/CopilotOptionsWorkingAnalysis.svelte";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import { toProvenanceBadge } from "../lib/provenance";
  import type {
    CopilotWorkingAnalysis,
    CrossTabHandoffEnvelope,
    IvSessionStatus,
    IvSurface,
    IvUnderlyingHistoryResponse,
    Position,
    StrategyLabHandoffEnvelope,
    SystemStatus,
    TimeSeriesPoint
  } from "../lib/api/types";
  import { ivWorkbenchState, type IvLoadOptions } from "../lib/stores/app";
  import { onDestroy } from "svelte";
  import { buildOptionsStrategyHandoff } from "../lib/view-models/research";
  import {
    STRATEGY_TEMPLATES,
    buildStrategyLegFromChainRow,
    buildStrategyTemplateLegs,
    daysToExpiry,
    deriveChainGreekRows,
    deriveChainRows,
    deriveImpliedProbabilitySelection,
    deriveImpliedProbabilitySlice,
    deriveImpliedProbabilitySurface,
    deriveIvSurfaceAlerts,
    deriveFittedSmileSamples,
    cellSource,
    cellSourceLabel,
    deriveIvSmile,
    deriveOptionPayoffMatrix,
    deriveOverviewSnapshot,
    deriveObservedSurfacePoints,
    deriveObservedTermStructure,
    deriveRealizedVolatility,
    deriveSkewRows,
    deriveStrategyPayoff,
    deriveStrategyPayoffMatrix,
    deriveStrategyGreeks,
    deriveStrategySizing,
    deriveSurfaceStats,
    deriveTermCurve,
    deriveTermStructure,
    hasParametricIvFit,
    isFittedCell,
    livePositionForSymbol,
    nearestStrikeIndex,
    optionsModes,
    selectedExpiryForSurface,
    type ChainRow,
    type ChainGreekRow,
    type GreekMetric,
    type IvSmile,
    type IvSmilePoint,
    type ImpliedProbabilitySelection,
    type ImpliedProbabilitySlice,
    type ImpliedProbabilitySurface,
    type OptionPayoffMatrix,
    type OptionsMode,
    type PayoffGlanceType,
    type StrategyLeg,
    type StrategyTemplateId,
    type StrategyGreekSummary,
    type StrategyPayoffMatrix,
    type StrategySizing,
    type StrategyOptionType,
    type StrategySide,
    type TermCurve,
    type TermCurvePoint,
  } from "../lib/view-models/iv";
  import type { SurfaceModel } from "../components/Surface3D.svelte";

  export let mode: OptionsMode = "overview";
  export let status: SystemStatus | null = null;
  export let requestedSymbol = "";
  export let result: IvSurface | null = null;
  export let workingAnalysis: CopilotWorkingAnalysis | null = null;
  export let session: IvSessionStatus | null = null;
  export let underlyingHistory: IvUnderlyingHistoryResponse | null = null;
  export let underlyingPricePoints: TimeSeriesPoint[] = [];
  export let researchPrimarySymbol: string | null = null;
  /** Live stock lines, used only to size a research structure against real exposure. */
  export let portfolioPositions: Position[] = [];
  export let loading = false;
  export let sessionLoading = false;
  export let errorMessage = "";
  export let onLoad: (options: IvLoadOptions) => void | Promise<void>;
  export let onStopSession: () => void | Promise<void>;
  export let onSendToCopilot: (handoff: CrossTabHandoffEnvelope) => Promise<unknown> | void = () => {};
  export let onSendToStrategyLab: ((handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void) | undefined = undefined;

  let symbol = requestedSymbol || "";
  let lastRequestedSymbol = requestedSymbol;
  let selectedExpiry: string | null = null;
  let selectedOptionType: StrategyOptionType = "call";
  let selectedSide: StrategySide = "long";
  // Neutral default: a straddle glance does not imply a directional recommendation.
  let payoffOptionType: PayoffGlanceType = "straddle";
  let strategyTemplateNotice = "";
  let selectedGreekMetric: GreekMetric = "delta";
  let strategyLegs: StrategyLeg[] = [];
  let surfaceModel: SurfaceModel = "linear";
  let probabilityRange: { lower: number; upper: number } | null = null;
  let probabilityDragStart: number | null = null;
  let lastProbabilityExpiry: string | null = null;
  let strategyContextMenu = {
    open: false,
    x: 0,
    y: 0,
    row: null as ChainRow | null
  };
  let Surface3DComponent: any = null;
  let surface3DLoading = false;

  $: if ((mode === "surface" || mode === "distribution") && !Surface3DComponent && !surface3DLoading) {
    surface3DLoading = true;
    void import("../components/Surface3D.svelte")
      .then((module) => { Surface3DComponent = module.default; })
      .finally(() => { surface3DLoading = false; });
  }

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const money = (value: number | null | undefined) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const pct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const signedPct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
  const signedMoney = (value: number | null | undefined) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const greek = (value: number | null | undefined, digits = 3) =>
    value == null || !Number.isFinite(value) ? "N/A" : value.toFixed(digits);
  const signedGreek = (value: number | null | undefined, digits = 3) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
  const shortTime = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";
  const formatExpiry = (expiry: string | null | undefined) => {
    if (!expiry) return "N/A";
    const match = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(expiry);
    return match ? `${match[1]}/${match[2]}/${match[3]}` : expiry;
  };
  const depthLabel = (value: string | null | undefined) =>
    value === "max"
      ? "Max"
      : value === "front_deep"
        ? "Front Deep"
        : value
          ? value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase())
          : "N/A";

  let activeExpiry: string | null = null;
  let chainRows: ChainRow[] = [];
  let chainGreekRows: ChainGreekRow[] = [];
  let overview = deriveOverviewSnapshot(result, selectedExpiry);
  let surfaceStats = deriveSurfaceStats(result);
  let termStructure = deriveTermStructure(result);
  let skewRows = deriveSkewRows(result);
  let realizedRows = deriveRealizedVolatility([], surfaceStats.frontAtmIv);
  let strategyPayoff = deriveStrategyPayoff(strategyLegs, result?.spot);
  let strategyPayoffMatrix: StrategyPayoffMatrix | null = null;
  let strategyContracts = 1;
  let strategySizing: StrategySizing = deriveStrategySizing(strategyPayoff, strategyLegs, strategyContracts, null);
  let strategyGreeks: StrategyGreekSummary | null = null;
  let probabilitySurface: ImpliedProbabilitySurface | null = null;
  let probabilitySlice: ImpliedProbabilitySlice | null = null;
  let probabilitySelection: ImpliedProbabilitySelection | null = null;
  let ivSmile: IvSmile | null = null;
  let hoverSmile: IvSmilePoint | null = null;
  let termCurve: TermCurve | null = null;
  let hasFittedModel = false;
  let observedSurfacePoints = deriveObservedSurfacePoints(result);
  let hoverTerm: TermCurvePoint | null = null;
  let hoveredSurface: { row: number; col: number } | null = null;
  let payoffMatrix: OptionPayoffMatrix | null = null;
  let atmStrikeIndex = 0;
  let surfaceAlerts: string[] = [];
  let requestSymbol = "";
  let displayedSymbol = "No surface";
  let historySymbol = "";
  let optionsHistoryMatches = false;
  let researchHistoryMatches = false;
  let realizedPricePoints: TimeSeriesPoint[] = [];
  let realizedSourceLabel = "N/A";

  $: if (!optionsModes.some((candidate) => candidate.id === mode)) {
    mode = "overview";
  }

  $: if (requestedSymbol && requestedSymbol !== lastRequestedSymbol) {
    lastRequestedSymbol = requestedSymbol;
    symbol = requestedSymbol.toUpperCase();
    selectedExpiry = null;
  }

  $: activeExpiry = selectedExpiryForSurface(result, selectedExpiry);
  $: chainRows = deriveChainRows(result, activeExpiry);
  $: chainGreekRows = deriveChainGreekRows(result, activeExpiry);
  $: overview = deriveOverviewSnapshot(result, activeExpiry);
  $: surfaceStats = deriveSurfaceStats(result);
  $: termStructure = deriveTermStructure(result);
  $: hasFittedModel = hasParametricIvFit(result);
  $: observedSurfacePoints = deriveObservedSurfacePoints(result);
  $: termCurve = deriveTermCurve(
    termStructure,
    300,
    132,
    hasFittedModel ? deriveObservedTermStructure(result) : []
  );
  $: skewRows = deriveSkewRows(result);
  $: historySymbol = (result?.symbol ?? requestSymbol).trim().toUpperCase();
  $: optionsHistoryMatches = Boolean(
    historySymbol && underlyingHistory?.symbol?.trim().toUpperCase() === historySymbol
  );
  $: surfaceBadge = result ? toProvenanceBadge(result) : null;
  $: historyBadge = optionsHistoryMatches && underlyingHistory ? toProvenanceBadge(underlyingHistory) : null;
  $: researchHistoryMatches = Boolean(
    historySymbol && researchPrimarySymbol?.trim().toUpperCase() === historySymbol && underlyingPricePoints.length
  );
  $: realizedPricePoints =
    optionsHistoryMatches && underlyingHistory?.points.length
      ? underlyingHistory.points
      : researchHistoryMatches
        ? underlyingPricePoints
        : [];
  $: realizedSourceLabel =
    optionsHistoryMatches && underlyingHistory?.points.length
      ? underlyingHistory.source_label || "Options underlying history"
      : researchHistoryMatches
        ? "Equity Research price history"
        : "N/A";
  $: selectedExpiryRowIndex = activeExpiry ? (result?.expiries ?? []).indexOf(activeExpiry) : -1;
  $: selectedAtmIv =
    selectedExpiryRowIndex >= 0 ? result?.iv_grid?.[selectedExpiryRowIndex]?.[atmStrikeIndex] ?? null : null;
  $: realizedRows = deriveRealizedVolatility(realizedPricePoints, surfaceStats.frontAtmIv, [20, 60, 120], {
    iv: selectedAtmIv,
    expiry: activeExpiry,
    days: activeExpiry ? daysToExpiry(activeExpiry) : null,
  });
  $: probabilitySurface = deriveImpliedProbabilitySurface(result);
  $: probabilitySlice = deriveImpliedProbabilitySlice(probabilitySurface, activeExpiry);
  $: if (probabilitySlice && lastProbabilityExpiry !== probabilitySlice.expiry) {
    lastProbabilityExpiry = probabilitySlice.expiry;
    probabilityRange = defaultProbabilityRange(probabilitySlice, result?.spot);
  }
  $: probabilitySelection = deriveImpliedProbabilitySelection(probabilitySlice, probabilityRange?.lower, probabilityRange?.upper);
  $: strategyPayoff = deriveStrategyPayoff(strategyLegs, result?.spot);
  $: strategyPayoffMatrix = deriveStrategyPayoffMatrix(strategyLegs, chainRows, result?.spot);
  $: livePosition = livePositionForSymbol(portfolioPositions, result?.symbol ?? symbol);
  $: strategySizing = deriveStrategySizing(strategyPayoff, strategyLegs, strategyContracts, livePosition);

  // Publish exactly what the workbench is showing so a Copilot run from Options
  // is grounded in the visible submode, expiry, legs, payoff and RV-IV state
  // rather than defaulting to the front expiry (GUA-20260903-2).
  $: ivWorkbenchState.set({
    mode,
    symbol: result?.symbol ?? displayedSymbol ?? null,
    selected_expiry: activeExpiry,
    selected_expiry_days: activeExpiry ? daysToExpiry(activeExpiry) : null,
    contracts: strategySizing.contracts,
    contract_multiplier: strategySizing.multiplier,
    legs: strategyLegs.map((leg) => ({
      side: leg.side,
      option_type: leg.optionType,
      expiry: leg.expiry,
      days_to_expiry: daysToExpiry(leg.expiry),
      strike: leg.strike,
      premium: leg.premium,
      quantity: leg.quantity,
    })),
    strategy: strategyLegs.length
      ? {
          net_premium_per_share: strategyPayoff.netPremium,
          net_premium_total: strategySizing.netPremiumTotal,
          premium_direction: strategySizing.premiumDirection,
          max_profit_per_share: strategyPayoff.maxProfit,
          max_loss_per_share: strategyPayoff.maxLoss,
          max_profit_total: strategySizing.maxProfitTotal,
          max_loss_total: strategySizing.maxLossTotal,
          breakevens: strategyPayoff.breakevens,
          net_delta: strategyGreeks?.delta ?? null,
          net_gamma: strategyGreeks?.gamma ?? null,
          net_vega: strategyGreeks?.vega ?? null,
          net_theta: strategyGreeks?.theta ?? null,
          shares_represented: strategySizing.sharesRepresented,
          live_position_shares: strategySizing.positionQuantity,
          coverage_ratio: strategySizing.coverageRatio,
          sizing_warnings: strategySizing.warnings,
        }
      : null,
    realized_vs_implied: realizedRows.map((row) => ({
      window_days: row.window,
      realized_vol: row.realizedVol,
      reference_iv: row.referenceIv,
      reference_iv_expiry: row.referenceExpiry,
      reference_iv_days: row.referenceDays,
      spread: row.spreadToReferenceIv,
    })),
  });

  onDestroy(() => ivWorkbenchState.set(null));
  $: strategyGreeks = deriveStrategyGreeks(strategyLegs, result);
  $: ivSmile = deriveIvSmile(
    chainRows,
    overview.atmPair?.strike,
    320,
    150,
    hasFittedModel ? deriveFittedSmileSamples(result, activeExpiry) : []
  );
  $: payoffMatrix = deriveOptionPayoffMatrix(chainRows, result?.spot, payoffOptionType);
  $: atmStrikeIndex = nearestStrikeIndex(result);
  $: requestSymbol = symbol.trim().toUpperCase() || result?.symbol?.trim().toUpperCase() || "";
  $: displayedSymbol = result?.symbol ?? (symbol.trim() ? normalizedSymbol() : "No surface");
  $: if (!loading && isSurfaceModel(result?.surface_model) && result?.surface_model !== surfaceModel) {
    surfaceModel = result.surface_model;
  }
  $: surfaceAlerts = deriveIvSurfaceAlerts({
    result,
    session,
    status,
    requestedSymbol: requestSymbol,
    errorMessage,
    loading,
    sessionLoading,
  });

  function normalizedSymbol() {
    return requestSymbol;
  }

  function activeMarketDataMode() {
    return status?.market_data_mode ?? result?.collection?.market_data_mode ?? session?.market_data_mode ?? "delayed";
  }

  async function loadMaxSurface() {
    const nextSymbol = normalizedSymbol();
    if (!nextSymbol) {
      return;
    }
    await onLoad({
      symbol: nextSymbol,
      marketDataMode: activeMarketDataMode(),
      waitSeconds: 60,
      depthPreset: "max",
      surfaceModel,
    });
  }

  async function chooseSurfaceModel(nextModel: SurfaceModel) {
    surfaceModel = nextModel;
    const nextSymbol = normalizedSymbol();
    if (!nextSymbol || !result) {
      return;
    }
    await onLoad({
      symbol: nextSymbol,
      marketDataMode: activeMarketDataMode(),
      waitSeconds: 60,
      depthPreset: result.collection?.depth_preset ?? "max",
      surfaceModel: nextModel,
    });
  }

  async function stopSession() {
    await onStopSession();
  }

  function chooseMode(nextMode: OptionsMode) {
    mode = nextMode;
  }

  function sendSurfaceToCopilot() {
    const surface = result;
    if (!surface) {
      return;
    }
    const handoff: CrossTabHandoffEnvelope = {
      source_tab: "iv",
      source_mode: mode,
      selected_entity: {
        entity_type: "options_surface",
        label: `${surface.symbol} Options Workspace`,
        normalized_id: surface.symbol,
        provider_id: surface.source_provider,
        native_id: surface.symbol,
        metadata: {
          symbol: surface.symbol,
          expiries: surface.expiries.length,
          strikes: surface.strikes.length,
          points: surface.points,
          selected_expiry: activeExpiry,
          freshness_label: surface.freshness_label,
          delayed: surface.delayed,
        },
      },
      selected_timeframe: surface.timestamp
        ? { label: `Snapshot ${shortTime(surface.timestamp)}`, start: null, end: surface.timestamp }
        : null,
      provider: surface.source_provider,
      source: null,
      warnings: surface.warnings ?? [],
      normalized_ids: { symbol: surface.symbol },
      timestamp: new Date().toISOString(),
      intended_target_tab: "copilot",
      intended_target_mode: "active_tab",
    };
    void onSendToCopilot(handoff);
  }

  function sendOptionRowToStrategyLab(row: ChainRow, optionType: StrategyOptionType, open = false) {
    if (!result || !onSendToStrategyLab) {
      return;
    }
    onSendToStrategyLab(
      buildOptionsStrategyHandoff(
        {
          surface: result,
          row,
          optionType,
          sourceMode: mode
        },
        { sourceMode: mode }
      ),
      { open }
    );
  }

  function contextMenuPosition(event: MouseEvent | KeyboardEvent) {
    if (event instanceof MouseEvent && event.type === "contextmenu") {
      return { x: event.clientX, y: event.clientY };
    }
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: rect.left + 12, y: rect.top + Math.min(rect.height, 32) };
  }

  function openOptionStrategyMenu(event: MouseEvent | KeyboardEvent, row: ChainRow) {
    event.preventDefault();
    const position = contextMenuPosition(event);
    strategyContextMenu = { open: true, x: position.x, y: position.y, row };
  }

  function handleOptionRowKeydown(event: KeyboardEvent, row: ChainRow) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      openOptionStrategyMenu(event, row);
    }
  }

  function handleOptionStrategyMenuSelect(action: string) {
    const row = strategyContextMenu.row;
    if (!row) {
      return;
    }
    if (action === "add-call") sendOptionRowToStrategyLab(row, "call", false);
    if (action === "add-call-open") sendOptionRowToStrategyLab(row, "call", true);
    if (action === "add-put") sendOptionRowToStrategyLab(row, "put", false);
    if (action === "add-put-open") sendOptionRowToStrategyLab(row, "put", true);
  }

  function closeStrategyMenu() {
    strategyContextMenu = { ...strategyContextMenu, open: false };
  }

  function addLeg(row: ChainRow, optionType = selectedOptionType, side = selectedSide) {
    const leg = buildStrategyLegFromChainRow(row, optionType, side);
    if (!leg) {
      return;
    }
    strategyLegs = [...strategyLegs, { ...leg, id: `${leg.id}-${strategyLegs.length + 1}` }];
    mode = "strategies";
  }

  function removeLeg(id: string) {
    strategyLegs = strategyLegs.filter((leg) => leg.id !== id);
  }

  function clearStrategy() {
    strategyLegs = [];
    strategyTemplateNotice = "";
  }

  function applyStrategyTemplate(templateId: StrategyTemplateId) {
    const template = STRATEGY_TEMPLATES.find((item) => item.id === templateId);
    const built = buildStrategyTemplateLegs(templateId, chainRows, result?.spot);
    strategyLegs = built.legs;
    const summary = template ? `${template.label} (${template.stance})` : templateId;
    strategyTemplateNotice = built.warnings.length
      ? `${summary}: ${built.warnings.join(" ")}`
      : `${summary} built from the nearest priced strikes on ${formatExpiry(activeExpiry)}.`;
  }

  function payoffHeatStyle(pct: number, maxGain: number) {
    const color = pct >= 0 ? "var(--positive)" : "var(--negative)";
    const denom = pct >= 0 ? Math.max(maxGain, 0.01) : 1;
    const intensity = Math.min(0.52, (Math.abs(pct) / denom) * 0.52);
    return `background: color-mix(in srgb, ${color} ${Math.round(intensity * 100)}%, transparent);`;
  }

  function strategyPayoffHeatStyle(value: number | null | undefined) {
    if (value == null || !strategyPayoffMatrix) {
      return "";
    }
    const color = value >= 0 ? "var(--positive)" : "var(--negative)";
    const intensity = Math.min(0.52, (Math.abs(value) / Math.max(strategyPayoffMatrix.maxAbsPl, 0.01)) * 0.52);
    return `background: color-mix(in srgb, ${color} ${Math.round(intensity * 100)}%, transparent); color: ${color};`;
  }

  const payoffPct = (value: number) => `${value >= 0 ? "+" : ""}${Math.round(Math.max(-1, value) * 100)}`;

  function heatStyle(value: number | null | undefined) {
    if (value == null || surfaceStats.minIv == null || surfaceStats.maxIv == null) {
      return "";
    }
    const range = Math.max(surfaceStats.maxIv - surfaceStats.minIv, 0.01);
    const heat = Math.max(8, Math.min(58, ((value - surfaceStats.minIv) / range) * 58));
    return `background: color-mix(in srgb, var(--chart-primary) ${heat}%, var(--bg-0));`;
  }

  function rowClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function isSurfaceModel(value: string | null | undefined): value is SurfaceModel {
    return value === "linear" || value === "spline" || value === "ssvi";
  }

  const densityPct = (value: number) => `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
  const greekMetricLabel: Record<GreekMetric, string> = {
    delta: "Delta",
    gamma: "Gamma",
    vega: "Vega",
    theta: "Theta",
    rho: "Rho",
  };

  function formatGreekMetric(row: ChainGreekRow, side: "call" | "put") {
    const value = row[side]?.[selectedGreekMetric];
    const digits = selectedGreekMetric === "gamma" ? 4 : selectedGreekMetric === "theta" ? 3 : 3;
    return selectedGreekMetric === "delta" || selectedGreekMetric === "theta" || selectedGreekMetric === "rho"
      ? signedGreek(value, digits)
      : greek(value, digits);
  }

  function defaultProbabilityRange(slice: ImpliedProbabilitySlice, spot: number | null | undefined) {
    const center = spot && Number.isFinite(spot) ? spot : (slice.minStrike + slice.maxStrike) / 2;
    const halfWidth = Math.max((slice.maxStrike - slice.minStrike) * 0.16, 1);
    return {
      lower: Math.max(slice.minStrike, center - halfWidth),
      upper: Math.min(slice.maxStrike, center + halfWidth),
    };
  }

  function probabilityStrikeFromEvent(event: MouseEvent, slice: ImpliedProbabilitySlice) {
    const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
    const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * slice.width;
    const leftX = slice.points[0]?.x ?? 44;
    const rightX = slice.points.at(-1)?.x ?? slice.width - 12;
    const t = Math.max(0, Math.min(1, (x - leftX) / Math.max(rightX - leftX, 1)));
    return slice.minStrike + t * (slice.maxStrike - slice.minStrike);
  }

  function startProbabilitySelection(event: MouseEvent) {
    if (!probabilitySlice) return;
    const strike = probabilityStrikeFromEvent(event, probabilitySlice);
    probabilityDragStart = strike;
    probabilityRange = { lower: strike, upper: strike };
  }

  function moveProbabilitySelection(event: MouseEvent) {
    if (probabilityDragStart == null || !probabilitySlice) return;
    const strike = probabilityStrikeFromEvent(event, probabilitySlice);
    probabilityRange = {
      lower: Math.min(probabilityDragStart, strike),
      upper: Math.max(probabilityDragStart, strike),
    };
  }

  function endProbabilitySelection() {
    probabilityDragStart = null;
  }
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div>
        <span class="eyebrow">OPTIONS WORKSPACE</span>
        <h2>{displayedSymbol}</h2>
      </div>
      <div class="header-actions">
        <label class="symbol-control">
          <span>Symbol</span>
          <input bind:value={symbol} on:keydown={(event) => event.key === "Enter" && loadMaxSurface()} placeholder="SPY" />
        </label>
        <button class="primary-action" type="button" on:click={loadMaxSurface} disabled={loading || sessionLoading || !requestSymbol}>
          {loading ? "LOADING..." : result ? "Reload Max Surface" : "Load Max Surface"}
        </button>
        {#if session?.running}
          <button type="button" on:click={stopSession} disabled={sessionLoading}>
            {sessionLoading ? "STOPPING..." : "Stop Stream"}
          </button>
        {/if}
        <button type="button" on:click={sendSurfaceToCopilot} disabled={loading || !result}>Copilot</button>
      </div>
    </div>

    <div class="mode-row">
      <div class="mode-bar" role="tablist" aria-label="Options modes">
        {#each optionsModes as optionMode}
          <button
            class="mode-btn"
            class:selected={optionMode.id === mode}
            role="tab"
            aria-selected={optionMode.id === mode}
            type="button"
            on:click={() => chooseMode(optionMode.id)}
          >
            {optionMode.label}
          </button>
        {/each}
      </div>
      <div class="source-strip">
        <div><span>Spot</span><strong class:absent={money(result?.spot) === "N/A"}>{money(result?.spot)}</strong></div>
        <div><span>ATM IV</span><strong class:absent={pct(surfaceStats.frontAtmIv) === "N/A"}>{pct(surfaceStats.frontAtmIv)}</strong></div>
        <div><span>Term</span><strong class={rowClass(surfaceStats.termSlope)} class:absent={signedPct(surfaceStats.termSlope) === "N/A"}>{signedPct(surfaceStats.termSlope)}</strong></div>
        <div><span>Expiry</span><strong class:absent={formatExpiry(activeExpiry) === "N/A"}>{formatExpiry(activeExpiry)}</strong></div>
        <div><span>Depth</span><strong class:absent={depthLabel(result?.collection?.depth_preset) === "N/A"}>{depthLabel(result?.collection?.depth_preset)}</strong></div>
        <div><span>Source</span><ProvenanceBadge data={surfaceBadge} /></div>
      </div>
    </div>
  </article>

  {#if surfaceAlerts.length}
    <article class="panel alert-panel" role="alert">
      <h3>Options Data Issue</h3>
      <div class="warning-list">
        {#each surfaceAlerts.slice(0, 5) as message}
          <div>{message}</div>
        {/each}
      </div>
    </article>
  {/if}

  {#if mode === "realized_implied" && workingAnalysis}
    <CopilotOptionsWorkingAnalysis analysis={workingAnalysis} />
  {/if}

  {#if mode === "overview"}
    <div class="workspace-grid overview-grid">
      <div class="primary-column">
        <article class="panel kpi-panel">
          <div class="kpi-grid">
            <div class="metric"><span>Front ATM IV</span><strong class:absent={pct(surfaceStats.frontAtmIv) === "N/A"} class:fitted={isFittedCell(surfaceStats.frontAtmIvSource)}>{pct(surfaceStats.frontAtmIv)}</strong><small>{formatExpiry(surfaceStats.frontExpiry)}{isFittedCell(surfaceStats.frontAtmIvSource) ? " · fitted" : ""}</small></div>
            <div class="metric"><span>Back ATM IV</span><strong class:absent={pct(surfaceStats.backAtmIv) === "N/A"} class:fitted={isFittedCell(surfaceStats.backAtmIvSource)}>{pct(surfaceStats.backAtmIv)}</strong><small>{signedPct(surfaceStats.termSlope)} slope{isFittedCell(surfaceStats.backAtmIvSource) ? " · fitted" : ""}</small></div>
            <div class="metric"><span>ATM Strike</span><strong class:absent={fmt(surfaceStats.atmStrike, 2) === "N/A"}>{fmt(surfaceStats.atmStrike, 2)}</strong><small>Spot {money(result?.spot)}</small></div>
            <div class="metric"><span>Put / Call OI</span><strong class:absent={fmt(overview.putCallOpenInterestRatio, 2) === "N/A"}>{fmt(overview.putCallOpenInterestRatio, 2)}</strong><small>Volume {fmt(overview.putCallVolumeRatio, 2)}</small></div>
            <div class="metric"><span>Implied Move</span><strong class:absent={pct(overview.atmPair?.impliedMovePct) === "N/A"}>{pct(overview.atmPair?.impliedMovePct)}</strong><small>Straddle {money(overview.atmPair?.straddleMidpoint)}</small></div>
            <div class="metric"><span>Max Pain</span><strong class:absent={fmt(overview.maxPainStrike, 2) === "N/A"}>{fmt(overview.maxPainStrike, 2)}</strong><small>{overview.frontChain.length} chain rows</small></div>
          </div>
        </article>

        <article class="panel split-panel">
          <div class="panel-head">
            <h3>Front Expiry Chain</h3>
            <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
              {#each result?.expiries ?? [] as expiry}
                <option value={expiry}>{formatExpiry(expiry)} / {daysToExpiry(expiry)}D</option>
              {/each}
            </select>
          </div>
          {#if chainRows.length}
            <table class="chain-table">
              <thead>
                <tr>
                  <th>C Δ</th><th>C IV</th><th>C Px</th><th class="strike-cell">Strike</th><th>P Px</th><th>P IV</th><th>P Δ</th><th>Move</th>
                </tr>
              </thead>
              <tbody>
                {#each chainRows as row}
                  {@const callItm = row.distancePct != null && row.distancePct < 0}
                  {@const putItm = row.distancePct != null && row.distancePct > 0}
                  <tr
                    class:atm={row.strike === overview.atmPair?.strike}
                    class:handoff-row={Boolean(onSendToStrategyLab)}
                    tabindex={onSendToStrategyLab ? 0 : undefined}
                    on:contextmenu={(event) => openOptionStrategyMenu(event, row)}
                    on:keydown={(event) => handleOptionRowKeydown(event, row)}
                  >
                    <td class:itm={callItm} class:absent={fmt(row.callDelta, 3) === "N/A"}>{fmt(row.callDelta, 3)}</td>
                    <td class:itm={callItm} class:absent={pct(row.callIv) === "N/A"}>{pct(row.callIv)}</td>
                    <td class:itm={callItm} class:absent={money(row.callMidpoint) === "N/A"}>{money(row.callMidpoint)}</td>
                    <td class="strike-cell" class:absent={fmt(row.strike, 2) === "N/A"}>{fmt(row.strike, 2)}</td>
                    <td class:itm={putItm} class:absent={money(row.putMidpoint) === "N/A"}>{money(row.putMidpoint)}</td>
                    <td class:itm={putItm} class:absent={pct(row.putIv) === "N/A"}>{pct(row.putIv)}</td>
                    <td class:itm={putItm} class:absent={fmt(row.putDelta, 3) === "N/A"}>{fmt(row.putDelta, 3)}</td>
                    <td class:absent={pct(row.impliedMovePct) === "N/A"}>{pct(row.impliedMovePct)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <p class="muted">Load an options snapshot to populate the front-expiry chain.</p>
          {/if}
        </article>

        <article class="panel payoff-panel split-panel">
          <div class="panel-head">
            <h3>Payoff Glance</h3>
            <div class="payoff-controls">
              {#if payoffMatrix}
                <span class="payoff-meta">ATM {fmt(payoffMatrix.strike, 0)} {payoffOptionType} · @ {money(payoffMatrix.premium)} · IV {pct(payoffMatrix.sigma)} · % of max risk</span>
              {/if}
              <select bind:value={payoffOptionType} aria-label="Payoff option type">
                <option value="straddle">Straddle (neutral)</option>
                <option value="call">Call</option>
                <option value="put">Put</option>
              </select>
            </div>
          </div>
          {#if payoffMatrix}
            <div class="payoff-heatmap-wrap">
              <table class="payoff-heatmap">
                <thead>
                  <tr>
                    <th class="price-col">Price</th>
                    {#each payoffMatrix.dteColumns as dte}
                      <th>{dte === 0 ? "Exp" : `${dte}d`}</th>
                    {/each}
                    <th class="move-col">+/-%</th>
                  </tr>
                </thead>
                <tbody>
                  {#each payoffMatrix.rows as row}
                    <tr class:atm={Math.abs(row.movePct) < 1e-9}>
                      <th class="price-col">{fmt(row.price, 0)}</th>
                      {#each row.cells as cell}
                        <td style={payoffHeatStyle(cell.pct, payoffMatrix.maxGain)}>{payoffPct(cell.pct)}</td>
                      {/each}
                      <td class="move-col {rowClass(row.movePct)}" class:absent={signedPct(row.movePct, 0) === "N/A"}>{signedPct(row.movePct, 0)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="muted pad">No ATM option pair available to model payoff.</p>
          {/if}
        </article>
      </div>

      <div class="support-column">
        <article class="panel">
          <h3>
            Front IV Smile
            {#if ivSmile?.fitPoints.length}<span class="fit-legend"><i></i>Observed <b></b>{result?.surface_model_label ?? "Model fit"}</span>{/if}
            {#if hoverSmile}
              <span class="smile-readout">{fmt(hoverSmile.strike, 0)} · {pct(hoverSmile.iv)}{hoverSmile.isAtm ? " · ATM" : ""}</span>
            {/if}
          </h3>
          {#if ivSmile}
            <div class="smile-chart">
              <svg
                viewBox={`0 0 ${ivSmile.width} ${ivSmile.height}`}
                role="img"
                aria-label="Front expiry implied volatility smile"
                on:mouseleave={() => (hoverSmile = null)}
              >
                <line class="smile-axis" x1="32" y1={ivSmile.height - 18} x2={ivSmile.width - 8} y2={ivSmile.height - 18} />
                {#if ivSmile.atmX != null}
                  <line class="smile-atm" x1={ivSmile.atmX} y1="10" x2={ivSmile.atmX} y2={ivSmile.height - 18} />
                {/if}
                <path class="smile-area" d={ivSmile.areaPath} />
                <path class="smile-line" d={ivSmile.linePath} />
                {#each ivSmile.points as point}
                  <circle class:atm={point.isAtm} class:observed={ivSmile.fitPoints.length > 0} class="smile-dot" cx={point.x} cy={point.y} r={ivSmile.fitPoints.length ? (point.isAtm ? 3.2 : 2.6) : (point.isAtm ? 2.6 : 1.6)} />
                {/each}
                {#if hoverSmile}
                  <line class="smile-guide" x1={hoverSmile.x} y1="10" x2={hoverSmile.x} y2={ivSmile.height - 18} />
                  <circle class="smile-dot hover" cx={hoverSmile.x} cy={hoverSmile.y} r="3.4" />
                {/if}
                {#each ivSmile.points as point}
                  <circle
                    class="smile-hit"
                    cx={point.x}
                    cy={point.y}
                    r="9"
                    role="presentation"
                    on:mouseenter={() => (hoverSmile = point)}
                  />
                {/each}
                <text class="smile-label" x="2" y="14">{pct(ivSmile.maxIv)}</text>
                <text class="smile-label" x="2" y={ivSmile.height - 20}>{pct(ivSmile.minIv)}</text>
                <text class="smile-label strike-min" x="32" y={ivSmile.height - 5}>{fmt(ivSmile.minStrike, 0)}</text>
                <text class="smile-label strike-max" x={ivSmile.width - 8} y={ivSmile.height - 5}>{fmt(ivSmile.maxStrike, 0)}</text>
              </svg>
            </div>
          {:else}
            <p class="muted">No front slice available.</p>
          {/if}
        </article>

        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "chain"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header">
          <h3>Options Chain</h3>
          <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
            {#each result?.expiries ?? [] as expiry}
              <option value={expiry}>{formatExpiry(expiry)} / {daysToExpiry(expiry)}D</option>
            {/each}
          </select>
        </div>
        {#if chainRows.length}
          <table class="chain-table">
            <thead>
              <tr>
                <th>C OI</th><th>C Δ</th><th>C IV</th><th>Call</th><th class="strike-cell">Strike</th><th>Mny</th><th>Put</th><th>P IV</th><th>P Δ</th><th>P OI</th><th>Strategy</th>
              </tr>
            </thead>
            <tbody>
              {#each chainRows as row}
                {@const callItm = row.distancePct != null && row.distancePct < 0}
                {@const putItm = row.distancePct != null && row.distancePct > 0}
                <tr
                  class:atm={row.strike === overview.atmPair?.strike}
                  class:handoff-row={Boolean(onSendToStrategyLab)}
                  tabindex={onSendToStrategyLab ? 0 : undefined}
                  on:contextmenu={(event) => openOptionStrategyMenu(event, row)}
                  on:keydown={(event) => handleOptionRowKeydown(event, row)}
                >
                  <td class:itm={callItm} class:absent={fmt(row.callOpenInterest, 0) === "N/A"}>{fmt(row.callOpenInterest, 0)}</td>
                  <td class:itm={callItm} class:absent={fmt(row.callDelta, 3) === "N/A"}>{fmt(row.callDelta, 3)}</td>
                  <td class:itm={callItm} class:absent={pct(row.callIv) === "N/A"}>{pct(row.callIv)}</td>
                  <td class:itm={callItm} class:absent={money(row.callMidpoint) === "N/A"}>{money(row.callMidpoint)}</td>
                  <td class="strike-cell" class:absent={fmt(row.strike, 2) === "N/A"}>{fmt(row.strike, 2)}</td>
                  <td class={rowClass(row.distancePct)} class:absent={signedPct(row.distancePct) === "N/A"}>{signedPct(row.distancePct)}</td>
                  <td class:itm={putItm} class:absent={money(row.putMidpoint) === "N/A"}>{money(row.putMidpoint)}</td>
                  <td class:itm={putItm} class:absent={pct(row.putIv) === "N/A"}>{pct(row.putIv)}</td>
                  <td class:itm={putItm} class:absent={fmt(row.putDelta, 3) === "N/A"}>{fmt(row.putDelta, 3)}</td>
                  <td class:itm={putItm} class:absent={fmt(row.putOpenInterest, 0) === "N/A"}>{fmt(row.putOpenInterest, 0)}</td>
                  <td class="action-cell">
                    <button type="button" on:click={() => addLeg(row, "call")}>+C</button>
                    <button type="button" on:click={() => addLeg(row, "put")}>+P</button>
                    <button type="button" on:click={() => sendOptionRowToStrategyLab(row, "call", true)} disabled={!onSendToStrategyLab}>SL</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted pad">Load a snapshot to inspect the chain.</p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Chain Context</h3>
          <div class="metric-list">
            <div><span>Expiry</span><strong class:absent={formatExpiry(activeExpiry) === "N/A"}>{formatExpiry(activeExpiry)}</strong></div>
            <div><span>DTE</span><strong>{activeExpiry ? daysToExpiry(activeExpiry) : "N/A"}</strong></div>
            <div><span>Rows</span><strong>{chainRows.length}</strong></div>
            <div><span>ATM Pair</span><strong class:absent={fmt(overview.atmPair?.strike, 2) === "N/A"}>{fmt(overview.atmPair?.strike, 2)}</strong></div>
            <div><span>Straddle</span><strong class:absent={money(overview.atmPair?.straddleMidpoint) === "N/A"}>{money(overview.atmPair?.straddleMidpoint)}</strong></div>
          </div>
        </article>
        <article class="panel greek-panel">
          <div class="panel-head">
            <h3>Gamma-Owned Greeks</h3>
            <select bind:value={selectedGreekMetric} aria-label="Greek metric">
              <option value="delta">Delta</option>
              <option value="gamma">Gamma</option>
              <option value="vega">Vega</option>
              <option value="theta">Theta</option>
              <option value="rho">Rho</option>
            </select>
          </div>
          {#if chainGreekRows.length}
            <div class="compact-table">
              <table>
                <thead>
                  <tr><th>Strike</th><th>C {greekMetricLabel[selectedGreekMetric]}</th><th>P {greekMetricLabel[selectedGreekMetric]}</th><th>IV</th></tr>
                </thead>
                <tbody>
                  {#each chainGreekRows as row}
                    <tr class:atm={row.strike === overview.atmPair?.strike}>
                      <td class:absent={fmt(row.strike, 1) === "N/A"}>{fmt(row.strike, 1)}</td>
                      <td>{formatGreekMetric(row, "call")}</td>
                      <td>{formatGreekMetric(row, "put")}</td>
                      <td class:absent={pct(row.call?.sigma ?? row.put?.sigma) === "N/A"}>{pct(row.call?.sigma ?? row.put?.sigma)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="muted">Load a fitted surface to calculate Gamma-owned Greeks.</p>
          {/if}
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "surface"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel surface-hero">
          <div class="panel-head">
            <h3>IV Surface</h3>
          </div>
          {#if Surface3DComponent}
          <svelte:component this={Surface3DComponent}
            strikes={result?.strikes ?? []}
            expiries={result?.expiries ?? []}
            grid={result?.iv_grid ?? []}
            observedPoints={observedSurfacePoints}
            dte={(result?.expiries ?? []).map((expiry) => daysToExpiry(expiry))}
            {atmStrikeIndex}
            {surfaceModel}
            surfaceModelStatus={result?.surface_model_status ?? null}
            modelLoading={loading}
            onSurfaceModelChange={chooseSurfaceModel}
          />
          {:else}<div class="chart-empty">LOADING 3D SURFACE...</div>{/if}
        </article>

        <article class="panel table-panel">
          <div class="table-header">
            <h3>Surface Grid</h3>
            {#if hoveredSurface && result}
              <span class="surface-readout">
                {formatExpiry(result.expiries[hoveredSurface.row])} · {fmt(result.strikes[hoveredSurface.col], 1)} · {cellSource(result, hoveredSurface.row, hoveredSurface.col) === "unavailable" ? "N/A" : pct(result.iv_grid[hoveredSurface.row]?.[hoveredSurface.col])}
                <em>{cellSourceLabel(cellSource(result, hoveredSurface.row, hoveredSurface.col)) ?? "Source unknown"}</em>
              </span>
            {:else if result?.cell_sources?.length}
              <span class="fit-legend"><i></i>Observed <b></b>Fitted</span>
            {/if}
          </div>
          {#if result?.surface_model_discontinuities?.length}
            <ul class="surface-alert">
              {#each result.surface_model_discontinuities as note}<li>{note}</li>{/each}
            </ul>
          {/if}
          {#if result?.expiries.length && result.strikes.length}
            <div class="surface-scroll">
              <table class="surface-table" on:mouseleave={() => (hoveredSurface = null)}>
                <thead>
                  <tr>
                    <th>Expiry</th>
                    {#each result.strikes as strike, colIndex}
                      <th class:atm-strike={atmStrikeIndex === colIndex} class:col-hi={hoveredSurface?.col === colIndex}>{fmt(strike, 1)}</th>
                    {/each}
                  </tr>
                </thead>
                <tbody>
                  {#each result.expiries as expiry, rowIndex}
                    <tr class:row-hi={hoveredSurface?.row === rowIndex}>
                      <th>{formatExpiry(expiry)}<small>{daysToExpiry(expiry)}D</small></th>
                      {#each result.iv_grid[rowIndex] ?? [] as value, colIndex}
                        <td
                          style={heatStyle(value)}
                          class:cross={hoveredSurface?.row === rowIndex || hoveredSurface?.col === colIndex}
                          class:cell-hi={hoveredSurface?.row === rowIndex && hoveredSurface?.col === colIndex}
                          class:fitted={isFittedCell(cellSource(result, rowIndex, colIndex))}
                          class:absent={cellSource(result, rowIndex, colIndex) === "unavailable"}
                          title={cellSourceLabel(cellSource(result, rowIndex, colIndex)) ?? ""}
                          on:mouseenter={() => (hoveredSurface = { row: rowIndex, col: colIndex })}
                        >{cellSource(result, rowIndex, colIndex) === "unavailable" ? "N/A" : pct(value)}</td>
                      {/each}
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="muted pad">Load a max-depth surface snapshot to inspect expiry/strike volatility.</p>
          {/if}
        </article>
      </div>

      <div class="support-column">
        <article class="panel">
          <h3>
            Term Structure
            {#if termCurve?.observedPoints.length}<span class="fit-legend"><i></i>Observed <b></b>{result?.surface_model_label ?? "Model fit"}</span>{/if}
            {#if hoverTerm}
              <span class="smile-readout">{hoverTerm.dte}D · {pct(hoverTerm.iv)}</span>
            {/if}
          </h3>
          {#if termCurve}
            <div class="smile-chart">
              <svg
                viewBox={`0 0 ${termCurve.width} ${termCurve.height}`}
                role="img"
                aria-label="ATM term structure curve"
                on:mouseleave={() => (hoverTerm = null)}
              >
                <line class="smile-axis" x1="34" y1={termCurve.height - 20} x2={termCurve.width - 10} y2={termCurve.height - 20} />
                <path class="smile-area" d={termCurve.areaPath} />
                <path class="smile-line" d={termCurve.linePath} />
                {#each termCurve.observedPoints.length ? termCurve.observedPoints : termCurve.points as point}
                  <circle class:observed={termCurve.observedPoints.length > 0} class="smile-dot" cx={point.x} cy={point.y} r={termCurve.observedPoints.length ? 2.8 : 1.8} />
                {/each}
                {#if hoverTerm}
                  <line class="smile-guide" x1={hoverTerm.x} y1="10" x2={hoverTerm.x} y2={termCurve.height - 20} />
                  <circle class="smile-dot hover" cx={hoverTerm.x} cy={hoverTerm.y} r="3.4" />
                {/if}
                {#each termCurve.observedPoints.length ? termCurve.observedPoints : termCurve.points as point}
                  <circle
                    class="smile-hit"
                    cx={point.x}
                    cy={point.y}
                    r="10"
                    role="presentation"
                    on:mouseenter={() => (hoverTerm = point)}
                  />
                {/each}
                <text class="smile-label" x="2" y="14">{pct(termCurve.maxIv)}</text>
                <text class="smile-label" x="2" y={termCurve.height - 24}>{pct(termCurve.minIv)}</text>
                <text class="smile-label" x="34" y={termCurve.height - 6}>{termCurve.points[0].dte}D</text>
                <text class="smile-label strike-max" x={termCurve.width - 10} y={termCurve.height - 6}>{termCurve.points[termCurve.points.length - 1].dte}D</text>
              </svg>
            </div>
          {:else}
            <p class="muted">No term structure available.</p>
          {/if}
        </article>

        <article class="panel">
          <h3>Skew By Expiry</h3>
          <div class="compact-table">
            <table>
              <thead><tr><th>Expiry</th><th>Put</th><th>Call</th><th>Spread</th></tr></thead>
              <tbody>
                {#each skewRows as row}
                  <tr>
                    <td class:absent={formatExpiry(row.expiry) === "N/A"}>{formatExpiry(row.expiry)}</td>
                    <td class={rowClass(row.putSkew)} class:absent={signedPct(row.putSkew) === "N/A"}>{signedPct(row.putSkew)}</td>
                    <td class={rowClass(row.callSkew)} class:absent={signedPct(row.callSkew) === "N/A"}>{signedPct(row.callSkew)}</td>
                    <td class={rowClass(row.wingSpread)} class:absent={signedPct(row.wingSpread) === "N/A"}>{signedPct(row.wingSpread)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>

        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "realized_implied"}
    <div class="workspace-grid">
      <article class="panel table-panel">
        <div class="table-header">
          <h3>Realized vs IV</h3>
          <span class="tenor-note">
            Front {formatExpiry(surfaceStats.frontExpiry)}{surfaceStats.frontExpiry ? ` (${daysToExpiry(surfaceStats.frontExpiry)}D)` : ""}
            · Selected {formatExpiry(activeExpiry)}{activeExpiry ? ` (${daysToExpiry(activeExpiry)}D)` : ""}
          </span>
        </div>
        {#if realizedRows.some((row) => row.realizedVol != null)}
          <table>
            <thead><tr><th>Window</th><th>Realized Vol</th><th>Front ATM IV</th><th>Selected ATM IV</th><th>IV Premium</th><th>Obs</th></tr></thead>
            <tbody>
              {#each realizedRows as row}
                <tr>
                  <td>{row.window}D</td>
                  <td class:absent={pct(row.realizedVol) === "N/A"}>{pct(row.realizedVol)}</td>
                  <td class:absent={pct(surfaceStats.frontAtmIv) === "N/A"}>{pct(surfaceStats.frontAtmIv)}</td>
                  <td class:absent={pct(row.referenceIv) === "N/A"}>{pct(row.referenceIv)}</td>
                  <td class={rowClass(row.spreadToReferenceIv)} class:absent={signedPct(row.spreadToReferenceIv) === "N/A"}>{signedPct(row.spreadToReferenceIv)}</td>
                  <td>{row.observationCount}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="muted pad">
            No underlying price history is available for {historySymbol || displayedSymbol}. Refresh the Options surface to retry the listed-market history provider.
          </p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Boundary</h3>
          <div class="metric-list">
            <div><span>Implied Source</span><ProvenanceBadge data={surfaceBadge} /></div>
            <div><span>Realized Source</span><strong>{realizedSourceLabel}</strong></div>
            <div><span>Price Points</span><strong>{realizedPricePoints.length}</strong></div>
            <div><span>History Freshness</span><ProvenanceBadge data={historyBadge} /></div>
            <div><span>Front ATM IV</span><strong class:absent={pct(surfaceStats.frontAtmIv) === "N/A"}>{pct(surfaceStats.frontAtmIv)}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "distribution"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel surface-hero">
          <div class="panel-head">
            <h3>Implied Probability Surface</h3>
          </div>
          {#if Surface3DComponent}
          <svelte:component this={Surface3DComponent}
            strikes={probabilitySurface?.strikes ?? []}
            expiries={probabilitySurface?.expiries ?? []}
            grid={probabilitySurface?.densityGrid ?? []}
            dte={(probabilitySurface?.expiries ?? []).map((expiry) => daysToExpiry(expiry))}
            {atmStrikeIndex}
            {surfaceModel}
            surfaceModelStatus={result?.surface_model_status ?? null}
            modelLoading={loading}
            onSurfaceModelChange={chooseSurfaceModel}
            valueAxisLabel="Density"
            formatValue={densityPct}
            emptyMessage="Load a max-depth surface to render the implied probability surface."
          />
          {:else}<div class="chart-empty">LOADING 3D SURFACE...</div>{/if}
        </article>

        <article class="panel probability-slice-panel">
          <div class="panel-head">
            <h3>
              Probability Slice
              {#if probabilitySelection}
                <span class="surface-readout">
                  {fmt(probabilitySelection.lowerStrike, 1)}-{fmt(probabilitySelection.upperStrike, 1)} · {pct(probabilitySelection.probabilityMass, 2)}
                </span>
              {/if}
            </h3>
            <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
              {#each result?.expiries ?? [] as expiry}
                <option value={expiry}>{formatExpiry(expiry)} / {daysToExpiry(expiry)}D</option>
              {/each}
            </select>
          </div>
          {#if probabilitySlice}
            <div class="probability-chart">
              <svg
                viewBox={`0 0 ${probabilitySlice.width} ${probabilitySlice.height}`}
                role="img"
                aria-label="Implied probability density slice"
                on:mousedown={startProbabilitySelection}
                on:mousemove={moveProbabilitySelection}
                on:mouseup={endProbabilitySelection}
                on:mouseleave={endProbabilitySelection}
              >
                <line class="prob-axis" x1={probabilitySlice.points[0].x} y1={probabilitySlice.baseline} x2={probabilitySlice.points[probabilitySlice.points.length - 1].x} y2={probabilitySlice.baseline} />
                <path class="prob-area" d={probabilitySlice.areaPath} />
                {#if probabilitySelection}
                  <path class="prob-selected" d={probabilitySelection.areaPath} />
                {/if}
                <path class="prob-line" d={probabilitySlice.linePath} />
                {#each probabilitySlice.points as point}
                  <circle class="prob-dot" cx={point.x} cy={point.y} r="2" />
                {/each}
                <text class="smile-label" x="2" y="14">{densityPct(probabilitySlice.maxDensity)}</text>
                <text class="smile-label" x={probabilitySlice.points[0].x} y={probabilitySlice.height - 6}>{fmt(probabilitySlice.minStrike, 0)}</text>
                <text class="smile-label strike-max" x={probabilitySlice.points[probabilitySlice.points.length - 1].x} y={probabilitySlice.height - 6}>{fmt(probabilitySlice.maxStrike, 0)}</text>
              </svg>
            </div>
          {:else}
            <p class="muted">Load a surface with spot, expiries, strikes, and fitted IV cells to inspect implied probabilities.</p>
          {/if}
        </article>
      </div>

      <div class="support-column">
        <article class="panel">
          <h3>Assumptions</h3>
          <div class="metric-list">
            <div><span>Method</span><strong>Local lognormal RND proxy</strong></div>
            <div><span>Fit</span><strong>{result?.surface_model_label ?? "Line interpolation"}</strong></div>
            <div><span>Expiry</span><strong class:absent={formatExpiry(probabilitySlice?.expiry) === "N/A"}>{formatExpiry(probabilitySlice?.expiry)}</strong></div>
            <div><span>DTE</span><strong class:absent={probabilitySlice?.dte == null}>{probabilitySlice?.dte ?? "N/A"}</strong></div>
            <div><span>Visible Mass</span><strong class:absent={pct(probabilitySelection?.probabilityMass, 2) === "N/A"}>{pct(probabilitySelection?.probabilityMass, 2)}</strong></div>
            <div><span>Range</span><strong>{probabilitySelection ? `${fmt(probabilitySelection.lowerStrike, 1)}-${fmt(probabilitySelection.upperStrike, 1)}` : "N/A"}</strong></div>
          </div>
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {:else if mode === "strategies"}
    <div class="workspace-grid">
      <article class="panel">
        <div class="panel-head">
          <h3>Strategy Builder</h3>
          <div class="builder-controls">
            <select bind:value={selectedSide}>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
            <select bind:value={selectedOptionType}>
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
            <select value={activeExpiry ?? ""} on:change={(event) => selectedExpiry = event.currentTarget.value}>
              {#each result?.expiries ?? [] as expiry}
                <option value={expiry}>{formatExpiry(expiry)}</option>
              {/each}
            </select>
            <label class="contracts-field">
              Contracts
              <input
                type="number"
                min="1"
                step="1"
                bind:value={strategyContracts}
                on:change={() => (strategyContracts = Math.max(1, Math.round(Number(strategyContracts) || 1)))}
                aria-label="Contracts per structure"
              />
            </label>
            <button type="button" on:click={clearStrategy} disabled={!strategyLegs.length}>Clear</button>
          </div>
        </div>

        <div class="template-bar" role="group" aria-label="One-click strategy templates">
          <span class="template-label">Templates</span>
          {#each STRATEGY_TEMPLATES as template}
            <button
              type="button"
              class="template-button"
              title={template.stance}
              on:click={() => applyStrategyTemplate(template.id)}
              disabled={!chainRows.length}
            >
              {template.label}
            </button>
          {/each}
        </div>
        {#if strategyTemplateNotice}
          <p class="muted template-notice">{strategyTemplateNotice}</p>
        {/if}

        <div class="strategy-layout">
          <div class="compact-table chain-pick">
            <table>
              <thead><tr><th>Strike</th><th>Call</th><th>Put</th><th>Add</th></tr></thead>
              <tbody>
                {#each chainRows as row}
                  <tr
                    class:atm={row.strike === overview.atmPair?.strike}
                    class:handoff-row={Boolean(onSendToStrategyLab)}
                    tabindex={onSendToStrategyLab ? 0 : undefined}
                    on:contextmenu={(event) => openOptionStrategyMenu(event, row)}
                    on:keydown={(event) => handleOptionRowKeydown(event, row)}
                  >
                    <td class:absent={fmt(row.strike, 2) === "N/A"}>{fmt(row.strike, 2)}</td>
                    <td class:absent={money(row.callMidpoint) === "N/A"}>{money(row.callMidpoint)}</td>
                    <td class:absent={money(row.putMidpoint) === "N/A"}>{money(row.putMidpoint)}</td>
                    <td><button type="button" on:click={() => addLeg(row)}>Add</button></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>

          <div class="legs-panel">
            <h4>Legs</h4>
            {#if strategyLegs.length}
              {#each strategyLegs as leg}
                <div class="leg-row">
                  <span>{leg.side.toUpperCase()} {leg.optionType.toUpperCase()}</span>
                  <strong>{formatExpiry(leg.expiry)} {fmt(leg.strike, 2)} @ {money(leg.premium)}</strong>
                  <button type="button" on:click={() => removeLeg(leg.id)}>Remove</button>
                </div>
              {/each}
            {:else}
              <p class="muted">Add legs from the chain to calculate expiry payoff.</p>
            {/if}
          </div>
        </div>

        {#if strategyPayoffMatrix}
          <div class="strategy-payoff-table">
            <div class="table-header">
              <h3>Payoff Matrix</h3>
              <span class="payoff-meta">% of risk basis {money(strategyPayoffMatrix.riskBasis)} · mark-to-model by remaining DTE</span>
            </div>
            <div class="payoff-heatmap-wrap">
              <table class="payoff-heatmap">
                <thead>
                  <tr>
                    <th class="price-col">Price</th>
                    {#each strategyPayoffMatrix.dteColumns as dte}
                      <th>{dte === 0 ? "Exp" : `${dte}d`}</th>
                    {/each}
                    <th class="move-col">+/-%</th>
                  </tr>
                </thead>
                <tbody>
                  {#each strategyPayoffMatrix.rows as row}
                    <tr class:atm={Math.abs(row.movePct) < 1e-9}>
                      <th class="price-col">{fmt(row.price, 0)}</th>
                      {#each row.cells as cell}
                        <td style={strategyPayoffHeatStyle(cell.pl)} class:absent={signedMoney(cell.pl) === "N/A"}>{signedMoney(cell.pl)}</td>
                      {/each}
                      <td class="move-col {rowClass(row.movePct)}" class:absent={signedPct(row.movePct, 0) === "N/A"}>{signedPct(row.movePct, 0)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        {:else}
          <p class="muted pad">Add priced legs from the chain to populate the strategy payoff matrix.</p>
        {/if}
      </article>

      <div class="support-column">
        <article class="panel">
          <h3>Strategy Summary</h3>
          <p class="sizing-basis">
            Per share · {strategySizing.contracts} contract{strategySizing.contracts === 1 ? "" : "s"} x {strategySizing.multiplier} shares
          </p>
          <div class="metric-list">
            <div><span>Net Premium</span><strong class:absent={signedMoney(strategyPayoff.netPremium) === "N/A"}>{signedMoney(strategyPayoff.netPremium)}</strong></div>
            <div><span>Max Profit</span><strong>{strategyPayoff.maxProfit == null ? "Open" : signedMoney(strategyPayoff.maxProfit)}</strong></div>
            <div><span>Max Loss</span><strong>{strategyPayoff.maxLoss == null ? "Open" : signedMoney(strategyPayoff.maxLoss)}</strong></div>
            <div><span>Breakevens</span><strong>{strategyPayoff.breakevens.length ? strategyPayoff.breakevens.map((value) => fmt(value, 2)).join(", ") : "N/A"}</strong></div>
            <div><span>Net Delta</span><strong class:absent={signedGreek(strategyGreeks?.delta, 3) === "N/A"}>{signedGreek(strategyGreeks?.delta, 3)}</strong></div>
            <div><span>Net Gamma</span><strong class:absent={signedGreek(strategyGreeks?.gamma, 4) === "N/A"}>{signedGreek(strategyGreeks?.gamma, 4)}</strong></div>
            <div><span>Net Vega</span><strong class:absent={signedGreek(strategyGreeks?.vega, 3) === "N/A"}>{signedGreek(strategyGreeks?.vega, 3)}</strong></div>
            <div><span>Net Theta</span><strong class:absent={signedGreek(strategyGreeks?.theta, 3) === "N/A"}>{signedGreek(strategyGreeks?.theta, 3)}</strong></div>
            <div><span>Net Rho</span><strong class:absent={signedGreek(strategyGreeks?.rho, 3) === "N/A"}>{signedGreek(strategyGreeks?.rho, 3)}</strong></div>
          </div>
        </article>

        <article class="panel">
          <h3>Position Sizing</h3>
          {#if strategyLegs.length}
            <div class="metric-list">
              <div>
                <span>Total {strategySizing.premiumDirection === "credit" ? "Credit" : "Debit"}</span>
                <strong class:absent={signedMoney(strategySizing.netPremiumTotal) === "N/A"}>{signedMoney(strategySizing.netPremiumTotal)}</strong>
              </div>
              <div><span>Total Max Profit</span><strong>{strategySizing.maxProfitTotal == null ? "Open" : signedMoney(strategySizing.maxProfitTotal)}</strong></div>
              <div><span>Total Max Loss</span><strong>{strategySizing.maxLossTotal == null ? "Open" : signedMoney(strategySizing.maxLossTotal)}</strong></div>
              <div><span>Shares Delivered</span><strong>{strategySizing.sharesRepresented.toLocaleString()}</strong></div>
              <div>
                <span>Live Position</span>
                <strong class:absent={strategySizing.positionQuantity == null}>
                  {strategySizing.positionQuantity == null ? "N/A" : `${strategySizing.positionQuantity.toLocaleString()} sh`}
                </strong>
              </div>
              <div>
                <span>Coverage</span>
                <strong
                  class:absent={strategySizing.coverageRatio == null}
                  class:over-hedged={strategySizing.coverageRatio != null && strategySizing.coverageRatio > 1.05}
                >{strategySizing.coverageRatio == null ? "N/A" : pct(strategySizing.coverageRatio, 0)}</strong>
              </div>
              {#if strategySizing.maxWholeContractsWithinPosition != null}
                <div><span>Fits Without Over-Hedge</span><strong>{strategySizing.maxWholeContractsWithinPosition} contract{strategySizing.maxWholeContractsWithinPosition === 1 ? "" : "s"}</strong></div>
              {/if}
            </div>
            {#if strategySizing.warnings.length}
              <ul class="sizing-warnings">
                {#each strategySizing.warnings as warning}<li>{warning}</li>{/each}
              </ul>
            {/if}
            <p class="sizing-note">Research sizing only. Gamma does not route, place, or stage orders.</p>
          {:else}
            <p class="muted">Add priced legs to size the structure against live exposure.</p>
          {/if}
        </article>
        {@render DiagnosticsPanel(result, session, status, sessionLoading)}
      </div>
    </div>
  {/if}

  <CompactContextMenu
    open={strategyContextMenu.open}
    x={strategyContextMenu.x}
    y={strategyContextMenu.y}
    label="Options Strategy Lab actions"
    items={[
      { id: "add-call", label: "Add Call Context", disabled: !onSendToStrategyLab },
      { id: "add-call-open", label: "Call and Open", disabled: !onSendToStrategyLab },
      { id: "add-put", label: "Add Put Context", disabled: !onSendToStrategyLab },
      { id: "add-put-open", label: "Put and Open", disabled: !onSendToStrategyLab }
    ]}
    onSelect={handleOptionStrategyMenuSelect}
    onClose={closeStrategyMenu}
  />
</section>

{#snippet DiagnosticsPanel(result: IvSurface | null, session: IvSessionStatus | null, status: SystemStatus | null, sessionLoading: boolean)}
  <article class="panel diagnostics-panel">
    <h3>Data & Source</h3>
    <div class="metric-list">
      <div><span>Provider</span><ProvenanceBadge data={result ? toProvenanceBadge(result) : null} showTime={false} /></div>
      <div><span>Backend Mode</span><strong>{status?.market_data_mode ?? result?.collection?.market_data_mode ?? "unknown"}</strong></div>
      <div><span>Session</span><strong>{sessionLoading ? "loading" : session?.running ? "running" : session?.status_text ?? "idle"}</strong></div>
      <div><span>Fit</span><strong>{result?.surface_model_label ?? "Line interpolation"}</strong></div>
      <div><span>Cells</span><strong>{result?.quality ? `${result.quality.observed_surface_cells}/${result.quality.expected_surface_cells}` : "N/A"}</strong></div>
      <div><span>Lines</span><strong>{result?.collection ? `${result.collection.estimated_total_market_data_lines}/${result.collection.configured_market_data_line_budget}` : "N/A"}</strong></div>
      <div><span>Updated</span><strong class:absent={shortTime(result?.timestamp) === "N/A"}>{shortTime(result?.timestamp)}</strong></div>
    </div>
    {#if result?.transformation_note}
      <p class="note">{result.transformation_note}</p>
    {/if}
    {#if result?.warnings?.length || result?.messages?.length || result?.surface_model_notes?.length || session?.messages?.length}
      <div class="warning-list">
        {#each [...(result?.warnings ?? []), ...(result?.messages ?? []), ...(result?.surface_model_notes ?? []), ...(session?.messages ?? [])].slice(0, 4) as message}
          <div>{message}</div>
        {/each}
      </div>
    {/if}
  </article>
{/snippet}

<style>
  /* Local: this view's panels lay their own children out and do not want the
     base panel's grid gap between them. */
  .panel {
    display: block;
  }

  .view,
  .metric-list,
  .warning-list,
  .slice-list,
  .distribution,
  .strategy-layout,
  .legs-panel {
    display: grid;
    gap: var(--space-4);
  }

  .overview-grid {
    grid-template-columns: minmax(0, 1.35fr) minmax(22rem, 0.65fr);
  }

  .mode-row,
  .header-actions,
  .source-strip,
  .panel-head,
  .builder-controls,
  .bar-row,
  .dist-row,
  .metric-list > div,
  .leg-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .header-actions,
  .builder-controls {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .template-bar {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--divider);
  }

  .template-label {
    color: var(--text-2);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .template-button {
    font-size: var(--text-sm);
    padding: var(--space-2) var(--space-4);
  }

  .template-notice {
    font-size: var(--text-sm);
    padding: var(--space-2) 0 0;
  }

  .mode-row {
    align-items: stretch;
    flex-wrap: wrap;
  }

  span,
  .muted,
  th,
  small {
    color: var(--text-2);
  }

  th {
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  h2,
  h3,
  h4,
  p {
    margin: 0;
  }

  h2 {
    font-size: var(--text-lg);
    line-height: 1.2;
  }

  h3 {
    font-size: var(--text-base);
  }

  h4 {
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  strong {
    color: var(--text-0);
    font-weight: 650;
  }

  button,
  input,
  select {
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    min-height: 28px;
    padding: var(--space-2) var(--space-4);
    font: inherit;
    font-size: var(--text-base);
    border-radius: 2px;
  }

  button {
    cursor: pointer;
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
  }

  .primary-action {
    border-color: color-mix(in srgb, var(--accent) 34%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  .symbol-control {
    display: grid;
    gap: var(--space-1);
  }

  .symbol-control span {
    font-size: var(--text-xs);
    text-transform: uppercase;
  }

  .symbol-control input {
    width: 8rem;
  }

  .source-strip {
    flex: 1;
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .source-strip > div {
    min-width: 5.8rem;
    display: grid;
    gap: 0.08rem;
    text-align: right;
  }

  .source-strip span,
  .metric span {
    font-size: var(--text-xs);
    text-transform: uppercase;
  }

  .kpi-panel {
    padding: 0;
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
  }

  .metric {
    min-width: 0;
    padding: var(--space-4) var(--space-5);
    border-right: 1px solid var(--divider);
    display: grid;
    gap: var(--space-1);
  }

  .metric:last-child {
    border-right: 0;
  }

  .metric small {
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-header {
    min-height: 30px;
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
  }

  td {
    color: var(--text-1);
  }

  tbody tr:hover td {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  tbody tr.handoff-row {
    cursor: context-menu;
  }

  tbody tr.handoff-row:focus-visible td {
    outline: 1px solid color-mix(in srgb, var(--accent) 34%, transparent);
    outline-offset: -1px;
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  tr.atm td,
  th.atm-strike {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }

  /* Option chain: calls left, strike center, puts right. */
  .chain-table .strike-cell {
    font-weight: 700;
    color: var(--text-0);
    text-align: center;
    background: var(--bg-1);
    border-left: 1px solid var(--panel-strong);
    border-right: 1px solid var(--panel-strong);
  }

  /* In-the-money side shaded blue (call side when strike < spot, put side when strike > spot). */
  .chain-table td.itm {
    background: color-mix(in srgb, var(--accent) 11%, transparent);
  }

  /* ATM row in accent amber, overriding ITM shading. */
  .chain-table tr.atm td {
    color: var(--warning);
    background: color-mix(in srgb, var(--warning) 18%, transparent);
  }

  th small {
    display: block;
    margin-top: 0.08rem;
    font-size: var(--text-2xs);
    letter-spacing: 0;
  }

  .surface-scroll {
    overflow: auto;
    max-height: 42vh;
  }

  .surface-hero {
    padding: var(--space-4) var(--space-4) var(--space-4);
  }

  .surface-hero .panel-head {
    margin-bottom: var(--space-1);
  }

  .surface-readout {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.02em;
  }

  .surface-readout em {
    margin-left: var(--space-2);
    color: var(--text-2);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    font-style: normal;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* Fitted cells stay readable but never pass as quotes. */
  .surface-table td.fitted {
    color: var(--text-2);
    font-style: italic;
  }

  .metric strong.fitted {
    color: var(--text-1);
  }

  .contracts-field {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-2);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .contracts-field input {
    width: 4.5ch;
  }

  .sizing-basis {
    margin: 0 0 var(--space-2);
    color: var(--text-2);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .sizing-warnings {
    margin: var(--space-3) 0 0;
    padding-left: var(--space-4);
    color: var(--warning);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    line-height: 1.5;
  }

  .sizing-note {
    margin: var(--space-2) 0 0;
    color: var(--text-2);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
  }

  .metric-list strong.over-hedged {
    color: var(--warning);
  }

  .surface-alert {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--divider);
    list-style: none;
    color: var(--warning);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    line-height: 1.5;
  }

  .surface-table td {
    cursor: crosshair;
  }

  .surface-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--bg-1);
  }

  .surface-table tbody th {
    position: sticky;
    left: 0;
    z-index: 1;
    background: var(--bg-1);
  }

  .surface-table thead th:first-child {
    z-index: 2;
  }

  .surface-table th.col-hi,
  .surface-table tr.row-hi > th {
    color: var(--accent);
  }

  .surface-table td.cross {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }

  .surface-table td.cell-hi {
    background: color-mix(in srgb, var(--accent) 26%, transparent);
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .compact-table {
    overflow: auto;
  }

  .compact-table th,
  .compact-table td {
    padding: var(--space-2) var(--space-3);
  }

  .probability-slice-panel {
    padding: 0;
    overflow: hidden;
  }

  .probability-slice-panel .panel-head {
    min-height: 32px;
    padding: var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .probability-chart {
    height: 260px;
    padding: var(--space-4) var(--space-4) var(--space-3);
  }

  .probability-chart svg {
    width: 100%;
    height: 100%;
    display: block;
    cursor: crosshair;
  }

  .prob-axis {
    stroke: var(--panel-strong);
    stroke-width: 1;
  }

  .prob-area {
    fill: color-mix(in srgb, var(--chart-primary) 10%, transparent);
  }

  .prob-selected {
    fill: color-mix(in srgb, var(--chart-secondary) 38%, transparent);
  }

  .prob-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.7;
  }

  .prob-dot {
    fill: var(--chart-primary);
    opacity: 0.72;
  }

  .action-cell {
    display: flex;
    gap: var(--space-2);
  }

  .pad {
    padding: var(--space-4) var(--space-5);
  }

  .bar {
    flex: 1;
    min-width: 4rem;
    height: 0.42rem;
    background: var(--panel-strong);
  }

  .fill {
    height: 100%;
    background: var(--chart-primary);
  }

  .bar-row,
  .dist-row,
  .metric-list > div,
  .warning-list > div {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-2);
  }

  .split-panel {
    padding: 0;
    overflow: hidden;
  }

  .split-panel .panel-head {
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
  }

  .payoff-controls {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .payoff-meta {
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--text-2);
  }

  .payoff-controls select {
    min-height: 24px;
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-sm);
  }

  .payoff-heatmap-wrap {
    overflow: auto;
    max-height: 60vh;
  }

  .payoff-heatmap {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-xs);
  }

  .payoff-heatmap th,
  .payoff-heatmap td {
    padding: var(--space-1) var(--space-3);
    text-align: right;
    border-bottom: 1px solid var(--divider);
    border-right: 1px solid var(--divider);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .payoff-heatmap thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--bg-1);
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .payoff-heatmap td {
    color: var(--text-0);
  }

  .payoff-heatmap .price-col {
    position: sticky;
    left: 0;
    text-align: left;
    color: var(--text-1);
    font-weight: 650;
    background: var(--bg-1);
  }

  .payoff-heatmap thead .price-col {
    z-index: 2;
  }

  .payoff-heatmap tr.atm .price-col {
    color: var(--accent);
  }

  .payoff-heatmap .move-col {
    color: var(--text-2);
  }

  .strategy-payoff-table {
    margin-top: var(--space-4);
    border-top: 1px solid var(--divider);
  }

  .strategy-payoff-table .table-header {
    padding-left: 0;
    padding-right: 0;
  }

  .smile-chart {
    width: 100%;
  }

  .smile-chart svg {
    display: block;
    width: 100%;
    height: auto;
  }

  .smile-axis {
    stroke: var(--divider);
    stroke-width: 1;
  }

  .smile-atm {
    stroke: var(--accent);
    stroke-width: 1;
    stroke-dasharray: 3 3;
    opacity: 0.55;
  }

  .smile-area {
    fill: color-mix(in srgb, var(--chart-primary) 15%, transparent);
    stroke: none;
  }

  .smile-line {
    fill: none;
    stroke: var(--chart-primary);
    stroke-width: 1.6;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
  }

  .smile-dot {
    fill: var(--chart-primary);
  }

  .smile-dot.observed {
    fill: var(--text-0);
    stroke: var(--bg-0);
    stroke-width: 1.2;
  }

  .smile-dot.atm {
    fill: var(--accent);
  }

  .smile-dot.hover {
    fill: var(--text-0);
    stroke: var(--chart-primary);
    stroke-width: 1.4;
    vector-effect: non-scaling-stroke;
  }

  .smile-guide {
    stroke: var(--accent);
    stroke-width: 1;
    stroke-dasharray: 2 2;
    opacity: 0.7;
  }

  .smile-hit {
    fill: transparent;
    pointer-events: all;
    cursor: crosshair;
  }

  .smile-readout {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.02em;
    margin-left: var(--space-3);
  }

  .smile-label {
    fill: var(--text-2);
    font-size: var(--text-2xs);
  }

  .smile-label.strike-max {
    text-anchor: end;
  }

  .strategy-layout {
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.8fr);
    align-items: start;
  }

  .chain-pick {
    max-height: 58vh;
  }

  .legs-panel {
    border-left: 1px solid var(--divider);
    padding-left: var(--space-5);
  }

  .alert-panel {
    background: var(--panel-bg);
  }

  .fit-legend {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin-left: var(--space-3);
    color: var(--text-2);
    font-family: var(--app-font);
    font-size: var(--text-2xs);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .fit-legend i {
    width: var(--space-2);
    height: var(--space-2);
    background: var(--text-0);
  }

  .fit-legend b {
    width: var(--space-5);
    height: 1px;
    background: var(--chart-primary);
  }

  .alert-panel h3 {
    color: var(--warning);
  }

  .leg-row {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
  }

  .leg-row strong {
    font-size: var(--text-sm);
  }

  .diagnostics-panel .note {
    color: var(--text-1);
    line-height: 1.45;
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
  }

  .warning-list > div {
    color: var(--warning);
    line-height: 1.35;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1240px) {
    .overview-grid,
    .strategy-layout {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1180px) {
    .kpi-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .legs-panel {
      border-left: 0;
      padding-left: 0;
    }
  }

  @media (max-width: 760px) {
    .header-top,
    .mode-row,
    .header-actions,
    .source-strip {
      align-items: stretch;
      flex-direction: column;
    }

    .source-strip > div {
      text-align: left;
    }

    .mode-bar {
      grid-template-columns: 1fr;
      width: 100%;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }
  }
</style>
