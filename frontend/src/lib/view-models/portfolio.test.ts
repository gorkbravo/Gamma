import { describe, expect, it } from "vitest";
import type {
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot,
  SystemStatus
} from "../api/types";
import {
  classifyHistoryStatus,
  classifyPerformanceStatus,
  classifySnapshotStatus,
  derivePortfolioDiagnostics,
  derivePortfolioNotices,
  derivePortfolioReadiness,
  derivePositionEmptyState,
  filterAndSortPositions,
  initialHistoryRequestState,
  initialPerformanceRequestState,
  initialSnapshotRequestState,
  lookbackDaysForPortfolioTimeframe,
  positionQuoteStatus
} from "./portfolio";

const positions = [
  {
    symbol: "CASHUSD",
    sec_type: "CASH",
    currency: "USD",
    quantity: 1000,
    avg_cost: null,
    market_price: 1,
    market_value: 1000,
    unrealized_pnl: 0,
    weight: 0.25,
    base_market_value: 1000,
    fx_rate: 1,
    instrument_id: "cash:usd",
    display_symbol: "USD Cash",
    exchange: null,
    primary_exchange: null,
    provider: "portfolio",
    provider_id: "USD"
  },
  {
    symbol: "MSFT",
    sec_type: "STK",
    currency: "USD",
    quantity: 5,
    avg_cost: 300,
    market_price: 320,
    market_value: 1600,
    unrealized_pnl: 100,
    weight: 0.4,
    base_market_value: 1600,
    fx_rate: 1,
    instrument_id: "portfolio:stk:msft",
    display_symbol: "MSFT",
    exchange: "SMART",
    primary_exchange: "NASDAQ",
    provider: "ibkr",
    provider_id: "MSFT"
  },
  {
    symbol: "SAP",
    sec_type: "STK",
    currency: "EUR",
    quantity: 10,
    avg_cost: 120,
    market_price: 110,
    market_value: 1100,
    unrealized_pnl: -100,
    weight: 0.35,
    base_market_value: 1100,
    fx_rate: 1.08,
    instrument_id: "portfolio:stk:sap",
    display_symbol: "SAP",
    exchange: "SMART",
    primary_exchange: "XETRA",
    provider: "ibkr",
    provider_id: "SAP"
  }
];

