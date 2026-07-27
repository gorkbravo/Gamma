import type {
  DiagnosticsResponse,
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  Position,
  ProviderUsageResponse,
  SystemStatus
} from "../api/types";

export type PortfolioChartMode = "value" | "growth" | "drawdown";
export type PortfolioTimeframe = "1m" | "2m" | "1y" | "3y" | "max";

export interface PortfolioPreferences {
  benchmarkSymbol: string;
  timeframe: PortfolioTimeframe;
  chartMode: PortfolioChartMode;
}

export type SnapshotUiStatus =
  | "idle"
  | "loading"
  | "ready"
  | "partial"
  | "empty"
  | "unavailable"
  | "failed";

export type HistoryUiStatus =
  | "idle"
  | "loading"
  | "ready"
  | "empty"
  | "recovered"
  | "degraded"
  | "failed";

export type PerformanceUiStatus =
  | "idle"
  | "loading"
  | "ready"
  | "partial"
  | "unavailable"
  | "failed";

export interface PortfolioRequestState<TStatus extends string> {
  status: TStatus;
  initialLoading: boolean;
  refreshing: boolean;
  error: string | null;
  warnings: string[];
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
}

export type SnapshotRequestState = PortfolioRequestState<SnapshotUiStatus>;
export type HistoryRequestState = PortfolioRequestState<HistoryUiStatus>;
export type PerformanceRequestState = PortfolioRequestState<PerformanceUiStatus>;

export interface PortfolioHistoryHealth {
  status?: string | null;
  point_count?: number | null;
  base_currency?: string | null;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
  malformed_row_count?: number | null;
  duplicate_row_count?: number | null;
  recovery_archive_name?: string | null;
  last_write_at?: string | null;
  warnings?: string[];
}

export type PortfolioSnapshotWithMetadata = PortfolioSnapshot & {
  state?: string | null;
  source_provider?: string | null;
  retrieved_at?: string | null;
  origin?: string | null;
  freshness_label?: string | null;
  transformation_note?: string | null;
  quote_mode?: string | null;
  market_data_mode?: string | null;
  complete?: boolean | null;
  connection_ready?: boolean | null;
  account_summary_available?: boolean | null;
  account_subscription_usable?: boolean | null;
  requested_position_count?: number | null;
  quoted_position_count?: number | null;
  missing_quote_count?: number | null;
  missing_quote_symbols?: string[];
  cached_quote_count?: number | null;
  cached_quote_symbols?: string[];
  delayed_quote_count?: number | null;
  delayed_quote_symbols?: string[];
  available_value_count?: number | null;
  history_store_health?: PortfolioHistoryHealth | null;
};

export type PortfolioHistoryWithMetadata = PortfolioHistoryResponse & {
  state?: string | null;
  source_provider?: string | null;
  retrieved_at?: string | null;
  origin?: string | null;
  freshness_label?: string | null;
  transformation_note?: string | null;
  warnings?: string[];
  health?: PortfolioHistoryHealth | null;
};

export type PortfolioPerformanceWithMetadata = PortfolioPerformanceResponse & {
  state?: string | null;
  source_provider?: string | null;
  retrieved_at?: string | null;
  origin?: string | null;
  freshness_label?: string | null;
  transformation_note?: string | null;
  complete?: boolean | null;
  requested_position_count?: number | null;
  covered_position_count?: number | null;
  history_coverage_ratio?: number | null;
  missing_history_symbols?: string[];
  missing_fx_symbols?: string[];
  history_source?: string | null;
  history_source_provider?: string | null;
  history_freshness_label?: string | null;
  history_transformation_note?: string | null;
  history_point_count?: number | null;
  benchmark_freshness_label?: string | null;
  benchmark_transformation_note?: string | null;
  benchmark_source_provider?: string | null;
};

