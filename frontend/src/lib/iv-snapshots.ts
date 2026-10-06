import type { IvSurface } from "./api/types";
import { getJson, postJson } from "./api/client";

export interface IvSnapshot {
  snapshot_id: string;
  captured_at: string;
  surface: IvSurface;
}
export interface IvSnapshotSummary {
  snapshot_id: string;
  captured_at: string;
  symbol: string;
  timestamp: string;
  source_provider: string;
  freshness_label: string;
  points: number;
}
export const listIvSnapshots = (symbol: string) =>
  getJson<{ snapshots: IvSnapshotSummary[]; warnings: string[] }>(`/iv/snapshots?symbol=${encodeURIComponent(symbol)}`);
export const readIvSnapshot = (id: string) => getJson<IvSnapshot>(`/iv/snapshots/${encodeURIComponent(id)}`);
export const captureIvSnapshot = (surface: IvSurface) => postJson<IvSnapshot>("/iv/snapshots", surface);

function observations(surface: IvSurface, expiry: string): Map<number, number> {
  const values = new Map<number, number>();
  // Pair IVs are collected observations even when the display grid uses SSVI.
  for (const pair of surface.pairs ?? []) {
    const iv = pair.blended_implied_volatility;
    if (pair.expiry === expiry && iv != null && Number.isFinite(iv) && iv > 0) values.set(pair.strike, iv);
  }
  const row = surface.expiries.indexOf(expiry);
  surface.strikes.forEach((strike, column) => {
    const iv = surface.iv_grid[row]?.[column];
    if (!values.has(strike) && surface.cell_sources?.[row]?.[column] === "observed" && Number.isFinite(iv) && iv > 0) {
      values.set(strike, iv);
    }
  });
  return values;
}

export interface IvComparisonRow {
  expiry: string;
  strike: number | null;
  putStrike: number | null;
  callStrike: number | null;
  before: number | null;
  after: number | null;
  change: number | null;
  putSkewBefore: number | null;
  putSkewAfter: number | null;
  putSkewChange: number | null;
  callSkewBefore: number | null;
  callSkewAfter: number | null;
  callSkewChange: number | null;
}
const difference = (a: number | null, b: number | null) => a != null && b != null ? b - a : null;
const skew = (values: Map<number, number>, strike: number | null, atm: number | null) =>
  strike != null && atm != null && values.has(strike) ? values.get(strike)! - atm : null;

export function compareIvSnapshots(before: IvSurface | null, after: IvSurface | null): { rows: IvComparisonRow[]; warnings: string[] } {
  if (!before || !after) return { rows: [], warnings: [] };
  if (before.symbol !== after.symbol) return { rows: [], warnings: ["Select captures of the same underlying."] };
  const warnings: string[] = [];
  if (before.source_provider !== after.source_provider || before.freshness_label !== after.freshness_label || before.delayed !== after.delayed) {
    warnings.push("The captures have different provider or data-mode labels; check their evidence before interpreting changes.");
  }
  const rows = before.expiries.filter((expiry) => after.expiries.includes(expiry)).sort().map((expiry) => {
    const oldValues = observations(before, expiry), newValues = observations(after, expiry);
    const strikes = [...oldValues.keys()].sort((a, b) => a - b);
    const strike = before.spot != null ? [...strikes].sort((a, b) => Math.abs(a - before.spot!) - Math.abs(b - before.spot!))[0] ?? null : null;
    const putStrike = strike == null ? null : strikes.filter((s) => s < strike)[0] ?? null;
    const callStrike = strike == null ? null : strikes.filter((s) => s > strike).at(-1) ?? null;
    const oldAtm = strike == null ? null : oldValues.get(strike) ?? null;
    const newAtm = strike == null ? null : newValues.get(strike) ?? null;
    const putBefore = skew(oldValues, putStrike, oldAtm), putAfter = skew(newValues, putStrike, newAtm);
    const callBefore = skew(oldValues, callStrike, oldAtm), callAfter = skew(newValues, callStrike, newAtm);
    return { expiry, strike, putStrike, callStrike, before: oldAtm, after: newAtm, change: difference(oldAtm, newAtm),
      putSkewBefore: putBefore, putSkewAfter: putAfter, putSkewChange: difference(putBefore, putAfter),
      callSkewBefore: callBefore, callSkewAfter: callAfter, callSkewChange: difference(callBefore, callAfter) };
  });
  if (before.expiries.length !== rows.length || after.expiries.length !== rows.length) warnings.push("Only common expiry dates are compared; unmatched expiries are excluded.");
  if (!rows.length) warnings.push("These captures have no common expiry dates.");
  if (rows.some((row) => row.change == null || row.putSkewChange == null || row.callSkewChange == null)) warnings.push("Some exact observed strikes are missing. Their changes are unavailable; fitted cells are excluded.");
  return { rows, warnings };
}