describe("portfolio view model helpers", () => {
  it("filters and sorts positions for the browser table", () => {
    const filtered = filterAndSortPositions(positions, {
      search: "st",
      sortKey: "base_market_value",
      descending: true,
      includeCash: false
    });

    expect(filtered.map((position) => position.symbol)).toEqual(["MSFT", "SAP"]);
  });

  it("derives portfolio diagnostics from the snapshot", () => {
    const diagnostics = derivePortfolioDiagnostics({
      timestamp: "2026-03-01T00:00:00Z",
      base_currency: "USD",
      account_summary: {},
      positions,
      total_market_value: 2700,
      total_cash: 1000,
      net_liquidation: 3700,
      day_pnl: 0,
      day_pnl_pct: 0,
      day_pnl_source: "account_summary",
      warnings: []
    });

    expect(diagnostics.largestPosition?.symbol).toBe("MSFT");
    expect(diagnostics.bestPnl?.symbol).toBe("MSFT");
    expect(diagnostics.worstPnl?.symbol).toBe("SAP");
    expect(diagnostics.cashWeight).toBeCloseTo(1000 / 3700);
  });

  it("classifies independent snapshot, history, and performance states", () => {
    expect(classifySnapshotStatus(makeSnapshot({ state: "partial", complete: false }))).toBe("partial");
    expect(classifySnapshotStatus(makeSnapshot({ positions: [], state: "empty" }))).toBe("empty");
    expect(
      classifyHistoryStatus(makeHistory({ state: "recovered", health: { status: "recovered" } }))
    ).toBe("recovered");
    expect(
      classifyPerformanceStatus(
        makePerformance({
          state: "partial",
          complete: false,
          benchmark_source: "cash_0"
        })
      )
    ).toBe("partial");
    expect(
      classifyPerformanceStatus(
        makePerformance({
          state: undefined,
          complete: undefined,
          performance_points: [{ timestamp: "2026-07-27T00:00:00Z", value: 1 }]
        })
      )
    ).toBe("ready");
  });

  it("distinguishes a populated account with no filter matches from an empty account", () => {
    const populated = makeSnapshot();
    expect(
      derivePositionEmptyState({
        snapshot: populated,
        snapshotStatus: "ready",
        filteredCount: 0,
        search: "NO_MATCH",
        includeCash: true
      })
    ).toMatchObject({
      kind: "filter_empty",
      title: "No positions match this filter",
      canClearFilter: true
    });

    expect(
      derivePositionEmptyState({
        snapshot: makeSnapshot({ positions: [], state: "empty" }),
        snapshotStatus: "empty",
        filteredCount: 0,
        search: "",
        includeCash: true
      })
    ).toMatchObject({
      kind: "account_empty",
      title: "Account has no positions",
      canClearFilter: false
    });
  });

  it("surfaces explicit mock, disconnected, partial quote, and benchmark fallback notices", () => {
    const snapshotState = {
      ...initialSnapshotRequestState(),
      status: "partial" as const
    };
    const historyState = {
      ...initialHistoryRequestState(),
      status: "ready" as const
    };
    const performanceState = {
      ...initialPerformanceRequestState(),
      status: "partial" as const
    };
    const notices = derivePortfolioNotices({
      snapshot: makeSnapshot({
        state: "partial",
        complete: false,
        requested_position_count: 3,
        quoted_position_count: 2,
        missing_quote_count: 1
      }),
      history: makeHistory(),
      performance: makePerformance({
        state: "partial",
        benchmark_source: "cash_0"
      }),
      snapshotState,
      historyState,
      performanceState,
      systemStatus: makeSystemStatus({ mock_mode: true })
    });

    expect(notices.map((notice) => notice.title)).toEqual(
      expect.arrayContaining(["Demo portfolio", "Partial quote snapshot", "Cash 0% benchmark fallback"])
    );

    const disconnected = derivePortfolioNotices({
      snapshot: null,
      history: null,
      performance: null,
      snapshotState: { ...initialSnapshotRequestState(), status: "unavailable" },
      historyState: initialHistoryRequestState(),
      performanceState: initialPerformanceRequestState(),
      systemStatus: makeSystemStatus({
        mock_mode: false,
        connection: {
          connected: false,
          status_text: "Status: Disconnected",
          action_text: "Connect",
          action_enabled: true,
          active_account: null
        }
      })
    });
    expect(disconnected.some((notice) => notice.title === "TWS is disconnected")).toBe(true);
  });

  it("does not hide recovered persistence when snapshot health is stronger than the history GET", () => {
    const notices = derivePortfolioNotices({
      snapshot: makeSnapshot({
        history_store_health: {
          status: "recovered",
          point_count: 2,
          recovery_archive_name: "portfolio_history_live.corrupt.csv"
        }
      }),
      history: makeHistory({
        state: "ready",
        health: { status: "ready", point_count: 2 }
      }),
      performance: makePerformance(),
      snapshotState: { ...initialSnapshotRequestState(), status: "ready" },
      historyState: { ...initialHistoryRequestState(), status: "ready" },
      performanceState: { ...initialPerformanceRequestState(), status: "ready" }
    });

    expect(notices).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          title: "Local history recovered",
          detail: expect.stringContaining("portfolio_history_live.corrupt.csv")
        })
      ])
    );
  });

  it("summarizes readiness without exposing the raw account identifier", () => {
    const readiness = derivePortfolioReadiness({
      snapshot: makeSnapshot({
        account_summary_available: true,
        account_subscription_usable: true,
        requested_position_count: 3,
        quoted_position_count: 3,
        market_data_mode: "live",
        freshness_label: "live"
      }),
      history: makeHistory(),
      performance: makePerformance(),
      snapshotState: {
        ...initialSnapshotRequestState(),
        status: "ready",
        lastSuccessAt: "2026-07-27T10:00:00Z"
      },
      historyState: { ...initialHistoryRequestState(), status: "ready" },
      performanceState: { ...initialPerformanceRequestState(), status: "ready" },
      systemStatus: makeSystemStatus({
        connection: {
          connected: true,
          status_text: "Status: Connected",
          action_text: "Disconnect",
          action_enabled: true,
          active_account: "DU123456"
        }
      })
    });

    expect(readiness.modeLabel).toBe("LIVE / IBKR");
    expect(JSON.stringify(readiness)).not.toContain("DU123456");
    expect(readiness.rows).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "Account Subscription", value: "Usable" }),
        expect.objectContaining({ label: "Quote Coverage", value: "3 / 3" })
      ])
    );
  });

  it("labels per-position quote provenance and keeps Max inside the API limit", () => {
    const snapshot = makeSnapshot({
      cached_quote_symbols: ["MSFT"],
      delayed_quote_symbols: ["SAP"],
      missing_quote_symbols: ["LMT"],
      market_data_mode: "live"
    });
    expect(positionQuoteStatus(snapshot, positions[1]).label).toBe("Cached");
    expect(positionQuoteStatus(snapshot, positions[2]).label).toBe("Delayed");
    expect(
      positionQuoteStatus(snapshot, {
        ...positions[1],
        symbol: "LMT",
        display_symbol: "LMT",
        market_price: null
      }).label
    ).toBe("Missing");
    expect(lookbackDaysForPortfolioTimeframe("max")).toBe(2520);
  });
});

