import { describe, expect, it } from "vitest";
import type { IvSessionStatus, IvSurface, SystemStatus, TimeSeriesPoint } from "../api/types";
import {
  blackScholesPrice,
  blackScholesGreeks,
  buildStrategyLegFromChainRow,
  buildStrategyTemplateLegs,
  deriveChainRows,
  daysToExpiry,
  deriveChainGreekRows,
  deriveDistributionBuckets,
  deriveImpliedProbabilitySelection,
  deriveImpliedProbabilitySlice,
  deriveImpliedProbabilitySurface,
  deriveFittedSmileSamples,
  deriveIvSurfaceAlerts,
  deriveIvSmile,
  deriveObservedSurfacePoints,
  deriveObservedTermStructure,
  deriveOptionPayoffMatrix,
  deriveOverviewSnapshot,
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
  livePositionForSymbol,
  nearestStrikeIndex,
  reconcileStrategyToSymbol,
} from "./iv";

const connectedStatus: SystemStatus = {
  healthy: true,
  app_name: "Gamma",
  backend: "test",
  mock_mode: false,
  base_currency: "USD",
  market_data_mode: "delayed",
  connection: {
    connected: true,
    status_text: "Connected",
    action_text: "Disconnect",
    action_enabled: true,
    active_account: "TEST",
  },
  cached_symbols: [],
};

const idleSession: IvSessionStatus = {
  running: false,
  status_text: "Idle",
  active_symbol: null,
  market_data_mode: "delayed",
  messages: [],
  surface: makeSurface({
    snapshot_available: false,
    spot: null,
    expiries: [],
    strikes: [],
    iv_grid: [],
    points: 0,
  }),
};

function makeSurface(overrides: Partial<IvSurface> = {}): IvSurface {
  return {
    symbol: "SPY",
    timestamp: "2026-04-21T12:00:00Z",
    retrieved_at: "2026-04-21T12:00:01Z",
    snapshot_available: true,
    spot: 100,
    expiries: ["20260515", "20260619", "20260717"],
    strikes: [90, 95, 100, 105, 110],
    iv_grid: [
      [0.24, 0.21, 0.18, 0.19, 0.22],
      [0.27, 0.23, 0.2, 0.21, 0.24],
      [0.29, 0.25, 0.22, 0.23, 0.26],
    ],
    delayed: true,
    points: 15,
    warnings: [],
    messages: [],
    source_provider: "ibkr",
    origin: "gamma.iv.surface.ibkr",
    transformation_note: "test",
    freshness_label: "delayed",
    collection: null,
    quality: null,
    pairs: [
      {
        pair_id: "20260515-95",
        expiry: "20260515",
        strike: 95,
        days_to_expiry: 24,
        call_contract_id: "c-95",
        put_contract_id: "p-95",
        call_midpoint: 6,
        put_midpoint: 1,
        call_mark_price: null,
        put_mark_price: null,
        call_price: 6,
        put_price: 1,
        call_price_source: "midpoint",
        put_price_source: "midpoint",
        call_implied_volatility: 0.21,
        put_implied_volatility: 0.2,
        blended_implied_volatility: 0.205,
        call_delta: 0.7,
        put_delta: -0.3,
        call_open_interest: 100,
        put_open_interest: 80,
        call_volume: 20,
        put_volume: 15,
        straddle_midpoint: 7,
        synthetic_forward_price: null,
        implied_move_pct: 0.07,
        call_put_parity_gap: null,
      },
      {
        pair_id: "20260515-100",
        expiry: "20260515",
        strike: 100,
        days_to_expiry: 24,
        call_contract_id: "c-100",
        put_contract_id: "p-100",
        call_midpoint: 3,
        put_midpoint: 3,
        call_mark_price: null,
        put_mark_price: null,
        call_price: 3,
        put_price: 3,
        call_price_source: "midpoint",
        put_price_source: "midpoint",
        call_implied_volatility: 0.18,
        put_implied_volatility: 0.18,
        blended_implied_volatility: 0.18,
        call_delta: 0.5,
        put_delta: -0.5,
        call_open_interest: 120,
        put_open_interest: 150,
        call_volume: 30,
        put_volume: 45,
        straddle_midpoint: 6,
        synthetic_forward_price: null,
        implied_move_pct: 0.06,
        call_put_parity_gap: null,
      },
      {
        pair_id: "20260515-105",
        expiry: "20260515",
        strike: 105,
        days_to_expiry: 24,
        call_contract_id: "c-105",
        put_contract_id: "p-105",
        call_midpoint: 1,
        put_midpoint: 6,
        call_mark_price: null,
        put_mark_price: null,
        call_price: 1,
        put_price: 6,
        call_price_source: "midpoint",
        put_price_source: "midpoint",
        call_implied_volatility: 0.19,
        put_implied_volatility: 0.2,
        blended_implied_volatility: 0.195,
        call_delta: 0.3,
        put_delta: -0.7,
        call_open_interest: 90,
        put_open_interest: 110,
        call_volume: 12,
        put_volume: 18,
        straddle_midpoint: 7,
        synthetic_forward_price: null,
        implied_move_pct: 0.07,
        call_put_parity_gap: null,
      },
    ],
    ...overrides,
  };
}

