import { describe, expect, it } from "vitest";
import { normalizeChartData, parseApiTimestampToUtcSeconds } from "./chart-data";

describe("parseApiTimestampToUtcSeconds", () => {
  it("treats timezone-less API timestamps as UTC", () => {
    expect(parseApiTimestampToUtcSeconds("2026-03-29T02:00:35")).toBe(
      parseApiTimestampToUtcSeconds("2026-03-29T02:00:35Z"),
    );
  });
});

describe("normalizeChartData", () => {
  it("sorts ascending and keeps the last value for duplicate timestamps", () => {
    const normalized = normalizeChartData([
      { time: 30, value: 3 },
      { time: 10, value: 1 },
      { time: 20, value: 2 },
      { time: 20, value: 4 },
    ]);

    expect(normalized).toEqual([
      { time: 10, value: 1 },
      { time: 20, value: 4 },
      { time: 30, value: 3 },
    ]);
  });
});
