import { describe, expect, it } from "vitest";
import type { UTCTimestamp } from "lightweight-charts";
import { normalizeChartData, parseApiTimestampToUtcSeconds, weekOverWeekChange } from "./chart-data";

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
      { time: 30 as UTCTimestamp, value: 3 },
      { time: 10 as UTCTimestamp, value: 1 },
      { time: 20 as UTCTimestamp, value: 2 },
      { time: 20 as UTCTimestamp, value: 4 },
    ]);

    expect(normalized).toEqual([
      { time: 10 as UTCTimestamp, value: 1 },
      { time: 20 as UTCTimestamp, value: 4 },
      { time: 30 as UTCTimestamp, value: 3 },
    ]);
  });
});

describe("weekOverWeekChange", () => {
  it("compares the latest value with the one five sessions earlier", () => {
    expect(weekOverWeekChange([100, 101, 102, 103, 104, 110])).toBeCloseTo(0.1);
    expect(weekOverWeekChange([90, 100, null, 101, 102, 103, 104, 99])).toBeCloseTo(-0.01);
  });

  it("returns null without enough history or with a zero base", () => {
    expect(weekOverWeekChange([1, 2, 3, 4, 5])).toBeNull();
    expect(weekOverWeekChange([0, 1, 2, 3, 4, 5])).toBeNull();
  });
});