export type PortfolioNoticeTone = "info" | "warning" | "error";
export type PortfolioNoticeAction =
  | "refresh_snapshot"
  | "retry_history"
  | "retry_performance"
  | "diagnostics"
  | "force_subscribe";

export interface PortfolioNotice {
  id: string;
  tone: PortfolioNoticeTone;
  title: string;
  detail: string;
  action?: PortfolioNoticeAction;
  actionLabel?: string;
}

export interface PortfolioReadinessRow {
  label: string;
  value: string;
  detail: string;
  tone: "neutral" | "positive" | "warning" | "negative";
}

export interface PortfolioReadiness {
  modeLabel: string;
  rows: PortfolioReadinessRow[];
  lastSuccessfulRefresh: string | null;
  lastFailure: string | null;
}

export interface PositionEmptyState {
  kind: "no_snapshot" | "account_empty" | "filter_empty" | "cash_hidden" | "unavailable";
  title: string;
  detail: string;
  canClearFilter: boolean;
}

export interface PositionQuoteStatus {
  label: "Live" | "Delayed" | "Cached" | "Mock" | "Missing" | "Available" | "Unavailable";
  tone: "neutral" | "positive" | "warning" | "negative";
  detail: string;
}

export type PortfolioSortKey =
  | "symbol"
  | "sec_type"
  | "quantity"
  | "market_price"
  | "market_value"
  | "base_market_value"
  | "unrealized_pnl"
  | "weight";

export interface PortfolioTableOptions {
  search: string;
  sortKey: PortfolioSortKey;
  descending: boolean;
  includeCash: boolean;
}

export interface PortfolioDiagnostics {
  grossExposure: number;
  netExposure: number;
  cashWeight: number | null;
  largestPosition: Position | null;
  bestPnl: Position | null;
  worstPnl: Position | null;
  bySecurityType: Array<{ key: string; count: number }>;
  byCurrency: Array<{ key: string; count: number }>;
}

export function classifySnapshotStatus(snapshot: PortfolioSnapshot | null): SnapshotUiStatus {
  if (!snapshot) {
    return "unavailable";
  }
  const metadata = snapshot as PortfolioSnapshotWithMetadata;
  const explicit = normalizeState(metadata.state);
  if (isSnapshotStatus(explicit)) {
    return explicit;
  }
  if (metadata.connection_ready === false) {
    return "unavailable";
  }
  if (
    metadata.complete === false ||
    (metadata.missing_quote_count ?? 0) > 0 ||
    (metadata.requested_position_count != null &&
      metadata.quoted_position_count != null &&
      metadata.quoted_position_count < metadata.requested_position_count)
  ) {
    return "partial";
  }
  const accountAvailable =
    metadata.account_summary_available ?? Object.keys(snapshot.account_summary ?? {}).length > 0;
  if (snapshot.positions.length === 0 && accountAvailable) {
    return "empty";
  }
  return "ready";
}

export function classifyHistoryStatus(history: PortfolioHistoryResponse | null): HistoryUiStatus {
  if (!history) {
    return "failed";
  }
  const metadata = history as PortfolioHistoryWithMetadata;
  const explicit = normalizeState(metadata.state);
  if (isHistoryStatus(explicit)) {
    return explicit;
  }
  const health = normalizeState(metadata.health?.status);
  if (health === "recovered") {
    return "recovered";
  }
  if (health === "degraded" || health === "corrupt" || health === "unhealthy") {
    return "degraded";
  }
  return history.points.length ? "ready" : "empty";
}

export function classifyPerformanceStatus(
  performance: PortfolioPerformanceResponse | null
): PerformanceUiStatus {
  if (!performance) {
    return "unavailable";
  }
  const metadata = performance as PortfolioPerformanceWithMetadata;
  const explicit = normalizeState(metadata.state);
  if (isPerformanceStatus(explicit)) {
    return explicit;
  }
  if (
    metadata.complete === false ||
    performance.benchmark_source === "cash_0" ||
    (metadata.history_coverage_ratio != null && metadata.history_coverage_ratio < 1) ||
    (metadata.missing_history_symbols ?? performance.missing_symbols).length > 0 ||
    (metadata.missing_fx_symbols?.length ?? 0) > 0
  ) {
    return "partial";
  }
  return performance.performance_points.length > 0 ? "ready" : "unavailable";
}

