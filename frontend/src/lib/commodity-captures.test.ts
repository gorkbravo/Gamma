import { describe, expect, it } from "vitest";
import { curveNodeQuality, commodityCaptureTime, spreadPointNote, type CommoditySpreadHistory } from "./commodity-captures";
import type { CommodityCurveNode } from "./api/types";

describe("retained commodity quote evidence", () => {
  it("shows offset-free provider datetimes as UTC and converts explicit offsets correctly", () => {
    expect(commodityCaptureTime("2026-10-06T17:17:30")).toBe("2026-10-06 17:17:30 UTC");
    expect(commodityCaptureTime("2026-10-06T17:17:30+02:00")).toBe("2026-10-06 15:17:30 UTC");
  });
  it("distinguishes a zero price, missing quote, absent contract and unknown quality", () => {
    const node = { price: 0, source_provider: "ibkr" } as CommodityCurveNode;
    expect(curveNodeQuality(node)).toContain("quality unknown");
    expect(curveNodeQuality(node)).not.toContain("unavailable");
    expect(curveNodeQuality({ ...node, price: null })).toBe("Quote unavailable");
    expect(curveNodeQuality(null)).toBe("Absent");
  });
  it("keeps cached, delayed and prior-close evidence distinct from a fresh snapshot", () => {
    const node = { price: 70, source_provider: "ibkr_cached", quote_field: "close", delayed: true, freshness_label: "cached" } as CommodityCurveNode;
    const quality = curveNodeQuality(node);
    expect(quality).toContain("cached"); expect(quality).toContain("delayed"); expect(quality).toContain("close");
    expect(quality).not.toContain("live");
  });
});

// Revisión 2026-10-15: un spread con patas de distinta evidencia ya no se presenta como observado sin más.
describe("calendar spread point notes", () => {
  const point = { capture_id: "a", captured_at: "2026-10-02T15:00:00Z", as_of: "2026-10-02T15:00:00Z", left: null, right: null,
    value: 1, status: "mixed_quote_evidence" } as CommoditySpreadHistory["points"][number];
  it("names the leg evidence that differs and the superseded saves", () => {
    const note = spreadPointNote({ ...point, evidence_mismatch: ["quote_field", "freshness_label"], superseded_capture_ids: ["b"] });
    expect(note).toBe("Legs differ in quote field, freshness label · Latest of 2 saves at this observation time");
  });
  it("stays empty for a plain observed point and for records saved before the fields existed", () => {
    expect(spreadPointNote({ ...point, status: "observed", evidence_mismatch: [], superseded_capture_ids: [] })).toBe("");
    expect(spreadPointNote(point)).toBe("");
  });
});
