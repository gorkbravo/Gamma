import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";

import StrategyLabView from "./StrategyLabView.svelte";

describe("StrategyLabView Script mode", () => {
  it("exposes Script in the mode bar and selects the safe-preview workspace", () => {
    const { body } = render(StrategyLabView, {
      props: {
        mode: "script",
        onAnalyzeStrategy: vi.fn(),
        onLoadSaved: vi.fn(),
        onSaveResearch: vi.fn(),
        onDeleteSaved: vi.fn()
      }
    });

    expect(body).toContain("aria-label=\"Strategy Lab modes\"");
    expect(body).toContain(">Script</button>");
    expect(body).toMatch(/aria-selected="true"[^>]*>Script/);
    expect(body).toContain("Mock / Safe Preview");
    expect(body).not.toContain("Gamma Object Composer");
  });
});