export function initialSnapshotRequestState(): SnapshotRequestState {
  return {
    status: "idle",
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: [],
    lastSuccessAt: null,
    lastFailureAt: null
  };
}

export function initialHistoryRequestState(): HistoryRequestState {
  return {
    status: "idle",
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: [],
    lastSuccessAt: null,
    lastFailureAt: null
  };
}

export function initialPerformanceRequestState(): PerformanceRequestState {
  return {
    status: "idle",
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: [],
    lastSuccessAt: null,
    lastFailureAt: null
  };
}

export function normalizePortfolioBenchmark(value: string) {
  return value.trim().toUpperCase() || "SPY";
}

export function lookbackDaysForPortfolioTimeframe(timeframe: PortfolioTimeframe) {
  switch (timeframe) {
    case "1m":
      return 21;
    case "2m":
      return 42;
    case "3y":
      return 756;
    case "max":
      return 2520;
    case "1y":
    default:
      return 252;
  }
}

export function derivePositionEmptyState(input: {
  snapshot: PortfolioSnapshot | null;
  snapshotStatus: SnapshotUiStatus;
  filteredCount: number;
  search: string;
  includeCash: boolean;
}): PositionEmptyState | null {
  if (input.filteredCount > 0) {
    return null;
  }
  if (!input.snapshot) {
    if (input.snapshotStatus === "unavailable" || input.snapshotStatus === "failed") {
      return {
        kind: "unavailable",
        title: "Portfolio snapshot unavailable",
        detail: "Refresh the snapshot or inspect connection and provider diagnostics.",
        canClearFilter: false
      };
    }
    return {
      kind: "no_snapshot",
      title: "No portfolio snapshot loaded",
      detail: "Refresh the snapshot to load account positions.",
      canClearFilter: false
    };
  }
  if (
    (input.snapshotStatus === "unavailable" || input.snapshotStatus === "failed") &&
    input.snapshot.positions.length === 0
  ) {
    return {
      kind: "unavailable",
      title: "Portfolio snapshot unavailable",
      detail: "No usable account positions were returned. Check connection and account readiness.",
      canClearFilter: false
    };
  }
  if (input.snapshot.positions.length === 0) {
    return {
      kind: "account_empty",
      title: "Account has no positions",
      detail: "The account snapshot loaded successfully and contains no position lines.",
      canClearFilter: false
    };
  }
  if (input.search.trim()) {
    return {
      kind: "filter_empty",
      title: "No positions match this filter",
      detail: `The loaded account contains ${input.snapshot.positions.length} position ${
        input.snapshot.positions.length === 1 ? "line" : "lines"
      }.`,
      canClearFilter: true
    };
  }
  if (!input.includeCash) {
    return {
      kind: "cash_hidden",
      title: "Only cash positions are hidden",
      detail: "Enable Cash to show the loaded account lines.",
      canClearFilter: true
    };
  }
  return {
    kind: "unavailable",
    title: "Position values unavailable",
    detail: "The snapshot did not return usable position lines. Inspect diagnostics for provider detail.",
    canClearFilter: false
  };
}

