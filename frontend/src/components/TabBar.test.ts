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
          { id: "sitrep", label: "SITREP", pinned: true },
          { id: "risk", label: "RISK", pinned: false },
          { id: "prediction_markets", label: "PREDICTION MARKETS", pinned: false },
          { id: "macro", label: "MACRO", pinned: false },
        ],
        onSelect: vi.fn(),
        onClose: vi.fn(),
        onReset: vi.fn(),
        onReorder: vi.fn(),
      },
    });

    expect(body).toContain("Reset");
    expect(body).toContain("SITREP");
    expect(body).toContain("PREDICTION MARKETS");
    expect(body).toContain("Pinned");
  });
});
