import { describe, expect, it } from "vitest";
import { curveNodeQuality, commodityCaptureTime } from "./commodity-captures";
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