export function positionQuoteStatus(
  snapshot: PortfolioSnapshot | null,
  position: Position
): PositionQuoteStatus {
  const metadata = snapshot as PortfolioSnapshotWithMetadata | null;
  const symbol = normalizeSymbolLabel(position.display_symbol ?? position.symbol);
  const missing = normalizedSymbolSet(metadata?.missing_quote_symbols);
  const cached = normalizedSymbolSet(metadata?.cached_quote_symbols);
  const delayed = normalizedSymbolSet(metadata?.delayed_quote_symbols);
  if (cached.has(symbol)) {
    return {
      label: "Cached",
      tone: "warning",
      detail: "The latest usable cached quote is shown."
    };
  }
  if (missing.has(symbol) || (position.market_price == null && position.sec_type !== "CASH")) {
    return {
      label: "Missing",
      tone: "negative",
      detail: "No usable market quote was returned for this position."
    };
  }
  if (delayed.has(symbol) || normalizeState(metadata?.market_data_mode).includes("delay")) {
    return {
      label: "Delayed",
      tone: "warning",
      detail: "The provider identified this market data as delayed."
    };
  }
  const provider = normalizeState(metadata?.source_provider ?? position.provider);
  const freshness = normalizeState(metadata?.freshness_label);
  if (provider.includes("mock") || provider.includes("sample") || freshness === "mocked") {
    return {
      label: "Mock",
      tone: "neutral",
      detail: "This value belongs to the explicit demo portfolio."
    };
  }
  if (normalizeState(metadata?.market_data_mode) === "live" || freshness === "live") {
    return {
      label: "Live",
      tone: "positive",
      detail: "The current snapshot identifies this quote as live."
    };
  }
  if (position.market_price != null || position.base_market_value != null) {
    return {
      label: "Available",
      tone: "neutral",
      detail: "A usable value is present, but the quote freshness was not classified."
    };
  }
  return {
    label: "Unavailable",
    tone: "negative",
    detail: "No usable value is available."
  };
}

