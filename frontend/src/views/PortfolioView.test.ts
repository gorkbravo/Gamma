import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  SystemStatus
} from "../lib/api/types";
import {
  initialHistoryRequestState,
  initialPerformanceRequestState,
  initialSnapshotRequestState,
  type HistoryUiStatus,
  type PerformanceUiStatus,
  type SnapshotUiStatus
} from "../lib/view-models/portfolio";
import {
  portfolioHistoryRequestState,
  portfolioPerformanceRequestState,
  portfolioSnapshotRequestState,
  resetPortfolioUiStateForTests
} from "../lib/stores/portfolio";
import PortfolioView from "./PortfolioView.svelte";

describe("PortfolioView", () => {
  beforeEach(() => {
    resetPortfolioUiStateForTests();
  });

  it("renders an explicit mock portfolio with provider and quote provenance", () => {
    setRequestStates("ready", "ready", "ready");
    const { body } = renderView({
      snapshot: makeSnapshot({
        source_provider: "mock",
        origin: "sample",
        freshness_label: "mock",
        quote_mode: "Snapshot",
        market_data_mode: "mock",
        transformation_note: "Deterministic demo account snapshot."
      }),
      history: makeHistory(),
      performance: makePerformance(),
      systemStatus: makeSystemStatus({ mock_mode: true })
    });

    expect(body).toContain("MOCK / DEMO");
    expect(body).toContain("Demo portfolio");
    expect(body).toContain("explicit mock data");
    expect(body).toContain(">Mock<");
    expect(body).toContain("Deterministic demo account snapshot.");
    expect(body).toContain('aria-label="Portfolio performance benchmark"');
    expect(body).toContain('aria-label="Portfolio chart view"');
    expect(body).toContain('aria-haspopup="dialog"');
  });

  it("distinguishes a disconnected live provider from an empty account", () => {
    setRequestStates("unavailable", "empty", "unavailable");
    const { body } = renderView({
      snapshot: null,
      history: makeHistory({ points: [], state: "empty" }),
      performance: null,
      systemStatus: makeSystemStatus({
        mock_mode: false,
        connection: {
          connected: false,
          status_text: "Trader Workstation is not connected.",
          action_text: "Connect",
          action_enabled: true,
          active_account: null
        }
      })
    });

    expect(body).toContain("TWS is disconnected");
    expect(body).toContain("Connection setup");
    expect(body).toContain("Portfolio snapshot unavailable");
    expect(body).not.toContain("Account has no positions");
    expect(body).toContain("Retry snapshot");
  });

  it("shows a connected account-subscription failure with a safe remediation", () => {
    setRequestStates("empty", "empty", "unavailable");
    const { body } = renderView({
      snapshot: makeSnapshot({
        state: "empty",
        positions: [],
        requested_position_count: 0,
        quoted_position_count: 0,
        account_summary: {},
        account_summary_available: false,
        account_subscription_usable: false
      }),
      history: makeHistory({ points: [], state: "empty" }),
      performance: null,
      systemStatus: makeSystemStatus()
    });

    expect(body).toContain("No usable account subscription");
    expect(body).toContain("Force subscription");
    expect(body).toContain("Account snapshot is empty");
    expect(body).toContain("Account has no positions");
    expect(body).toContain("read-only account subscription");
  });

  it("keeps positions visible while explaining partial, cached, and missing quotes", () => {
    setRequestStates("partial", "ready", "partial");
    const snapshot = makeSnapshot({
      state: "partial",
      complete: false,
      positions: [
        makePosition({ symbol: "AAPL", display_symbol: "AAPL" }),
        makePosition({
          symbol: "BMW",
          display_symbol: "BMW",
          currency: "EUR",
          market_price: null,
          market_value: null,
          base_market_value: null,
          fx_rate: null
        })
      ],
      requested_position_count: 2,
      quoted_position_count: 1,
      missing_quote_count: 1,
      missing_quote_symbols: ["BMW"],
      cached_quote_count: 1,
      cached_quote_symbols: ["AAPL"]
    });
    const { body } = renderView({
      snapshot,
      history: makeHistory(),
      performance: makePerformance({
        state: "partial",
        complete: false,
        requested_position_count: 2,
        covered_position_count: 1,
        missing_symbols: ["BMW"],
        missing_history_symbols: ["BMW"],
        missing_fx_symbols: ["EURUSD"],
        history_coverage_ratio: 0.5
      }),
      systemStatus: makeSystemStatus()
    });

    expect(body).toContain("Partial quote snapshot");
    expect(body).toContain("1 of 2 requested position quotes are usable");
    expect(body).toContain(">Cached<");
    expect(body).toContain(">Missing<");
    expect(body).toContain("history: BMW");
    expect(body).toContain("FX: EURUSD");
    expect(body).toContain("Coverage 50.00%");
  });

  it("explains thin local history and an explicit Cash 0% benchmark fallback", () => {
    setRequestStates("ready", "empty", "partial");
    const { body } = renderView({
      snapshot: makeSnapshot(),
      history: makeHistory({
        state: "empty",
        points: [
          {
            timestamp: "2026-07-27T12:00:00Z",
            portfolio_value: 100_000,
            net_liquidation: 100_000,
            market_value: 90_000,
            cash: 10_000,
            base_currency: "USD"
          }
        ]
      }),
      performance: makePerformance({
        state: "partial",
        benchmark_source: "cash_0",
        benchmark_source_provider: "gamma_cash_0",
        benchmark_transformation_note: "Cash 0% was used because SPY history was unavailable."
      }),
      systemStatus: makeSystemStatus()
    });

    expect(body).toContain("Local history is still thin");
    expect(body).toContain("not a broker backfill");
    expect(body).toContain("Cash 0% benchmark fallback");
    expect(body).toContain("Benchmark: Cash 0%");
    expect(body).toContain("1 local point");
  });

  it("surfaces recovered persistence without exposing raw provider logs in the primary path", () => {
    setRequestStates("ready", "recovered", "ready");
    const { body } = renderView({
      snapshot: makeSnapshot(),
      history: makeHistory({
        state: "recovered",
        health: {
          status: "recovered",
          point_count: 2,
          base_currency: "USD",
          first_timestamp: "2026-07-26T12:00:00Z",
          last_timestamp: "2026-07-27T12:00:00Z",
          malformed_row_count: 1,
          duplicate_row_count: 0,
          recovery_archive_name: "portfolio-history.corrupt-20260727.csv",
          last_write_at: "2026-07-27T12:00:00Z",
          warnings: ["One malformed row was excluded."]
        }
      }),
      performance: makePerformance(),
      systemStatus: makeSystemStatus(),
      consoleEntries: [
        {
          label: "Provider exception",
          message: "RAW_ACCOUNT_IDENTIFIER_SHOULD_STAY_IN_DIAGNOSTICS",
          tone: "error"
        }
      ]
    });

    expect(body).toContain("Local history recovered");
    expect(body).toContain("portfolio-history.corrupt-20260727.csv");
    expect(body).toContain("locally accumulated snapshots");
    expect(body).not.toContain("RAW_ACCOUNT_IDENTIFIER_SHOULD_STAY_IN_DIAGNOSTICS");
  });

  it("retains valid snapshot and performance content during a refresh", () => {
    portfolioSnapshotRequestState.set({
      ...initialSnapshotRequestState(),
      status: "ready",
      refreshing: true,
      lastSuccessAt: "2026-07-27T12:00:00Z"
    });
    portfolioHistoryRequestState.set({
      ...initialHistoryRequestState(),
      status: "ready"
    });
    portfolioPerformanceRequestState.set({
      ...initialPerformanceRequestState(),
      status: "ready",
      refreshing: true
    });

    const { body } = renderView({
      snapshot: makeSnapshot({ net_liquidation: 123_456 }),
      history: makeHistory(),
      performance: makePerformance(),
      systemStatus: makeSystemStatus()
    });

    expect(body).toContain("REFRESHING SNAPSHOT...");
    expect(body).toContain("Last successful data remains visible.");
    expect(body).toContain("RECALCULATING PERFORMANCE...");
    expect(body).toContain("The current chart remains visible.");
    expect(body).toContain("123,456 USD");
    expect(body).toContain("AAPL");
  });

  it("renders independent history and performance failures with granular retry actions", () => {
    setRequestStates("ready", "failed", "failed");
    const { body } = renderView({
      snapshot: makeSnapshot(),
      history: null,
      performance: null,
      systemStatus: makeSystemStatus()
    });

    expect(body).toContain("Local history unavailable");
    expect(body).toContain("Retry history");
    expect(body).toContain("Performance calculation failed");
    expect(body).toContain("Retry performance");
    expect(body).toContain("AAPL");
  });
});

