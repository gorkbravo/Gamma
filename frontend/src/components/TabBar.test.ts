import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import TabBar from "./TabBar.svelte";

describe("TabBar", () => {
  it("renders pinned and reordered tabs with correct structure", () => {
    const { body } = render(TabBar, {
      props: {
        activeTab: "prediction_markets",
        open: true,
        tabs: [
          { id: "research", label: "Research", pinned: true },
          { id: "risk", label: "Risk", pinned: false },
          { id: "prediction_markets", label: "Prediction Markets", pinned: false },
          { id: "macro", label: "Macro", pinned: false },
        ],
        onSelect: vi.fn(),
        onClose: vi.fn(),
        onReset: vi.fn(),
        onReorder: vi.fn(),
      },
    });

    expect(body).toContain("Reset");
    expect(body).toContain("Research");
    expect(body).toContain("Prediction Markets");
    expect(body).toContain("Pinned");
  });
});
