import { get } from "svelte/store";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_WORKSPACE_TAB_ORDER,
  getDefaultTabOrder,
  getModeByShortcutIndex,
  getModeShortcutHint,
  getModeShortcutHintForIndex,
  getTabModes,
  getTabByShortcutIndex,
  moveWorkspaceTab,
  normalizeWorkspaceTabOrder,
  normalizeWorkspaceTabOrderState,
} from "./navigation";
import { createWorkspaceTabOrderStore, type StorageLike } from "./stores/navigation";

class MemoryStorage implements StorageLike {
  private readonly values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("navigation tab ordering", () => {
  it("returns the roadmap default order for each workspace", () => {
    expect(getDefaultTabOrder("portfolio")).toEqual(["portfolio", "risk", "iv"]);
    expect(getDefaultTabOrder("research")).toEqual([
      "research",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "risk",
      "iv",
    ]);
  });

  it("keeps the pinned first tab fixed even when restored state tries to move it", () => {
    expect(normalizeWorkspaceTabOrder("research", ["risk", "research", "iv", "macro", "prediction_markets"])).toEqual([
      "research",
      "risk",
      "iv",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
    ]);
  });

  it("appends newly introduced tabs at the end when restoring older saved order", () => {
    expect(normalizeWorkspaceTabOrder("research", ["research", "risk", "macro"])).toEqual([
      "research",
      "risk",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "iv",
    ]);
  });

  it("maps Ctrl+N to the reordered visual tab order", () => {
    const reorderedState = normalizeWorkspaceTabOrderState({
      research: ["research", "risk", "prediction_markets", "crypto", "macro", "iv"],
    });

    expect(getTabByShortcutIndex("research", reorderedState, 1)).toBe("research");
    expect(getTabByShortcutIndex("research", reorderedState, 2)).toBe("risk");
    expect(getTabByShortcutIndex("research", reorderedState, 3)).toBe("prediction_markets");
    expect(getTabByShortcutIndex("research", reorderedState, 4)).toBe("crypto");
  });

  it("maps Shift+N to registered mode order for mode-bearing tabs", () => {
    expect(getModeShortcutHintForIndex(0)).toBe("Shift+1");
    expect(getTabModes("macro").map((mode) => mode.id)).toEqual([
      "snapshot",
      "cross_asset",
      "rates_policy",
      "events_regimes",
    ]);
    expect(getModeByShortcutIndex("macro", 2)?.id).toBe("cross_asset");
    expect(getModeShortcutHint("crypto", "flows_liquidity")).toBe("Shift+3");
    expect(getModeByShortcutIndex("research", 1)).toBeNull();
  });

  it("reorders draggable tabs without moving the pinned first slot", () => {
    expect(moveWorkspaceTab("portfolio", ["portfolio", "risk", "iv"], "iv", 1)).toEqual(["portfolio", "iv", "risk"]);
    expect(moveWorkspaceTab("portfolio", ["portfolio", "risk", "iv"], "portfolio", 2)).toEqual(["portfolio", "risk", "iv"]);
  });
});

describe("workspace tab-order persistence", () => {
  it("persists reorders, restores them on reload, and keeps workspaces isolated", () => {
    const storage = new MemoryStorage();
    const store = createWorkspaceTabOrderStore(storage);

    store.reorder("research", "risk", 1);

    expect(get(store).research).toEqual(["research", "risk", "macro", "prediction_markets", "crypto", "fundamentals", "iv"]);
    expect(get(store).portfolio).toEqual(DEFAULT_WORKSPACE_TAB_ORDER.portfolio);

    const reloadedStore = createWorkspaceTabOrderStore(storage);
    expect(get(reloadedStore).research).toEqual([
      "research",
      "risk",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "iv",
    ]);
    expect(get(reloadedStore).portfolio).toEqual(DEFAULT_WORKSPACE_TAB_ORDER.portfolio);
  });

  it("resets a workspace back to its default order", () => {
    const storage = new MemoryStorage();
    const store = createWorkspaceTabOrderStore(storage);

    store.reorder("research", "risk", 1);
    expect(get(store).research).not.toEqual(DEFAULT_WORKSPACE_TAB_ORDER.research);

    store.reset("research");
    expect(get(store).research).toEqual(DEFAULT_WORKSPACE_TAB_ORDER.research);
  });
});
