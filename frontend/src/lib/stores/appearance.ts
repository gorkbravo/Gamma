import { writable } from "svelte/store";

/* Interface theme (visual refresh V3).

   The preference is System, Light or Dark and persists in localStorage. The
   resolved theme is written to data-theme on <html>, where tokens.css swaps
   its colour block; index.html applies the stored preference before first
   paint so a light window never flashes dark. Components that paint through
   a canvas or a library (charts, the map, the 3D surface) subscribe to
   `resolvedTheme` and re-read their tokens when it changes. */

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "gamma.theme";

// Dark stays the default until the light theme is complete (V4); the plan's
// target default is System.
export const DEFAULT_THEME_PREFERENCE: ThemePreference = "dark";

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

export function parseThemePreference(value: unknown): ThemePreference {
  return value === "system" || value === "light" || value === "dark" ? value : DEFAULT_THEME_PREFERENCE;
}

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): ResolvedTheme {
  if (preference === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return preference;
}

function systemPrefersDark() {
  return typeof matchMedia === "function" && matchMedia(SYSTEM_DARK_QUERY).matches;
}

function readStoredPreference(): ThemePreference {
  try {
    return parseThemePreference(typeof localStorage === "undefined" ? null : localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

const initialPreference = readStoredPreference();

export const themePreference = writable<ThemePreference>(initialPreference);
export const resolvedTheme = writable<ResolvedTheme>(resolveTheme(initialPreference, systemPrefersDark()));

let currentPreference = initialPreference;

function applyResolvedTheme() {
  const resolved = resolveTheme(currentPreference, systemPrefersDark());
  if (typeof document !== "undefined") {
    // The attribute changes first, so subscribers read the new tokens.
    document.documentElement.dataset.theme = resolved;
  }
  resolvedTheme.set(resolved);
}

export function setThemePreference(preference: ThemePreference) {
  currentPreference = preference;
  themePreference.set(preference);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Persistence is best-effort; the choice still applies to this window.
  }
  applyResolvedTheme();
}

/* Data figures: the typeface of figures in tables, stats and charts. It
   overrides --font-num only, so labels keep --font-ui and code --font-code.
   The empty choice is the default: the token's own stack, Instrument Sans
   with tabular figures. A stored monospace stays valid. */
export const DATA_FIGURES_STORAGE_KEY = "gamma.dataFigures";
export const DATA_FIGURE_FONTS = ["Cascadia Mono", "Consolas", "JetBrains Mono", "IBM Plex Mono", "Courier New"] as const;
export const DEFAULT_DATA_FIGURES_LABEL = "Instrument Sans (default)";
export type DataFigureFont = "" | (typeof DATA_FIGURE_FONTS)[number];

export function parseDataFigureFont(value: unknown): DataFigureFont {
  return (DATA_FIGURE_FONTS as readonly unknown[]).includes(value) ? (value as DataFigureFont) : "";
}

function readStoredDataFigures(): DataFigureFont {
  try {
    return parseDataFigureFont(typeof localStorage === "undefined" ? null : localStorage.getItem(DATA_FIGURES_STORAGE_KEY));
  } catch {
    return "";
  }
}

export const dataFigureFont = writable<DataFigureFont>(readStoredDataFigures());

function applyDataFigureFont(font: DataFigureFont) {
  if (typeof document === "undefined") return;
  if (font) {
    document.documentElement.style.setProperty("--font-num", `"${font}", monospace`);
  } else {
    document.documentElement.style.removeProperty("--font-num");
  }
}

export function setDataFigureFont(font: DataFigureFont) {
  dataFigureFont.set(font);
  try {
    if (font) {
      localStorage.setItem(DATA_FIGURES_STORAGE_KEY, font);
    } else {
      localStorage.removeItem(DATA_FIGURES_STORAGE_KEY);
    }
  } catch {
    // Best-effort, as for the theme.
  }
  applyDataFigureFont(font);
}

/* A choice made in another window of the app (the key bindings window, a
   second tab) reaches this one as a storage event, so every open window
   follows without a reload. */
export function applyStoredChange(key: string | null, newValue: string | null) {
  if (key === THEME_STORAGE_KEY) {
    currentPreference = parseThemePreference(newValue);
    themePreference.set(currentPreference);
    applyResolvedTheme();
  } else if (key === DATA_FIGURES_STORAGE_KEY) {
    const font = parseDataFigureFont(newValue);
    dataFigureFont.set(font);
    applyDataFigureFont(font);
  }
}

/* Called once per window before the app mounts: applies both choices,
   follows the operating system while the preference is System, and follows
   changes made in the app's other windows. */
export function initAppearance() {
  applyResolvedTheme();
  applyDataFigureFont(readStoredDataFigures());
  if (typeof matchMedia === "function") {
    matchMedia(SYSTEM_DARK_QUERY).addEventListener("change", () => {
      if (currentPreference === "system") applyResolvedTheme();
    });
  }
  if (typeof window !== "undefined") {
    window.addEventListener("storage", (event) => applyStoredChange(event.key, event.newValue));
  }
}
