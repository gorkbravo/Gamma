import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import CompactContextMenu from "./CompactContextMenu.svelte";

describe("CompactContextMenu", () => {
  it("renders compact menu actions when open", () => {
    const { body } = render(CompactContextMenu, {
      props: {
        open: true,
        x: 12,
        y: 24,
        label: "Strategy actions",
        items: [
          { id: "add", label: "Add to Strategy" },
          { id: "add-open", label: "Add and Open" }
        ],
        onSelect: vi.fn(),
        onClose: vi.fn()
      }
    });

    expect(body).toContain('role="menu"');
    expect(body).toContain('aria-label="Strategy actions"');
    expect(body).toContain("Add to Strategy");
    expect(body).toContain("Add and Open");
  });

  it("does not render menu chrome when closed", () => {
    const { body } = render(CompactContextMenu, {
      props: {
        open: false,
        items: [{ id: "add", label: "Add to Strategy" }]
      }
    });

    expect(body).not.toContain('role="menu"');
    expect(body).not.toContain("Add to Strategy");
  });
});
