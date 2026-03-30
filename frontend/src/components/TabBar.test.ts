import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import TabBar from "./TabBar.svelte";

describe("TabBar", () => {
  it("renders pinned and reordered tabs with live shortcut hints", () => {
    const { body } = render(TabBar, {
      props: {
        activeTab: "prediction_markets",
        open: true,
        tabs: [
          { id: "research", label: "Research", pinned: true, shortcutHint: "Ctrl+1" },
          { id: "risk", label: "Risk", pinned: false, shortcutHint: "Ctrl+2" },
          { id: "prediction_markets", label: "Prediction Markets", pinned: false, shortcutHint: "Ctrl+3" },
          { id: "macro", label: "Macro", pinned: false, shortcutHint: "Ctrl+4" },
        ],
        onSelect: vi.fn(),
        onClose: vi.fn(),
        onReset: vi.fn(),
        onReorder: vi.fn(),
      },
    });

    expect(body).toContain("Reset");
    expect(body).toContain("Pinned");
    expect(body).toContain("Research");
    expect(body).toContain("Prediction Markets");
    expect(body).toContain("Ctrl+1");
    expect(body).toContain("Ctrl+3");
    expect(body).toContain("Visual order controls `Ctrl+1...N`.");
  });
});