export function derivePortfolioNotices(input: {
  snapshot: PortfolioSnapshot | null;
  history: PortfolioHistoryResponse | null;
  performance: PortfolioPerformanceResponse | null;
  snapshotState: SnapshotRequestState;
  historyState: HistoryRequestState;
  performanceState: PerformanceRequestState;
  systemStatus?: SystemStatus | null;
  diagnostics?: DiagnosticsResponse | null;
}): PortfolioNotice[] {
  const notices: PortfolioNotice[] = [];
  const snapshot = input.snapshot as PortfolioSnapshotWithMetadata | null;
  const history = input.history as PortfolioHistoryWithMetadata | null;
  const performance = input.performance as PortfolioPerformanceWithMetadata | null;
  const effectiveHistoryStatus = strongerHistoryStatus(
    input.historyState.status,
    snapshot?.history_store_health?.status,
    history?.health?.status
  );
  const mockMode = input.systemStatus?.mock_mode ?? input.diagnostics?.mock_mode ?? false;
  const connected =
    mockMode ||
    input.systemStatus?.connection.connected === true ||
    input.diagnostics?.connection.connected === true;

  if (mockMode) {
    notices.push({
      id: "mock-mode",
      tone: "info",
      title: "Demo portfolio",
      detail: "This is explicit mock data for product evaluation, not a broker account snapshot."
    });
  } else if (!connected) {
    notices.push({
      id: "provider-disconnected",
      tone: "error",
      title: "TWS is disconnected",
      detail: "Start Trader Workstation, verify the API session, then refresh the snapshot.",
      action: "diagnostics",
      actionLabel: "Connection setup"
    });
  }

  if (input.snapshotState.status === "loading") {
    notices.push({
      id: "snapshot-loading",
      tone: "info",
      title: "Loading portfolio snapshot",
      detail: "Account and quote coverage are being requested."
    });
  } else if (input.snapshotState.status === "failed" || input.snapshotState.status === "unavailable") {
    notices.push({
      id: "snapshot-failed",
      tone: "error",
      title: input.snapshot ? "Snapshot refresh failed" : "Portfolio snapshot unavailable",
      detail: input.snapshot
        ? "The last successful snapshot remains visible. Retry when the provider is ready."
        : "No usable snapshot is available. Check connection and account readiness, then retry.",
      action: "refresh_snapshot",
      actionLabel: "Retry snapshot"
    });
  } else if (input.snapshotState.status === "partial") {
    const requested = snapshot?.requested_position_count ?? input.snapshot?.positions.length ?? 0;
    const quoted = snapshot?.quoted_position_count ?? Math.max(0, requested - (snapshot?.missing_quote_count ?? 0));
    notices.push({
      id: "snapshot-partial",
      tone: "warning",
      title: "Partial quote snapshot",
      detail: `${quoted} of ${requested} requested position quotes are usable. Missing values remain explicit in the table.`,
      action: "refresh_snapshot",
      actionLabel: "Retry snapshot"
    });
  } else if (input.snapshotState.status === "empty") {
    notices.push({
      id: "snapshot-empty",
      tone: "info",
      title: "Account snapshot is empty",
      detail: "The account subscription loaded, but the account currently has no positions."
    });
  }

  if (
    connected &&
    !mockMode &&
    (snapshot?.account_subscription_usable === false ||
      (snapshot?.account_summary_available === false && snapshot?.connection_ready !== false))
  ) {
    notices.push({
      id: "account-subscription",
      tone: "warning",
      title: "No usable account subscription",
      detail: "TWS is connected, but Gamma has not received a usable account summary. Request a read-only account resubscription.",
      action: "force_subscribe",
      actionLabel: "Force subscription"
    });
  }

  if (effectiveHistoryStatus === "failed") {
    notices.push({
      id: "history-failed",
      tone: "error",
      title: "Local history unavailable",
      detail: "Snapshot data remains usable. Retry the local history read or inspect persistence diagnostics.",
      action: "retry_history",
      actionLabel: "Retry history"
    });
  } else if (effectiveHistoryStatus === "recovered") {
    notices.push({
      id: "history-recovered",
      tone: "warning",
      title: "Local history recovered",
      detail: (history?.health?.recovery_archive_name ?? snapshot?.history_store_health?.recovery_archive_name)
        ? `Valid rows were recovered; the unreadable source was archived as ${history?.health?.recovery_archive_name ?? snapshot?.history_store_health?.recovery_archive_name}.`
        : "Valid rows were recovered and the unreadable source was quarantined for diagnosis.",
      action: "diagnostics",
      actionLabel: "Review diagnostics"
    });
  } else if (effectiveHistoryStatus === "degraded") {
    notices.push({
      id: "history-degraded",
      tone: "warning",
      title: "Local history is degraded",
      detail: "Some stored rows were malformed or duplicated. Gamma preserved valid rows and reports the exclusions in diagnostics.",
      action: "diagnostics",
      actionLabel: "Review diagnostics"
    });
  } else if (
    effectiveHistoryStatus === "empty" ||
    (input.history != null && input.history.points.length < 2)
  ) {
    notices.push({
      id: "history-thin",
      tone: "info",
      title: "Local history is still thin",
      detail: "Gamma needs at least two locally observed daily snapshots for a stored-value return. This is not a broker backfill.",
      action: "refresh_snapshot",
      actionLabel: "Refresh snapshot"
    });
  }

  if (input.performanceState.status === "failed") {
    notices.push({
      id: "performance-failed",
      tone: "error",
      title: "Performance calculation failed",
      detail: "The snapshot and local history remain visible. Retry only the performance calculation.",
      action: "retry_performance",
      actionLabel: "Retry performance"
    });
  } else if (input.performanceState.status === "unavailable" && input.snapshot != null) {
    notices.push({
      id: "performance-unavailable",
      tone: "warning",
      title: "Performance unavailable",
      detail: performance?.message
        ? `${performance.message}${input.performance ? " The last successful series remains visible when available." : ""}`
        : "There is not enough usable constituent or local history to calculate performance. The last successful series remains visible when available.",
      action: "retry_performance",
      actionLabel: "Retry performance"
    });
  } else if (input.performanceState.status === "partial") {
    const missingHistory = performance?.missing_history_symbols ?? performance?.missing_symbols ?? [];
    const missingFx = performance?.missing_fx_symbols ?? [];
    const parts = [
      missingHistory.length ? `history: ${missingHistory.join(", ")}` : "",
      missingFx.length ? `FX: ${missingFx.join(", ")}` : ""
    ].filter(Boolean);
    notices.push({
      id: "performance-partial",
      tone: "warning",
      title: performance?.benchmark_source === "cash_0" ? "Cash 0% benchmark fallback" : "Partial performance coverage",
      detail:
        performance?.benchmark_source === "cash_0"
          ? `${performance.benchmark_symbol} was unavailable; portfolio performance is shown against an explicit Cash 0% fallback.`
          : parts.length
            ? `Coverage gaps — ${parts.join(" · ")}.`
            : "Performance uses only the usable history and FX coverage reported by the API.",
      action: "retry_performance",
      actionLabel: "Retry performance"
    });
  }

  return dedupeNotices(notices);
}

