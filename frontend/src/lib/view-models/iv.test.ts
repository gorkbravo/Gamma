import { describe, expect, it } from "vitest";
import type { IvSurface, TimeSeriesPoint } from "../api/types";
import {
  daysToExpiry,
  deriveDistributionBuckets,
  deriveRealizedVolatility,
  deriveSkewRows,
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
    pairs: [],
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

  it("parses days to expiry from TWS-style expiry strings", () => {
    expect(daysToExpiry("20260501", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("2026-05-01", new Date("2026-04-21T10:00:00Z"))).toBe(10);
    expect(daysToExpiry("bad", new Date("2026-04-21T10:00:00Z"))).toBe(0);
  });
});
