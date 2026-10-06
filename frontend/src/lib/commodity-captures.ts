import type { CommodityInstrument, CommodityCurveSnapshot, CommodityCurveNode, CommodityFuturesContract, CommodityCoverageMetadata } from "./api/types";

export interface CommodityCapturePayload { instrument: CommodityInstrument; curve: CommodityCurveSnapshot; coverage: CommodityCoverageMetadata; }
export interface CommodityCurveCapture { version: number; id: string; captured_at: string; payload: CommodityCapturePayload; checksum: string; }
export interface CommodityCurveComparison {
  baseline: CommodityCurveCapture; comparison: CommodityCurveCapture; unit: string; currency: string;
  rows: Array<{ contract_id: string; contract: CommodityFuturesContract; baseline: CommodityCurveNode | null; comparison: CommodityCurveNode | null; change: number | null; status: string }>;
  warnings: string[];
}
export interface CommodityCalendarSpread {
  id: string; captured_at: string; payload: { label: string; instrument_id: string; unit: string; currency: string;
    left_contract: CommodityFuturesContract; right_contract: CommodityFuturesContract; source_capture_id: string; formula: string; };
}
export interface CommoditySpreadHistory {
  spread: CommodityCalendarSpread;
  points: Array<{ capture_id: string; captured_at: string; as_of: string; left: CommodityCurveNode | null; right: CommodityCurveNode | null; value: number | null; status: string }>;
  warnings: string[];
}

export function curveNodeQuality(node: CommodityCurveNode | null | undefined): string {
  if (!node) return "Absent";
  if (node.price == null) return "Quote unavailable";
  return [node.source_provider || "unknown provider", node.freshness_label ?? "quality unknown",
    node.delayed === true ? "delayed" : null, node.quote_field].filter(Boolean).join(" · ");
}

export function captureLabel(capture: CommodityCurveCapture): string {
  return `${commodityCaptureTime(capture.payload.curve.as_of)} · ${[...new Set(capture.payload.curve.nodes.map(n => n.source_provider))].join("/")} · ${capture.id.slice(0, 6)}`;
}

export function commodityCaptureTime(value: string): string {
  // Gamma's provider datetimes without an offset are UTC, not browser-local time.
  const utc = value.includes("T") && !/(Z|[+-]\d{2}:\d{2})$/i.test(value) ? `${value}Z` : value;
  return `${new Date(utc).toISOString().replace("T", " ").slice(0, 19)} UTC`;
}
