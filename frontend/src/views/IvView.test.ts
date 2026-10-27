import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import IvView from "./IvView.svelte";

describe("IvView accessible names (GUA-20261021-16, live check 2026-10-27)", () => {
  it("names the symbol input and the Strategy Builder selects", () => {
    const { body } = render(IvView, {
      props: { mode: "strategies", onLoad: vi.fn(), onStopSession: vi.fn() } as never
    });
    // Antes el campo se llamaba por su placeholder ("SPY") y los selectores no tenían nombre.
    expect(body).toMatch(/<input[^>]*aria-label="Options underlying symbol"/);
    expect(body).toContain('aria-label="Strategy leg side"');
    expect(body).toContain('aria-label="Strategy leg option type"');
    expect(body).toContain('aria-label="Strategy expiry"');
  });
});
