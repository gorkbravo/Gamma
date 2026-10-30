import { describe, expect, it } from "vitest";
import { get } from "svelte/store";
import {
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
  it("keeps a listed font and falls back to the token's own stack", () => {
    expect(parseDataFigureFont("Consolas")).toBe("Consolas");
    expect(parseDataFigureFont("Comic Sans MS")).toBe("");
    expect(parseDataFigureFont(null)).toBe("");
  });
});