function makeSnapshot(overrides: Record<string, unknown> = {}): PortfolioSnapshot {
  return {
    timestamp: "2026-07-27T10:00:00Z",
    base_currency: "USD",
    account_summary: { BuyingPower: "10000" },
    positions,
    total_market_value: 2700,
    total_cash: 1000,
    net_liquidation: 3700,
    day_pnl: 25,
    day_pnl_pct: 0.0067,
    day_pnl_source: "account_summary",
    warnings: [],
    state: "ready",
    source_provider: "ibkr",
    retrieved_at: "2026-07-27T10:00:01Z",
    origin: "portfolio_service.snapshot",
    freshness_label: "live",
    transformation_note: "Base-currency values are Gamma-normalized.",
    quote_mode: "Snapshot",
    market_data_mode: "live",
    complete: true,
    connection_ready: true,
    account_summary_available: true,
    account_subscription_usable: true,
    requested_position_count: 3,
    quoted_position_count: 3,
    missing_quote_count: 0,
    missing_quote_symbols: [],
    cached_quote_count: 0,
    cached_quote_symbols: [],
    delayed_quote_count: 0,
    delayed_quote_symbols: [],
    available_value_count: 3,
    ...overrides
  } as PortfolioSnapshot;
}

function makeHistory(overrides: Record<string, unknown> = {}): PortfolioHistoryResponse {
  return {
    source: "local_history_store",
    points: [
      {
        timestamp: "2026-07-26T10:00:00Z",
        portfolio_value: 3600,
        net_liquidation: 3600,
        market_value: 2600,
        cash: 1000,
        base_currency: "USD"
      },
      {
        timestamp: "2026-07-27T10:00:00Z",
        portfolio_value: 3700,
        net_liquidation: 3700,
        market_value: 2700,
        cash: 1000,
        base_currency: "USD"
      }
    ],
    state: "ready",
    source_provider: "local_history_store",
    retrieved_at: "2026-07-27T10:00:01Z",
    origin: "portfolio_history_store",
    freshness_label: "historical",
    transformation_note: "Locally accumulated daily snapshots.",
    warnings: [],
    health: {
      status: "ready",
      point_count: 2,
      base_currency: "USD",
      first_timestamp: "2026-07-26T10:00:00Z",
      last_timestamp: "2026-07-27T10:00:00Z",
      malformed_row_count: 0,
      duplicate_row_count: 0,
      recovery_archive_name: null,
      last_write_at: "2026-07-27T10:00:00Z",
      warnings: []
    },
    ...overrides
  } as PortfolioHistoryResponse;
}

function makePerformance(overrides: Record<string, unknown> = {}): PortfolioPerformanceResponse {
  return {
    benchmark_symbol: "SPY",
    benchmark_source: "history_SPY",
    benchmark_source_provider: "mock",
    performance_points: [
      { timestamp: "2026-07-26T00:00:00Z", value: 1 },
      { timestamp: "2026-07-27T00:00:00Z", value: 1.01 }
    ],
    benchmark_points: [
      { timestamp: "2026-07-26T00:00:00Z", value: 1 },
      { timestamp: "2026-07-27T00:00:00Z", value: 1.005 }
    ],
    portfolio_base_value: 3700,
    missing_symbols: [],
    day_pnl: 25,
    day_pnl_pct: 0.0067,
    day_pnl_source: "account_summary",
    message: null,
    warnings: [],
    state: "ready",
    source_provider: "gamma",
    retrieved_at: "2026-07-27T10:00:02Z",
    origin: "portfolio_service.performance",
    freshness_label: "derived",
    transformation_note: "Gamma-derived weighted returns.",
    complete: true,
    requested_position_count: 2,
    covered_position_count: 2,
    history_coverage_ratio: 1,
    missing_history_symbols: [],
    missing_fx_symbols: [],
    history_source: "configured_provider_chain",
    history_source_provider: "mock",
    history_freshness_label: "mocked",
    history_transformation_note: "Mock constituent histories.",
    history_point_count: 252,
    benchmark_freshness_label: "mocked",
    benchmark_transformation_note: "Mock SPY benchmark.",
    ...overrides
  } as PortfolioPerformanceResponse;
}

function makeSystemStatus(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    healthy: true,
    app_name: "Gamma",
    backend: "FastAPI",
    mock_mode: false,
    base_currency: "USD",
    market_data_mode: "live",
    connection: {
      connected: true,
      status_text: "Status: Connected",
      action_text: "Disconnect",
      action_enabled: true,
      active_account: null
    },
    cached_symbols: [],
    ...overrides
  };
}
