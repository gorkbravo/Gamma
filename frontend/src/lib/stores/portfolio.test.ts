import { get } from "svelte/store";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  PortfolioHistoryResponse,
  PortfolioPerformanceResponse,
  PortfolioSnapshot
} from "../api/types";
import {
  loadPortfolioPerformanceData,
  loadPortfolioSnapshotData,
  portfolioHistory,
  portfolioHistoryRequestState,
  portfolioPerformance,
  portfolioPerformanceRequestState,
  portfolioPreferences,
  portfolioSnapshot,
  portfolioSnapshotRequestState,
  resetPortfolioUiStateForTests
} from "./portfolio";

describe("portfolio request orchestration", () => {
  beforeEach(() => {
    resetPortfolioUiStateForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("deduplicates duplicate in-flight snapshot refreshes", async () => {
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = String(input);
        requests.push(path);
        if (path.includes("/portfolio/snapshot")) return jsonResponse(makeSnapshot());
        if (path.includes("/portfolio/history")) return jsonResponse(makeHistory());
        if (path.includes("/portfolio/performance")) return jsonResponse(makePerformance("SPY"));
        throw new Error(`Unexpected request ${path}`);
      })
    );

    const [first, second] = await Promise.all([
      loadPortfolioSnapshotData(),
      loadPortfolioSnapshotData()
    ]);

    expect(first).toBe(true);
    expect(second).toBe(true);
    expect(requests.filter((path) => path.includes("/portfolio/snapshot"))).toHaveLength(1);
    expect(requests.filter((path) => path.includes("/portfolio/history"))).toHaveLength(1);
    expect(requests.filter((path) => path.includes("/portfolio/performance"))).toHaveLength(1);
  });

  it("retains the last good snapshot and performance when a typed unavailable snapshot arrives", async () => {
    const priorSnapshot = makeSnapshot({ timestamp: "2026-07-26T10:00:00Z" });
    const priorPerformance = makePerformance("SPY");
    portfolioSnapshot.set(priorSnapshot);
    portfolioPerformance.set(priorPerformance);

    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = String(input);
        requests.push(path);
        if (path.includes("/portfolio/snapshot")) {
          return jsonResponse(
            makeSnapshot({
              state: "unavailable",
              complete: false,
              connection_ready: false,
              positions: [],
              account_summary: {},
              timestamp: "2026-07-27T10:00:00Z"
            })
          );
        }
        if (path.includes("/portfolio/history")) return jsonResponse(makeHistory());
        throw new Error(`Unexpected request ${path}`);
      })
    );

    const loaded = await loadPortfolioSnapshotData();

    expect(loaded).toBe(false);
    expect(get(portfolioSnapshot)).toBe(priorSnapshot);
    expect(get(portfolioPerformance)).toBe(priorPerformance);
    expect(get(portfolioSnapshotRequestState)).toMatchObject({
      status: "unavailable",
      refreshing: false
    });
    expect(get(portfolioSnapshotRequestState).lastFailureAt).not.toBeNull();
    expect(requests.some((path) => path.includes("/portfolio/performance"))).toBe(false);
  });

  it("keeps prior data visible and marks refresh progress until a replacement arrives", async () => {
    const priorSnapshot = makeSnapshot({ timestamp: "2026-07-26T10:00:00Z" });
    portfolioSnapshot.set(priorSnapshot);
    const snapshotRequest = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = String(input);
        if (path.includes("/portfolio/snapshot")) return snapshotRequest.promise;
        if (path.includes("/portfolio/history")) return jsonResponse(makeHistory());
        if (path.includes("/portfolio/performance")) return jsonResponse(makePerformance("SPY"));
        throw new Error(`Unexpected request ${path}`);
      })
    );

    const pending = loadPortfolioSnapshotData();
    await Promise.resolve();

    expect(get(portfolioSnapshot)).toBe(priorSnapshot);
    expect(get(portfolioSnapshotRequestState).refreshing).toBe(true);
    snapshotRequest.resolve(jsonResponse(makeSnapshot()));
    await pending;
    expect(get(portfolioSnapshotRequestState).refreshing).toBe(false);
  });

  it("keeps snapshot and performance success independent from a history failure", async () => {
    const priorHistory = makeHistory({
      points: [{ ...makeHistory().points[0] }]
    });
    portfolioHistory.set(priorHistory);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = String(input);
        if (path.includes("/portfolio/snapshot")) return jsonResponse(makeSnapshot());
        if (path.includes("/portfolio/history")) throw new Error("history disk error");
        if (path.includes("/portfolio/performance")) return jsonResponse(makePerformance("SPY"));
        throw new Error(`Unexpected request ${path}`);
      })
    );

    expect(await loadPortfolioSnapshotData()).toBe(true);
    expect(get(portfolioSnapshot)?.state).toBe("ready");
    expect(get(portfolioPerformance)?.benchmark_symbol).toBe("SPY");
    expect(get(portfolioHistory)).toBe(priorHistory);
    expect(get(portfolioHistoryRequestState).status).toBe("failed");
  });

  it("uses latest-intent ordering for A to B to A performance requests", async () => {
    const snapshot = makeSnapshot();
    portfolioSnapshot.set(snapshot);
    const spyRequest = deferred<Response>();
    const qqqRequest = deferred<Response>();
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const path = String(input);
        requests.push(path);
        const body = JSON.parse(String(init?.body ?? "{}")) as { benchmark_symbol?: string };
        if (body.benchmark_symbol === "SPY") return spyRequest.promise;
        if (body.benchmark_symbol === "QQQ") return qqqRequest.promise;
        throw new Error(`Unexpected benchmark ${body.benchmark_symbol}`);
      })
    );

    const firstSpy = loadPortfolioPerformanceData({
      snapshot,
      benchmarkSymbol: "SPY",
      lookbackDays: 252
    });
    const qqq = loadPortfolioPerformanceData({
      snapshot,
      benchmarkSymbol: "QQQ",
      lookbackDays: 42
    });
    const latestSpy = loadPortfolioPerformanceData({
      snapshot,
      benchmarkSymbol: "SPY",
      lookbackDays: 252
    });

    qqqRequest.resolve(jsonResponse(makePerformance("QQQ")));
    await qqq;
    expect(get(portfolioPerformance)).toBeNull();

    spyRequest.resolve(jsonResponse(makePerformance("SPY")));
    await Promise.all([firstSpy, latestSpy]);

    expect(get(portfolioPerformance)?.benchmark_symbol).toBe("SPY");
    expect(get(portfolioPreferences)).toMatchObject({
      benchmarkSymbol: "SPY",
      timeframe: "1y"
    });
    expect(requests).toHaveLength(2);
    expect(get(portfolioPerformanceRequestState).status).toBe("ready");
  });
});