export function derivePortfolioReadiness(input: {
  snapshot: PortfolioSnapshot | null;
  history: PortfolioHistoryResponse | null;
  performance: PortfolioPerformanceResponse | null;
  snapshotState: SnapshotRequestState;
  historyState: HistoryRequestState;
  performanceState: PerformanceRequestState;
  systemStatus?: SystemStatus | null;
  diagnostics?: DiagnosticsResponse | null;
  providerUsage?: ProviderUsageResponse | null;
}): PortfolioReadiness {
  const snapshot = input.snapshot as PortfolioSnapshotWithMetadata | null;
  const history = input.history as PortfolioHistoryWithMetadata | null;
  const performance = input.performance as PortfolioPerformanceWithMetadata | null;
  const mockMode = input.systemStatus?.mock_mode ?? input.diagnostics?.mock_mode ?? false;
  const connection = input.systemStatus?.connection ?? input.diagnostics?.connection ?? null;
  const connected = mockMode || connection?.connected === true;
  const accountAvailable =
    snapshot?.account_summary_available ??
    (snapshot != null && Object.keys(snapshot.account_summary ?? {}).length > 0);
  const accountUsable = snapshot?.account_subscription_usable ?? accountAvailable;
  const requested = snapshot?.requested_position_count ?? snapshot?.positions.length ?? 0;
  const quoted = snapshot?.quoted_position_count ?? Math.max(0, requested - (snapshot?.missing_quote_count ?? 0));
  const pointCount = history?.health?.point_count ?? history?.points.length ?? input.diagnostics?.local_history_entries ?? 0;
  const historyHealth = strongerHistoryStatus(
    input.historyState.status,
    snapshot?.history_store_health?.status,
    history?.health?.status
  );
  const ibkrHealth = input.providerUsage?.health.find((row) =>
    ["ibkr", "ibkr_portfolio"].includes(row.provider_id)
  );
  const snapshotFreshness = snapshot?.freshness_label ?? (mockMode ? "mocked" : "unknown");
  const benchmarkLabel =
    performance?.benchmark_source === "cash_0"
      ? `${performance.benchmark_symbol} · Cash 0% fallback`
      : performance
        ? `${performance.benchmark_symbol} · ${performance.benchmark_source}`
        : "Unavailable";
  const lastSuccess = input.snapshotState.lastSuccessAt;
  const lastFailure = input.snapshotState.lastFailureAt;

  return {
    modeLabel: mockMode ? "MOCK / DEMO" : "LIVE / IBKR",
    rows: [
      {
        label: "TWS Connection",
        value: mockMode ? "Not required" : connected ? "Connected" : "Disconnected",
        detail: mockMode
          ? "Explicit demo provider"
          : ibkrHealth?.reason || connection?.status_text || "Connection state unavailable",
        tone: connected ? "positive" : "negative"
      },
      {
        label: "Account Subscription",
        value: mockMode ? "Demo account" : accountUsable ? "Usable" : connected ? "Needs subscription" : "Unavailable",
        detail: accountAvailable
          ? "Account summary received; identifier hidden"
          : "No usable account summary received",
        tone: accountUsable ? "positive" : connected ? "warning" : "negative"
      },
      {
        label: "Market Data",
        value: titleCase(snapshot?.market_data_mode ?? input.systemStatus?.market_data_mode ?? input.diagnostics?.market_data_mode ?? "unknown"),
        detail: `${titleCase(snapshotFreshness)} · quote mode ${snapshot?.quote_mode ?? "unknown"}`,
        tone: snapshotFreshness === "live" ? "positive" : snapshotFreshness === "unavailable" ? "negative" : "warning"
      },
      {
        label: "Quote Coverage",
        value: requested ? `${quoted} / ${requested}` : input.snapshotState.status === "empty" ? "Empty account" : "Unavailable",
        detail:
          (snapshot?.missing_quote_count ?? 0) > 0
            ? `${snapshot?.missing_quote_count} missing · ${snapshot?.cached_quote_count ?? 0} cached · ${snapshot?.delayed_quote_count ?? 0} delayed`
            : requested
              ? "All requested position quotes usable"
              : "No position quote request",
        tone: input.snapshotState.status === "partial" ? "warning" : requested || input.snapshotState.status === "empty" ? "positive" : "negative"
      },
      {
        label: "Local History",
        value: `${pointCount} ${pointCount === 1 ? "point" : "points"}`,
        detail: historyHealth
          ? `${titleCase(historyHealth)} · locally accumulated snapshots`
          : "Locally accumulated snapshots; not a broker backfill",
        tone:
          historyHealth === "ready"
            ? "positive"
            : historyHealth === "recovered" || historyHealth === "degraded"
              ? "warning"
              : "neutral"
      },
      {
        label: "Benchmark",
        value: benchmarkLabel,
        detail:
          performance?.benchmark_freshness_label || performance?.benchmark_transformation_note || "No benchmark calculation loaded",
        tone: performance?.benchmark_source === "cash_0" ? "warning" : performance ? "positive" : "neutral"
      }
    ],
    lastSuccessfulRefresh: lastSuccess,
    lastFailure
  };
}

