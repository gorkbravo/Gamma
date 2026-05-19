import { render } from "svelte/server";
import { beforeEach, describe, expect, it } from "vitest";
import KeyBindingsWindow from "./KeyBindingsWindow.svelte";
import { resetWorkspaceTabOrder } from "./lib/stores/navigation";

describe("KeyBindingsWindow", () => {
  beforeEach(() => {
    resetWorkspaceTabOrder("portfolio");
    resetWorkspaceTabOrder("research");
  });

  it("renders default action bindings and derived workspace shortcuts", () => {
    const { body } = render(KeyBindingsWindow);

    expect(body).toContain("Key Bindings");
    expect(body).toContain("Toggle sidebar");
    expect(body).toContain("Refresh active view");
    expect(body).toContain("Ctrl+B or `");
    expect(body).toContain("Portfolio Workspace");
    expect(body).toContain("Research Workspace");
    expect(body).toContain("EQUITY RESEARCH");
    expect(body).toContain("STRATEGY LAB");
    expect(body).toContain("Mode Shortcuts");
    expect(body).toContain("Shift+1");
    expect(body).toContain("Flows &amp; Liquidity");
    expect(body).toContain("Derived / pinned");
    expect(body).toContain("Explicit");
  });
});
