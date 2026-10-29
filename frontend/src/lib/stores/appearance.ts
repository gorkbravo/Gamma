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

/* Called once per window before the app mounts: applies the theme and
   follows the operating system while the preference is System. */
export function initAppearance() {
  applyResolvedTheme();
  if (typeof matchMedia === "function") {
    matchMedia(SYSTEM_DARK_QUERY).addEventListener("change", () => {
      if (currentPreference === "system") applyResolvedTheme();
    });
  }
}
