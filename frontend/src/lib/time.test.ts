import { describe, expect, it } from "vitest";

import { apiInstantDate, parseApiInstant } from "./time";

describe("API instant parsing", () => {
  // Regresión GUA-20261021-3: un `retrieved_at` naive es UTC, no hora local.
  it("reads offset-less API instants as UTC", () => {
    expect(parseApiInstant("2026-10-21T10:30:52.391105")).toBe(Date.UTC(2026, 9, 21, 10, 30, 52, 391));
    expect(parseApiInstant("2026-10-21T10:32:58")).toBe(Date.UTC(2026, 9, 21, 10, 32, 58));
    expect(parseApiInstant("2026-10-21 10:32")).toBe(Date.UTC(2026, 9, 21, 10, 32));
  });

  it("keeps explicit zones and plain dates as they are", () => {
    expect(parseApiInstant("2026-10-21T12:38:17+02:00")).toBe(Date.UTC(2026, 9, 21, 10, 38, 17));
    expect(parseApiInstant("2026-10-21T10:38:17Z")).toBe(Date.UTC(2026, 9, 21, 10, 38, 17));
    expect(parseApiInstant("2026-10-14")).toBe(Date.parse("2026-10-14"));
  });

  it("returns NaN or null for missing and unparseable values", () => {
    expect(parseApiInstant(null)).toBeNaN();
    expect(parseApiInstant("not a time")).toBeNaN();
    expect(apiInstantDate(undefined)).toBeNull();
    expect(apiInstantDate("2026-10-21T10:30:52")?.toISOString()).toBe("2026-10-21T10:30:52.000Z");
  });
});
