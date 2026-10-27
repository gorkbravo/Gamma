// GUA-20261021-10: titular sin 0D, horizonte de plantillas, theta neta y estado vacío.
import { describe, expect, it } from "vitest";
import type { IvOptionPair, IvSessionStatus, IvSurface, SystemStatus } from "../api/types";
import { toProvenanceBadge } from "../provenance";
import {
  HEADLINE_MIN_DTE,
  STRATEGY_TEMPLATE_MIN_DTE,
  blackScholesGreeks,
  buildStrategyTemplateLegs,
  defaultStrategyExpiry,
  deriveChainRows,
  deriveIvSurfaceAlerts,
  deriveOverviewSnapshot,
  deriveStrategyGreeks,
  deriveSurfaceStats,
  describeHeadlineExpiry,
  selectHeadlineExpiry,
  selectedExpiryForSurface,
  type StrategyLeg,
} from "./iv";

// Momento de la auditoría: 2026-10-21 10:50 UTC (06:50 ET, opciones USA cerradas).
const AUDIT_NOW = new Date("2026-10-21T10:50:00Z");

function pair(expiry: string, strike: number, callIv: number, putIv: number, callPx: number, putPx: number): IvOptionPair {
  return {
    pair_id: `${expiry}-${strike}`,
    expiry,
    strike,
    days_to_expiry: null,
    call_contract_id: `c-${expiry}-${strike}`,
    put_contract_id: `p-${expiry}-${strike}`,
    call_midpoint: callPx,
    put_midpoint: putPx,
    call_mark_price: null,
    put_mark_price: null,
    call_price: callPx,
    put_price: putPx,
    call_price_source: "midpoint",
    put_price_source: "midpoint",
    call_implied_volatility: callIv,
    put_implied_volatility: putIv,
    blended_implied_volatility: (callIv + putIv) / 2,
    call_delta: null,
    put_delta: null,
    call_open_interest: 10,
    put_open_interest: 10,
    call_volume: 1,
    put_volume: 1,
    straddle_midpoint: callPx + putPx,
    synthetic_forward_price: null,
    implied_move_pct: (callPx + putPx) / 163,
    call_put_parity_gap: null,
  };
}

function surface(overrides: Partial<IvSurface> = {}): IvSurface {
  const expiries = overrides.expiries ?? ["20261021", "20261023", "20261030", "20261120", "20270219"];
  return {
    symbol: "USO",
    timestamp: "2026-10-21T10:50:00Z",
    retrieved_at: "2026-10-21T10:50:01Z",
    snapshot_available: true,
    spot: 163,
    expiries,
    strikes: [155, 163, 171],
    iv_grid: [
      [0.7, 0.563, 0.9],
      [0.6, 0.52, 0.62],
      [0.5, 0.48, 0.49],
      [0.48, 0.47, 0.47],
      [0.47, 0.469, 0.46],
    ].slice(0, expiries.length),
    delayed: false,
    points: 15,
    warnings: [],
    messages: [],
    source_provider: "ibkr",
    origin: "gamma.iv.surface.ibkr",
    transformation_note: "test",
    freshness_label: "stale",
    market_session: "closed",
    collection: null,
    quality: null,
    pairs: [
      pair("20261021", 163, 0.14, 0.986, 0.75, 0.6),
      pair("20261021", 171, 0.9, 0.9, 0.07, 8.1),
      pair("20261120", 163, 0.47, 0.47, 8.4, 8.2),
      pair("20261120", 171, 0.47, 0.47, 5.0, 12.6),
    ],
    ...overrides,
  };
}

describe("GUA-20261021-10 headline expiry", () => {
  it("skips the same-day and next-days expiries for the headline but keeps them in the chain", () => {
    const loaded = surface();
    const stats = deriveSurfaceStats(loaded, AUDIT_NOW);

    expect(HEADLINE_MIN_DTE).toBe(7);
    expect(stats.frontExpiry).toBe("20261030");
    expect(stats.frontExpiryDte).toBe(9);
    expect(stats.frontAtmIv).toBeCloseTo(0.48, 8);
    expect(stats.frontAtmIv).not.toBeCloseTo(0.563, 3);
    expect(stats.skippedExpiries).toEqual(["20261021", "20261023"]);
    expect(stats.termSlope).toBeCloseTo(0.469 - 0.48, 8);
    expect(describeHeadlineExpiry(stats)).toContain("Skipped 2026/10/21, 2026/10/23; still listed in the chain.");

    // La cadena 0D sigue disponible en cuanto se elige explícitamente.
    expect(deriveChainRows(loaded, "20261021").map((row) => row.strike)).toEqual([163, 171]);
    expect(deriveOverviewSnapshot(loaded, null, AUDIT_NOW).selectedExpiry).toBe("20261030");
    expect(deriveOverviewSnapshot(loaded, "20261021", AUDIT_NOW).selectedExpiry).toBe("20261021");
  });

  it("falls back to the shortest non-same-day expiry and skips 1D when the session is closed", () => {
    const shortOnly = { expiries: ["20261021", "20261022", "20261024"] };

    expect(selectHeadlineExpiry(surface({ ...shortOnly, market_session: "closed" }), AUDIT_NOW)).toMatchObject({
      expiry: "20261024",
      rule: "shortest_tradable",
      skippedExpiries: ["20261021", "20261022"],
    });
    expect(selectHeadlineExpiry(surface({ ...shortOnly, market_session: "regular" }), AUDIT_NOW)).toMatchObject({
      expiry: "20261022",
      rule: "shortest_tradable",
    });
    const onlyToday = selectHeadlineExpiry(surface({ expiries: ["20261021"] }), AUDIT_NOW);
    expect(onlyToday).toMatchObject({ expiry: "20261021", rule: "front_only", skippedExpiries: [] });
  });

  it("labels a closed-session snapshot as stale, never live", () => {
    const badge = toProvenanceBadge(surface(), { qualityLabel: "closed · last session" });
    expect(badge.state).toBe("stale");
    expect(badge.state).not.toBe("live");
  });
});

