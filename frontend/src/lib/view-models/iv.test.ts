import { describe, expect, it } from "vitest";
import type { IvSurface, TimeSeriesPoint } from "../api/types";
import {
  buildStrategyLegFromChainRow,
  deriveChainRows,
  daysToExpiry,
  deriveDistributionBuckets,
  deriveOverviewSnapshot,
  deriveRealizedVolatility,
  deriveSkewRows,
  deriveStrategyPayoff,
  deriveSurfaceStats,
  deriveTermStructure,
  nearestStrikeIndex,
} from "./iv";

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

  it("parses days to expiry from TWS-style expiry strings", () => {
    expect(daysToExpiry("20260501", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("2026-05-01", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("bad", new Date("2026-04-21T10:00:00Z"))).toBe(0);
  });
});
