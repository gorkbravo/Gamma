import { describe, expect, it } from "vitest";
import {
  buildHeroPriceChartSeries,
  computeSimpleMovingAverage,
  defaultHeroPriceChartSettings,
  heroPriceChartAvailability,
  heroPricePointFromApiPoint,
  normalizeHeroPriceChartSettings,
  normalizeHeroPricePoints
} from "./hero-price-chart";

describe("heroPriceChartAvailability", () => {
  it("detects close-only data", () => {
    expect(heroPriceChartAvailability([{ time: 1, close: 10 }])).toEqual({
      hasClose: true,
      hasOhlc: false,
      hasVolume: false
    });
  });

  it("detects volume-only data without OHLC", () => {
    expect(heroPriceChartAvailability([{ time: 1, volume: 100 }])).toEqual({
      hasClose: false,
      hasOhlc: false,
      hasVolume: true
    });
  });

  it("detects OHLCV data", () => {
    expect(heroPriceChartAvailability([{ time: 1, open: 9, high: 11, low: 8, close: 10, volume: 100 }])).toEqual({
      hasClose: true,
      hasOhlc: true,
      hasVolume: true
    });
  });
});

describe("computeSimpleMovingAverage", () => {
  it("emits values only after the full window exists", () => {
    expect(
      computeSimpleMovingAverage(
        [
          { time: 1, close: 10 },
          { time: 2, close: 11 },
          { time: 3, close: 12 }
        ],
        2
      )
    ).toEqual([
      { time: 2, value: 10.5 },
      { time: 3, value: 11.5 }
    ]);
  });
});

describe("normalizeHeroPricePoints", () => {
  it("filters invalid rows, sorts by time, and keeps the latest duplicate time", () => {
    expect(
      normalizeHeroPricePoints([
        { time: 3, close: 12 },
        { time: Number.NaN, close: 99 },
        { time: 4, close: Number.NaN },
        { time: 2, close: 10 },
        { time: 2, close: 11 },
        { time: 1, close: 9 }
      ])
    ).toEqual([
      { time: 1, close: 9 },
      { time: 2, close: 11 },
      { time: 3, close: 12 }
    ]);
  });
});

describe("heroPricePointFromApiPoint", () => {
  it("maps optional OHLCV fields from a generic API price point", () => {
    expect(
      heroPricePointFromApiPoint({
        timestamp: "2026-03-01T00:00:00Z",
        value: 104,
        open: 102,
        high: 105,
        low: 101,
        close: 104,
        volume: 1400
      })
    ).toEqual({
      time: 1772323200,
      close: 104,
      open: 102,
      high: 105,
      low: 101,
      volume: 1400
    });
  });

  it("uses fundamentals price when close is omitted", () => {
    expect(
      heroPricePointFromApiPoint({
        timestamp: "2026-03-01T00:00:00Z",
        price: 190,
        volume: 1200
      })
    ).toEqual({
      time: 1772323200,
      close: 190,
      volume: 1200
    });
  });
});

describe("normalizeHeroPriceChartSettings", () => {
  it("returns fresh default moving average arrays", () => {
    const normalized = normalizeHeroPriceChartSettings(null);
    normalized.movingAverages.push(20);

    expect(defaultHeroPriceChartSettings.movingAverages).toEqual([]);
    expect(normalizeHeroPriceChartSettings(null).movingAverages).toEqual([]);
  });

  it("normalizes invalid persisted settings while preserving valid moving averages and volume", () => {
    expect(
      normalizeHeroPriceChartSettings({
        priceStyle: "bars",
        volumeOverlay: true,
        movingAverages: [10, 20, 20, 200, "50"]
      })
    ).toEqual({
      priceStyle: "line",
      volumeOverlay: true,
      movingAverages: [20, 200]
    });
  });
});

describe("buildHeroPriceChartSeries", () => {
  it("falls back to line for requested candles without OHLC and keeps moving average overlay", () => {
    const series = buildHeroPriceChartSeries(
      [
        { time: 1, close: 10 },
        { time: 2, close: 11 },
        { time: 3, close: 12 }
      ],
      { priceStyle: "candlestick", volumeOverlay: false, movingAverages: [20] }
    );

    expect(series.map((item) => [item.id, item.type])).toEqual([
      ["price", "line"],
      ["ma-20", "line"]
    ]);
  });

  it("builds candlestick and histogram series for OHLCV data", () => {
    const series = buildHeroPriceChartSeries(
      [{ time: 1, open: 9, high: 11, low: 8, close: 10, volume: 100 }],
      { priceStyle: "candlestick", volumeOverlay: true, movingAverages: [] }
    );

    expect(series.map((item) => [item.id, item.type])).toEqual([
      ["price", "candlestick"],
      ["volume", "histogram"]
    ]);
  });

  it("puts volume histograms on the volume price scale", () => {
    const series = buildHeroPriceChartSeries(
      [{ time: 1, open: 9, high: 11, low: 8, close: 10, volume: 100 }],
      { priceStyle: "candlestick", volumeOverlay: true, movingAverages: [] }
    );

    expect(series.find((item) => item.id === "volume")?.priceScaleId).toBe("volume");
  });

  it("deduplicates moving average windows before building overlay series", () => {
    const series = buildHeroPriceChartSeries(
      [
        { time: 1, close: 10 },
        { time: 2, close: 11 },
        { time: 3, close: 12 }
      ],
      { priceStyle: "line", volumeOverlay: false, movingAverages: [20, 20] }
    );

    expect(series.filter((item) => item.id === "ma-20")).toHaveLength(1);
  });
});
