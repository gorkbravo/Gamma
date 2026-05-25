import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import HeroPriceChart, {
  canRenderHeroCandlesticks,
  readHeroPriceChartSettings,
  syncHeroPriceSettingsStorage,
  writeHeroPriceChartSettings,
  type HeroPriceSettingsStorage
} from "./HeroPriceChart.svelte";

describe("HeroPriceChart", () => {
  it("server-renders settings controls for close-only points", () => {
    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "close-only",
        points: [
          { time: 1, close: 10 },
          { time: 2, close: 11 }
        ]
      }
    });

    expect(body).toContain('aria-label="Hero chart settings"');
    expect(body).toContain("Chart Settings");
    expect(body).toContain("Candles unavailable");
    expect(body).toContain("Volume unavailable");
  });

  it("server-renders volume overlay control for volume points", () => {
    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "volume",
        points: [
          { time: 1, close: 10, volume: 100 },
          { time: 2, close: 11, volume: 120 }
        ]
      }
    });

    expect(body).toContain("Volume overlay");
    expect(body).not.toContain("Volume unavailable");
  });

  it("server-renders candle control when every point has OHLC", () => {
    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "ohlcv",
        points: [
          { time: 1, open: 9, high: 11, low: 8, close: 10, volume: 100 },
          { time: 2, open: 10, high: 12, low: 9, close: 11, volume: 120 }
        ]
      }
    });

    expect(body).toContain("Candles");
    expect(body).not.toContain("Candles unavailable");
    expect(body).toContain("Volume overlay");
  });

  it("loads settings for a changed chart key without writing old settings to the new key", () => {
    const writes: Array<[string, unknown]> = [];
    const next = syncHeroPriceSettingsStorage({
      storageKey: "gamma.heroPriceChart.next",
      loadedStorageKey: "gamma.heroPriceChart.previous",
      settings: { priceStyle: "candlestick", volumeOverlay: true, movingAverages: [20] },
      readSettings: () => ({ priceStyle: "line", volumeOverlay: false, movingAverages: [50] }),
      writeSettings: (key, value) => writes.push([key, value])
    });

    expect(next).toEqual({
      loadedStorageKey: "gamma.heroPriceChart.next",
      settings: { priceStyle: "line", volumeOverlay: false, movingAverages: [50] }
    });
    expect(writes).toEqual([]);
  });

  it("falls back when storage reads fail and no-ops when storage writes fail", () => {
    const storage: HeroPriceSettingsStorage = {
      getItem() {
        throw new Error("blocked");
      },
      setItem() {
        throw new Error("quota");
      }
    };

    expect(readHeroPriceChartSettings(storage, "gamma.heroPriceChart.blocked")).toEqual({
      priceStyle: "line",
      volumeOverlay: false,
      movingAverages: []
    });
    expect(() =>
      writeHeroPriceChartSettings(storage, "gamma.heroPriceChart.blocked", {
        priceStyle: "candlestick",
        volumeOverlay: true,
        movingAverages: [20]
      })
    ).not.toThrow();
  });

  it("marks candles unavailable for mixed OHLC and close-only points", () => {
    const { body } = render(HeroPriceChart, {
      props: {
        chartKey: "mixed",
        points: [
          { time: 1, open: 9, high: 11, low: 8, close: 10 },
          { time: 2, close: 11 }
        ]
      }
    });

    expect(canRenderHeroCandlesticks([{ time: 1, open: 9, high: 11, low: 8, close: 10 }, { time: 2, close: 11 }])).toBe(
      false
    );
    expect(body).toContain("Candles unavailable");
  });
});