function renderView(overrides: Partial<Parameters<typeof makeViewProps>[0]> = {}) {
  return render(PortfolioView, {
    props: makeViewProps(overrides)
  });
}

function makeViewProps(overrides: {
  snapshot?: PortfolioSnapshot | null;
  history?: PortfolioHistoryResponse | null;
  performance?: PortfolioPerformanceResponse | null;
  systemStatus?: SystemStatus | null;
  consoleEntries?: Array<{ label: string; message: string; tone: "info" | "warning" | "error" | "action" }>;
} = {}) {
  return {
    snapshot: overrides.snapshot ?? null,
    history: overrides.history ?? null,
    performance: overrides.performance ?? null,
    loading: false,
    systemStatus: overrides.systemStatus ?? null,
    providerUsage: null,
    diagnostics: null,
    diagnosticsLog: [],
    consoleEntries: overrides.consoleEntries ?? [],
    diagnosticsOpen: false,
    diagnosticsLoading: false,
    diagnosticsActionLoading: false,
    onRefreshSnapshot: vi.fn(),
    onRetryHistory: vi.fn(),
    onReloadPerformance: vi.fn(),
    onToggleDiagnostics: vi.fn(),
    onRefreshDiagnostics: vi.fn(),
    onRunDiagnostics: vi.fn(),
    onForceSubscribe: vi.fn(),
    onClearHistory: vi.fn()
  };
}