describe("options surface view models", () => {
  it("explains an idle empty surface and names the visible symbol", () => {
    expect(deriveIvSurfaceAlerts({
      result: null,
      session: idleSession,
      status: connectedStatus,
      requestedSymbol: "xle",
    })).toEqual([
      "No options surface snapshot is available for XLE. The provider session is idle; load the surface and check options entitlements if collection remains unavailable.",
    ]);
  });

  it("distinguishes disconnected and collecting empty states", () => {
    const disconnected = deriveIvSurfaceAlerts({
      result: null,
      session: idleSession,
      status: {
        ...connectedStatus,
        connection: { ...connectedStatus.connection, connected: false },
      },
      requestedSymbol: "SPY",
    });
    const collecting = deriveIvSurfaceAlerts({
      result: null,
      session: { ...idleSession, running: true, active_symbol: "QQQ" },
      status: connectedStatus,
      requestedSymbol: "",
    });

    expect(disconnected).toEqual([
      "IBKR/TWS is disconnected. Connect it before loading an options surface for SPY.",
    ]);
    expect(collecting).toEqual([
      "The QQQ options session is running, but no surface snapshot has been collected yet.",
    ]);
  });

  it("preserves provider detail without duplicating messages", () => {
    const unavailable = makeSurface({
      snapshot_available: false,
      spot: null,
      expiries: [],
      strikes: [],
      iv_grid: [],
      points: 0,
      warnings: ["No market data entitlement for XLE."],
      messages: ["No market data entitlement for XLE."],
    });

    expect(deriveIvSurfaceAlerts({
      result: unavailable,
      session: idleSession,
      status: connectedStatus,
      requestedSymbol: "XLE",
    })).toEqual([
      "No options surface snapshot is available for XLE. The provider session is idle; load the surface and check options entitlements if collection remains unavailable.",
      "No market data entitlement for XLE.",
    ]);
  });

  it("does not render an availability alert while loading or after data arrives", () => {
    expect(deriveIvSurfaceAlerts({
      result: null,
      session: idleSession,
      status: connectedStatus,
      requestedSymbol: "SPY",
      loading: true,
    })).toEqual([]);
    expect(deriveIvSurfaceAlerts({
      result: makeSurface(),
      session: idleSession,
      status: connectedStatus,
      requestedSymbol: "SPY",
    })).toEqual([]);
  });

  it("derives ATM term and surface diagnostics", () => {
    const surface = makeSurface();

    expect(nearestStrikeIndex(surface)).toBe(2);
    expect(deriveTermStructure(surface)).toEqual([
      { expiry: "20260515", iv: 0.18 },
      { expiry: "20260619", iv: 0.2 },
      { expiry: "20260717", iv: 0.22 },
    ]);
    const stats = deriveSurfaceStats(surface);
    expect(stats).toMatchObject({
      atmStrike: 100,
      frontExpiry: "20260515",
      frontAtmIv: 0.18,
      backAtmIv: 0.22,
      populatedPoints: 15,
    });
    expect(stats.termSlope).toBeCloseTo(0.04, 8);
  });

  it("derives wing skew from the selected surface", () => {
    const rows = deriveSkewRows(makeSurface());

    expect(rows[0]).toMatchObject({
      expiry: "20260515",
      atmIv: 0.18,
      putWingStrike: 90,
      callWingStrike: 110,
    });
    expect(rows[0].putSkew).toBeCloseTo(0.06, 8);
    expect(rows[0].callSkew).toBeCloseTo(0.04, 8);
    expect(rows[0].wingSpread).toBeCloseTo(0.02, 8);
  });

  it("derives realized volatility windows from research price history", () => {
    const points: TimeSeriesPoint[] = Array.from({ length: 70 }, (_, index) => ({
      timestamp: `2026-02-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z`,
      value: 100 + index + Math.sin(index) * 2,
    }));

    const rows = deriveRealizedVolatility(points, 0.22, [20, 60]);

    expect(rows).toHaveLength(2);
    expect(rows[0].window).toBe(20);
    expect(rows[0].realizedVol).toBeGreaterThan(0);
    expect(rows[0].spreadToFrontIv).not.toBeNull();
    expect(rows[1].observationCount).toBe(60);
  });

  it("builds a normalized distribution proxy from front ATM IV", () => {
    const buckets = deriveDistributionBuckets(makeSurface(), 9);
    const total = buckets.reduce((sum, bucket) => sum + bucket.probability, 0);

    expect(buckets).toHaveLength(9);
    expect(total).toBeCloseTo(1, 6);
  });

  it("derives implied probability surface slices and selected probability mass", () => {
    const probabilitySurface = deriveImpliedProbabilitySurface(makeSurface());
    const slice = deriveImpliedProbabilitySlice(probabilitySurface, "20260515", 420, 180);
    const selection = deriveImpliedProbabilitySelection(slice, 95, 105);

    expect(probabilitySurface).not.toBeNull();
    expect(probabilitySurface!.densityGrid).toHaveLength(3);
    expect(slice).not.toBeNull();
    expect(slice!.points.map((point) => point.strike)).toEqual([90, 95, 100, 105, 110]);
    expect(selection).not.toBeNull();
    expect(selection!.probabilityMass).toBeGreaterThan(0);
    expect(selection!.probabilityMass).toBeLessThanOrEqual(1);
    expect(selection!.areaPath.endsWith("Z")).toBe(true);
  });

  it("derives chain rows and overview ratios from paired options", () => {
    const surface = makeSurface();
    const rows = deriveChainRows(surface, "20260515");
    const overview = deriveOverviewSnapshot(surface, "20260515");

    expect(rows.map((row) => row.strike)).toEqual([95, 100, 105]);
    expect(overview.atmPair?.strike).toBe(100);
    expect(overview.putCallOpenInterestRatio).toBeCloseTo(340 / 310, 8);
    expect(overview.putCallVolumeRatio).toBeCloseTo(78 / 62, 8);
    expect(overview.maxPainStrike).toBe(100);
  });

  it("uses display price fallbacks for chain rows", () => {
    const surface = makeSurface({
      pairs: [
        {
          ...makeSurface().pairs[0],
          call_midpoint: null,
          put_midpoint: null,
          call_mark_price: 6.1,
          put_mark_price: 1.1,
          call_price: 6.2,
          put_price: 1.2,
          call_price_source: "last",
          put_price_source: "mark",
        },
      ],
    });

    const [row] = deriveChainRows(surface, "20260515");

    expect(row.callMidpoint).toBe(6.2);
    expect(row.putMidpoint).toBe(1.2);
    expect(row.callPriceSource).toBe("last");
    expect(row.putPriceSource).toBe("mark");
  });

  it("builds expiry payoff for a simple long call strategy", () => {
    const row = deriveChainRows(makeSurface(), "20260515")[1];
    const leg = buildStrategyLegFromChainRow(row, "call", "long");
    expect(leg).not.toBeNull();

    const payoff = deriveStrategyPayoff(leg ? [leg] : [], 100, 9);

    expect(payoff.netPremium).toBeCloseTo(-3, 8);
    expect(payoff.maxLoss).toBeLessThanOrEqual(-3);
    expect(payoff.points[0].payoff).toBeCloseTo(-3, 8);
    expect(payoff.points.at(-1)?.payoff).toBeGreaterThan(0);
    expect(payoff.breakevens[0]).toBeCloseTo(103, 0);
  });

  it("reports defined risk for spreads and open-ended tails only for net call exposure", () => {
    const rows = deriveChainRows(makeSurface(), "20260515");

    // Put spread: long 100P @ 3, short 95P @ 1 → defined risk on both sides.
    const longPut = buildStrategyLegFromChainRow(rows[1], "put", "long");
    const shortPut = buildStrategyLegFromChainRow(rows[0], "put", "short");
    const putSpread = deriveStrategyPayoff([longPut!, shortPut!], 100, 9);
    expect(putSpread.netPremium).toBeCloseTo(-2, 8);
    expect(putSpread.maxLoss).toBeCloseTo(-2, 8);
    expect(putSpread.maxProfit).toBeCloseTo(3, 8);

    // Call spread: long 100C @ 3, short 105C @ 1 → also defined on both sides.
    const longCall = buildStrategyLegFromChainRow(rows[1], "call", "long");
    const shortCall = buildStrategyLegFromChainRow(rows[2], "call", "short");
    const callSpread = deriveStrategyPayoff([longCall!, shortCall!], 100, 9);
    expect(callSpread.maxLoss).toBeCloseTo(-2, 8);
    expect(callSpread.maxProfit).toBeCloseTo(3, 8);

    // Long call alone: unbounded upside, loss capped at premium.
    const longCallOnly = deriveStrategyPayoff([longCall!], 100, 9);
    expect(longCallOnly.maxProfit).toBeNull();
    expect(longCallOnly.maxLoss).toBeCloseTo(-3, 8);

    // Short call alone: unbounded loss, profit capped at premium.
    const shortCallOnly = deriveStrategyPayoff([shortCall!], 100, 9);
    expect(shortCallOnly.maxLoss).toBeNull();
    expect(shortCallOnly.maxProfit).toBeCloseTo(1, 8);

    // Short put alone: loss is large but bounded at an underlying price of zero.
    const shortPutOnly = deriveStrategyPayoff([shortPut!], 100, 9);
    expect(shortPutOnly.maxLoss).toBeCloseTo(-(95 - 1), 8);
    expect(shortPutOnly.maxProfit).toBeCloseTo(1, 8);
  });

  it("builds one-click strategy templates from the priced chain", () => {
    const surface = makeSurface();
    const rows = deriveChainRows(surface, "20260515");

    const callSpread = buildStrategyTemplateLegs("call_spread", rows, surface.spot);
    expect(callSpread.legs).toHaveLength(2);
    expect(callSpread.legs[0]).toMatchObject({ optionType: "call", side: "long", strike: 100 });
    expect(callSpread.legs[1]).toMatchObject({ optionType: "call", side: "short", strike: 105 });

    const putSpread = buildStrategyTemplateLegs("put_spread", rows, surface.spot);
    expect(putSpread.legs[0]).toMatchObject({ optionType: "put", side: "long", strike: 100 });
    expect(putSpread.legs[1]).toMatchObject({ optionType: "put", side: "short", strike: 95 });

    const straddle = buildStrategyTemplateLegs("straddle", rows, surface.spot);
    expect(straddle.legs.map((leg) => leg.optionType).sort()).toEqual(["call", "put"]);
    expect(new Set(straddle.legs.map((leg) => leg.strike)).size).toBe(1);
    expect(straddle.legs.every((leg) => leg.side === "long")).toBe(true);

    const collar = buildStrategyTemplateLegs("collar", rows, surface.spot);
    expect(collar.legs[0]).toMatchObject({ optionType: "put", side: "long", strike: 95 });
    expect(collar.legs[1]).toMatchObject({ optionType: "call", side: "short", strike: 105 });
    expect(collar.warnings.some((warning) => warning.includes("long underlying"))).toBe(true);

    const riskReversal = buildStrategyTemplateLegs("risk_reversal", rows, surface.spot);
    expect(riskReversal.legs[0]).toMatchObject({ optionType: "put", side: "short", strike: 95 });
    expect(riskReversal.legs[1]).toMatchObject({ optionType: "call", side: "long", strike: 105 });
    expect(riskReversal.warnings.some((warning) => warning.includes("short put"))).toBe(true);

    const empty = buildStrategyTemplateLegs("call_spread", [], surface.spot);
    expect(empty.legs).toHaveLength(0);
    expect(empty.warnings.length).toBeGreaterThan(0);
  });

  it("derives a neutral straddle payoff glance", () => {
    const surface = makeSurface();
    const rows = deriveChainRows(surface, "20260515");
    const matrix = deriveOptionPayoffMatrix(rows, surface.spot, "straddle", 24, 9, 5);

    expect(matrix).not.toBeNull();
    expect(matrix!.optionType).toBe("straddle");
    expect(matrix!.strike).toBe(100);
    expect(matrix!.premium).toBeCloseTo(6, 8);
    const expiryColumnIndex = matrix!.dteColumns.indexOf(0);
    const topRow = matrix!.rows[0];
    const expiryValue = topRow.cells[expiryColumnIndex].value;
    expect(expiryValue).toBeCloseTo(Math.abs(topRow.price - 100), 6);
  });

  it("builds a strategy payoff matrix from selected legs and chain IV", () => {
    const surface = makeSurface();
    const rows = deriveChainRows(surface, "20260515");
    const callLeg = buildStrategyLegFromChainRow(rows[1], "call", "long");
    const putLeg = buildStrategyLegFromChainRow(rows[1], "put", "short");
    const matrix = deriveStrategyPayoffMatrix([callLeg!, putLeg!], rows, surface.spot, 9, 5);

    expect(matrix).not.toBeNull();
    expect(matrix!.dteColumns.at(-1)).toBe(0);
    expect(matrix!.rows).toHaveLength(9);
    expect(matrix!.rows[0].cells).toHaveLength(matrix!.dteColumns.length);
    expect(matrix!.maxAbsPl).toBeGreaterThan(0);
    expect(matrix!.riskBasis).toBeGreaterThan(0);
  });

  it("prices options with Black-Scholes and respects intrinsic boundaries", () => {
    // ATM call with time value must exceed its (zero) intrinsic value.
    const atmCall = blackScholesPrice("call", 100, 100, 30 / 365, 0.2);
    expect(atmCall).toBeGreaterThan(0);

    // At expiry, value collapses to intrinsic.
    expect(blackScholesPrice("call", 110, 100, 0, 0.2)).toBeCloseTo(10, 6);
    expect(blackScholesPrice("put", 90, 100, 0, 0.2)).toBeCloseTo(10, 6);
    expect(blackScholesPrice("call", 90, 100, 0, 0.2)).toBe(0);

    // Put-call parity with zero rate: C - P == S - K.
    const call = blackScholesPrice("call", 105, 100, 0.5, 0.25);
    const put = blackScholesPrice("put", 105, 100, 0.5, 0.25);
    expect(call - put).toBeCloseTo(5, 6);
  });

  it("derives Gamma-owned Greeks from the fitted surface grid", () => {
    const surface = makeSurface();
    const atmCall = blackScholesGreeks("call", 100, 100, 30 / 365, 0.2);
    const greekRows = deriveChainGreekRows(surface, "20260515");
    const chainRows = deriveChainRows(surface, "20260515");
    const leg = buildStrategyLegFromChainRow(chainRows[1], "call", "long");
    const summary = deriveStrategyGreeks(leg ? [leg] : [], surface);

    expect(atmCall.delta).toBeGreaterThan(0.5);
    expect(atmCall.gamma).toBeGreaterThan(0);
    expect(atmCall.vega).toBeGreaterThan(0);
    expect(greekRows).toHaveLength(surface.strikes.length);
    expect(greekRows[2].call?.sigma).toBeCloseTo(surface.iv_grid[0][2], 8);
    expect(greekRows[2].put?.delta).toBeLessThan(0);
    expect(summary).not.toBeNull();
    expect(summary!.delta).toBeGreaterThan(0);
    expect(summary!.legCount).toBe(1);
  });

  it("builds an IV smile geometry from front chain rows", () => {
    const rows = deriveChainRows(makeSurface(), "20260515");
    const smile = deriveIvSmile(rows, 100, 320, 150);

    expect(smile).not.toBeNull();
    expect(smile!.points.map((point) => point.strike)).toEqual([95, 100, 105]);
    expect(smile!.points.find((point) => point.isAtm)?.strike).toBe(100);
    expect(smile!.linePath.startsWith("M")).toBe(true);
    expect(smile!.areaPath.endsWith("Z")).toBe(true);
    expect(smile!.atmX).not.toBeNull();
    // X is monotonic with strike, Y stays inside the viewBox.
    expect(smile!.points[0].x).toBeLessThan(smile!.points[2].x);
    for (const point of smile!.points) {
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(150);
    }
  });

  it("separates observed smile points from an applied parametric fit", () => {
    const surface = makeSurface({ surface_model: "ssvi", surface_model_status: "applied" });
    const rows = deriveChainRows(surface, "20260515");
    const fitted = deriveFittedSmileSamples(surface, "20260515");
    const smile = deriveIvSmile(rows, 100, 320, 150, fitted);

    expect(hasParametricIvFit(surface)).toBe(true);
    expect(hasParametricIvFit({ ...surface, surface_model: "spline" })).toBe(false);
    expect(hasParametricIvFit({ ...surface, surface_model_status: "fallback" })).toBe(false);
    expect(smile?.points).toHaveLength(3);
    expect(smile?.fitPoints).toHaveLength(5);
    expect(smile?.linePath).toContain(smile!.fitPoints[0].x.toFixed(1));
  });

  it("derives observed 3D coordinates and observed ATM term points from option pairs", () => {
    const surface = makeSurface({ surface_model: "ssvi", surface_model_status: "partial" });
    const observed = deriveObservedSurfacePoints(surface);
    const observedTerm = deriveObservedTermStructure(surface);

    expect(observed.map((point) => [point.rowIndex, point.colIndex, point.strike])).toEqual([
      [0, 1, 95],
      [0, 2, 100],
      [0, 3, 105],
    ]);
    expect(observed.every((point) => point.iv > 0)).toBe(true);
    expect(observedTerm).toEqual([{ expiry: "20260515", iv: 0.18 }]);
  });

  it("derives an ATM call payoff matrix across price levels and DTE", () => {
    const rows = deriveChainRows(makeSurface(), "20260515");
    const matrix = deriveOptionPayoffMatrix(rows, 100, "call", 24);

    expect(matrix).not.toBeNull();
    expect(matrix!.optionType).toBe("call");
    expect(matrix!.strike).toBe(100);
    // Premium is the ATM call midpoint = max risk for a long call.
    expect(matrix!.premium).toBe(3);
    // Columns run from the longest DTE down to expiry (0).
    expect(matrix!.dteColumns[0]).toBe(24);
    expect(matrix!.dteColumns.at(-1)).toBe(0);
    // Rows run top (highest price) to bottom (lowest price).
    expect(matrix!.rows[0].price).toBeGreaterThan(matrix!.rows.at(-1)!.price);

    const expiryCol = matrix!.dteColumns.length - 1;
    const topRow = matrix!.rows[0];
    const bottomRow = matrix!.rows.at(-1)!;
    // Deep ITM at expiry is a large gain; deep OTM at expiry is a total (-100%) loss.
    expect(topRow.cells[expiryCol].pct).toBeGreaterThan(0);
    expect(bottomRow.cells[expiryCol].pct).toBeCloseTo(-1, 6);
    // movePct sign tracks distance from spot.
    expect(topRow.movePct).toBeGreaterThan(0);
    expect(bottomRow.movePct).toBeLessThan(0);
  });

  it("returns no payoff matrix without a priced ATM pair", () => {
    const rows = deriveChainRows(makeSurface(), "20260515");
    expect(deriveOptionPayoffMatrix([], 100, "call")).toBeNull();
    expect(deriveOptionPayoffMatrix(rows, null, "call")).toBeNull();
  });

  it("falls back to the nearest priced strike when the exact ATM strike is unquoted", () => {
    // Strike 100 sits nearest spot but is fully unquoted; 95 is the closest priced call.
    const surface = makeSurface();
    surface.pairs = surface.pairs.map((pair) =>
      pair.strike === 100
        ? { ...pair, call_midpoint: null, call_price: null, call_mark_price: null, call_implied_volatility: null, blended_implied_volatility: null }
        : pair
    );
    const rows = deriveChainRows(surface, "20260515");
    const matrix = deriveOptionPayoffMatrix(rows, 100, "call", 24);

    expect(matrix).not.toBeNull();
    expect(matrix!.strike).toBe(95);
    expect(matrix!.premium).toBe(6);
  });

  it("builds a term-structure curve ordered by DTE", () => {
    const term = deriveTermStructure(makeSurface());
    const curve = deriveTermCurve(term, 300, 130);

    expect(curve).not.toBeNull();
    expect(curve!.points.map((point) => point.expiry)).toEqual(["20260515", "20260619", "20260717"]);
    // DTE strictly increasing, X strictly increasing with it.
    for (let i = 1; i < curve!.points.length; i += 1) {
      expect(curve!.points[i].dte).toBeGreaterThanOrEqual(curve!.points[i - 1].dte);
      expect(curve!.points[i].x).toBeGreaterThanOrEqual(curve!.points[i - 1].x);
    }
    expect(curve!.linePath.startsWith("M")).toBe(true);
    expect(curve!.areaPath.endsWith("Z")).toBe(true);
    expect(deriveTermCurve([], 300, 130)).toBeNull();
  });

  it("projects observed term points separately from the fitted curve", () => {
    const term = deriveTermStructure(makeSurface());
    const curve = deriveTermCurve(term, 300, 130, [{ expiry: "20260515", iv: 0.195 }]);

    expect(curve?.observedPoints).toHaveLength(1);
    expect(curve?.observedPoints[0].iv).toBe(0.195);
    expect(curve?.points).toHaveLength(3);
  });

  it("parses days to expiry from TWS-style expiry strings", () => {
    expect(daysToExpiry("20260501", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("2026-05-01", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("bad", new Date("2026-04-21T10:00:00Z"))).toBe(0);
  });
});

describe("deriveStrategySizing", () => {
  const payoff = {
    points: [],
    netPremium: -10.67,
    maxProfit: 14.33,
    maxLoss: -10.67,
    breakevens: [329.33],
  };
  const legs = [
    { id: "a", optionType: "put", side: "long", expiry: "20261120", strike: 340, premium: 18, quantity: 1 },
    { id: "b", optionType: "put", side: "short", expiry: "20261120", strike: 315, premium: 7.33, quantity: 1 },
  ] as any;

  it("converts per-share payoff into contract totals with an explicit multiplier", () => {
    const sizing = deriveStrategySizing(payoff as any, legs, 2, { symbol: "GOOGL", quantity: 400 });

    expect(sizing.multiplier).toBe(100);
    expect(sizing.contracts).toBe(2);
    expect(sizing.netPremiumTotal).toBeCloseTo(-2134, 6);
    expect(sizing.premiumDirection).toBe("debit");
    expect(sizing.maxProfitTotal).toBeCloseTo(2866, 6);
    expect(sizing.sharesRepresented).toBe(200);
    expect(sizing.coverageRatio).toBeCloseTo(0.5, 6);
  });

  it("warns when a single contract already exceeds the live holding", () => {
    const sizing = deriveStrategySizing(payoff as any, legs, 1, { symbol: "GOOGL", quantity: 60 });

    expect(sizing.maxWholeContractsWithinPosition).toBe(0);
    expect(sizing.warnings.join(" ")).toContain("exceeds the live 60-share position");
  });

  it("warns on over-hedge and reports the largest whole-contract size that fits", () => {
    const sizing = deriveStrategySizing(payoff as any, legs, 5, { symbol: "GOOGL", quantity: 250 });

    expect(sizing.coverageRatio).toBeCloseTo(2, 6);
    expect(sizing.maxWholeContractsWithinPosition).toBe(2);
    expect(sizing.warnings.join(" ")).toContain("Over-hedged");
  });

  it("says so when there is no live position to cover", () => {
    const sizing = deriveStrategySizing(payoff as any, legs, 1, null);

    expect(sizing.coverageRatio).toBeNull();
    expect(sizing.warnings.join(" ")).toContain("no account coverage");
  });

  it("keeps a legless builder free of sizing warnings", () => {
    const sizing = deriveStrategySizing({ ...payoff, netPremium: 0 } as any, [], 1, null);

    expect(sizing.sharesRepresented).toBe(0);
    expect(sizing.warnings).toEqual([]);
  });
});

describe("livePositionForSymbol", () => {
  const positions = [
    { symbol: "GOOGL", sec_type: "STK", quantity: 120 },
    { symbol: "GOOGL", sec_type: "OPT", quantity: 3 },
    { symbol: "MSFT", sec_type: "STK", quantity: 40 },
  ];

  it("aggregates stock lines only and ignores option lines", () => {
    expect(livePositionForSymbol(positions as any, "googl")).toEqual({ symbol: "GOOGL", quantity: 120 });
  });

  it("returns null when the symbol is not held", () => {
    expect(livePositionForSymbol(positions as any, "AAPL")).toBeNull();
    expect(livePositionForSymbol(positions as any, "")).toBeNull();
  });
});

describe("reconcileStrategyToSymbol", () => {
  const googlLegs = [
    { id: "a", optionType: "put", side: "long", expiry: "20261120", strike: 335, premium: 16.2, quantity: 1 },
    { id: "b", optionType: "put", side: "short", expiry: "20261120", strike: 315, premium: 8.11, quantity: 1 },
  ] as any;

  it("clears a GOOGL spread when the loaded symbol becomes AAPL", () => {
    const result = reconcileStrategyToSymbol("AAPL", "GOOGL", googlLegs, 3);

    expect(result.cleared).toBe(true);
    expect(result.legs).toEqual([]);
    expect(result.contracts).toBe(1);
    expect(result.strategySymbol).toBe("AAPL");
    expect(result.notice).toContain("Cleared the GOOGL structure");
    expect(result.notice).toContain("rebuild on AAPL");
  });

  it("leaves the structure alone when the symbol is unchanged", () => {
    const result = reconcileStrategyToSymbol("GOOGL", "GOOGL", googlLegs, 3);

    expect(result.cleared).toBe(false);
    expect(result.legs).toBe(googlLegs);
    expect(result.contracts).toBe(3);
  });

  it("normalizes casing and whitespace before comparing", () => {
    const result = reconcileStrategyToSymbol("  googl ", "GOOGL", googlLegs, 2);

    expect(result.cleared).toBe(false);
    expect(result.legs).toBe(googlLegs);
  });

  it("adopts the first symbol without a notice when nothing is built yet", () => {
    const result = reconcileStrategyToSymbol("GOOGL", null, [], 1);

    expect(result.cleared).toBe(false);
    expect(result.strategySymbol).toBe("GOOGL");
    expect(result.notice).toBe("");
  });

  it("clears the structure when the surface is unloaded entirely", () => {
    const result = reconcileStrategyToSymbol(null, "GOOGL", googlLegs, 1);

    expect(result.cleared).toBe(true);
    expect(result.strategySymbol).toBeNull();
    expect(result.legs).toEqual([]);
  });
});
