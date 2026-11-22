// Shared test fixture: an intraday view with a delayed session, one gap point,
// one disconnection and a leg without a mark (I3d).
import type { IdeaIntradayView } from "./api/types";

export const INTRADAY_VIEW: IdeaIntradayView = {
  label: "Hypothetical, not executed",
  available: true,
  status: "recording",
  status_reason: null,
  tws_connected: true,
  session: "2026-11-10",
  sessions: ["2026-11-10", "2026-11-09"],
  reference: { session: "2026-11-09", net_return: -0.001 },
  summary: {
    as_of: "2026-11-10T15:25:00",
    today_return: 0.0123,
    net_return: 0.0113,
    intraday_drawdown: -0.004,
    quality: "delayed",
    qualities: ["delayed"],
    marks: 3,
    gaps: 1,
    segment: 1,
  },
  points: [
    { at: "2026-11-10T15:00:00", segment: 1, net_return: 0.01, gross_return: 0.011, today_return: 0.011, drawdown: 0, quality: "delayed", gap: false, state: "priced", missing: [], carried: [] },
    { at: "2026-11-10T15:05:00", segment: 1, net_return: null, gross_return: null, today_return: null, drawdown: null, quality: "delayed", gap: true, state: "gap", missing: ["MSFT"], carried: [] },
    { at: "2026-11-10T15:25:00", segment: 1, net_return: 0.0113, gross_return: 0.0123, today_return: 0.0123, drawdown: -0.004, quality: "delayed", gap: false, state: "priced", missing: [], carried: [] },
  ],
  gaps: [{ start: "2026-11-10T15:05:00", end: "2026-11-10T15:25:00", kind: "disconnected", reason: "Trader Workstation disconnected." }],
  legs: [
    { key: "equity:AAPL", label: "AAPL", price: 204, field: "delayedLast", md_type: 3, quality: "delayed", carried: false, reference_close: 200, move: 0.02, missing_reason: null },
    { key: "equity:MSFT", label: "MSFT", price: null, field: null, md_type: null, quality: null, carried: false, reference_close: 400, move: null, missing_reason: "No price for MSFT." },
  ],
  warnings: [],
  methodology: "Hypothetical, not executed. IBKR marks.",
  cadence_seconds: 300,
  closed_cadence_seconds: 3600,
  source_provider: "IBKR/TWS market-data snapshots",
  origin: "ibkr.reqMktData(snapshot)",
  transformation_note: null,
};
