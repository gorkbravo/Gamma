import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import HeroPriceChart from "./HeroPriceChart.svelte";

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
});
