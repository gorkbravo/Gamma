import { describe, expect, it } from "vitest";
import { colorWithAlpha, resolveChartColor } from "./chart-colors";

describe("resolveChartColor", () => {
  it("resolves css variable colors from theme tokens", () => {
    const tokens = {
      getPropertyValue(name: string) {
        return name === "--chart-primary" ? "#7aa6c8" : "";
      }
    };

    expect(resolveChartColor("var(--chart-primary)", tokens)).toBe("#7aa6c8");
  });

  it("maps default chart colors back to the active theme tokens", () => {
    const tokens = {
      getPropertyValue(name: string) {
        return name === "--chart-secondary" ? "#c49a5a" : "";
      }
    };

    expect(resolveChartColor("#c49a5a", tokens)).toBe("#c49a5a");
  });
});

describe("colorWithAlpha", () => {
  it("builds rgba strings from hex colors", () => {
    expect(colorWithAlpha("#7aa6c8", 0.2)).toBe("rgba(122, 166, 200, 0.2)");
  });

  it("builds rgba strings from rgb colors", () => {
    expect(colorWithAlpha("rgb(198, 107, 97)", 0.08)).toBe("rgba(198, 107, 97, 0.08)");
  });
});
