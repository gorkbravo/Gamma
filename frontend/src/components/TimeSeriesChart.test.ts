import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

describe("TimeSeriesChart", () => {
  it("server-renders candlestick and histogram series metadata", () => {
    const series: ChartSeries[] = [
      {
        id: "price",
        label: "Price",
        color: "var(--accent)",
        type: "candlestick",
        data: [{ time: 1, open: 9, high: 11, low: 8, close: 10 }]
      },
      {
        id: "volume",
        label: "Volume",
        color: "var(--text-2)",
        type: "histogram",
        priceScaleId: "volume",
        data: [{ time: 1, value: 100 }]
      }
    ];

    const { body } = render(TimeSeriesChart, {
      props: {
        series,
        height: 180,
        showLegend: true
      }
    });

    expect(body).toContain("Price");
    expect(body).toContain("Volume");
    expect(body).toContain("height:180px");
    const componentSource = readFileSync(fileURLToPath(new URL("./TimeSeriesChart.svelte", import.meta.url)), "utf8");
    expect(componentSource).toContain("CandlestickSeries");
    expect(componentSource).toContain("HistogramSeries");
  });
});