export function filterAndSortPositions(
  positions: Position[],
  options: PortfolioTableOptions
): Position[] {
  const query = options.search.trim().toLowerCase();
  const filtered = positions.filter((position) => {
    if (!options.includeCash && isCashPosition(position)) {
      return false;
    }
    if (!query) {
      return true;
    }
    return [
      position.symbol,
      position.sec_type,
      position.currency
    ]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(query));
  });

  const direction = options.descending ? -1 : 1;
  return [...filtered].sort((left, right) => {
    const leftValue = sortableValue(left, options.sortKey);
    const rightValue = sortableValue(right, options.sortKey);
    if (typeof leftValue === "string" || typeof rightValue === "string") {
      return String(leftValue).localeCompare(String(rightValue)) * direction;
    }
    return (leftValue - rightValue) * direction;
  });
}

export function derivePortfolioDiagnostics(snapshot: PortfolioSnapshot | null): PortfolioDiagnostics {
  const positions = snapshot?.positions ?? [];
  const grossExposure = positions.reduce((sum, position) => sum + Math.abs(position.base_market_value ?? 0), 0);
  const netExposure = positions.reduce((sum, position) => sum + (position.base_market_value ?? 0), 0);
  const total = snapshot?.net_liquidation ?? snapshot?.total_market_value ?? null;
  const cash = positions
    .filter(isCashPosition)
    .reduce((sum, position) => sum + (position.base_market_value ?? 0), 0);

  return {
    grossExposure,
    netExposure,
    cashWeight: total && total > 0 ? cash / total : null,
    largestPosition: maxBy(positions, (position) => Math.abs(position.base_market_value ?? 0)),
    bestPnl: maxBy(positions, (position) => position.unrealized_pnl ?? Number.NEGATIVE_INFINITY),
    worstPnl: minBy(positions, (position) => position.unrealized_pnl ?? Number.POSITIVE_INFINITY),
    bySecurityType: bucketCounts(positions.map((position) => position.sec_type || "Unknown")),
    byCurrency: bucketCounts(positions.map((position) => position.currency || "Unknown"))
  };
}

