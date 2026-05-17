import { describe, expect, it } from "vitest";
import {
  buildHeroPriceChartSeries,
  computeSimpleMovingAverage,
  heroPriceChartAvailability,
  normalizeHeroPriceChartSettings
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

describe("normalizeHeroPriceChartSettings", () => {
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
});
