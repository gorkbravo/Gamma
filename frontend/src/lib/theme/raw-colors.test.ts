import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/* Raw-colour gate (visual refresh V2).

   Colour values live in tokens.css. Components and primitives.css name a
   token, or mix one into transparent for a lighter strength:
     color-mix(in srgb, var(--accent) 6%, transparent)
   which paints the same pixel as rgba(122, 166, 200, 0.06) but follows the
   token when a theme changes it. Colours built in script use mixToken() or
   read the token at runtime (chart-colors.ts).

   This test fails on a hex literal or an rgb()/rgba() literal with numeric
   channels in any .svelte file or in primitives.css, unless the exception
   list below names it. An entry whose literal is gone fails too, so the
   list cannot go stale. docs/visual_refresh_plan.md carries the same list. */

interface RawColorException {
  file: string;
  literal: string;
  reason: string;
}

const RAW_COLOR_EXCEPTIONS: RawColorException[] = [
  ...["0.22", "0.08", "0.34", "0.14", "0.2", "0.06", "0"].map((alpha) => ({
    file: "components/FanChart.svelte",
    literal: `rgba(122, 166, 200, ${alpha})`,
    reason: "SVG gradient stop: a mixed or var() stop colour interpolates in floating point and moves pixels by one level"
  })),
  { file: "components/FanChart.svelte", literal: "rgba(42, 56, 70, 0.26)", reason: "grid line, a one-off navy with no token" },
  { file: "components/FanChart.svelte", literal: "rgba(244, 247, 251, 0.94)", reason: "history line, a one-off white with no token" },
  { file: "components/FanChart.svelte", literal: "rgba(244, 247, 251, 0.12)", reason: "history line halo, same one-off white" },
  { file: "components/FanChart.svelte", literal: "rgba(106, 168, 255, 0.32)", reason: "tooltip edge, a one-off blue with no token" },
  { file: "components/StatusRail.svelte", literal: "rgba(8, 13, 18, 0.98)", reason: "settings popover background, a one-off near-black with no token" },
  { file: "components/MaritimeMap.svelte", literal: "rgba(2, 6, 12, 0.7)", reason: "vessel chevron outline drawn on canvas, a one-off with no token" },
  { file: "components/MacroCoherencePanel.svelte", literal: "rgba(255, 255, 255, 0.015)", reason: "component is not imported anywhere" },
  { file: "views/RiskView.svelte", literal: "rgb(87, 135, 176)", reason: "eighth cluster colour, no token" },
  { file: "views/RiskView.svelte", literal: "rgb(253,231,37)", reason: "end stop of the viridis data colormap, which encodes data rather than theme" }
];

const SRC = fileURLToPath(new URL("../..", import.meta.url));
// A hex colour of 3, 4, 6 or 8 digits that is not part of a word, an entity
// (&#123;), a link fragment (href="#abc") or a longer identifier.
const HEX = /(?<![&\w])(?<!href=["'])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])/g;
const RGB = /rgba?\(\s*\d[^)]*\)/g;

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walk(path) : [path];
  });
}

function rawColors() {
  return walk(SRC)
    .filter((path) => path.endsWith(".svelte") || path.endsWith("primitives.css"))
    .flatMap((path) => {
      const file = relative(SRC, path).replace(/\\/g, "/");
      const text = readFileSync(path, "utf8");
      return [...text.matchAll(HEX), ...text.matchAll(RGB)].map((match) => ({
        file,
        line: text.slice(0, match.index).split("\n").length,
        literal: match[0]
      }));
    });
}

const isException = (found: { file: string; literal: string }) =>
  RAW_COLOR_EXCEPTIONS.some((entry) => entry.file === found.file && entry.literal === found.literal);

describe("raw colour gate", () => {
  const found = rawColors();

  it("finds no raw colour literals outside the documented exceptions", () => {
    const unexpected = found.filter((item) => !isException(item)).map((item) => `${item.file}:${item.line} ${item.literal}`);
    expect(unexpected).toEqual([]);
  });

  it("lists only exceptions that still exist", () => {
    const stale = RAW_COLOR_EXCEPTIONS
      .filter((entry) => !found.some((item) => item.file === entry.file && item.literal === entry.literal))
      .map((entry) => `${entry.file} ${entry.literal}`);
    expect(stale).toEqual([]);
  });
});
