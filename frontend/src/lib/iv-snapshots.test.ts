import { describe, expect, it } from "vitest";
import type { IvSurface } from "./api/types";
import { compareIvSnapshots } from "./iv-snapshots";

const surface = (overrides: Partial<IvSurface> = {}): IvSurface => ({
  symbol: "SPY", spot: 100, timestamp: "2026-10-06T14:00:00Z", retrieved_at: "2026-10-06T14:00:00Z",
  snapshot_available: true, points: 3, expiries: ["20261120"], strikes: [95, 100, 105],
  iv_grid: [[0.3, 0.25, 0.26]], cell_sources: [["observed", "observed", "observed"]],
  pairs: [], delayed: true, source_provider: "mock", freshness_label: "mocked", origin: "test",
  transformation_note: null, warnings: [], messages: [], collection: null, quality: null, ...overrides,
});

describe("Options historical comparison", () => {
  it("holds exact baseline ATM and wing strikes fixed despite a spot shift", () => {
    const result = compareIvSnapshots(surface(), surface({ spot: 105, iv_grid: [[0.34, 0.27, 0.27]] }));
    const row = result.rows[0];
    expect(row.strike).toBe(100);
    expect(row.change).toBeCloseTo(0.02);
    expect(row.putSkewChange).toBeCloseTo(0.02);
    expect(row.callSkewChange).toBeCloseTo(-0.01);
  });
  it("does not substitute a fitted cell for a missing observed strike", () => {
    const result = compareIvSnapshots(surface(), surface({ cell_sources: [["observed", "model_fitted", "observed"]] }));
    expect(result.rows[0].after).toBeNull();
    expect(result.rows[0].change).toBeNull();
    expect(result.warnings.join(" ")).toContain("fitted cells are excluded");
  });
  it("uses collected pair observations for a model-fitted display grid", () => {
    const pairs = [{ expiry: "20261120", strike: 100, blended_implied_volatility: 0.28 }] as IvSurface["pairs"];
    const result = compareIvSnapshots(surface(), surface({ pairs, iv_grid: [[0.8, 0.8, 0.8]], cell_sources: [["model_fitted", "model_fitted", "model_fitted"]] }));
    expect(result.rows[0].after).toBe(0.28);
    expect(result.rows[0].change).toBeCloseTo(0.03);
    expect(result.rows[0].putSkewChange).toBeNull();
  });
  it("requires the same symbol and exact expiry dates", () => {
    expect(compareIvSnapshots(surface(), surface({ symbol: "AAPL" })).rows).toEqual([]);
    const result = compareIvSnapshots(surface(), surface({ expiries: ["20261218"] }));
    expect(result.rows).toEqual([]);
    expect(result.warnings).toContain("These captures have no common expiry dates.");
  });
  it("warns about provider/data-mode changes and keeps true zero changes", () => {
    const result = compareIvSnapshots(surface(), surface({ source_provider: "ibkr", freshness_label: "live", delayed: false }));
    expect(result.rows[0].change).toBe(0);
    expect(result.warnings.join(" ")).toContain("different provider");
  });
});
