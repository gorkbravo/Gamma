<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import SearchDropdown from "../components/SearchDropdown.svelte";
  import HeroPriceChart from "../components/HeroPriceChart.svelte";
  import ProvenanceBadge from "../components/ProvenanceBadge.svelte";
  import { toProvenanceBadge } from "../lib/provenance";
  import type {
    CrossTabHandoffEnvelope,
    CopilotWorkingAnalysis,
    FundamentalsDcfModel,
    FundamentalsDcfScenario,
    FundamentalsDcfSnapshotList,
    FundamentalsFinancials,
    FundamentalsOverview,
    FundamentalsPeers,
    FundamentalsReference,
    FundamentalsReverseValuation,
    FundamentalsSearchResponse,
    StrategyLabHandoffEnvelope
  } from "../lib/api/types";
  import type {
    FundamentalsDcfSavePayload,
    FundamentalsSearchOptions,
    FundamentalsSearchState,
    FundamentalsSelectOptions
  } from "../lib/stores/app";
  import { heroPricePointFromApiPoint, type HeroPricePoint } from "../lib/view-models/hero-price-chart";
  import {
    buildDcfSavePayload,
    amendmentSummary,
    createDcfDraft,
    dcfDecisionGateFromWarnings,
    driverTone,
    findDcfScenario,
    fundamentalsModes,
    normalizePeerTickers,
    parseEditableNumber,
    setDraftActiveScenario,
    snapshotDisplayName,
    statementTrends,
    statementViewForSelection,
    sourceTracesForStatement,
    updateDraftAssumptionSeriesValue,
    updateDraftOverride,
    terminalValueFraming,
    updateDraftScalarAssumption,
    type FundamentalsDcfDraft,
    type FundamentalsMode,
    type FundamentalsStatementBasis,
    type FundamentalsStatementKind
  } from "../lib/view-models/fundamentals";

  export let search: FundamentalsSearchResponse | null = null;
  export let selectedTicker: string | null = null;
  export let focusedTicker: string | null = null;
  export let overview: FundamentalsOverview | null = null;
  export let financials: FundamentalsFinancials | null = null;
  export let dcfModel: FundamentalsDcfModel | null = null;
  export let peers: FundamentalsPeers | null = null;
  export let reverseValuation: FundamentalsReverseValuation | null = null;
  export let workingAnalysis: CopilotWorkingAnalysis | null = null;
  export let reference: FundamentalsReference | null = null;
  export let dcfSnapshots: FundamentalsDcfSnapshotList | null = null;
  export let loading = false;
  export let searchState: FundamentalsSearchState = {
    query: "",
    loading: false,
    refreshing: false,
    stale: false,
    error: null,
    requestedAt: null,
    completedAt: null
  };
  export let saving = false;
  export let loadWarnings: string[] = [];
  export let onSearch: (options?: FundamentalsSearchOptions) => Promise<unknown> | void;
  export let onSelectCompany: (ticker: string, options?: FundamentalsSelectOptions) => Promise<unknown> | void;
  export let onSavePeerBasket: (ticker: string, peerTickers: string[]) => Promise<unknown> | void;
  export let onSaveDcfModel: (ticker: string, payload: FundamentalsDcfSavePayload) => Promise<unknown> | void;
  export let onSaveDcfSnapshot: (ticker: string, name?: string) => Promise<unknown> | void;
  export let onLoadDcfSnapshot: (ticker: string, snapshotId: string) => Promise<unknown> | void;
  export let onSendToCopilot: (handoff: CrossTabHandoffEnvelope) => Promise<unknown> | void = () => {};
  export let onSendToStrategyLab: (handoff: StrategyLabHandoffEnvelope, options?: { open?: boolean }) => Promise<unknown> | void = () => {};
  export let onOpenRelatedTab: (target: "equity_research" | "risk" | "iv", ticker: string, label: string) => Promise<unknown> | void = () => {};

  const modeOptions = fundamentalsModes;
  const statementOptions: Array<{ id: FundamentalsStatementKind; label: string }> = [
    { id: "income", label: "Income" },
    { id: "balance", label: "Balance Sheet" },
    { id: "cashflow", label: "Cash Flow" },
    { id: "ratios", label: "Ratios" }
  ];
  const basisOptions: Array<{ id: FundamentalsStatementBasis; label: string }> = [
    { id: "annual", label: "Annual" },
    { id: "quarterly", label: "Quarterly" }
  ];
  const familyLabels: Record<string, string> = {
    valuation: "Valuation",
    profitability: "Profitability",
    growth: "Growth",
    returns: "Returns",
    balance_sheet: "Balance Sheet",
    efficiency: "Efficiency",
    leverage: "Leverage",
    liquidity: "Liquidity"
  };
  const lowerBetterMetricIds = new Set(["ev_to_sales", "ev_to_ebit", "price_to_earnings", "net_debt_to_ebit"]);
  const positiveOnlyLowerBetterMetricIds = new Set(["ev_to_sales", "ev_to_ebit", "price_to_earnings"]);
  const marketContextMetricIds = ["current_price", "market_cap", "enterprise_value", "ev_to_sales", "ev_to_ebit", "net_debt", "diluted_shares"];

  export let mode: FundamentalsMode = "overview";
  let searchQuery = "";
  let statementBasis: FundamentalsStatementBasis = "annual";
  let statementKind: FundamentalsStatementKind = "income";
  let peerDraftTickers: string[] = [];
  let manualPeerTickers = "";
  let peerDirty = false;
  let dcfDraft: FundamentalsDcfDraft = createDcfDraft(null);
  let dcfDirty = false;
  let snapshotName = "";
  let peerFingerprint = "";
  let dcfFingerprint = "";
  let searchHydratedTicker = "";

  const currency = (value: number | null | undefined, digits = 0) =>
    value == null
      ? "N/A"
      : new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: digits
        }).format(value);

  const compactCurrency = (value: number | null | undefined) => {
    if (value == null) return "N/A";
    const absolute = Math.abs(value);
    if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
    if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
    if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    return currency(value, 0);
  };

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const finiteNumber = (value: unknown) =>
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "N/A";

  function companySummary(currentOverview: FundamentalsOverview | null, company: FundamentalsOverview["company"] | FundamentalsFinancials["company"] | null) {
    if (!company) {
      return "Select a company to load the SEC profile, filings, statements, and DCF context.";
    }
    const sourcedSummary = String(currentOverview?.company_summary?.summary ?? "").trim();
    if (sourcedSummary) {
      return sourcedSummary;
    }
    return "Business summary unavailable for the current company payload.";
  }

  function heatmapScore(metricId: string, value: number | null | undefined, rowValues: Array<number | null | undefined>) {
    if (value == null || !Number.isFinite(value)) {
      return null;
    }
    if (positiveOnlyLowerBetterMetricIds.has(metricId) && value <= 0) {
      return null;
    }
    const comparableValues = rowValues.filter((candidate): candidate is number => {
      if (candidate == null || !Number.isFinite(candidate)) {
        return false;
      }
      if (positiveOnlyLowerBetterMetricIds.has(metricId)) {
        return candidate > 0;
      }
      return true;
    });
    if (comparableValues.length < 2) {
      return 0.5;
    }
    const minimum = Math.min(...comparableValues);
    const maximum = Math.max(...comparableValues);
    if (minimum === maximum) {
      return 0.5;
    }
    const scaled = (value - minimum) / (maximum - minimum);
    return lowerBetterMetricIds.has(metricId) ? 1 - scaled : scaled;
  }

  function heatmapCellClass(metricId: string, value: number | null | undefined, rowValues: Array<number | null | undefined>) {
    const score = heatmapScore(metricId, value, rowValues);
    if (score == null) return "heat-neutral";
    if (score >= 0.88) return "heat-positive-strong";
    if (score >= 0.72) return "heat-positive";
    if (score >= 0.58) return "heat-positive-soft";
    if (score >= 0.42) return "heat-warning";
    if (score >= 0.28) return "heat-negative-soft";
    if (score >= 0.14) return "heat-negative";
    return "heat-negative-strong";
  }

  function toneClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function metricTone(metricId: string, value: number | null | undefined) {
    if (value == null) return "";
    if (metricId.includes("yield") || metricId.includes("margin") || metricId.includes("growth") || metricId === "roic" || metricId === "roe" || metricId === "cash_conversion") {
      return toneClass(value);
    }
    return "";
  }

  function bridgeTone(unit: string | null | undefined, value: number | null | undefined) {
    if (value == null || unit !== "currency") return "";
    return toneClass(value);
  }

  function sanitySeverityClass(severity: string | null | undefined) {
    const normalized = String(severity ?? "").toLowerCase();
    if (normalized === "error") return "negative";
    if (normalized === "warning") return "warning";
    if (normalized === "ok") return "positive";
    return "";
  }

  function isGammaDerivedStatementCell(sourceProvider: string | null | undefined) {
    return statementKind !== "ratios" && sourceProvider === "gamma";
  }

  function sensitivityHeatClass(value: number | null | undefined, currentPrice: number | null | undefined) {
    if (value == null || !Number.isFinite(value)) return "";
    if (currentPrice == null || !Number.isFinite(currentPrice) || currentPrice <= 0) return "sens-heat-mid";
    const upside = (value - currentPrice) / currentPrice;
    if (upside >= 0.2) return "sens-heat-pos-strong";
    if (upside >= 0.05) return "sens-heat-pos";
    if (upside >= -0.05) return "sens-heat-mid";
    if (upside >= -0.2) return "sens-heat-neg";
    return "sens-heat-neg-strong";
  }

  function reverseSensitivityHeatClass(value: number | null | undefined) {
    if (value == null || !Number.isFinite(value)) return "";
    if (value >= 0.18) return "sens-heat-neg-strong";
    if (value >= 0.12) return "sens-heat-neg";
    if (value >= 0.06) return "sens-heat-mid";
    if (value >= 0) return "sens-heat-pos";
    return "sens-heat-pos-strong";
  }

  function editableValue(value: number | null | undefined, unit: string) {
    if (value == null) return "";
    if (unit === "percent") return (value * 100).toFixed(1);
    if (unit === "ratio") return value.toFixed(3);
    // Currency / shares: thousand separators + accounting parens for negatives.
    const magnitude = Math.abs(value).toLocaleString("en-US", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    });
    return value < 0 ? `(${magnitude})` : magnitude;
  }

  function parseAssumptionInput(rawValue: string, unit: string) {
    const parsed = parseEditableNumber(rawValue);
    if (parsed == null) return null;
    return unit === "percent" ? parsed / 100 : parsed;
  }

  function currentCompanyHandoffMetadata() {
    return {
      ticker: currentCompany?.ticker ?? null,
      cik: currentCompany?.cik ?? null,
      exchange: currentCompany?.exchange ?? null,
      latest_report_period: currentCompany?.latest_report_period ?? null,
      latest_filing_date: currentCompany?.latest_filing_date ?? null,
      peer_tickers: overview?.peer_basket?.peer_tickers ?? peers?.peer_basket?.peer_tickers ?? [],
      active_dcf_scenario: activeScenario
        ? {
            scenario_id: activeScenario.scenario_id,
            label: activeScenario.label,
            implied_value_per_share: activeScenario.summary?.implied_value_per_share ?? null,
            current_price: activeScenario.summary?.current_price ?? null,
            upside_downside_pct: activeScenario.summary?.upside_downside_pct ?? null,
            assumptions: activeScenario.assumptions
          }
        : null,
      reverse_valuation_drivers: reverseDrivers.map((driver) => ({
        driver_id: driver.driver_id,
        implied_value: driver.implied_value,
        base_value: driver.base_value,
        gap_to_base: driver.gap_to_base,
        success: driver.success
      })),
      filing_count: referenceFilings.length,
      source_provider: currentCompany?.source_provider ?? null
    };
  }

  function sendCurrentCompanyToCopilot() {
    const company = currentCompany;
    if (!company) {
      return;
    }
    const handoff: CrossTabHandoffEnvelope = {
      source_tab: "fundamentals",
      source_mode: mode,
      selected_entity: {
        entity_type: "equity",
        label: `${company.name} (${company.ticker})`,
        normalized_id: company.ticker,
        provider_id: company.cik,
        native_id: company.cik,
        metadata: currentCompanyHandoffMetadata()
      },
      selected_timeframe: company.latest_report_period
        ? { label: `Latest report ${shortDate(company.latest_report_period)}`, start: null, end: company.latest_report_period }
        : null,
      provider: company.source_provider,
      source: null,
      warnings: combinedWarnings,
      normalized_ids: {
        ticker: company.ticker,
        ...(company.cik ? { cik: company.cik } : {})
      },
      timestamp: new Date().toISOString(),
      intended_target_tab: "copilot",
      intended_target_mode: "active_tab"
    };
    void onSendToCopilot(handoff);
  }

  function sendCurrentCompanyToStrategyLab() {
    const company = currentCompany;
    if (!company) return;
    const handoff: StrategyLabHandoffEnvelope = {
      source_tab: "fundamentals",
      source_mode: mode,
      selected_entity: {
        entity_type: "equity_symbol",
        label: `${company.name} (${company.ticker})`,
        normalized_id: company.ticker,
        provider_id: company.ticker,
        native_id: company.cik,
        metadata: { ...currentCompanyHandoffMetadata(), symbol: company.ticker }
      },
      selected_timeframe: company.latest_report_period
        ? { label: `Latest report ${shortDate(company.latest_report_period)}`, start: null, end: company.latest_report_period }
        : null,
      provider: company.source_provider,
      source: null,
      warnings: combinedWarnings,
      normalized_ids: { symbol: company.ticker, ticker: company.ticker, ...(company.cik ? { cik: company.cik } : {}) },
      timestamp: new Date().toISOString(),
      intended_target_tab: "strategy_lab",
      intended_target_mode: "composer",
      resolver_capability: "return_leg",
      asset_class: "equity",
      value_kind: "return",
      default_side: "long",
      default_weight: null
    };
    void onSendToStrategyLab(handoff, { open: true });
  }

  function openRelatedTab(target: "equity_research" | "risk" | "iv") {
    if (!currentCompany) return;
    void onOpenRelatedTab(target, currentCompany.ticker, currentCompany.name);
  }

  function projectionEditableValue(scenario: FundamentalsDcfScenario | null, lineKey: string, index: number) {
    const overrideValues = dcfDraft.scenarios[dcfDraft.activeScenarioId]?.overrides[lineKey] ?? [];
    const overrideValue = overrideValues[index];
    if (overrideValue != null) {
      return editableValue(overrideValue, "currency");
    }
    const row = scenario?.projection_rows.find((item) => item.line_key === lineKey);
    return editableValue(row?.values[index], row?.unit ?? "currency");
  }

  function dcfScalarInputLabel(label: string) {
    const scenarioLabel = activeScenario?.label?.trim();
    return scenarioLabel ? `${label} (${scenarioLabel} scenario)` : label;
  }

  function dcfYearInputLabel(rowLabel: string, year: number) {
    return `${rowLabel} ${year}`;
  }

  function dcfProjectionInputLabel(rowLabel: string, year: number) {
    return `${rowLabel} projection ${year}`;
  }

  function markDcfEdited() {
    dcfDirty = true;
  }

  function assumptionSeriesValue(scenarioId: string, key: string, index: number) {
    const raw = dcfDraft.scenarios[scenarioId]?.assumptions[key];
    return Array.isArray(raw) ? (raw[index] as number | null | undefined) : null;
  }

  function scalarAssumptionValue(scenarioId: string, key: string) {
    const raw = dcfDraft.scenarios[scenarioId]?.assumptions[key];
    return typeof raw === "number" ? raw : null;
  }

  async function runSearch(forceRefresh = false) {
    const trimmed = searchQuery.trim();
    lastAutoSearchQuery = trimmed;
    await onSearch({
      query: trimmed || undefined,
      limit: 12,
      forceRefresh
    });
  }

  let searchDebounceHandle: ReturnType<typeof setTimeout> | undefined;
  let lastAutoSearchQuery = "";
  const SEARCH_DEBOUNCE_MS = 250;

  function scheduleAutoSearch(query: string) {
    if (searchDebounceHandle !== undefined) {
      clearTimeout(searchDebounceHandle);
      searchDebounceHandle = undefined;
    }
    const trimmed = query.trim();
    // Skip when the value just hydrated from the focal ticker — that is not a user keystroke.
    if (trimmed && trimmed === searchHydratedTicker) return;
    if (trimmed === lastAutoSearchQuery) return;
    searchDebounceHandle = setTimeout(() => {
      searchDebounceHandle = undefined;
      void runSearch(false);
    }, SEARCH_DEBOUNCE_MS);
  }

  async function chooseCompany(ticker: string, options: FundamentalsSelectOptions = {}) {
    searchQuery = ticker.trim().toUpperCase();
    await onSelectCompany(ticker, options);
  }

  function togglePeer(ticker: string, checked: boolean) {
    const normalized = ticker.trim().toUpperCase();
    if (!normalized || normalized === overview?.company.ticker) return;
    peerDraftTickers = checked
      ? normalizePeerTickers(overview?.company.ticker ?? "", [...peerDraftTickers, normalized])
      : peerDraftTickers.filter((item) => item !== normalized);
    peerDirty = true;
  }

  function addManualPeers() {
    if (!overview) return;
    const tickers = manualPeerTickers
      .split(/[\s,;]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean);
    const nextTickers = normalizePeerTickers(overview.company.ticker, [...peerDraftTickers, ...tickers]);
    if (nextTickers.join("|") === peerDraftTickers.join("|")) {
      manualPeerTickers = "";
      return;
    }
    peerDraftTickers = nextTickers;
    manualPeerTickers = "";
    peerDirty = true;
  }

  function handleManualPeerKeydown(event: KeyboardEvent) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addManualPeers();
  }

  async function savePeerBasket() {
    if (!overview) return;
    await onSavePeerBasket(overview.company.ticker, normalizePeerTickers(overview.company.ticker, peerDraftTickers));
    peerDirty = false;
  }

  function selectScenario(nextScenarioId: string) {
    dcfDraft = setDraftActiveScenario(dcfDraft, nextScenarioId);
    dcfDirty = true;
  }

  function handleAssumptionChange(key: string, unit: string, index: number, event: Event) {
    dcfDraft = updateDraftAssumptionSeriesValue(
      dcfDraft,
      dcfDraft.activeScenarioId,
      key,
      index,
      parseAssumptionInput((event.currentTarget as HTMLInputElement).value, unit)
    );
    dcfDirty = true;
  }

  function handleScalarChange(key: string, event: Event) {
    dcfDraft = updateDraftScalarAssumption(
      dcfDraft,
      dcfDraft.activeScenarioId,
      key,
      parseAssumptionInput((event.currentTarget as HTMLInputElement).value, "percent")
    );
    dcfDirty = true;
  }

  function handleProjectionOverrideChange(lineKey: string, index: number, event: Event) {
    dcfDraft = updateDraftOverride(
      dcfDraft,
      dcfDraft.activeScenarioId,
      lineKey,
      index,
      parseEditableNumber((event.currentTarget as HTMLInputElement).value)
    );
    dcfDirty = true;
  }

  async function saveDcfDraft() {
    if (!dcfModel) return;
    await onSaveDcfModel(dcfModel.ticker, buildDcfSavePayload(dcfDraft));
    dcfDirty = false;
  }

  async function saveSnapshot() {
    if (!dcfModel) return;
    await onSaveDcfSnapshot(dcfModel.ticker, snapshotName.trim() || undefined);
    snapshotName = "";
  }

  async function loadSnapshot(snapshotId: string) {
    if (!dcfModel) return;
    await onLoadDcfSnapshot(dcfModel.ticker, snapshotId);
  }

  onMount(() => {
    if (!search?.results?.length && !overview && !financials && !dcfModel) {
      void runSearch(false);
    }
  });

  onDestroy(() => {
    if (searchDebounceHandle !== undefined) {
      clearTimeout(searchDebounceHandle);
      searchDebounceHandle = undefined;
    }
  });

  $: {
    const nextPeerFingerprint = `${overview?.company.ticker ?? ""}:${overview?.peer_basket?.peer_tickers.join(",") ?? ""}`;
    if (nextPeerFingerprint !== peerFingerprint) {
      peerFingerprint = nextPeerFingerprint;
      peerDraftTickers = [...(overview?.peer_basket?.peer_tickers ?? [])];
      peerDirty = false;
    }
  }

  $: {
    const nextDcfFingerprint = JSON.stringify({
      ticker: dcfModel?.ticker ?? "",
      retrievedAt: dcfModel?.retrieved_at ?? "",
      activeScenarioId: dcfModel?.active_scenario_id ?? "",
      scenarioIds: dcfModel?.scenarios.map((scenario) => scenario.scenario_id) ?? []
    });
    if (nextDcfFingerprint !== dcfFingerprint) {
      dcfFingerprint = nextDcfFingerprint;
      dcfDraft = createDcfDraft(dcfModel);
      dcfDirty = false;
    }
  }

  $: {
    const nextTicker = overview?.company?.ticker ?? financials?.company?.ticker ?? "";
    if (nextTicker && nextTicker !== searchHydratedTicker && searchQuery.trim().length === 0) {
      searchQuery = nextTicker;
      searchHydratedTicker = nextTicker;
      lastAutoSearchQuery = nextTicker;
    } else if (!nextTicker) {
      searchHydratedTicker = "";
    }
  }

  $: scheduleAutoSearch(searchQuery);

  $: currentCompany = overview?.company ?? financials?.company ?? null;
  $: headlineMetrics = overview?.headline_metrics ?? [];
  $: headlineStripMetrics = headlineMetrics.slice(0, 5);
  $: searchResults = search?.results ?? [];
  $: searchLoading = searchState.loading;
  $: searchHasStaleResults = searchState.loading && searchResults.length > 0;
  $: searchEmptyLabel = searchState.error ? "Search unavailable" : "No SEC matches";
  $: searchDropdownResults = searchResults.map((result) => ({
    id: result.ticker,
    primary: `${result.ticker}${result.exchange ? ` | ${result.exchange}` : ""}`,
    secondary: result.name,
    state: result.ticker === selectedTicker ? "Active" : null,
    selected: result.ticker === selectedTicker
  }));
  $: overviewWarnings = overview?.warnings ?? [];
  $: financialWarnings = financials?.warnings ?? [];
  $: dcfWarnings = dcfModel?.warnings ?? [];
  $: peerWarnings = peers?.warnings ?? [];
  $: reverseWarnings = reverseValuation?.warnings ?? [];
  $: referenceWarnings = [...(reference?.warnings ?? []), ...(reference?.provider_warnings ?? []), ...(reference?.inspection?.warnings ?? [])];
  $: combinedWarnings = [...loadWarnings, ...overviewWarnings, ...financialWarnings, ...dcfWarnings, ...peerWarnings, ...reverseWarnings, ...referenceWarnings].reduce<string[]>((rows, warning) => {
    const text = warning.trim();
    if (!text || rows.includes(text)) {
      return rows;
    }
    return [...rows, text];
  }, []);
  $: dcfDecisionGate = dcfDecisionGateFromWarnings([...dcfWarnings, ...referenceWarnings]);
  $: currentStatement = statementViewForSelection(financials, statementBasis, statementKind);
  $: currentRatioView = statementViewForSelection(financials, statementBasis, "ratios");
  $: currentSourceTraces = sourceTracesForStatement(reference, statementBasis, statementKind).slice(0, 24);
  $: activeScenario = findDcfScenario(dcfModel, dcfDraft.activeScenarioId);
  $: activeTerminalFraming = terminalValueFraming(activeScenario);
  $: activeScenarioSummary = activeScenario?.summary ?? null;
  $: activeCostOfCapitalRows = activeScenario?.cost_of_capital_rows ?? [];
  $: activeValuationBridgeRows = activeScenario?.valuation_bridge_rows ?? [];
  $: activeSanityChecks = activeScenario?.sanity_checks ?? [];
  $: dcfSummaryRows = dcfModel?.scenarios.filter((scenario) => scenario.summary != null) ?? [];
  $: dcfScenarioValueScale = (() => {
    const values: number[] = [];
    for (const scenario of dcfSummaryRows) {
      const low = scenario.summary?.implied_value_low;
      const high = scenario.summary?.implied_value_high;
      const point = scenario.summary?.implied_value_per_share;
      if (typeof low === "number" && Number.isFinite(low)) values.push(low);
      if (typeof high === "number" && Number.isFinite(high)) values.push(high);
      if (typeof point === "number" && Number.isFinite(point)) values.push(point);
    }
    const currentPrice = dcfSummaryRows[0]?.summary?.current_price;
    if (typeof currentPrice === "number" && Number.isFinite(currentPrice)) values.push(currentPrice);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return null;
    return { min, max };
  })();
  function scenarioRangePercent(value: number | null | undefined) {
    if (!dcfScenarioValueScale || value == null || !Number.isFinite(value)) return null;
    const { min, max } = dcfScenarioValueScale;
    return ((value - min) / (max - min)) * 100;
  }
  $: filingCount = overview?.filings?.length ?? financials?.filings?.length ?? 0;
  $: dilutedSharesMetric = headlineMetrics.find((metric) => metric.metric_id === "diluted_shares") ?? null;
  $: companyAbout = companySummary(overview, currentCompany);
  $: companySummarySource = overview?.company_summary ?? null;
  $: companyBadge = currentCompany ? toProvenanceBadge(currentCompany, { state: "historical" }) : null;
  $: summaryBadge = companySummarySource
    ? toProvenanceBadge(companySummarySource, {
        provider: companySummarySource.model_provider ?? companySummarySource.source_provider,
        state: companySummarySource.model_provider ? "model" : "historical",
        retrievedAt: companySummarySource.generated_at ?? companySummarySource.retrieved_at
      })
    : null;
  $: priceContextMetric = overview?.headline_metrics.find((metric) => metric.metric_id === "current_price") ?? null;
  $: priceContextBadge = priceContextMetric ? toProvenanceBadge(priceContextMetric) : null;
  $: derivedAnalyticsBadge =
    overview?.peer_heatmap || dcfModel
      ? toProvenanceBadge(overview?.peer_heatmap ?? dcfModel, { provider: "gamma", state: "derived" })
      : null;
  $: companyInfoRows = [
    { label: "Exchange", value: currentCompany?.exchange ?? "N/A" },
    { label: "SIC", value: currentCompany?.sic_description ?? currentCompany?.sic ?? "N/A" },
    { label: "Latest Reported", value: shortDate(currentCompany?.latest_report_period) },
    { label: "Latest Filed", value: shortDate(currentCompany?.latest_filing_date) },
    { label: "Diluted Shares", value: dilutedSharesMetric?.display_value ?? "N/A" },
    { label: "Filings Loaded", value: filingCount ? `${filingCount}` : "N/A" }
  ];
  $: headerNote = combinedWarnings[0] ?? "";
  $: marketContextMetrics = marketContextMetricIds
    .map((metricId) => headlineMetrics.find((metric) => metric.metric_id === metricId))
    .filter((metric): metric is NonNullable<typeof headlineMetrics[number]> => Boolean(metric));
  $: heroPricePoints = (overview?.price_history ?? [])
    .map((point) => heroPricePointFromApiPoint(point))
    .filter((point): point is HeroPricePoint => point !== null);
  $: groupedHeatmapRows = Object.entries(
    (overview?.peer_heatmap?.rows ?? []).reduce<Record<string, NonNullable<FundamentalsOverview["peer_heatmap"]>["rows"]>>((groups, row) => {
      const family = row.family ?? "other";
      groups[family] = [...(groups[family] ?? []), row];
      return groups;
    }, {})
  );
  $: peerHeatmap = peers?.peer_heatmap ?? overview?.peer_heatmap ?? null;
  $: groupedPeerHeatmapRows = Object.entries(
    (peerHeatmap?.rows ?? []).reduce<Record<string, NonNullable<FundamentalsOverview["peer_heatmap"]>["rows"]>>((groups, row) => {
      const family = row.family ?? "other";
      groups[family] = [...(groups[family] ?? []), row];
      return groups;
    }, {})
  );
  $: peerComparisons = peers?.comparisons ?? [];
  $: reverseDrivers = reverseValuation?.drivers ?? [];
  $: reverseDcfAidDrivers = reverseDrivers.slice(0, 3);
  $: reverseGapMetrics = reverseValuation?.scenario_gap_metrics ?? [];
  $: referenceFilings = reference?.filings ?? overview?.filings ?? financials?.filings ?? [];
  $: currentStatementTrends = statementTrends(currentStatement, 8);
  $: currentAmendmentSummary = amendmentSummary(currentStatement, financials?.filings ?? []);
  $: normalizedFocusedTicker = focusedTicker?.trim().toUpperCase() ?? "";
  $: focusedTickerNotice = normalizedFocusedTicker && !searchLoading && searchState.query.trim().toUpperCase() === normalizedFocusedTicker && currentCompany?.ticker !== normalizedFocusedTicker
    ? `${normalizedFocusedTicker} has no matching SEC company profile. ETFs, funds, and unsupported non-US issuers can stay in equity focus, but filing-backed Fundamentals cannot load them yet.`
    : "";
  $: referenceInspection = reference?.inspection ?? null;
  $: dcfSnapshotRows = dcfSnapshots?.snapshots ?? [];
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <span class="title">Fundamentals Research</span>
      {#if currentCompany}
        <span class="subtitle">{currentCompany.name} ({currentCompany.ticker}){currentCompany.exchange ? ` · ${currentCompany.exchange}` : ""}</span>
      {/if}
      {#if loading}<span class="loading-pill">Refreshing</span>{/if}
      {#if searchLoading}
        <span class:secondary-pill={searchHasStaleResults} class="loading-pill">{searchHasStaleResults ? "Search Refresh" : "Searching"}</span>
      {/if}
      {#if saving}<span class="loading-pill secondary-pill">Saving</span>{/if}
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Fundamentals modes">
        {#each modeOptions as option}
          <button class="mode-btn" class:selected={option.id === mode} role="tab" aria-selected={option.id === mode} type="button" on:click={() => (mode = option.id)}>
            {option.label}
          </button>
        {/each}
      </div>
      <div class="headline-strip">
        {#each headlineStripMetrics as metric}
          <div class="headline-kpi">
            <span class="headline-kpi-label">{metric.label}</span>
            <strong class="headline-kpi-value" class:absent={metric.display_value == null}>{metric.display_value ?? "N/A"}</strong>
          </div>
        {/each}
      </div>
    </div>

    <div class="search-strip">
      <div class="search-actions">
        <div class="search-control filter-wide">
          <div class="search-heading">
            <span class="search-label">Company Search</span>
            {#if searchHasStaleResults}
              <span class="search-state">Stale results</span>
            {/if}
          </div>
          <SearchDropdown
            bind:value={searchQuery}
            placeholder="AAPL, Microsoft, NVDA..."
            ariaLabel="Company search"
            emptyLabel={searchEmptyLabel}
            loading={searchLoading}
            stale={searchHasStaleResults}
            results={searchDropdownResults}
            enterBehavior="select-first"
            on:submit={() => runSearch(false)}
            on:select={(event) => chooseCompany(String(event.detail.id))}
          />
        </div>
        <button type="button" on:click={() => runSearch(false)} disabled={loading || searchLoading}>{searchLoading ? "Searching..." : "Run Search"}</button>
        <button type="button" class="secondary" on:click={() => runSearch(true)} disabled={loading || searchLoading}>Refresh Search</button>
        {#if currentCompany}
          <button type="button" class="secondary" on:click={() => chooseCompany(currentCompany.ticker, { forceRefresh: true, resetThread: false })} disabled={loading}>
            Refresh {currentCompany.ticker}
          </button>
          <button type="button" class="secondary" on:click={sendCurrentCompanyToCopilot} disabled={loading}>
            Send to Copilot
          </button>
          <button type="button" class="secondary" on:click={sendCurrentCompanyToStrategyLab} disabled={loading}>
            Strategy Lab
          </button>
        {/if}
      </div>

      {#if currentCompany}
        <div class="handoff-strip" aria-label="Open selected company in another research tab">
          <span class="focus-label">Continue in</span>
          <button type="button" class="link-button" on:click={() => openRelatedTab("equity_research")}>Equity Research</button>
          <button type="button" class="link-button" on:click={() => openRelatedTab("risk")}>Risk</button>
          <button type="button" class="link-button" on:click={() => openRelatedTab("iv")}>Options</button>
          <small>Preserves {currentCompany.ticker}, the active Fundamentals mode, scenario context, and warnings.</small>
        </div>
      {/if}

      {#if focusedTickerNotice}
        <div class="context-warning" role="status">
          <span class="focus-label">Equity focus</span>
          <p>{focusedTickerNotice}</p>
        </div>
      {/if}

      {#if headerNote}
        <div class="header-note" title={combinedWarnings.join(" | ")}>
          <span class="focus-label">Note</span>
          <p>{headerNote}</p>
          {#if combinedWarnings.length > 1}
            <small>+{combinedWarnings.length - 1}</small>
          {/if}
        </div>
      {/if}
    </div>
  </article>

  {#if mode === "reverse_valuation" && workingAnalysis?.status === "active"}
    <article class="panel working-analysis-banner" aria-label="Temporary Copilot working analysis">
      <div>
        <span>Temporary working analysis</span>
        <strong>{workingAnalysis.title}</strong>
      </div>
      <div class="working-analysis-result">
        <span>Captured result</span>
        <strong>
          {currency(finiteNumber(workingAnalysis.outputs.current_price), 2)} price ·
          {compactCurrency(finiteNumber(workingAnalysis.outputs.target_equity_value))} equity value
        </strong>
      </div>
      <p>
        Session scoped · {String(workingAnalysis.entity.ticker ?? workingAnalysis.entity.normalized_id ?? "Equity")}
        · opened from Copilot. This view has not saved or changed a Fundamentals DCF model.
      </p>
      <small>{workingAnalysis.contract_version}</small>
    </article>
  {/if}

  {#if mode === "overview"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Company</p>
              <h3>Profile</h3>
            </div>
            <small>{currentCompany?.cik ?? "No CIK"}</small>
          </div>

          <div class="profile-grid">
            <div class="profile-about">
              <p>{companyAbout}</p>
              {#if companySummarySource}
                <div class="summary-source-row">
                  <span>{companySummarySource.section ?? "Summary"}</span>
                  <strong>{companySummarySource.source_form ?? companySummarySource.source_provider}</strong>
                  <small>{shortDate(companySummarySource.filing_date)} | {companySummarySource.model_provider ?? "no model"}</small>
                </div>
              {/if}
            </div>
            <div class="meta-flat">
              {#each companyInfoRows as row}
                <div class="meta-row">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              {/each}
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Market Context</p>
              <h3>Price and Valuation</h3>
            </div>
            <small>{overview?.price_history?.length ?? 0} points</small>
          </div>

          {#if heroPricePoints.length}
            <div class="chart-panel">
              <HeroPriceChart chartKey="fundamentals:equity" points={heroPricePoints} height={240} emptyMessage="No price history available." />
            </div>
          {:else}
            <div class="empty-panel">No price history</div>
          {/if}

          <div class="kpi-grid valuation-kpi-grid">
            {#each (marketContextMetrics.length ? marketContextMetrics : headlineMetrics.slice(0, 7)) as metric}
              <div class="metric">
                <span>{metric.label}</span>
                <strong class={metricTone(metric.metric_id, metric.value)} class:absent={metric.display_value == null}>{metric.display_value ?? "N/A"}</strong>
              </div>
            {/each}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Comps</p>
              <h3>Peer Heatmap</h3>
            </div>
            <small>{overview?.peer_heatmap?.tickers.length ?? 0} companies</small>
          </div>

          <div class="table-wrap heatmap-wrap">
            <table>
              <thead>
                <tr>
                  <th>Family</th>
                  <th>Metric</th>
                  {#each overview?.peer_heatmap?.tickers ?? [] as ticker}
                    <th class:selected-col={ticker === currentCompany?.ticker}>{ticker}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if groupedHeatmapRows.length}
                  {#each groupedHeatmapRows as [family, rows]}
                    {#each rows as row, rowIndex}
                      <tr>
                        <td class="family-cell">{rowIndex === 0 ? (familyLabels[family] ?? family) : ""}</td>
                        <td>{row.label}</td>
                        {#each row.cells as cell}
                          <td class:selected-cell={cell.ticker === currentCompany?.ticker}>
                            <div class={`heat-cell ${heatmapCellClass(row.metric_id, cell.value, row.cells.map((candidate) => candidate.value))}`}>
                              <strong class:absent={cell.display_value == null}>{cell.display_value ?? "N/A"}</strong>
                            </div>
                          </td>
                        {/each}
                      </tr>
                    {/each}
                  {/each}
                {:else}
                  <tr><td colspan={(overview?.peer_heatmap?.tickers.length ?? 0) + 2}>No peer heatmap data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Research Object</p>
              <h3>Peer Basket</h3>
            </div>
            <small>{peerDraftTickers.length} peers selected</small>
          </div>

          <div class="builder-actions">
            <div class="peer-manual-control">
              <input
                type="text"
                bind:value={manualPeerTickers}
                on:keydown={handleManualPeerKeydown}
                placeholder="AMAT, LRCX, KLAC"
                aria-label="Peer tickers"
                disabled={!overview || saving}
              />
              <button type="button" class="secondary compact-button" on:click={addManualPeers} disabled={!manualPeerTickers.trim() || !overview || saving}>
                Add
              </button>
            </div>
            <button type="button" class="secondary" on:click={savePeerBasket} disabled={!peerDirty || saving || !overview}>
              {saving ? "Saving..." : "Save Basket"}
            </button>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Use</th><th>Ticker</th><th>Reason</th><th>Exchange</th></tr>
              </thead>
              <tbody>
                {#if overview?.peer_candidates?.length}
                  {#each overview.peer_candidates as candidate}
                    <tr>
                      <td>
                        <input type="checkbox" checked={peerDraftTickers.includes(candidate.ticker)} on:change={(event) => togglePeer(candidate.ticker, (event.currentTarget as HTMLInputElement).checked)} />
                      </td>
                      <td><strong>{candidate.ticker}</strong><small>{candidate.name}</small></td>
                      <td class:absent={candidate.reason == null}>{candidate.reason ?? "N/A"}</td>
                      <td class:absent={candidate.exchange == null}>{candidate.exchange ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">No peer candidates</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">DCF</p>
              <h3>Scenario Summary</h3>
            </div>
            <small>{dcfSummaryRows.length} scenarios</small>
          </div>

          <div class="focus-list">
            {#if dcfSummaryRows.length}
              {#each dcfSummaryRows as scenario}
                {@const lowPct = scenarioRangePercent(scenario.summary?.implied_value_low)}
                {@const highPct = scenarioRangePercent(scenario.summary?.implied_value_high)}
                {@const pointPct = scenarioRangePercent(scenario.summary?.implied_value_per_share)}
                {@const pricePct = scenarioRangePercent(scenario.summary?.current_price)}
                <div class="focus-row compact-focus scenario-row">
                  <span class="focus-label">{scenario.label}</span>
                  <strong class={toneClass(scenario.summary?.upside_downside_pct)} class:absent={currency(scenario.summary?.implied_value_per_share, 2) === "N/A"}>{currency(scenario.summary?.implied_value_per_share, 2)}</strong>
                  <p>
                    EV {compactCurrency(scenario.summary?.enterprise_value)}
                    | Equity {compactCurrency(scenario.summary?.equity_value)}
                    | {pct(scenario.summary?.upside_downside_pct)}
                  </p>
                  {#if lowPct != null && highPct != null && highPct > lowPct}
                    <div class="scenario-range" title={`WACC × terminal growth sensitivity range: ${currency(scenario.summary?.implied_value_low, 2)} – ${currency(scenario.summary?.implied_value_high, 2)}`}>
                      <div class="range-track">
                        <div class="range-fill {toneClass(scenario.summary?.upside_downside_pct)}" style={`left:${lowPct}%; right:${100 - highPct}%`}></div>
                        {#if pointPct != null}
                          <div class="range-point" style={`left:${pointPct}%`}></div>
                        {/if}
                        {#if pricePct != null}
                          <div class="range-price-tick" style={`left:${pricePct}%`} title={`Current price ${currency(scenario.summary?.current_price, 2)}`}></div>
                        {/if}
                      </div>
                      <div class="range-bounds">
                        <small>{currency(scenario.summary?.implied_value_low, 0)}</small>
                        <small>{currency(scenario.summary?.implied_value_high, 0)}</small>
                      </div>
                    </div>
                  {/if}
                </div>
              {/each}
            {:else}
              <div class="focus-row compact-focus">
                <span class="focus-label">DCF</span>
                <strong>No model yet</strong>
              </div>
            {/if}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Source Trail</p>
              <h3>Filings and Provenance</h3>
            </div>
            <small>{overview?.filings?.length ?? 0} filings</small>
          </div>

          <div class="focus-list">
            <div class="focus-row compact-focus">
              <span class="focus-label">Company</span>
              <ProvenanceBadge data={companyBadge} />
              <p>{currentCompany?.origin ?? "N/A"}</p>
            </div>
            <div class="focus-row compact-focus">
              <span class="focus-label">Business Summary</span>
              <ProvenanceBadge data={summaryBadge} />
              <p>{companySummarySource?.origin ?? "N/A"}</p>
            </div>
            <div class="focus-row compact-focus">
              <span class="focus-label">Price Context</span>
              <ProvenanceBadge data={priceContextBadge} />
              <p>{priceContextMetric?.origin ?? "N/A"}</p>
            </div>
            <div class="focus-row compact-focus">
              <span class="focus-label">Derived Analytics</span>
              <ProvenanceBadge data={derivedAnalyticsBadge} />
              <p>{overview?.peer_heatmap?.transformation_note ?? dcfModel?.transformation_note ?? "N/A"}</p>
            </div>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Form</th><th>Report</th><th>Filed</th><th>Amend</th></tr>
              </thead>
              <tbody>
                {#if overview?.filings?.length}
                  {#each overview.filings as filing}
                    <tr>
                      <td>{filing.form}</td>
                      <td class:absent={shortDate(filing.report_period) === "N/A"}>{shortDate(filing.report_period)}</td>
                      <td class:absent={shortDate(filing.filing_date) === "N/A"}>{shortDate(filing.filing_date)}</td>
                      <td>{filing.is_amendment ? "Yes" : "No"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">No filings</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </aside>
    </div>
  {:else if mode === "peers"}
    <div class="peers-shell">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Peer Basket</p>
            <h3>{peers?.peer_basket.basket_label ?? overview?.peer_basket?.basket_label ?? "Selected Peers"}</h3>
          </div>
          <div class="panel-actions">
            <small>{peers?.peer_basket.display_order.length ?? overview?.peer_basket?.display_order.length ?? 0} companies</small>
            <div class="peer-manual-control">
              <input
                type="text"
                bind:value={manualPeerTickers}
                on:keydown={handleManualPeerKeydown}
                placeholder="AMAT, LRCX, KLAC"
                aria-label="Peer tickers"
                disabled={!overview || saving}
              />
              <button type="button" class="secondary compact-button" on:click={addManualPeers} disabled={!manualPeerTickers.trim() || !overview || saving}>
                Add
              </button>
            </div>
            <button type="button" class="secondary" on:click={savePeerBasket} disabled={!peerDirty || saving || !overview}>
              {saving ? "Saving..." : "Save Basket"}
            </button>
          </div>
        </div>

        <div class="peer-layout">
          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Use</th><th>Ticker</th><th>Reason</th><th>Market Cap</th><th>Revenue</th></tr>
              </thead>
              <tbody>
                {#if (peers?.peer_candidates ?? overview?.peer_candidates ?? []).length}
                  {#each peers?.peer_candidates ?? overview?.peer_candidates ?? [] as candidate}
                    <tr>
                      <td>
                        <input type="checkbox" checked={peerDraftTickers.includes(candidate.ticker)} on:change={(event) => togglePeer(candidate.ticker, (event.currentTarget as HTMLInputElement).checked)} />
                      </td>
                      <td><strong>{candidate.ticker}</strong><small>{candidate.name}</small></td>
                      <td class:absent={candidate.reason == null}>{candidate.reason ?? "N/A"}</td>
                      <td class:absent={compactCurrency(candidate.market_cap) === "N/A"}>{compactCurrency(candidate.market_cap)}</td>
                      <td class:absent={compactCurrency(candidate.revenue) === "N/A"}>{compactCurrency(candidate.revenue)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="5">No peer candidates</td></tr>
                {/if}
              </tbody>
            </table>
          </div>

          <div class="focus-list peer-diagnostics">
            <div class="focus-row compact-focus">
              <span class="focus-label">Stable Order</span>
              <strong>{(peers?.peer_basket.display_order ?? overview?.peer_basket?.display_order ?? []).join(" | ") || "N/A"}</strong>
              <p>{peers?.peer_basket.transformation_note ?? overview?.peer_basket?.transformation_note ?? "N/A"}</p>
            </div>
            {#each peers?.diagnostics ?? [] as diagnostic}
              <div class="focus-row compact-focus">
                <span class="focus-label">{diagnostic.ticker}</span>
                <strong>{diagnostic.missing_metric_ids.length} missing metrics</strong>
                <p>{diagnostic.warning ?? diagnostic.missing_metric_ids.join(", ")}</p>
              </div>
            {/each}
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Comparison</p>
            <h3>Valuation, Profitability, Growth, Efficiency, Leverage</h3>
          </div>
          <small>{peerComparisons.length} rows</small>
        </div>

        <div class="table-wrap peer-comparison-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Reason</th>
                {#each peerComparisons[0]?.metrics ?? [] as metric}
                  <th>{metric.label}</th>
                {/each}
                <th>Warnings</th>
              </tr>
            </thead>
            <tbody>
              {#if peerComparisons.length}
                {#each peerComparisons as row}
                  <tr>
                    <td class:selected-cell={row.ticker === currentCompany?.ticker}><strong>{row.ticker}</strong><small>{row.name}</small></td>
                    <td>{row.candidate_reason ?? (row.selected ? "selected" : "candidate")}</td>
                    {#each row.metrics as metric}
                      <td class={metricTone(metric.metric_id, metric.value)} class:absent={metric.display_value == null}>{metric.display_value ?? "N/A"}</td>
                    {/each}
                    <td>{row.warnings.join(" | ") || "None"}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="4">No peer comparison data</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Heatmap</p>
            <h3>Metric Families</h3>
          </div>
          <small>{peerHeatmap?.rows.length ?? 0} metrics</small>
        </div>

        <div class="table-wrap heatmap-wrap">
          <table>
            <thead>
              <tr>
                <th>Family</th>
                <th>Metric</th>
                {#each peerHeatmap?.tickers ?? [] as ticker}
                  <th class:selected-col={ticker === currentCompany?.ticker}>{ticker}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if groupedPeerHeatmapRows.length}
                {#each groupedPeerHeatmapRows as [family, rows]}
                  {#each rows as row, rowIndex}
                    <tr>
                      <td class="family-cell">{rowIndex === 0 ? (familyLabels[family] ?? family) : ""}</td>
                      <td>{row.label}</td>
                      {#each row.cells as cell}
                        <td class:selected-cell={cell.ticker === currentCompany?.ticker}>
                          <div class={`heat-cell ${heatmapCellClass(row.metric_id, cell.value, row.cells.map((candidate) => candidate.value))}`}>
                            <strong class:absent={cell.display_value == null}>{cell.display_value ?? "N/A"}</strong>
                          </div>
                        </td>
                      {/each}
                    </tr>
                  {/each}
                {/each}
              {:else}
                <tr><td colspan={(peerHeatmap?.tickers.length ?? 0) + 2}>No peer heatmap data</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  {:else if mode === "financials"}
    <div class="financials-shell">
      <div class="financials-insight-grid">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Period Comparison</p>
              <h3>{statementBasis === "annual" ? "YoY" : "QoQ"} Statement Changes</h3>
            </div>
            <small>{currentStatementTrends.length} comparable rows</small>
          </div>
          <div class="table-wrap compact-wrap">
            <table>
              <thead><tr><th>Line</th><th>Latest</th><th>Prior</th><th>Change</th></tr></thead>
              <tbody>
                {#if currentStatementTrends.length}
                  {#each currentStatementTrends as trend}
                    <tr>
                      <td>{trend.label}</td>
                      <td><strong>{trend.latestDisplay}</strong><small>{trend.latestLabel}</small></td>
                      <td>{trend.priorDisplay}<small>{trend.priorLabel}</small></td>
                      <td class={toneClass(trend.change)}>{trend.changeDisplay}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">Two comparable periods are required for trend analysis.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel amendment-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Restatement Context</p>
              <h3>Amendments</h3>
            </div>
            <small>{currentAmendmentSummary.amendmentFilings} amended filings</small>
          </div>
          <div class="kpi-grid compact-kpi-grid">
            <div class="metric"><span>Statement periods</span><strong>{currentAmendmentSummary.amendedPeriods}</strong></div>
            <div class="metric"><span>Mapped cells</span><strong>{currentAmendmentSummary.amendedCells}</strong></div>
            <div class="metric"><span>Latest amendment</span><strong class:absent={shortDate(currentAmendmentSummary.latestAmendmentDate) === "N/A"}>{shortDate(currentAmendmentSummary.latestAmendmentDate)}</strong></div>
          </div>
          <p class="method-note">Amendment markers come from SEC filing forms and normalized period metadata. They flag source chronology; they do not claim every amended filing changed every mapped value.</p>
        </article>
      </div>

      <article class="panel table-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Statement Viewer</p>
            <h3>{statementOptions.find((option) => option.id === statementKind)?.label ?? "Statement"}</h3>
          </div>
          <div class="panel-actions">
            <div class="mode-bar compact-bar">
              {#each basisOptions as option}
                <button type="button" class:selected={option.id === statementBasis} on:click={() => (statementBasis = option.id)}>{option.label}</button>
              {/each}
            </div>
            <div class="mode-bar compact-bar statement-bar">
              {#each statementOptions as option}
                <button type="button" class:selected={option.id === statementKind} on:click={() => (statementKind = option.id)}>{option.label}</button>
              {/each}
            </div>
          </div>
        </div>

        <div class="table-wrap statement-wrap">
          <table>
            <thead>
              <tr>
                <th>Line Item</th>
                {#each currentStatement?.periods ?? [] as period}
                  <th>{period.label}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if currentStatement?.lines?.length}
                {#each currentStatement.lines as line}
                  <tr>
                    <td class="statement-label-cell"><strong>{line.label}</strong></td>
                    {#each line.cells as cell}
                      <td
                        class:gamma-derived-cell={isGammaDerivedStatementCell(cell.source_provider)}
                        title={isGammaDerivedStatementCell(cell.source_provider) ? (cell.transformation_note ?? "Gamma derived this value from adjacent normalized statement rows.") : undefined}
                      >
                        <strong class:absent={cell.display_value == null}>{cell.display_value ?? "N/A"}</strong>
                      </td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(currentStatement?.periods.length ?? 0) + 1}>No statement data</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
        {#if currentStatement?.lines?.some((line) => line.cells.some((cell) => isGammaDerivedStatementCell(cell.source_provider)))}
          <div class="statement-legend">
            <span class="legend-swatch gamma-derived-swatch"></span>
            <span>Gamma-derived</span>
          </div>
        {/if}
      </article>

      <div class="financials-support-grid">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Ratios</p>
              <h3>{statementBasis === "annual" ? "Annual" : "Quarterly"} Trend Grid</h3>
            </div>
            <small>{currentRatioView?.lines.length ?? 0} rows</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ratio</th>
                  {#each currentRatioView?.periods ?? [] as period}
                    <th>{period.label}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if currentRatioView?.lines?.length}
                  {#each currentRatioView.lines as line}
                    <tr>
                      <td>{line.label}</td>
                      {#each line.cells as cell}
                        <td class={metricTone(line.line_key, cell.value)} class:absent={cell.display_value == null}>{cell.display_value ?? "N/A"}</td>
                      {/each}
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan={(currentRatioView?.periods.length ?? 0) + 1}>No ratio data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Raw vs Normalized</p>
              <h3>Source Trace</h3>
            </div>
            <small>{currentSourceTraces.length} rows</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Line</th><th>Period</th><th>Value</th><th>Concept</th><th>Filing</th><th>Note</th></tr>
              </thead>
              <tbody>
                {#if currentSourceTraces.length}
                  {#each currentSourceTraces as trace}
                    <tr>
                      <td>{trace.line_label}</td>
                      <td>{trace.period_label ?? trace.period_key}</td>
                      <td class:absent={trace.display_value == null}>{trace.display_value ?? "N/A"}</td>
                      <td>{trace.concept_name ?? "Derived"}</td>
                      <td>{trace.filing_form ?? "N/A"} {trace.is_amendment ? "A" : ""}<small>{trace.accession_number ?? ""}</small></td>
                      <td class:absent={trace.transformation_note == null}>{trace.transformation_note ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="6">No source trace</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Chronology</p>
              <h3>Filing History</h3>
            </div>
            <small>{financials?.filings?.length ?? 0} filings</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Form</th><th>Report</th><th>Filed</th><th>Accession</th></tr>
              </thead>
              <tbody>
                {#if financials?.filings?.length}
                  {#each financials.filings as filing}
                    <tr>
                      <td>{filing.form}</td>
                      <td class:absent={shortDate(filing.report_period) === "N/A"}>{shortDate(filing.report_period)}</td>
                      <td class:absent={shortDate(filing.filing_date) === "N/A"}>{shortDate(filing.filing_date)}</td>
                      <td class:absent={filing.accession_number == null}>{filing.accession_number ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">No filings</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </div>
  {:else if mode === "dcf"}
    <div class="dcf-shell">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Scenario Engine</p>
            <h3>Bear / Base / Bull</h3>
          </div>
          <div class="panel-actions">
            {#if dcfDirty}<span class="dirty-pill">Pending recalculation</span>{/if}
            <button type="button" on:click={saveDcfDraft} disabled={!dcfDirty || saving || !dcfModel}>{saving ? "Saving..." : "Recalculate + Save"}</button>
          </div>
        </div>

        <div class="scenario-strip">
          {#each dcfModel?.scenarios ?? [] as scenario}
            <button type="button" class:scenario-card={true} class:selected-scenario={scenario.scenario_id === dcfDraft.activeScenarioId} on:click={() => selectScenario(scenario.scenario_id)}>
              <span>{scenario.label}</span>
              <strong>{dcfDecisionGate.blocked ? "Gated" : currency(scenario.summary?.implied_value_per_share, 2)}</strong>
              <small class={dcfDecisionGate.blocked ? "" : toneClass(scenario.summary?.upside_downside_pct)}>
                {dcfDecisionGate.blocked ? "Input coverage" : pct(scenario.summary?.upside_downside_pct)}
              </small>
            </button>
          {/each}
        </div>

        {#if dcfDecisionGate.blocked}
          <div class="decision-gate">
            <div>
              <strong>DCF valuation gated</strong>
              <p>Gamma found missing required fundamentals, so precise enterprise value, equity value, per-share value, and sensitivity outputs are suppressed.</p>
            </div>
            <ul>
              {#each dcfDecisionGate.reasons.slice(0, 4) as reason}
                <li>{reason}</li>
              {/each}
            </ul>
          </div>
        {/if}

        <div class="kpi-grid scenario-kpi-grid">
          <article class="metric">
            <span>Current Price</span>
            <strong class:absent={currency(activeScenarioSummary?.current_price, 2) === "N/A"}>{currency(activeScenarioSummary?.current_price, 2)}</strong>
          </article>
          <article class="metric">
            <span>Enterprise Value</span>
            <strong>{dcfDecisionGate.blocked ? "N/A" : compactCurrency(activeScenarioSummary?.enterprise_value)}</strong>
          </article>
          <article class="metric">
            <span>Equity Value</span>
            <strong>{dcfDecisionGate.blocked ? "N/A" : compactCurrency(activeScenarioSummary?.equity_value)}</strong>
          </article>
          <article class="metric">
            <span>Implied / Share</span>
            <strong>{dcfDecisionGate.blocked ? "N/A" : currency(activeScenarioSummary?.implied_value_per_share, 2)}</strong>
          </article>
          <article class="metric">
            <span>Upside / Downside</span>
            <strong class={dcfDecisionGate.blocked ? "" : toneClass(activeScenarioSummary?.upside_downside_pct)}>{dcfDecisionGate.blocked ? "N/A" : pct(activeScenarioSummary?.upside_downside_pct)}</strong>
          </article>
        </div>

        <div class="terminal-framing" aria-label="Terminal value framing">
          <div><span>Terminal growth</span><strong class:absent={pct(activeTerminalFraming.terminalGrowth) === "N/A"}>{pct(activeTerminalFraming.terminalGrowth)}</strong></div>
          <div><span>WACC</span><strong class:absent={pct(activeTerminalFraming.wacc) === "N/A"}>{pct(activeTerminalFraming.wacc)}</strong></div>
          <div><span>Implied terminal EV / FCF</span><strong>{activeTerminalFraming.impliedTerminalFcfMultiple == null ? "N/A" : `${activeTerminalFraming.impliedTerminalFcfMultiple.toFixed(1)}x`}</strong></div>
          <div><span>PV terminal share of EV</span><strong class:absent={pct(activeTerminalFraming.terminalValueShare) === "N/A"}>{pct(activeTerminalFraming.terminalValueShare)}</strong></div>
          <p>This is a framing of the active perpetual-growth DCF, not a second valuation method. The implied multiple makes duration dependence easier to inspect.</p>
        </div>
      </article>

      <div class="dcf-diagnostics-grid">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Cost Of Capital</p>
              <h3>WACC Bridge</h3>
            </div>
            <small>{activeScenario?.label ?? "No scenario"}</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Input</th><th>Value</th><th>Note</th></tr>
              </thead>
              <tbody>
                {#if activeCostOfCapitalRows.length}
                  {#each activeCostOfCapitalRows as row}
                    <tr>
                      <td>{row.label}</td>
                      <td class="numeric-cell" class:absent={row.display_value == null}>{row.display_value ?? "N/A"}</td>
                      <td><small>{row.note ?? row.transformation_note ?? "N/A"}</small></td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="3">No WACC bridge data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Valuation Pressure</p>
              <h3>Driver Bridge</h3>
            </div>
            <small>{activeScenario?.label ?? "No scenario"}</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Driver</th><th>Value / Share</th><th>Read</th></tr>
              </thead>
              <tbody>
                {#if activeValuationBridgeRows.length}
                  {#each activeValuationBridgeRows as row}
                    <tr>
                      <td>{row.label}</td>
                      <td class={`numeric-cell ${bridgeTone(row.unit, row.value)}`} class:absent={row.display_value == null}>{row.display_value ?? "N/A"}</td>
                      <td><small>{row.note ?? row.transformation_note ?? "N/A"}</small></td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="3">No valuation bridge data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Model Quality</p>
              <h3>Sanity Checks</h3>
            </div>
            <small>{activeScenario?.label ?? "No scenario"}</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Check</th><th>Severity</th><th>Value</th><th>Benchmark</th><th>Read</th></tr>
              </thead>
              <tbody>
                {#if activeSanityChecks.length}
                  {#each activeSanityChecks as check}
                    <tr>
                      <td>{check.label}</td>
                      <td class={sanitySeverityClass(check.severity)}>{check.severity.toUpperCase()}</td>
                      <td class="numeric-cell" class:absent={check.display_value == null}>{check.display_value ?? "N/A"}</td>
                      <td><small>{check.benchmark ?? "N/A"}</small></td>
                      <td><small>{check.message ?? check.transformation_note ?? "N/A"}</small></td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="5">No DCF sanity checks</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Implied Expectations</p>
              <h3>Reverse Valuation Aid</h3>
            </div>
            <small>{reverseDcfAidDrivers.length} drivers</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Driver</th><th>Market-Implied</th><th>Base</th><th>Gap</th></tr>
              </thead>
              <tbody>
                {#if reverseDcfAidDrivers.length}
                  {#each reverseDcfAidDrivers as driver}
                    <tr>
                      <td>{driver.label}</td>
                      <td class={dcfDecisionGate.blocked ? "" : driverTone(driver)}>{dcfDecisionGate.blocked ? "N/A" : driver.display_value ?? "N/A"}</td>
                      <td class:absent={driver.base_display_value == null}>{driver.base_display_value ?? "N/A"}</td>
                      <td class={dcfDecisionGate.blocked ? "" : driverTone(driver)}>{dcfDecisionGate.blocked ? "N/A" : driver.gap_display_value ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">Reverse valuation drivers appear when market price, shares, net debt, and normalized DCF inputs are available.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Persistence</p>
            <h3>DCF Snapshots</h3>
          </div>
          <div class="panel-actions snapshot-actions">
            <input bind:value={snapshotName} placeholder="Snapshot name" aria-label="DCF snapshot name" />
            <button type="button" class="secondary" on:click={saveSnapshot} disabled={!dcfModel || saving}>{saving ? "Saving..." : "Save Snapshot"}</button>
          </div>
        </div>

        <div class="table-wrap compact-wrap">
          <table>
            <thead>
              <tr><th>Name</th><th>Created</th><th>Active</th><th>Value / Share</th><th>Load</th></tr>
            </thead>
            <tbody>
              {#if dcfSnapshotRows.length}
                {#each dcfSnapshotRows as snapshot}
                  {@const activeSummary = snapshot.scenario_summaries.find((summary) => summary.scenario_id === snapshot.active_scenario_id) ?? snapshot.scenario_summaries[0]}
                  <tr>
                    <td><strong>{snapshotDisplayName(snapshot.name, snapshot.created_at)}</strong><small>{snapshot.snapshot_id}</small></td>
                    <td class:absent={shortDate(snapshot.created_at) === "N/A"}>{shortDate(snapshot.created_at)}</td>
                    <td>{snapshot.active_scenario_id}</td>
                    <td class:absent={currency(activeSummary?.implied_value_per_share, 2) === "N/A"}>{currency(activeSummary?.implied_value_per_share, 2)}</td>
                    <td><button type="button" class="secondary compact-button" on:click={() => loadSnapshot(snapshot.snapshot_id)} disabled={saving}>Load</button></td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="5">No saved snapshots</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Historical Block</p>
            <h3>Actuals</h3>
          </div>
          <small>{dcfModel?.historical_year_labels.length ?? 0} periods</small>
        </div>

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
            <thead>
              <tr>
                <th>Line</th>
                {#each dcfModel?.historical_year_labels ?? [] as label}
                  <th>{label}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if dcfModel?.actual_rows?.length}
                {#each dcfModel.actual_rows as row}
                  <tr>
                    <td class="sheet-label">{row.label}</td>
                    {#each row.display_values as value}
                      <td class="sheet-cell sheet-cell-fixed"><span class="sheet-fixed" class:absent={value == null}>{value ?? "N/A"}</span></td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.historical_year_labels.length ?? 0) + 1}>No historical actuals</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Drivers</p>
            <h3>Scenario Assumptions</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"}</small>
        </div>

        <div class="scalar-grid">
          <label>
            <span>WACC %</span>
            <input
              class="editable-input"
              value={editableValue(scalarAssumptionValue(dcfDraft.activeScenarioId, "wacc_pct"), "percent")}
              aria-label={dcfScalarInputLabel("WACC")}
              title={`Editable DCF assumption: ${dcfScalarInputLabel("WACC")}`}
              on:input={markDcfEdited}
              on:change={(event) => handleScalarChange("wacc_pct", event)}
            />
          </label>
          <label>
            <span>Terminal Growth %</span>
            <input
              class="editable-input"
              value={editableValue(scalarAssumptionValue(dcfDraft.activeScenarioId, "terminal_growth_pct"), "percent")}
              aria-label={dcfScalarInputLabel("Terminal growth")}
              title={`Editable DCF assumption: ${dcfScalarInputLabel("Terminal growth")}`}
              on:input={markDcfEdited}
              on:change={(event) => handleScalarChange("terminal_growth_pct", event)}
            />
          </label>
        </div>

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
            <thead>
              <tr>
                <th>Driver</th>
                {#each dcfModel?.projection_years ?? [] as year}
                  <th>{year}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if activeScenario?.assumption_rows?.length}
                {#each activeScenario.assumption_rows as row}
                  <tr>
                    <td class="sheet-label">{row.label}</td>
                    {#each dcfModel?.projection_years ?? [] as year, index}
                      <td class="sheet-cell sheet-cell-edit">
                        <input
                          class="sheet-input"
                          value={editableValue(assumptionSeriesValue(dcfDraft.activeScenarioId, row.line_key, index), row.unit)}
                          aria-label={dcfYearInputLabel(row.label, year)}
                          title={`Editable DCF assumption: ${dcfYearInputLabel(row.label, year)}`}
                          on:input={markDcfEdited}
                          on:change={(event) => handleAssumptionChange(row.line_key, row.unit, index, event)}
                        />
                      </td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.projection_years.length ?? 0) + 1}>No scenario assumptions</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Projection Sheet</p>
            <h3>Working Scenario Line</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"} drives the visible projection sheet</small>
        </div>

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
            <thead>
              <tr>
                <th>Line</th>
                {#each dcfModel?.projection_years ?? [] as year}
                  <th>{year}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if activeScenario?.projection_rows?.length}
                {#each activeScenario.projection_rows as row}
                  <tr>
                    <td class="sheet-label">{row.label}</td>
                    {#each dcfModel?.projection_years ?? [] as year, index}
                      <td class="sheet-cell" class:sheet-cell-edit={row.editable} class:sheet-cell-fixed={!row.editable} class:overridden-cell={row.overridden[index]}>
                        {#if row.editable}
                          <input
                            class="sheet-input"
                            value={projectionEditableValue(activeScenario, row.line_key, index)}
                            aria-label={dcfProjectionInputLabel(row.label, year)}
                            title={`Editable DCF projection override: ${dcfProjectionInputLabel(row.label, year)}`}
                            on:input={markDcfEdited}
                            on:change={(event) => handleProjectionOverrideChange(row.line_key, index, event)}
                          />
                        {:else}
                          <span class="sheet-fixed" class:absent={row.display_values[index] == null}>{row.display_values[index] ?? "N/A"}</span>
                        {/if}
                      </td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.projection_years.length ?? 0) + 1}>No projection rows</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Sensitivity</p>
            <h3>WACC vs Terminal Growth</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"}</small>
        </div>

        <div class="table-wrap compact-wrap sheet-wrap">
          <table class="sheet-table sensitivity-table">
            <thead>
              <tr>
                <th>Terminal \\ WACC</th>
                {#each dcfModel?.sensitivity_matrix?.wacc_values ?? [] as wacc}
                  <th>{pct(wacc)}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if dcfModel?.sensitivity_matrix?.rows?.length}
                {#each dcfModel.sensitivity_matrix.rows as row, rowIndex}
                  <tr>
                    <td class="sheet-label" class:absent={pct(dcfModel.sensitivity_matrix.terminal_growth_values[rowIndex]) === "N/A"}>{pct(dcfModel.sensitivity_matrix.terminal_growth_values[rowIndex])}</td>
                    {#each row as cell}
                      <td class={`sheet-cell sens-cell ${dcfDecisionGate.blocked ? "" : sensitivityHeatClass(cell.implied_value_per_share, activeScenarioSummary?.current_price)}`}>{dcfDecisionGate.blocked ? "N/A" : currency(cell.implied_value_per_share, 2)}</td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.sensitivity_matrix?.wacc_values.length ?? 0) + 1}>No sensitivity data</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  {:else if mode === "reverse_valuation"}
    <div class="reverse-shell">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Market-Implied Expectations</p>
            <h3>Reverse Valuation</h3>
          </div>
          <small>{reverseValuation?.source_provider ?? "No provider"}</small>
        </div>

        <div class="kpi-grid scenario-kpi-grid">
          <article class="metric">
            <span>Current Price</span>
            <strong class:absent={currency(reverseValuation?.current_price, 2) === "N/A"}>{currency(reverseValuation?.current_price, 2)}</strong>
          </article>
          <article class="metric">
            <span>Target Equity Value</span>
            <strong class:absent={compactCurrency(reverseValuation?.target_equity_value) === "N/A"}>{compactCurrency(reverseValuation?.target_equity_value)}</strong>
          </article>
          <article class="metric">
            <span>Target EV</span>
            <strong class:absent={compactCurrency(reverseValuation?.target_enterprise_value) === "N/A"}>{compactCurrency(reverseValuation?.target_enterprise_value)}</strong>
          </article>
          <article class="metric">
            <span>Base Value / Share</span>
            <strong>{dcfDecisionGate.blocked ? "N/A" : currency(reverseValuation?.base_case_summary?.implied_value_per_share, 2)}</strong>
          </article>
          <article class="metric">
            <span>Base Gap</span>
            <strong class={dcfDecisionGate.blocked ? "" : toneClass(reverseValuation?.base_case_summary?.upside_downside_pct)}>{dcfDecisionGate.blocked ? "N/A" : pct(reverseValuation?.base_case_summary?.upside_downside_pct)}</strong>
          </article>
        </div>
        {#if dcfDecisionGate.blocked}
          <div class="decision-gate">
            <div>
              <strong>Reverse valuation gated</strong>
              <p>Market-implied solves depend on the same DCF mechanics, so Gamma suppresses solved-path outputs until required financial lines are mapped or manually overridden.</p>
            </div>
            <ul>
              {#each dcfDecisionGate.reasons.slice(0, 4) as reason}
                <li>{reason}</li>
              {/each}
            </ul>
          </div>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Drivers</p>
            <h3>Implied Inputs</h3>
          </div>
          <small>{reverseDrivers.length} solved paths</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Driver</th><th>Implied</th><th>Base</th><th>Gap</th><th>Solved EV</th><th>Status</th><th>Note</th></tr>
            </thead>
            <tbody>
              {#if reverseDrivers.length}
                {#each reverseDrivers as driver}
                  <tr>
                    <td><strong>{driver.label}</strong><small>{driver.driver_id}</small></td>
                    <td class={dcfDecisionGate.blocked ? "" : driverTone(driver)}>{dcfDecisionGate.blocked ? "N/A" : driver.display_value ?? "N/A"}</td>
                    <td class:absent={driver.base_display_value == null}>{driver.base_display_value ?? "N/A"}</td>
                    <td class={dcfDecisionGate.blocked ? "" : driverTone(driver)}>{dcfDecisionGate.blocked ? "N/A" : driver.gap_display_value ?? "N/A"}</td>
                    <td>{dcfDecisionGate.blocked ? "N/A" : compactCurrency(driver.solved_enterprise_value)}</td>
                    <td>{dcfDecisionGate.blocked ? "Gated" : driver.success ? "Solved" : "Bounded"}</td>
                    <td>{driver.warnings.join(" | ") || driver.transformation_note || "N/A"}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="7">No reverse valuation drivers</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <div class="financials-support-grid">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Base Gap</p>
              <h3>Scenario Gap Metrics</h3>
            </div>
            <small>{reverseGapMetrics.length} metrics</small>
          </div>
          <div class="kpi-grid valuation-kpi-grid">
            {#each reverseGapMetrics as metric}
              <article class="metric">
                <span>{metric.label}</span>
                <strong class={dcfDecisionGate.blocked ? "" : metricTone(metric.metric_id, metric.value)}>{dcfDecisionGate.blocked ? "N/A" : metric.display_value ?? "N/A"}</strong>
              </article>
            {:else}
              <div class="empty-panel">Scenario gap metrics appear with the reverse valuation payload.</div>
            {/each}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Sensitivity</p>
              <h3>WACC / Terminal Growth</h3>
            </div>
            <small>{reverseValuation?.sensitivity_matrix?.rows.length ?? 0} rows</small>
          </div>
          <div class="table-wrap compact-wrap sheet-wrap">
            <table class="sheet-table sensitivity-table">
              <thead>
                <tr>
                  <th>Terminal \\ WACC</th>
                  {#each reverseValuation?.sensitivity_matrix?.wacc_values ?? [] as wacc}
                    <th>{pct(wacc)}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if reverseValuation?.sensitivity_matrix?.rows?.length}
                  {#each reverseValuation.sensitivity_matrix.rows as row, rowIndex}
                    <tr>
                      <td class="sheet-label" class:absent={pct(reverseValuation.sensitivity_matrix.terminal_growth_values[rowIndex]) === "N/A"}>{pct(reverseValuation.sensitivity_matrix.terminal_growth_values[rowIndex])}</td>
                      {#each row as cell}
                        <td class={`sheet-cell sens-cell ${dcfDecisionGate.blocked ? "" : reverseSensitivityHeatClass(cell.implied_revenue_growth_pct)}`}>
                          <strong>{dcfDecisionGate.blocked ? "N/A" : pct(cell.implied_revenue_growth_pct)}</strong>
                          <small>{dcfDecisionGate.blocked ? "Input coverage gated" : `EBIT ${pct(cell.implied_ebit_margin_pct)} | FCF ${pct(cell.implied_fcf_cagr_pct)}`}</small>
                        </td>
                      {/each}
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan={(reverseValuation?.sensitivity_matrix?.wacc_values.length ?? 0) + 1}>No reverse sensitivity data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </div>
  {:else}
    <div class="reference-shell">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Reference</p>
            <h3>Filing Chronology</h3>
          </div>
          <small>{referenceFilings.length} filings</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>Form</th><th>Report Period</th><th>Filed</th><th>Accession</th><th>Amendment</th><th>Provider</th></tr>
            </thead>
            <tbody>
              {#if referenceFilings.length}
                {#each referenceFilings as filing}
                  <tr>
                    <td>{filing.form}</td>
                    <td class:absent={shortDate(filing.report_period) === "N/A"}>{shortDate(filing.report_period)}</td>
                    <td class:absent={shortDate(filing.filing_date) === "N/A"}>{shortDate(filing.filing_date)}</td>
                    <td class:absent={filing.accession_number == null}>{filing.accession_number ?? "N/A"}</td>
                    <td>{filing.is_amendment ? "Yes" : "No"}</td>
                    <td>{filing.source_provider}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="6">No filings</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <div class="financials-support-grid">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Coverage</p>
              <h3>Taxonomy Mapping</h3>
            </div>
            <small>{referenceInspection?.coverage.length ?? 0} rows</small>
          </div>
          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Statement</th><th>Line</th><th>Concepts</th><th>Observed</th><th>Derived</th><th>Warning</th></tr>
              </thead>
              <tbody>
                {#if referenceInspection?.coverage.length}
                  {#each referenceInspection.coverage as row}
                    <tr>
                      <td>{row.basis} {row.statement}</td>
                      <td>{row.line_label}</td>
                      <td>{row.concept_names.join(", ") || "N/A"}</td>
                      <td>{row.observed_periods} / {row.observed_periods + row.missing_periods}</td>
                      <td>{row.derived_observations}</td>
                      <td>{row.warning ?? "None"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="6">No coverage data</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Provider</p>
              <h3>Identity and Config</h3>
            </div>
            <small>{reference?.provider_warnings.length ?? 0} warnings</small>
          </div>
          <div class="focus-list">
            <div class="focus-row compact-focus">
              <span class="focus-label">Source</span>
              <strong>{reference?.source_provider ?? currentCompany?.source_provider ?? "N/A"}</strong>
              <p>{reference?.origin ?? currentCompany?.origin ?? "N/A"}</p>
            </div>
            {#each reference?.provider_warnings ?? [] as warning}
              <div class="focus-row compact-focus">
                <span class="focus-label">Warning</span>
                <strong>Configuration</strong>
                <p>{warning}</p>
              </div>
            {/each}
            <div class="focus-row compact-focus">
              <span class="focus-label">Inspection</span>
              <strong class:absent={referenceInspection?.source_provider == null}>{referenceInspection?.source_provider ?? "N/A"}</strong>
              <p>{referenceInspection?.transformation_note ?? "N/A"}</p>
            </div>
          </div>
        </article>
      </div>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Trace</p>
            <h3>Normalized Rows to Source Concepts</h3>
          </div>
          <small>{referenceInspection?.traces.length ?? 0} rows</small>
        </div>
        <div class="table-wrap statement-wrap">
          <table>
            <thead>
              <tr><th>Statement</th><th>Line</th><th>Period</th><th>Value</th><th>Concept</th><th>Filing</th><th>Derived Note</th></tr>
            </thead>
            <tbody>
              {#if referenceInspection?.traces.length}
                {#each referenceInspection.traces as trace}
                  <tr>
                    <td>{trace.basis} {trace.statement}</td>
                    <td>{trace.line_label}</td>
                    <td>{trace.period_label ?? trace.period_key}</td>
                    <td class:absent={trace.display_value == null}>{trace.display_value ?? "N/A"}</td>
                    <td>{trace.concept_name ?? "Derived"}</td>
                    <td>{trace.filing_form ?? "N/A"} | {shortDate(trace.filing_date)}<small>{trace.accession_number ?? ""}</small></td>
                    <td class:absent={trace.transformation_note == null}>{trace.transformation_note ?? "N/A"}</td>
                  </tr>
                {/each}
              {:else}
                <tr><td colspan="7">No trace data</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  {/if}
</section>

<style>
  .view,
  .notes-list,
  .focus-list,
  .meta-flat {
    display: grid;
    gap: var(--space-4);
  }

  .view {
    gap: var(--space-4);
  }

  .dcf-shell,
  .peers-shell,
  .reverse-shell,
  .reference-shell {
    display: grid;
    gap: var(--space-4);
  }

  .financials-shell {
    display: grid;
    gap: var(--space-4);
  }

  .financials-support-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }

  .financials-insight-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.55fr) minmax(18rem, 0.75fr);
    gap: var(--space-4);
    align-items: start;
  }

  .amendment-panel {
    align-content: start;
  }

  .dcf-diagnostics-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }

  .peer-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(18rem, 0.8fr);
    gap: var(--space-4);
    align-items: start;
  }

  .working-analysis-banner {
    grid-template-columns: minmax(12rem, 0.7fr) minmax(14rem, 0.75fr) minmax(0, 1.5fr) auto;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-5);
    border-left: 2px solid var(--accent);
    background: transparent;
  }

  .working-analysis-banner > div {
    display: grid;
    gap: var(--space-1);
  }

  .working-analysis-banner span,
  .working-analysis-banner small {
    color: var(--accent);
    font-size: var(--text-2xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .working-analysis-banner strong {
    color: var(--text-0);
    font-size: var(--text-sm);
  }

  .working-analysis-result strong {
    font-variant-numeric: tabular-nums;
  }

  .working-analysis-banner p {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: 1.45;
  }

  /* Panels whose primary content is a single table fill edge-to-edge:
     the panel border is the table's container, no inner frame. */
  .panel.table-panel,
  .panel:has(> .panel-header + .table-wrap:last-child) {
    padding: 0;
    gap: 0;
  }

  .panel.table-panel > .panel-header,
  .panel:has(> .panel-header + .table-wrap:last-child) > .panel-header {
    padding: var(--space-2) var(--space-5);
    border-bottom: 1px solid var(--divider);
    min-height: 26px;
  }

  .panel.table-panel > .table-wrap,
  .panel:has(> .panel-header + .table-wrap:last-child) > .table-wrap {
    border: 0;
    background: transparent;
  }

  .header-panel {
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
  }

  .header-top,
  .mode-kpi-row,
  .headline-title-row,
  .builder-actions,
  .panel-actions,
  .search-actions,
  .search-strip,
  .headline-strip,
  .scenario-strip {
    display: flex;
    gap: var(--space-4);
  }

  .header-top {
    align-items: baseline;
  }

  .handoff-strip,
  .context-warning {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 28px;
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .handoff-strip small {
    margin-left: auto;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .link-button {
    min-height: 24px;
    padding: var(--space-1) var(--space-3);
    border-color: var(--panel-border);
    background: transparent;
    color: var(--accent);
  }

  .context-warning {
    align-items: flex-start;
    color: var(--warning);
  }

  .context-warning p {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .mode-kpi-row {
    justify-content: space-between;
    align-items: flex-start;
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

  /* Sub-panel headers: collapse eyebrow + h3 stack into a single 26px row.
     The mode bar already names the section context, so the eyebrow is redundant. */
  .panel:not(.header-panel) > .panel-header {
    align-items: center;
    min-height: 26px;
  }

  .panel:not(.header-panel) > .panel-header > div:first-child {
    display: contents;
  }

  .panel:not(.header-panel) > .panel-header .eyebrow {
    display: none;
  }

  .panel:not(.header-panel) > .panel-header h3 {
    font-size: var(--text-base);
    font-weight: 700;
    letter-spacing: 0;
  }

  .headline-title-row,
  .search-actions,
  .headline-strip,
  .search-strip,
  .scenario-strip {
    flex-wrap: wrap;
  }

  .headline-block {
    display: grid;
    gap: var(--space-1);
  }

  .subtitle,
  .muted,
  .focus-row p,
  .meta-row span {
    color: var(--text-2);
  }

  .dirty-pill {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-1);
    padding: var(--space-1) var(--space-4);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  .dirty-pill {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 35%, var(--panel-strong));
  }

  .compact-bar {
    grid-template-columns: repeat(2, auto);
  }

  .statement-bar {
    grid-template-columns: repeat(4, auto);
  }

  .snapshot-actions {
    align-items: end;
    flex-wrap: wrap;
  }

  .peer-manual-control {
    display: inline-flex;
    align-items: stretch;
    min-width: min(18rem, 100%);
  }

  .peer-manual-control input {
    min-width: 10rem;
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
  }

  .peer-manual-control button {
    min-height: 1.65rem;
    border-left: 0;
  }

  .snapshot-actions input {
    min-width: 12rem;
  }

  .compact-button {
    min-height: 1.65rem;
    padding: var(--space-2) var(--space-4);
  }

  button,
  .scenario-card {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-0);
    padding: var(--space-2) var(--space-4);
    font: inherit;
    font-size: var(--text-sm);
    border-radius: var(--radius-sm);
    cursor: pointer;
  }

  .scenario-card.selected-scenario {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  button:hover,
  .scenario-card:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
  }

  button.secondary {
    color: var(--text-1);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
    border-color: var(--panel-border);
  }

  .scenario-card {
    display: grid;
    gap: var(--space-1);
    text-align: left;
  }

  .scenario-card {
    padding: var(--space-3) var(--space-4);
  }

  .scenario-card strong {
    font-size: var(--text-base);
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

  .secondary-pill {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 28%, transparent);
    background: color-mix(in srgb, var(--warning) 6%, transparent);
  }

  label,
  .search-control {
    display: grid;
    gap: var(--space-2);
  }

  .filter-wide {
    flex: 1 1 14rem;
  }

  .search-control {
    min-width: 10rem;
    max-width: 18rem;
  }

  .search-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .search-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .search-state {
    color: var(--warning);
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .header-note {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: var(--space-4);
    align-items: center;
    min-width: 0;
    max-width: 32rem;
    padding-left: var(--space-5);
    border-left: 1px solid var(--divider);
  }

  .header-note p,
  .header-note small {
    color: var(--text-2);
    margin: 0;
  }

  .header-note p {
    font-size: var(--text-xs);
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    min-width: 0;
  }

  .header-note small {
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  input {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-3) var(--space-4);
    font: inherit;
    font-size: var(--text-sm);
    min-height: 1.75rem;
    border-radius: var(--radius-sm);
  }

  .search-strip {
    justify-content: space-between;
    align-items: end;
  }

  .search-actions {
    align-items: end;
    min-width: 0;
    flex-wrap: nowrap;
  }

  .search-strip button {
    min-height: 1.75rem;
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .grid-input {
    min-width: 6rem;
    text-align: right;
    padding-inline: var(--space-3);
  }

  .sheet-table {
    table-layout: fixed;
  }

  .table-wrap.sheet-wrap {
    overflow-x: hidden;
  }

  .sheet-table thead th {
    text-align: right;
    padding: var(--space-3) var(--space-4);
  }

  .sheet-table thead th:first-child {
    text-align: left;
  }

  .sheet-table tbody td {
    padding: 0;
    border-top: 1px solid var(--divider);
    border-left: 1px solid var(--divider);
    vertical-align: middle;
    height: 1.85rem;
  }

  .sheet-table tbody td:first-child {
    border-left: 0;
  }

  .sheet-table .sheet-label {
    padding: 0 var(--space-4);
    color: var(--text-1);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sheet-table .sheet-cell {
    text-align: right;
  }

  .sheet-table .sheet-fixed {
    display: block;
    padding: 0 var(--space-4);
    color: var(--accent);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .sheet-table .sheet-input {
    display: block;
    width: 100%;
    min-width: 0;
    min-height: 0;
    border: 0;
    background: transparent;
    color: var(--text-0);
    text-align: right;
    padding: 0 var(--space-4);
    height: 1.83rem;
    font: inherit;
    font-size: var(--text-base);
    font-variant-numeric: tabular-nums;
  }

  .sheet-table .sheet-input:focus {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
    background: var(--bg-1);
  }

  .sheet-table .sheet-cell-edit {
    position: relative;
    background: color-mix(in srgb, var(--accent) 7%, var(--bg-1));
  }

  .sheet-table .sheet-cell-edit::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 2px;
    background: color-mix(in srgb, var(--accent) 65%, transparent);
    pointer-events: none;
  }

  .sheet-table .sheet-cell-edit:hover {
    background: color-mix(in srgb, var(--accent) 11%, var(--bg-1));
  }

  .sheet-table .sheet-cell-edit .sheet-input {
    color: var(--text-0);
  }

  .sheet-table .sheet-cell-edit .sheet-input:focus {
    background: color-mix(in srgb, var(--accent) 10%, var(--bg-1));
  }

  .sheet-table .sheet-cell-fixed {
    background: var(--bg-0);
  }

  .sensitivity-table .sens-cell {
    padding: 0 var(--space-4);
    text-align: right;
    color: var(--text-0);
    font-variant-numeric: tabular-nums;
  }

  .sensitivity-table .sens-cell strong,
  .sensitivity-table .sens-cell small {
    display: block;
  }

  .sensitivity-table .sens-cell small {
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.25;
  }

  .sens-heat-pos-strong {
    background: color-mix(in srgb, var(--positive) 32%, transparent);
  }

  .sens-heat-pos {
    background: color-mix(in srgb, var(--positive) 18%, transparent);
  }

  .sens-heat-mid {
    background: color-mix(in srgb, var(--warning) 16%, transparent);
  }

  .sens-heat-neg {
    background: color-mix(in srgb, var(--negative) 18%, transparent);
  }

  .sens-heat-neg-strong {
    background: color-mix(in srgb, var(--negative) 32%, transparent);
  }

  .scalar-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 12rem));
    gap: var(--space-4);
  }

  .scalar-grid label {
    border-left: 2px solid color-mix(in srgb, var(--accent) 65%, transparent);
    padding-left: var(--space-4);
  }

  .scalar-grid .editable-input {
    background: color-mix(in srgb, var(--accent) 7%, var(--bg-1));
  }

  .scalar-grid .editable-input:hover,
  .scalar-grid .editable-input:focus {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--panel-strong));
    background: color-mix(in srgb, var(--accent) 11%, var(--bg-1));
  }

  .focus-label,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .headline-kpi-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    line-height: 1.1;
  }

  h3,
  p,
  small,
  strong {
    margin: 0;
  }

  h3 {
    font-size: var(--text-base);
    font-weight: 700;
  }

  .headline-strip {
    border-left: 1px solid var(--divider);
  }

  .headline-kpi {
    display: grid;
    gap: 0.05rem;
    padding: var(--space-1) var(--space-5);
    border-right: 1px solid var(--divider);
    min-width: 5.5rem;
    text-align: left;
  }

  .headline-kpi-value {
    display: block;
    color: var(--text-0);
    font-size: var(--text-sm);
    font-weight: 600;
    line-height: 1.15;
  }

  .profile-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
    gap: var(--space-5);
  }

  .profile-about,
  .meta-row,
  .focus-row,
  .note-row {
    display: grid;
    gap: var(--space-1);
  }

  .meta-row,
  .focus-row,
  .note-row {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-4);
  }

  .meta-row:first-child,
  .focus-row:first-child,
  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .scenario-range {
    margin-top: var(--space-3);
    display: grid;
    gap: var(--space-1);
  }

  .scenario-range .range-track {
    position: relative;
    height: 0.4rem;
    background: color-mix(in srgb, var(--text-2) 18%, transparent);
  }

  .scenario-range .range-fill {
    position: absolute;
    top: 0;
    bottom: 0;
    background: color-mix(in srgb, var(--text-1) 55%, transparent);
  }

  .scenario-range .range-fill.positive {
    background: color-mix(in srgb, var(--positive) 55%, transparent);
  }

  .scenario-range .range-fill.negative {
    background: color-mix(in srgb, var(--negative) 55%, transparent);
  }

  .scenario-range .range-point {
    position: absolute;
    top: 50%;
    width: 0.5rem;
    height: 0.5rem;
    margin-left: -0.25rem;
    background: var(--text-0);
    transform: translateY(-50%);
  }

  .scenario-range .range-price-tick {
    position: absolute;
    top: -0.15rem;
    bottom: -0.15rem;
    width: 2px;
    margin-left: -1px;
    background: var(--warning);
    border-radius: 1px;
  }

  .scenario-range .range-bounds {
    display: flex;
    justify-content: space-between;
    font-size: var(--text-xs);
    color: var(--text-2);
  }

  .profile-about p {
    color: var(--text-1);
    line-height: 1.45;
  }

  .summary-source-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: var(--space-4);
    align-items: baseline;
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .summary-source-row span {
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .summary-source-row strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .summary-source-row small {
    color: var(--text-2);
    white-space: nowrap;
  }

  .chart-panel {
    padding: 0;
    background: transparent;
  }

  .empty-panel {
    border: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-sm);
    min-height: 5rem;
    display: grid;
    place-items: center;
    text-align: center;
    padding: var(--space-4);
  }

  .decision-gate {
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
    gap: var(--space-5);
    margin-top: var(--space-5);
    padding: var(--space-5) var(--space-5);
    border: 1px solid color-mix(in srgb, var(--warning) 34%, var(--panel-border));
    background: color-mix(in srgb, var(--warning) 7%, var(--surface-0));
  }

  .decision-gate strong {
    color: var(--warning);
    font-size: var(--text-sm);
  }

  .decision-gate p,
  .decision-gate li {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .decision-gate ul {
    margin: 0;
    padding-left: var(--space-6);
  }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(8.8rem, 1fr));
    gap: 0;
    padding-block: var(--space-1);
  }

  .valuation-kpi-grid {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }

  .scenario-kpi-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .compact-kpi-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .compact-kpi-grid .metric {
    padding-inline: var(--space-4);
  }

  .compact-kpi-grid .metric strong {
    font-size: var(--text-base);
  }

  .method-note {
    margin: 0;
    padding-top: var(--space-3);
    border-top: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .terminal-framing {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    border-block: 1px solid var(--divider);
  }

  .terminal-framing > div {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-5);
    border-left: 1px solid var(--divider);
  }

  .terminal-framing > div:first-child {
    border-left: 0;
  }

  .terminal-framing span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .terminal-framing p {
    grid-column: 1 / -1;
    margin: 0;
    padding: var(--space-3) var(--space-5);
    border-top: 1px solid var(--divider);
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .metric {
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    padding: var(--space-2) var(--space-6);
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .metric strong {
    display: block;
    margin: var(--space-2) 0;
    font-size: var(--text-lg);
  }

  .table-wrap {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: auto;
    max-height: 30rem;
  }

  .numeric-cell {
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .compact-wrap {
    max-height: 18rem;
  }

  .peer-comparison-wrap {
    max-height: 28rem;
  }

  .heatmap-wrap {
    max-height: 34rem;
  }

  .statement-wrap {
    max-height: 42rem;
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
    font-weight: 500;
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
  }

  tbody td {
    padding: var(--space-3) var(--space-4);
    border-top: 1px solid var(--divider);
    vertical-align: middle;
    font-size: var(--text-sm);
  }

  tbody td small {
    display: block;
    margin-top: var(--space-1);
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .period-head {
    display: grid;
    gap: var(--space-1);
  }

  .statement-label-cell {
    min-width: 14rem;
  }

  .gamma-derived-cell {
    color: var(--data-cool);
    background: color-mix(in srgb, var(--data-cool) 10%, transparent);
    outline: 1px solid color-mix(in srgb, var(--data-cool) 24%, transparent);
    outline-offset: -1px;
  }

  .statement-legend {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.35;
    padding: var(--space-2) var(--space-5);
    border-top: 1px solid var(--divider);
  }

  .legend-swatch {
    width: 0.7rem;
    height: 0.7rem;
    border: 1px solid var(--divider);
    flex: 0 0 auto;
  }

  .gamma-derived-swatch {
    background: color-mix(in srgb, var(--data-cool) 22%, transparent);
    border-color: color-mix(in srgb, var(--data-cool) 38%, var(--divider));
  }

  .statement-label-cell strong,
  .statement-wrap tbody td strong {
    display: block;
    color: var(--text-0);
    font-weight: 600;
  }

  .family-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .selected-col,
  .selected-cell {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .selected-cell .heat-cell {
    outline: 1px solid color-mix(in srgb, var(--accent) 32%, transparent);
    outline-offset: -1px;
  }

  .heat-cell {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-3);
    margin: -0.18rem -0.12rem;
    min-height: 2rem;
    align-content: center;
  }

  .heat-cell strong {
    font-size: var(--text-base);
  }

  .heat-positive-strong {
    background: color-mix(in srgb, var(--positive) 28%, transparent);
  }

  .heat-positive {
    background: color-mix(in srgb, var(--positive) 22%, transparent);
  }

  .heat-positive-soft {
    background: color-mix(in srgb, var(--positive) 12%, transparent);
  }

  .heat-warning {
    background: color-mix(in srgb, var(--warning) 18%, transparent);
  }

  .heat-negative-soft {
    background: color-mix(in srgb, color-mix(in srgb, var(--negative) 58%, var(--warning)) 16%, transparent);
  }

  .heat-negative-strong {
    background: color-mix(in srgb, var(--negative) 28%, transparent);
  }

  .heat-negative {
    background: color-mix(in srgb, var(--negative) 20%, transparent);
  }

  .heat-neutral {
    background: transparent;
    color: var(--text-2);
  }

  .overridden-cell {
    background: color-mix(in srgb, var(--warning) 7%, transparent);
  }

  .positive {
    color: var(--positive);
  }

  .warning {
    color: var(--warning);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1180px) {
    .workspace-grid,
    .peer-layout,
    .profile-grid,
    .financials-support-grid,
    .financials-insight-grid,
    .dcf-diagnostics-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .working-analysis-banner {
      grid-template-columns: 1fr;
    }

    .header-top,
    .mode-kpi-row,
    .panel-header,
    .search-actions,
    .search-strip {
      flex-direction: column;
      align-items: stretch;
    }

    .search-control,
    .filter-wide {
      flex: none;
      width: 100%;
      max-width: none;
    }

    .headline-kpi {
      border-left: 0;
      border-top: 1px solid var(--divider);
      text-align: left;
      padding-left: 0;
    }

    .headline-kpi:first-child {
      border-top: 0;
    }

    .mode-bar,
    .compact-bar,
    .statement-bar {
      width: 100%;
      grid-template-columns: 1fr;
    }

    .scalar-grid {
      grid-template-columns: 1fr;
    }

    .valuation-kpi-grid,
    .scenario-kpi-grid {
      grid-template-columns: 1fr;
    }

    .terminal-framing {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .handoff-strip {
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .handoff-strip small {
      width: 100%;
      margin-left: 0;
    }

    .header-note {
      grid-template-columns: 1fr;
      gap: var(--space-2);
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: var(--space-4);
      max-width: none;
    }
  }
</style>
