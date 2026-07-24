import { describe, expect, it } from "vitest";

import {
  normalizeProvenanceState,
  provenanceTitle,
  provenanceTone,
  shortProvenanceTimestamp,
  toProvenanceBadge
} from "./provenance";

describe("normalizeProvenanceState", () => {
  it("maps live-family aliases to live", () => {
    expect(normalizeProvenanceState("live")).toBe("live");
    expect(normalizeProvenanceState("fresh")).toBe("live");
    expect(normalizeProvenanceState("current_public_api")).toBe("live");
    expect(normalizeProvenanceState("real time")).toBe("live");
  });

  it("keeps cached, sample, and synthetic distinct", () => {
    expect(normalizeProvenanceState("cached")).toBe("cached");
    expect(normalizeProvenanceState("sample")).toBe("sample");
    expect(normalizeProvenanceState("mock")).toBe("sample");
    expect(normalizeProvenanceState("synthetic")).toBe("synthetic");
  });

  it("maps unavailable-family aliases and falls back to unknown", () => {
    expect(normalizeProvenanceState("n/a")).toBe("unavailable");
    expect(normalizeProvenanceState("not_available")).toBe("unavailable");
    expect(normalizeProvenanceState(null)).toBe("unknown");
    expect(normalizeProvenanceState("weird-vendor-string")).toBe("unknown");
  });
});

describe("provenanceTone", () => {
  it("uses positive only for live and negative only for unavailable", () => {
    expect(provenanceTone("live")).toBe("positive");
    expect(provenanceTone("unavailable")).toBe("negative");
    expect(provenanceTone("delayed")).toBe("warning");
    expect(provenanceTone("sample")).toBe("warning");
    expect(provenanceTone("derived")).toBe("neutral");
    expect(provenanceTone("unknown")).toBe("neutral");
  });
});

describe("toProvenanceBadge", () => {
  it("normalizes a backend payload shape", () => {
    const badge = toProvenanceBadge({
      source_provider: "yfinance",
      freshness_label: "delayed",
      retrieved_at: "2026-06-12T10:30:00Z",
      transformation_note: "Adjusted close normalized to daily returns.",
      warnings: ["Unofficial provider."]
    });
    expect(badge.provider).toBe("yfinance");
    expect(badge.state).toBe("delayed");
    expect(badge.retrievedAt).toBe("2026-06-12T10:30:00Z");
    expect(badge.transformationNote).toContain("Adjusted close");
    expect(badge.warnings).toEqual(["Unofficial provider."]);
  });

  it("reads nested freshness status objects and provider fallback", () => {
    const badge = toProvenanceBadge({
      provider: "polymarket",
      freshness: { status: "stale" }
    });
    expect(badge.provider).toBe("polymarket");
    expect(badge.state).toBe("stale");
  });

  it("supports overrides and handles null input", () => {
    const empty = toProvenanceBadge(null);
    expect(empty.provider).toBeNull();
    expect(empty.state).toBe("unknown");
    const forced = toProvenanceBadge(null, { provider: "ibkr", state: "live", qualityLabel: "official" });
    expect(forced.provider).toBe("ibkr");
    expect(forced.state).toBe("live");
    expect(forced.qualityLabel).toBe("official");
  });
});

describe("shortProvenanceTimestamp", () => {
  it("returns a date for non-today timestamps and null for garbage", () => {
    expect(shortProvenanceTimestamp("2025-01-15T10:00:00Z")).toBe("2025-01-15");
    expect(shortProvenanceTimestamp("not-a-date")).toBeNull();
    expect(shortProvenanceTimestamp(null)).toBeNull();
  });

  it("returns a clock time for today's timestamps", () => {
    const value = shortProvenanceTimestamp(new Date().toISOString());
    expect(value).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("provenanceTitle", () => {
  it("includes provider, state, timestamps, note, and capped warnings", () => {
    const title = provenanceTitle(
      toProvenanceBadge({
        source_provider: "sec_edgar",
        freshness_label: "historical",
        retrieved_at: "2026-06-01T00:00:00Z",
        transformation_note: "Normalized from 10-K filing.",
        warnings: ["a", "b", "c", "d", "e", "f"]
      }, { qualityLabel: "filing-backed" })
    );
    expect(title).toContain("Provider: sec_edgar");
    expect(title).toContain("State: historical");
    expect(title).toContain("Quality: filing-backed");
    expect(title).toContain("Retrieved: 2026-06-01T00:00:00Z");
    expect(title).toContain("Transformation: Normalized from 10-K filing.");
    expect(title).toContain("+2 more warnings");
  });

  it("surfaces unrecognized raw labels in the state line", () => {
    const title = provenanceTitle(toProvenanceBadge({ freshness_label: "vendor_special" }));
    expect(title).toContain("State: unknown (reported: vendor_special)");
  });
});
