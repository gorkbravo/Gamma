import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/* Contrast gate (visual refresh V3).

   Resolves the colour tokens in tokens.css for each theme (the :root block,
   with the light block layered on top for the light theme), composites
   translucent colours over their background, and checks WCAG AA: 4.5:1 for
   text, 3:1 for graphics and the focus ring. */

type Rgba = [number, number, number, number];

const CSS = readFileSync(fileURLToPath(new URL("./tokens.css", import.meta.url)), "utf8");

function block(selector: string) {
  const start = CSS.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`missing block ${selector}`);
  const body = CSS.slice(CSS.indexOf("{", start) + 1, CSS.indexOf("\n}", start));
  const tokens = new Map<string, string>();
  for (const match of body.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    tokens.set(match[1], match[2].trim());
  }
  return tokens;
}

const DARK = block(":root");
const LIGHT = new Map([...DARK, ...block(':root[data-theme="light"]')]);

function parseColor(value: string): Rgba {
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const digits = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join("") : hex[1];
    return [0, 2, 4].map((i) => parseInt(digits.slice(i, i + 2), 16)).concat(1) as Rgba;
  }
  const rgb = value.match(/^rgba?\(([^)]+)\)$/i);
  if (rgb) {
    const [r, g, b, a = "1"] = rgb[1].split(",").map((part) => part.trim());
    return [Number(r), Number(g), Number(b), Number(a)];
  }
  if (value === "transparent") return [0, 0, 0, 0];
  throw new Error(`unparsed colour ${value}`);
}

function resolve(value: string, tokens: Map<string, string>): Rgba {
  const trimmed = value.trim();
  const variable = trimmed.match(/^var\((--[\w-]+)\)$/);
  if (variable) {
    const next = tokens.get(variable[1]);
    if (!next) throw new Error(`undefined token ${variable[1]}`);
    return resolve(next, tokens);
  }
  const mix = trimmed.match(/^color-mix\(in srgb,\s*(.+?)\s+([\d.]+)%,\s*(.+)\)$/);
  if (mix) {
    // Premultiplied sRGB interpolation, as browsers mix.
    const a = resolve(mix[1], tokens);
    const b = resolve(mix[3], tokens);
    const p = Number(mix[2]) / 100;
    const alpha = a[3] * p + b[3] * (1 - p);
    if (alpha === 0) return [0, 0, 0, 0];
    const channel = (i: number) => (a[i] * a[3] * p + b[i] * b[3] * (1 - p)) / alpha;
    return [channel(0), channel(1), channel(2), alpha];
  }
  return parseColor(trimmed);
}

function over(top: Rgba, bottom: Rgba): Rgba {
  const a = top[3] + bottom[3] * (1 - top[3]);
  const channel = (i: number) => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a;
  return [channel(0), channel(1), channel(2), a];
}

function luminance([r, g, b]: Rgba) {
  const linear = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(foreground: string, background: string[], tokens: Map<string, string>) {
  // Backgrounds stack bottom-up, e.g. a soft fill over the panel.
  const bg = background.map((name) => resolve(`var(${name})`, tokens)).reduce((below, layer) => over(layer, below));
  const fg = over(resolve(`var(${foreground})`, tokens), bg);
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

const SURFACES = [["--panel-bg"], ["--panel-bg", "--tint"], ["--panel-bg", "--surface-0"]];
const TEXT = ["--text-0", "--text-1", "--text-2", "--accent", "--accent-2", "--positive", "--negative", "--warning"];
const TEXT_ON_FILL: Array<[string, string[]]> = [
  ["--accent", ["--panel-bg", "--accent-soft"]],
  ["--accent", ["--panel-bg", "--active-bg"]],
  ["--positive", ["--panel-bg", "--positive-soft"]],
  ["--negative", ["--panel-bg", "--negative-soft"]],
  ["--warning", ["--panel-bg", "--warning-soft"]],
  ["--text-0", ["--panel-bg", "--hover-bg"]],
  ["--text-2", ["--panel-bg", "--hover-bg"]],
  ["--text-2", ["--panel-bg", "--active-bg"]],
  ["--text-0", ["--canvas"]],
  ["--text-1", ["--canvas"]],
  ["--accent", ["--canvas"]],
  ["--text-0", ["--panel-bg", "--button-bg"]],
  ["--text-0", ["--canvas", "--button-bg"]],
  ["--text-1", ["--canvas", "--tint"]]
];
// Edgeless buttons need a fill that still shows against what they sit on:
// the button fill a clear step (1.15:1), the ghost tint at least a trace.
const BUTTON_FILLS: Array<[string, number]> = [["--button-bg", 1.15], ["--tint", 1.05]];
const GRAPHICS = [
  "--chart-primary", "--chart-secondary", "--chart-negative",
  "--cat-1", "--cat-2", "--cat-3", "--cat-4", "--cat-5", "--cat-6", "--cat-7", "--cat-8",
  "--data-hot", "--data-warm", "--data-cool", "--data-cold", "--data-elevated", "--data-extreme",
  "--focus-ring"
];

for (const [theme, tokens] of [["dark", DARK], ["light", LIGHT]] as const) {
  describe(`${theme} theme contrast`, () => {
    it("keeps text at 4.5:1 on panels, tints and surfaces", () => {
      const failures = SURFACES.flatMap((bg) => TEXT.map((fg) => [fg, bg.join(" + "), contrast(fg, bg, tokens)] as const))
        .filter(([, , ratio]) => ratio < 4.5)
        .map(([fg, bg, ratio]) => `${fg} on ${bg}: ${ratio.toFixed(2)}`);
      expect(failures).toEqual([]);
    });

    it("keeps text at 4.5:1 on its soft fill", () => {
      const failures = TEXT_ON_FILL.map(([fg, bg]) => [fg, bg.join(" + "), contrast(fg, bg, tokens)] as const)
        .filter(([, , ratio]) => ratio < 4.5)
        .map(([fg, bg, ratio]) => `${fg} on ${bg}: ${ratio.toFixed(2)}`);
      expect(failures).toEqual([]);
    });

    it("keeps button fills visible on the sheet and the canvas", () => {
      const failures = BUTTON_FILLS.flatMap(([fill, min]) => ["--panel-bg", "--canvas"].map((base) => [fill, base, min, contrast(fill, [base], tokens)] as const))
        .filter(([, , min, ratio]) => ratio < min)
        .map(([fill, base, min, ratio]) => `${fill} on ${base}: ${ratio.toFixed(3)} < ${min}`);
      expect(failures).toEqual([]);
    });

    it("keeps chart, categorical and focus colours at 3:1 on panels", () => {
      const failures = GRAPHICS.map((fg) => [fg, contrast(fg, ["--panel-bg"], tokens)] as const)
        .filter(([, ratio]) => ratio < 3)
        .map(([fg, ratio]) => `${fg}: ${ratio.toFixed(2)}`);
      expect(failures).toEqual([]);
    });
  });
}