function setRequestStates(
  snapshotStatus: SnapshotUiStatus,
  historyStatus: HistoryUiStatus,
  performanceStatus: PerformanceUiStatus
) {
  portfolioSnapshotRequestState.set({
    ...initialSnapshotRequestState(),
    status: snapshotStatus
  });
  portfolioHistoryRequestState.set({
    ...initialHistoryRequestState(),
    status: historyStatus
  });
  portfolioPerformanceRequestState.set({
    ...initialPerformanceRequestState(),
    status: performanceStatus
  });
}

function makeSystemStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    healthy: true,
    app_name: "Gamma",
    backend: "FastAPI",
    mock_mode: false,
    base_currency: "USD",
    market_data_mode: "delayed_frozen",
    connection: {
      connected: true,
      status_text: "Connected to TWS.",
      action_text: "Disconnect",
      action_enabled: true,
      active_account: "hidden-by-view"
    },
    cached_symbols: [],
    ...overrides
  };
}

function makeSnapshot(overrides: Partial<PortfolioSnapshot> = {}): PortfolioSnapshot {
  return {
    timestamp: "2026-07-27T12:00:00Z",
    base_currency: "USD",
    account_summary: { "NetLiquidation:USD": "100000" },
    positions: [makePosition()],
    total_market_value: 90_000,
    total_cash: 10_000,
    net_liquidation: 100_000,
    day_pnl: 250,
    day_pnl_pct: 0.0025,
    day_pnl_source: "account_summary",
    warnings: [],
    state: "ready",
    source_provider: "ibkr",
    retrieved_at: "2026-07-27T12:00:00Z",
    origin: "provider",
    freshness_label: "delayed",
    transformation_note: "Position values normalized into USD by Gamma.",
    quote_mode: "Snapshot",
    market_data_mode: "delayed_frozen",
    complete: true,
    connection_ready: true,
    account_summary_available: true,
    account_subscription_usable: true,
    requested_position_count: 1,
    quoted_position_count: 1,
    missing_quote_count: 0,
    missing_quote_symbols: [],
    cached_quote_count: 0,
    cached_quote_symbols: [],
    delayed_quote_count: 1,
    delayed_quote_symbols: ["AAPL"],
    available_value_count: 1,
    ...overrides
  };
}

