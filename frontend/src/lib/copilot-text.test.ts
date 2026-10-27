import { describe, expect, it } from "vitest";
import { hasCopilotText, isNumericCell, parseCopilotRichText } from "./copilot-text";

// GUA-20261021-13: la justificación del Operator traía una tabla Markdown que se veía como
// tuberías dentro de un párrafo.
const RATIONALE = [
  "Same-month spreads from the loaded curves:",
  "| Delivery | Brent | WTI | Spread |",
  "| --- | ---: | ---: | ---: |",
  "| Dec-26 | 111.05 | 99.93 | 11.12 |",
  "| Jan-27 | **107.33** | 98.05 |",
  "",
  "- Prompt-concentrated",
  "- Decays to ~$5 by Apr-27"
].join("\n");

describe("parseCopilotRichText", () => {
  it("splits paragraphs, Markdown tables and lists into escaped segments", () => {
    const segments = parseCopilotRichText(RATIONALE);
    expect(segments.map((segment) => segment.kind)).toEqual(["paragraph", "table", "list"]);
    const table = segments[1];
    if (table.kind !== "table") throw new Error("expected a table");
    expect(table.header).toEqual(["Delivery", "Brent", "WTI", "Spread"]);
    expect(table.align).toEqual([null, "right", "right", "right"]);
    // Las filas cortas se rellenan y el énfasis no renderizable se quita.
    expect(table.rows).toEqual([
      ["Dec-26", "111.05", "99.93", "11.12"],
      ["Jan-27", "107.33", "98.05", ""]
    ]);
    expect(segments[2]).toEqual({
      kind: "list",
      ordered: false,
      items: ["Prompt-concentrated", "Decays to ~$5 by Apr-27"]
    });
  });

  it("keeps plain prose (including stray pipes) as one paragraph", () => {
    expect(parseCopilotRichText("Brent | WTI spread widened.\nSecond line.")).toEqual([
      { kind: "paragraph", text: "Brent | WTI spread widened.\nSecond line." }
    ]);
    expect(parseCopilotRichText("   ")).toEqual([]);
    expect(parseCopilotRichText(null)).toEqual([]);
  });

  it("renders a pipe table without separator row or outer pipes (live check 2026-10-27)", () => {
    const rationale = [
      "Prices are USD/bbl.",
      "",
      "Delivery | Brent | WTI | Brent−WTI",
      "Dec-26 | 114.10 | 100.01 | 14.09",
      "Jan-27 | 109.64 | NA | NA",
      "",
      "Brent | WTI spread widened."
    ].join("\n");
    expect(parseCopilotRichText(rationale)).toEqual([
      { kind: "paragraph", text: "Prices are USD/bbl." },
      {
        kind: "table",
        header: ["Delivery", "Brent", "WTI", "Brent−WTI"],
        align: [null, null, null, null],
        rows: [
          ["Dec-26", "114.10", "100.01", "14.09"],
          ["Jan-27", "109.64", "NA", "NA"]
        ]
      },
      { kind: "paragraph", text: "Brent | WTI spread widened." }
    ]);
  });

  it("detects numeric cells and empty text", () => {
    expect(isNumericCell("111.05")).toBe(true);
    expect(isNumericCell("-2.3%")).toBe(true);
    expect(isNumericCell("Dec-26")).toBe(false);
    expect(hasCopilotText(" \n")).toBe(false);
    expect(hasCopilotText("x")).toBe(true);
  });
});
