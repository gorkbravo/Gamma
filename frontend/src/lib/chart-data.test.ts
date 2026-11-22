import { describe, expect, it } from "vitest";
import type { UTCTimestamp } from "lightweight-charts";
import {
  formatPercentAxisValue,
  normalizeChartData,
  percentAxisFormat,
  normalizeChartDataWithGaps,
  splitAtGaps,
  parseApiTimestampToUtcSeconds,
  weekOverWeekChange,
} from "./chart-data";

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

describe("normalizeChartDataWithGaps", () => {
  it("keeps a missing value as a break instead of dropping it", () => {
    const normalized = normalizeChartDataWithGaps([
      { time: 30 as UTCTimestamp, value: 3 },
      { time: 10 as UTCTimestamp, value: 1 },
      { time: 20 as UTCTimestamp, value: Number.NaN },
      { time: 40 as UTCTimestamp, value: Number.POSITIVE_INFINITY },
    ]);
    expect(normalized.map((point) => point.time)).toEqual([10, 20, 30, 40]);
    expect(Number.isNaN(normalized[1].value)).toBe(true);
    expect(Number.isNaN(normalized[3].value)).toBe(true);
    // La versión normal descarta los huecos: la línea los cruzaría.
    expect(normalizeChartData([{ time: 20 as UTCTimestamp, value: Number.NaN }])).toEqual([]);
  });
});

describe("splitAtGaps", () => {
  it("splits a series into runs so no line crosses a gap", () => {
    const { runs, gaps } = splitAtGaps([
      { time: 10 as UTCTimestamp, value: 1 },
      { time: 20 as UTCTimestamp, value: 2 },
      { time: 30 as UTCTimestamp, value: Number.NaN },
      { time: 40 as UTCTimestamp, value: 4 },
      { time: 50 as UTCTimestamp, value: Number.NaN },
    ]);
    expect(runs.map((run) => run.map((point) => point.time))).toEqual([[10, 20], [40]]);
    expect(gaps).toEqual([30, 50]);
    expect(splitAtGaps([])).toEqual({ runs: [], gaps: [] });
  });
});

describe("percentAxisFormat", () => {
  it("prints a percent series' own value (lightweight-charts' percent format did not)", () => {
    const format = percentAxisFormat(2.468);
    expect(format.type).toBe("custom");
    expect(format.minMove).toBe(0.01);
    expect(format.formatter(2.468)).toBe("2.47%");
    expect(format.formatter(0.6)).toBe("0.60%");
    expect(format.formatter(0.627)).toBe("0.63%");
    expect(format.formatter(-4)).toBe("−4.00%");
    expect(format.formatter(-0.001)).toBe("0.00%");
    expect(percentAxisFormat(123.4).formatter(123.45)).toBe("123.5%");
    expect(formatPercentAxisValue(Number.NaN)).toBe("");
  });
});