describe("GUA-20261021-10 strategy template horizon", () => {
  it("defaults templates to the first expiry with at least 30 DTE", () => {
    const loaded = surface();
    const horizon = defaultStrategyExpiry(loaded, AUDIT_NOW);

    expect(STRATEGY_TEMPLATE_MIN_DTE).toBe(30);
    expect(horizon).toBe("20261120");
    const active = selectedExpiryForSurface(loaded, null, horizon);
    const built = buildStrategyTemplateLegs("call_spread", deriveChainRows(loaded, active), loaded.spot);
    expect(built.legs.map((leg) => [leg.expiry, leg.strike, leg.side])).toEqual([
      ["20261120", 163, "long"],
      ["20261120", 171, "short"],
    ]);
  });

  it("uses the closest available expiry when none reaches the horizon and keeps explicit choices", () => {
    const short = surface({ expiries: ["20261021", "20261030", "20261113"] });

    expect(defaultStrategyExpiry(short, AUDIT_NOW)).toBe("20261113");
    expect(selectedExpiryForSurface(short, "20261021", "20261113")).toBe("20261021");
    expect(selectedExpiryForSurface(short, "29991231", "20261113")).toBe("20261113");
    expect(defaultStrategyExpiry(surface({ expiries: [] }), AUDIT_NOW)).toBeNull();
  });
});

describe("GUA-20261021-10 net theta aggregation", () => {
  const flat = surface({
    spot: 100,
    expiries: ["20261120"],
    strikes: [95, 100, 105],
    iv_grid: [[0.2, 0.2, 0.2]],
  });
  const leg = (strike: number, side: StrategyLeg["side"], quantity = 1, expiry = "20261120"): StrategyLeg => ({
    id: `${side}-${strike}`,
    optionType: "call",
    side,
    expiry,
    strike,
    premium: 1,
    quantity,
  });

  it("sums per-share daily theta with long minus short and quantity weights", () => {
    const years = 30 / 365;
    const longAtm = blackScholesGreeks("call", 100, 100, years, 0.2);
    const shortWing = blackScholesGreeks("call", 100, 105, years, 0.2);

    const spread = deriveStrategyGreeks([leg(100, "long"), leg(105, "short")], flat, AUDIT_NOW)!;
    expect(spread.theta).toBeCloseTo(longAtm.theta - shortWing.theta, 10);
    // Un call spread largo con IV plana pierde valor temporal.
    expect(spread.theta).toBeLessThan(0);
    // Theta por acción y por día natural: -S·φ(d1)·σ / (2√T) / 365 ≈ -0.0381 $/día (ATM 30D, 20 % vol).
    expect(longAtm.theta).toBeCloseTo(-0.0381, 4);
    expect(spread.shortDatedLegCount).toBe(0);

    const doubled = deriveStrategyGreeks([leg(100, "long", 2), leg(105, "short", 2)], flat, AUDIT_NOW)!;
    expect(doubled.theta).toBeCloseTo(2 * spread.theta, 10);
    expect(deriveStrategyGreeks([leg(105, "short")], flat, AUDIT_NOW)!.theta).toBeCloseTo(-shortWing.theta, 10);
  });

  it("explains the audit's positive theta: a stale 0D chain with an inflated wing IV", () => {
    // Cadena 0D del audit: IV del ATM 56.3 % (media de 14 % y 98.6 %), ala 171 inflada.
    const stale = surface({ spot: 163, expiries: ["20261021"], strikes: [163, 171], iv_grid: [[0.563, 1.1]] });
    const greeks = deriveStrategyGreeks([leg(163, "long", 1, "20261021"), leg(171, "short", 1, "20261021")], stale, AUDIT_NOW)!;

    expect(greeks.theta).toBeGreaterThan(0);
    expect(greeks.shortDatedLegCount).toBe(2);
  });
});

describe("GUA-20261021-10 empty symbol state", () => {
  const status: SystemStatus = {
    healthy: true,
    app_name: "Gamma",
    backend: "test",
    mock_mode: false,
    base_currency: "USD",
    market_data_mode: "auto",
    connection: { connected: true, status_text: "Connected", action_text: "Disconnect", action_enabled: true, active_account: "TEST" },
    cached_symbols: [],
  };
  // Un backend anterior informaba "SPY" como símbolo activo de una sesión inactiva.
  const idleWithLegacySymbol: IvSessionStatus = {
    running: false,
    status_text: "Idle",
    active_symbol: "SPY",
    market_data_mode: "auto",
    messages: [],
    surface: surface({ snapshot_available: false, spot: null, expiries: [], strikes: [], iv_grid: [], points: 0, pairs: [] }),
  };

  it("prompts for a symbol instead of naming SPY", () => {
    const [message] = deriveIvSurfaceAlerts({ result: null, session: idleWithLegacySymbol, status, requestedSymbol: "  " });

    expect(message).toBe("Enter an underlying symbol and load the surface to see its options chain.");
    expect(message).not.toContain("SPY");
  });

  it("does not name SPY when disconnected without a symbol", () => {
    const [message] = deriveIvSurfaceAlerts({
      result: null,
      session: idleWithLegacySymbol,
      status: { ...status, connection: { ...status.connection, connected: false } },
      requestedSymbol: "",
    });

    expect(message).toContain("enter an underlying symbol");
    expect(message).not.toContain("SPY");
  });
});