function makePosition(overrides: Partial<PortfolioSnapshot["positions"][number]> = {}) {
  return {
    symbol: "AAPL",
    sec_type: "STK",
    currency: "USD",
    quantity: 10,
    avg_cost: 185,
    market_price: 200,
    market_value: 2_000,
    unrealized_pnl: 150,
    weight: 0.02,
    base_market_value: 2_000,
    fx_rate: 1,
    instrument_id: "AAPL:STK:USD",
    display_symbol: "AAPL",
    exchange: "SMART",
    primary_exchange: "NASDAQ",
    provider: "ibkr",
    provider_id: "ibkr",
    ...overrides
  };
}

function makeHistory(overrides: Partial<PortfolioHistoryResponse> = {}): PortfolioHistoryResponse {
  return {
    source: "local_csv",
    source_provider: "gamma_local_history",
    origin: "local_persistence",
    freshness_label: "locally accumulated",
    transformation_note: "One locally observed snapshot per day.",
    warnings: [],
    state: "ready",
    points: [
      {
        timestamp: "2026-07-26T12:00:00Z",
        portfolio_value: 99_000,
        net_liquidation: 99_000,
        market_value: 89_000,
        cash: 10_000,
        base_currency: "USD"
      },
      {
        timestamp: "2026-07-27T12:00:00Z",
        portfolio_value: 100_000,
        net_liquidation: 100_000,
        market_value: 90_000,
        cash: 10_000,
        base_currency: "USD"
      }
    ],
    health: {
      status: "ready",
      point_count: 2,
      base_currency: "USD",
      first_timestamp: "2026-07-26T12:00:00Z",
      last_timestamp: "2026-07-27T12:00:00Z",
      malformed_row_count: 0,
      duplicate_row_count: 0,
      recovery_archive_name: null,
      last_write_at: "2026-07-27T12:00:00Z",
      warnings: []
    },
    ...overrides
  };
}

function makePerformance(
  overrides: Partial<PortfolioPerformanceResponse> = {}
): PortfolioPerformanceResponse {
  return {
    benchmark_symbol: "SPY",
    benchmark_source: "mock",
    benchmark_source_provider: "mock",
    performance_points: [
      { timestamp: "2026-07-26T12:00:00Z", value: 1 },
      { timestamp: "2026-07-27T12:00:00Z", value: 1.01 }
    ],
    benchmark_points: [
      { timestamp: "2026-07-26T12:00:00Z", value: 1 },
      { timestamp: "2026-07-27T12:00:00Z", value: 1.005 }
    ],
    portfolio_base_value: 100_000,
    missing_symbols: [],
    day_pnl: 250,
    day_pnl_pct: 0.0025,
    day_pnl_source: "account_summary",
    message: null,
    warnings: [],
    state: "ready",
    source_provider: "gamma_performance",
    origin: "derived",
    freshness_label: "derived",
    transformation_note: "Gamma-derived position-weighted return series.",
    complete: true,
    requested_position_count: 1,
    covered_position_count: 1,
    history_coverage_ratio: 1,
    missing_history_symbols: [],
    missing_fx_symbols: [],
    history_source: "constituent_history",
    history_point_count: 2,
    benchmark_freshness_label: "mock",
    benchmark_transformation_note: "Deterministic benchmark fixture.",
    ...overrides
  };
}
