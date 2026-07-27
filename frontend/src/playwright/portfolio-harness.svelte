<script lang="ts">
  import PortfolioView from "../views/PortfolioView.svelte";
  import type {
    DiagnosticsResponse,
    PortfolioHistoryResponse,
    PortfolioPerformanceResponse,
    PortfolioSnapshot,
    ProviderUsageResponse,
    SystemStatus
  } from "../lib/api/types";
  import {
    portfolioHistoryRequestState,
    portfolioPerformanceRequestState,
    portfolioSnapshotRequestState
  } from "../lib/stores/portfolio";

  const scenario = new URLSearchParams(window.location.search).get("scenario") ?? "partial";
  const timestamp = "2026-07-27T12:00:00Z";
  const snapshot = scenario === "empty" ? emptySnapshot() : partialSnapshot();
  const history = scenario === "empty" ? emptyHistory() : degradedHistory();
  const performance = scenario === "empty" ? unavailablePerformance() : partialPerformance();

  let diagnosticsOpen = false;

  portfolioSnapshotRequestState.set({
    status: scenario === "empty" ? "empty" : "partial",
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: snapshot.warnings,
    lastSuccessAt: timestamp,
    lastFailureAt: null
  });
  portfolioHistoryRequestState.set({
    status: scenario === "empty" ? "empty" : "degraded",
    initialLoading: false,
    refreshing: false,
    error: null,
    warnings: history.warnings ?? [],
    lastSuccessAt: timestamp,
    lastFailureAt: null
  });
  portfolioPerformanceRequestState.set({
    status: scenario === "empty" ? "unavailable" : "partial",
    initialLoading: false,
    refreshing: false,
    error: scenario === "empty" ? "Two locally observed snapshots are required." : null,
    warnings: performance.warnings,
    lastSuccessAt: scenario === "empty" ? null : timestamp,
    lastFailureAt: scenario === "empty" ? timestamp : null
  });

  function record(type: string, payload: unknown = null) {
    window.__gammaPortfolioEvents.push({ type, payload });
  }

  const systemStatus: SystemStatus = {
    healthy: true,
    app_name: "Gamma",
    backend: "playwright",
    mock_mode: true,
    base_currency: "USD",
    market_data_mode: "delayed",
    connection: {
      connected: true,
      status_text: "Mock provider ready",
      action_text: "Disconnect",
      action_enabled: false,
      active_account: null
    },
    cached_symbols: []
  };

  const diagnostics: DiagnosticsResponse = {
    generated_at: timestamp,
    mock_mode: true,
    base_currency: "USD",
    market_data_mode: "delayed",
    connection: systemStatus.connection,
    history_cache: { hits: 3, misses: 1, hit_rate: 0.75 },
    local_history_entries: history.points.length,
    local_history_path: "data/portfolio_history_mock.csv",
    recent_errors: ["Raw provider diagnostic detail remains in the console."],
    cached_symbols: [],
    research_scope_type: "portfolio",
    research_primary_symbol: null,
    research_synthetic_count: 0,
    iv_running: false,
    iv_status_text: "idle",
    iv_active_symbol: null
  };

  const providerUsage: ProviderUsageResponse = {
    generated_at: timestamp,
    providers: [],
    health: [
      {
        provider_id: "ibkr_portfolio",
        display_name: "IBKR Portfolio",
        health_status: "available",
        health_label: "Mock provider ready",
        expected_when: "Live mode",
        reason: "Explicit deterministic demo provider is active.",
        action_label: null,
        call_count: 1,
        success_count: 1,
        unavailable_count: 0,
        error_count: 0,
        last_called_at: timestamp
      }
    ],
    recent_calls: [],
    total_calls: 1,
    source_provider: "gamma",
    origin: "playwright.portfolio.provider_usage",
    transformation_note: "Deterministic browser fixture."
  };

  function partialSnapshot(): PortfolioSnapshot {
    return {
      timestamp,
      base_currency: "USD",
      account_summary: {
        "NetLiquidation:USD": "125000",
        "BuyingPower:USD": "50000",
        "TotalCashValue:USD": "25000"
      },
      positions: [
        {
          symbol: "LMT",
          sec_type: "STK",
          currency: "USD",
          quantity: 100,
          avg_cost: 470,
          market_price: 500,
          market_value: 50000,
          unrealized_pnl: 3000,
          weight: 0.4,
          base_market_value: 50000,
          fx_rate: 1,
          instrument_id: "ibkr:LMT",
          display_symbol: "LMT",
          exchange: "SMART",
          primary_exchange: "NYSE",
          provider: "mock",
          provider_id: "LMT"
        },
        {
          symbol: "SAP",
          sec_type: "STK",
          currency: "EUR",
          quantity: 200,
          avg_cost: 180,
          market_price: null,
          market_value: null,
          unrealized_pnl: null,
          weight: null,
          base_market_value: null,
          fx_rate: null,
          instrument_id: "ibkr:SAP",
          display_symbol: "SAP",
          exchange: "SMART",
          primary_exchange: "IBIS",
          provider: "mock",
          provider_id: "SAP"
        },
        {
          symbol: "CASH_USD",
          sec_type: "CASH",
          currency: "USD",
          quantity: 25000,
          avg_cost: 1,
          market_price: 1,
          market_value: 25000,
          unrealized_pnl: 0,
          weight: 0.2,
          base_market_value: 25000,
          fx_rate: 1,
          instrument_id: "ibkr:CASH_USD",
          display_symbol: "CASH_USD",
          exchange: null,
          primary_exchange: null,
          provider: "mock",
          provider_id: "CASH_USD"
        }
      ],
      total_market_value: 100000,
      total_cash: 25000,
      net_liquidation: 125000,
      day_pnl: 725,
      day_pnl_pct: 0.00583,
      day_pnl_source: "historical_eod",
      warnings: ["Snapshot quote missing for SAP"],
      state: "partial",
      source_provider: "mock",
      retrieved_at: timestamp,
      origin: "playwright.portfolio.snapshot",
      freshness_label: "mocked",
      transformation_note: "Explicit demo portfolio with Gamma base-currency normalization.",
      quote_mode: "Snapshot",
      market_data_mode: "delayed",
      complete: false,
      connection_ready: true,
      account_summary_available: true,
      account_subscription_usable: true,
      requested_position_count: 2,
      quoted_position_count: 1,
      missing_quote_count: 1,
      missing_quote_symbols: ["SAP"],
      cached_quote_count: 0,
      cached_quote_symbols: [],
      delayed_quote_count: 1,
      delayed_quote_symbols: ["LMT"],
      available_value_count: 1,
      history_store_health: {
        status: "degraded",
        point_count: 2,
        base_currency: "USD",
        first_timestamp: "2026-07-26T12:00:00Z",
        last_timestamp: timestamp,
        malformed_row_count: 1,
        duplicate_row_count: 0,
        recovery_archive_name: "portfolio_history_mock.partial-recovery.csv",
        last_write_at: timestamp,
        warnings: ["Ignored 1 malformed local portfolio history row; valid rows remain available."]
      }
    };
  }

  function emptySnapshot(): PortfolioSnapshot {
    return {
      ...partialSnapshot(),
      positions: [],
      total_market_value: 0,
      total_cash: 125000,
      net_liquidation: 125000,
      warnings: ["No positions in account"],
      state: "empty",
      complete: true,
      requested_position_count: 0,
      quoted_position_count: 0,
      missing_quote_count: 0,
      missing_quote_symbols: [],
      delayed_quote_count: 0,
      delayed_quote_symbols: [],
      available_value_count: 0,
      history_store_health: {
        status: "empty",
        point_count: 0,
        base_currency: null,
        first_timestamp: null,
        last_timestamp: null,
        malformed_row_count: 0,
        duplicate_row_count: 0,
        recovery_archive_name: null,
        last_write_at: null,
        warnings: []
      }
    };
  }

  function degradedHistory(): PortfolioHistoryResponse {
    return {
      source: "local_history_store",
      state: "degraded",
      source_provider: "local_history_store",
      retrieved_at: timestamp,
      origin: "playwright.portfolio.local_history",
      freshness_label: "historical",
      transformation_note: "Locally accumulated daily snapshots; not a broker backfill.",
      points: [
        {
          timestamp: "2026-07-26T12:00:00Z",
          portfolio_value: 123500,
          net_liquidation: 123500,
          market_value: 99000,
          cash: 24500,
          base_currency: "USD"
        },
        {
          timestamp,
          portfolio_value: 125000,
          net_liquidation: 125000,
          market_value: 100000,
          cash: 25000,
          base_currency: "USD"
        }
      ],
      health: {
        status: "degraded",
        point_count: 2,
        base_currency: "USD",
        first_timestamp: "2026-07-26T12:00:00Z",
        last_timestamp: timestamp,
        malformed_row_count: 1,
        duplicate_row_count: 0,
        recovery_archive_name: "portfolio_history_mock.partial-recovery.csv",
        last_write_at: timestamp,
        warnings: ["Ignored 1 malformed local portfolio history row; valid rows remain available."]
      },
      warnings: ["Ignored 1 malformed local portfolio history row; valid rows remain available."]
    };
  }

  function emptyHistory(): PortfolioHistoryResponse {
    return {
      source: "local_history_store",
      state: "empty",
      source_provider: "local_history_store",
      retrieved_at: timestamp,
      origin: "playwright.portfolio.local_history",
      freshness_label: "historical",
      transformation_note: "Locally accumulated daily snapshots; not a broker backfill.",
      points: [],
      health: {
        status: "empty",
        point_count: 0,
        base_currency: null,
        first_timestamp: null,
        last_timestamp: null,
        malformed_row_count: 0,
        duplicate_row_count: 0,
        recovery_archive_name: null,
        last_write_at: null,
        warnings: []
      },
      warnings: []
    };
  }

  function partialPerformance(): PortfolioPerformanceResponse {
    return {
      benchmark_symbol: "SPY",
      benchmark_source: "cash_0",
      performance_points: [
        { timestamp: "2026-07-26T12:00:00Z", value: 1 },
        { timestamp, value: 1.012 }
      ],
      benchmark_points: [
        { timestamp: "2026-07-26T12:00:00Z", value: 1 },
        { timestamp, value: 1 }
      ],
      portfolio_base_value: 123500,
      missing_symbols: ["SAP"],
      day_pnl: 725,
      day_pnl_pct: 0.00583,
      day_pnl_source: "historical_eod",
      message: null,
      warnings: [
        "Missing history for: SAP",
        "Position SAP FX unavailable for EUR->USD conversion",
        "No benchmark data for SPY; using Cash (0%) benchmark"
      ],
      state: "partial",
      source_provider: "gamma",
      retrieved_at: timestamp,
      origin: "playwright.portfolio.performance",
      freshness_label: "derived",
      transformation_note: "Gamma-derived weighted performance from aligned constituent histories.",
      complete: false,
      requested_position_count: 2,
      covered_position_count: 1,
      history_coverage_ratio: 0.5,
      missing_history_symbols: ["SAP"],
      missing_fx_symbols: ["SAP"],
      history_source: "constituent_history",
      history_point_count: 2,
      history_source_provider: "mock",
      history_freshness_label: "mocked",
      history_transformation_note: "Explicit mock constituent history.",
      benchmark_source_provider: "gamma_cash_0",
      benchmark_freshness_label: "derived",
      benchmark_transformation_note: "Cash 0% fallback because requested benchmark history was unavailable."
    };
  }

  function unavailablePerformance(): PortfolioPerformanceResponse {
    return {
      ...partialPerformance(),
      benchmark_source: "none",
      performance_points: [],
      benchmark_points: [],
      missing_symbols: [],
      warnings: [],
      state: "unavailable",
      complete: false,
      requested_position_count: 0,
      covered_position_count: 0,
      history_coverage_ratio: null,
      missing_history_symbols: [],
      missing_fx_symbols: [],
      history_source: "unavailable",
      history_point_count: 0,
      history_source_provider: "unavailable",
      history_freshness_label: "unavailable",
      history_transformation_note: "No performance source is available.",
      benchmark_source_provider: "unavailable",
      benchmark_freshness_label: "unavailable",
      benchmark_transformation_note: "No benchmark calculation is available.",
      message: "Two locally observed snapshots are required."
    };
  }