export function performanceLatestValue(
  performance: PortfolioPerformanceResponse | null
): number | null {
  return performance?.performance_points.at(-1)?.value ?? null;
}

function sortableValue(position: Position, sortKey: PortfolioSortKey): number | string {
  switch (sortKey) {
    case "symbol":
      return position.symbol;
    case "sec_type":
      return position.sec_type;
    case "quantity":
      return position.quantity ?? 0;
    case "market_price":
      return position.market_price ?? Number.NEGATIVE_INFINITY;
    case "market_value":
      return position.market_value ?? Number.NEGATIVE_INFINITY;
    case "unrealized_pnl":
      return position.unrealized_pnl ?? Number.NEGATIVE_INFINITY;
    case "weight":
      return position.weight ?? Number.NEGATIVE_INFINITY;
    case "base_market_value":
    default:
      return position.base_market_value ?? Number.NEGATIVE_INFINITY;
  }
}

function bucketCounts(values: string[]): Array<{ key: string; count: number }> {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((left, right) => right.count - left.count || left.key.localeCompare(right.key));
}

function maxBy<T>(items: T[], score: (item: T) => number): T | null {
  let winner: T | null = null;
  let winnerScore = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    const currentScore = score(item);
    if (currentScore > winnerScore) {
      winner = item;
      winnerScore = currentScore;
    }
  }
  return winner;
}

function minBy<T>(items: T[], score: (item: T) => number): T | null {
  let winner: T | null = null;
  let winnerScore = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const currentScore = score(item);
    if (currentScore < winnerScore) {
      winner = item;
      winnerScore = currentScore;
    }
  }
  return winner;
}

function isCashPosition(position: Position) {
  return position.sec_type === "CASH" || position.symbol.startsWith("CASH");
}

function normalizeState(value: unknown) {
  return String(value ?? "").trim().toLowerCase();
}

function isSnapshotStatus(value: string): value is SnapshotUiStatus {
  return ["loading", "ready", "partial", "empty", "unavailable", "failed"].includes(value);
}

function isHistoryStatus(value: string): value is HistoryUiStatus {
  return ["loading", "ready", "empty", "recovered", "degraded", "failed"].includes(value);
}

function isPerformanceStatus(value: string): value is PerformanceUiStatus {
  return ["loading", "ready", "partial", "unavailable", "failed"].includes(value);
}

function normalizeSymbolLabel(value: string) {
  return value.trim().toUpperCase();
}

function normalizedSymbolSet(values: string[] | null | undefined) {
  return new Set((values ?? []).map(normalizeSymbolLabel));
}

function dedupeNotices(notices: PortfolioNotice[]) {
  const seen = new Set<string>();
  return notices.filter((notice) => {
    const key = `${notice.title.trim().toLowerCase()}:${notice.detail.trim().toLowerCase()}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function titleCase(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return "Unknown";
  }
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function strongerHistoryStatus(
  requestStatus: HistoryUiStatus,
  ...healthStatuses: Array<string | null | undefined>
): HistoryUiStatus {
  const statuses = [requestStatus, ...healthStatuses.map(normalizeState)];
  if (statuses.includes("failed") || statuses.includes("unhealthy") || statuses.includes("corrupt")) {
    return "failed";
  }
  if (statuses.includes("recovered")) {
    return "recovered";
  }
  if (statuses.includes("degraded")) {
    return "degraded";
  }
  if (requestStatus === "loading" || requestStatus === "idle") {
    return requestStatus;
  }
  return requestStatus;
}
