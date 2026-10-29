import { describe, expect, it } from "vitest";
import { DEFAULT_THEME_PREFERENCE, parseDataFigureFont, parseThemePreference, resolveTheme } from "./appearance";

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

describe("data figures font", () => {
  it("keeps a listed font and falls back to the token's own stack", () => {
    expect(parseDataFigureFont("Consolas")).toBe("Consolas");
    expect(parseDataFigureFont("Comic Sans MS")).toBe("");
    expect(parseDataFigureFont(null)).toBe("");
  });
});
