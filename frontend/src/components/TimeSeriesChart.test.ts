import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import TimeSeriesChart from "./TimeSeriesChart.svelte";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { UTCTimestamp } from "lightweight-charts";

interface ChartSeries {
  id: string;
  label: string;
  color: string;
  type?: "line" | "area" | "candlestick" | "histogram";
  priceScaleId?: string;
  data: Array<
    | { time: UTCTimestamp; value: number }
    | { time: UTCTimestamp; open: number; high: number; low: number; close: number }
  >;
}

describe("TimeSeriesChart", () => {
  it("server-renders candlestick and histogram series metadata", () => {
    const series: ChartSeries[] = [
      {
        id: "price",
        label: "Price",
        color: "var(--accent)",
        type: "candlestick",
        data: [{ time: 1 as UTCTimestamp, open: 9, high: 11, low: 8, close: 10 }]
      },
      {
        id: "volume",
        label: "Volume",
        color: "var(--text-2)",
        type: "histogram",
        priceScaleId: "volume",
        data: [{ time: 1 as UTCTimestamp, value: 100 }]
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
