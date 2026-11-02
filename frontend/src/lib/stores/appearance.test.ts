import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { get } from "svelte/store";
import {
  DATA_FIGURE_FONTS,
  DEFAULT_DATA_FIGURES_LABEL,
  DEFAULT_THEME_PREFERENCE,
  applyStoredChange,
  dataFigureFont,
  parseDataFigureFont,
  parseThemePreference,
  resolveTheme,
  resolvedTheme,
  themePreference
} from "./appearance";

describe("theme preference", () => {
  it("defaults to dark until the light theme is complete", () => {
    expect(DEFAULT_THEME_PREFERENCE).toBe("dark");
    expect(parseThemePreference(null)).toBe("dark");
    expect(parseThemePreference("sepia")).toBe("dark");
  });

  it("keeps a stored choice", () => {
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("system")).toBe("system");
  });

  it("resolves System from the operating system and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("changes from another window", () => {
  it("follows a theme or data figures choice stored elsewhere and ignores other keys", () => {
    applyStoredChange("gamma.theme", "light");
    expect(get(themePreference)).toBe("light");
    expect(get(resolvedTheme)).toBe("light");

    applyStoredChange("gamma.dataFigures", "Consolas");
    expect(get(dataFigureFont)).toBe("Consolas");

    applyStoredChange("gamma.macro", "dark");
    expect(get(themePreference)).toBe("light");

    applyStoredChange("gamma.theme", null);
    expect(get(themePreference)).toBe("dark");
  });
});

describe("data figures font", () => {
  it("keeps a stored monospace and falls back to the token's own stack", () => {
    expect(parseDataFigureFont("Consolas")).toBe("Consolas");
    for (const font of DATA_FIGURE_FONTS) {
      expect(parseDataFigureFont(font)).toBe(font);
    }
    expect(parseDataFigureFont("Comic Sans MS")).toBe("");
    expect(parseDataFigureFont(null)).toBe("");
  });

  it("names Instrument Sans as the default and offers only monospaces besides it", () => {
    expect(DEFAULT_DATA_FIGURES_LABEL).toBe("Instrument Sans (default)");
    expect(DATA_FIGURE_FONTS).not.toContain("Instrument Sans");
    expect(DATA_FIGURE_FONTS).toEqual(["Cascadia Mono", "Consolas", "JetBrains Mono", "IBM Plex Mono", "Courier New"]);
  });

  it("keeps Instrument Sans with tabular figures as the token's own stack", () => {
    const tokens = readFileSync(fileURLToPath(new URL("../theme/tokens.css", import.meta.url)), "utf8");
    expect(tokens).toMatch(/--font-num: "Instrument Sans",/);
    expect(tokens).toMatch(/font-variant-numeric: tabular-nums;\s*font-feature-settings: "tnum" 1;/);
  });
});