function makeSnapshot(overrides: Record<string, unknown> = {}): PortfolioSnapshot {
  return {
    timestamp: "2026-07-27T10:00:00Z",
    base_currency: "USD",
    account_summary: { BuyingPower: "10000" },
    positions: [
      {
        symbol: "MSFT",
        sec_type: "STK",
        currency: "USD",
        quantity: 5,
        avg_cost: 300,
        market_price: 320,
        market_value: 1600,
        unrealized_pnl: 100,
        weight: 1,
        base_market_value: 1600,
        fx_rate: 1,
        instrument_id: "ibkr:msft",
        display_symbol: "MSFT",
        exchange: "SMART",
        primary_exchange: "NASDAQ",
        provider: "ibkr",
        provider_id: "MSFT"
      }
    ],
    total_market_value: 1600,
    total_cash: 0,
    net_liquidation: 1600,
    day_pnl: 20,
    day_pnl_pct: 0.0125,
    day_pnl_source: "account_summary",
    warnings: [],
    state: "ready",
    source_provider: "ibkr",
    retrieved_at: "2026-07-27T10:00:01Z",
    origin: "portfolio_service.snapshot",
    freshness_label: "live",
    transformation_note: "Gamma-normalized snapshot.",
    quote_mode: "Snapshot",
    market_data_mode: "live",
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
    delayed_quote_count: 0,
    delayed_quote_symbols: [],
    available_value_count: 1,
    ...overrides
  } as PortfolioSnapshot;
}

function makeHistory(overrides: Record<string, unknown> = {}): PortfolioHistoryResponse {
  return {
    source: "local_history_store",
    points: [
      {
        timestamp: "2026-07-26T10:00:00Z",
        portfolio_value: 1580,
        net_liquidation: 1580,
        market_value: 1580,
        cash: 0,
        base_currency: "USD"
      },
      {
        timestamp: "2026-07-27T10:00:00Z",
        portfolio_value: 1600,
        net_liquidation: 1600,
        market_value: 1600,
        cash: 0,
        base_currency: "USD"
      }
    ],
    state: "ready",
    source_provider: "local_history_store",
    retrieved_at: "2026-07-27T10:00:01Z",
    origin: "portfolio_history_store",
    freshness_label: "historical",
    transformation_note: "Local daily observations.",
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

function makePerformance(
  benchmarkSymbol: string,
  overrides: Record<string, unknown> = {}
): PortfolioPerformanceResponse {
  return {
    benchmark_symbol: benchmarkSymbol,
    benchmark_source: `history_${benchmarkSymbol}`,
    benchmark_source_provider: "mock",
    performance_points: [
      { timestamp: "2026-07-26T00:00:00Z", value: 1 },
      { timestamp: "2026-07-27T00:00:00Z", value: 1.01 }
    ],
    benchmark_points: [
      { timestamp: "2026-07-26T00:00:00Z", value: 1 },
      { timestamp: "2026-07-27T00:00:00Z", value: 1.005 }
    ],
    portfolio_base_value: 1600,
    missing_symbols: [],
    day_pnl: 20,
    day_pnl_pct: 0.0125,
    day_pnl_source: "account_summary",
    message: null,
    warnings: [],
    state: "ready",
    source_provider: "gamma",
    retrieved_at: "2026-07-27T10:00:02Z",
    origin: "portfolio_service.performance",
    freshness_label: "derived",
    transformation_note: "Gamma-derived performance.",
    complete: true,
    requested_position_count: 1,
    covered_position_count: 1,
    history_coverage_ratio: 1,
    missing_history_symbols: [],
    missing_fx_symbols: [],
    history_source: "configured_provider_chain",
    history_source_provider: "mock",
    history_freshness_label: "mocked",
    history_transformation_note: "Mock history.",
    history_point_count: 252,
    benchmark_freshness_label: "mocked",
    benchmark_transformation_note: "Mock benchmark.",
    ...overrides
  } as PortfolioPerformanceResponse;
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}
