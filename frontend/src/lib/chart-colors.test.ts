import { describe, expect, it } from "vitest";
import { colorWithAlpha, mixToken, resolveChartColor } from "./chart-colors";

describe("resolveChartColor", () => {
  it("resolves css variable colors from theme tokens", () => {
    const tokens = {
      getPropertyValue(name: string) {
        return name === "--chart-primary" ? "#7aa6c8" : "";
      }
    };

    expect(resolveChartColor("var(--chart-primary)", tokens)).toBe("#7aa6c8");
  });

  it("follows the active chart theme", () => {
    const amber = {
      getPropertyValue(name: string) {
        return name === "--chart-primary" ? "#d4a054" : "";
      }
    };

    expect(resolveChartColor("var(--chart-primary)", amber)).toBe("#d4a054");
  });

  it("passes literal colors through without a token lookup", () => {
    const tokens = {
      getPropertyValue() {
        throw new Error("no lookup expected");
      }
    };

    expect(resolveChartColor(" #c49a5a ", tokens)).toBe("#c49a5a");
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

describe("mixToken", () => {
  it("mixes a token into transparent at the given strength", () => {
    expect(mixToken("--accent", 0.2)).toBe("color-mix(in srgb, var(--accent) 20%, transparent)");
  });

  it("keeps fractional strengths and clamps the range", () => {
    expect(mixToken("--positive", 0.123)).toBe("color-mix(in srgb, var(--positive) 12.3%, transparent)");
    expect(mixToken("--negative-muted", 1.4)).toBe("color-mix(in srgb, var(--negative-muted) 100%, transparent)");
  });
});
