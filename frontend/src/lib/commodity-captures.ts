import type { CommodityInstrument, CommodityCurveSnapshot, CommodityCurveNode, CommodityFuturesContract, CommodityCoverageMetadata } from "./api/types";

export interface CommodityCapturePayload { instrument: CommodityInstrument; curve: CommodityCurveSnapshot; coverage: CommodityCoverageMetadata; }
// mode separa capturas de muestra (mock) y en vivo; mode_inferred marca registros antiguos clasificados por su evidencia.
export interface CommodityCurveCapture { version: number; id: string; captured_at: string; mode?: "live" | "mock"; mode_inferred?: boolean; payload: CommodityCapturePayload; checksum: string; }
export interface CommodityCurveComparison {
  baseline: CommodityCurveCapture; comparison: CommodityCurveCapture; unit: string; currency: string;
  rows: Array<{ contract_id: string; contract: CommodityFuturesContract; baseline: CommodityCurveNode | null; comparison: CommodityCurveNode | null; change: number | null; status: string }>;
  warnings: string[];
}
export interface CommodityCalendarSpread {
  id: string; captured_at: string; mode?: "live" | "mock"; mode_inferred?: boolean; payload: { label: string; instrument_id: string; unit: string; currency: string;
    left_contract: CommodityFuturesContract; right_contract: CommodityFuturesContract; source_capture_id: string; formula: string; };
}
export interface CommoditySpreadHistory {
  spread: CommodityCalendarSpread;
  points: Array<{ capture_id: string; captured_at: string; as_of: string; left: CommodityCurveNode | null; right: CommodityCurveNode | null; value: number | null; status: string;
    /** Campos de evidencia que difieren entre patas (status mixed_quote_evidence). */
    evidence_mismatch?: string[];
    /** Capturas anteriores con el mismo as_of a las que sustituye este punto. */
    superseded_capture_ids?: string[] }>;
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

/** Texto de la celda de estado de un punto de spread, con la evidencia que lo degrada o sustituye. */
export function spreadPointNote(point: CommoditySpreadHistory["points"][number]): string {
  const notes: string[] = [];
  if (point.evidence_mismatch?.length) notes.push(`Legs differ in ${point.evidence_mismatch.join(", ").replaceAll("_", " ")}`);
  if (point.superseded_capture_ids?.length) notes.push(`Latest of ${point.superseded_capture_ids.length + 1} saves at this observation time`);
  return notes.join(" · ");
}