</script>

<PortfolioView
  {snapshot}
  {history}
  {performance}
  {systemStatus}
  {providerUsage}
  {diagnostics}
  diagnosticsLog={["Raw provider diagnostic detail remains in the console."]}
  consoleEntries={[
    {
      label: "Runtime",
      message: "Raw provider diagnostic detail remains in the console.",
      tone: "error"
    }
  ]}
  {diagnosticsOpen}
  onRefreshSnapshot={() => {
    record("refresh_snapshot");
    return true;
  }}
  onRetryHistory={() => {
    record("retry_history");
    return true;
  }}
  onReloadPerformance={(options) => {
    record("reload_performance", options);
    return true;
  }}
  onToggleDiagnostics={() => {
    diagnosticsOpen = !diagnosticsOpen;
    record("toggle_diagnostics", diagnosticsOpen);
    return true;
  }}
  onRefreshDiagnostics={() => {
    record("refresh_diagnostics");
    return true;
  }}
  onRunDiagnostics={() => {
    record("run_diagnostics");
    return { success: true };
  }}
  onForceSubscribe={() => {
    record("force_subscribe");
    return { success: true };
  }}
  onClearHistory={() => {
    record("clear_history");
    return {
      success: true,
      archived: true,
      archive_name: "portfolio_history_mock.cleared.csv",
      lines: ["Local portfolio history cleared and archived."]
    };
  }}
/>
