import { get } from "svelte/store";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_WORKSPACE_TAB_ORDER,
  getDefaultTabOrder,
  getModeByShortcutIndex,
  getModeRegistrySnapshot,
  getModeShortcutHint,
  getModeShortcutHintForIndex,
  getTabLabel,
  getTabModes,
  getTabByShortcutIndex,
  hasRegisteredModes,
  moveWorkspaceTab,
  normalizeWorkspaceTabOrder,
  normalizeWorkspaceTabOrderState,
  resolveNavigationPath,
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
      "sitrep",
      "equity_research",
      "strategy_lab",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "commodities",
      "maritime",
      "copilot",
      "risk",
      "iv",
    ]);
  });

  it("keeps the pinned first tab fixed even when restored state tries to move it", () => {
    expect(normalizeWorkspaceTabOrder("research", ["risk", "research", "iv", "macro", "prediction_markets"])).toEqual([
      "sitrep",
      "risk",
      "equity_research",
      "iv",
      "macro",
      "prediction_markets",
      "strategy_lab",
      "crypto",
      "fundamentals",
      "commodities",
      "maritime",
      "copilot",
    ]);
  });

  it("appends newly introduced tabs at the end when restoring older saved order", () => {
    expect(normalizeWorkspaceTabOrder("research", ["research", "risk", "macro"])).toEqual([
      "sitrep",
      "equity_research",
      "risk",
      "macro",
      "strategy_lab",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "commodities",
      "maritime",
      "copilot",
      "iv",
    ]);
  });

  it("maps Ctrl+N to the reordered visual tab order", () => {
    const reorderedState = normalizeWorkspaceTabOrderState({
      research: ["sitrep", "risk", "prediction_markets", "crypto", "macro", "iv"],
    });

    expect(getTabByShortcutIndex("research", reorderedState, 1)).toBe("sitrep");
    expect(getTabByShortcutIndex("research", reorderedState, 2)).toBe("risk");
    expect(getTabByShortcutIndex("research", reorderedState, 3)).toBe("prediction_markets");
    expect(getTabByShortcutIndex("research", reorderedState, 4)).toBe("crypto");
  });

  it("maps Shift+N to registered mode order for mode-bearing tabs", () => {
    expect(getModeShortcutHintForIndex(0)).toBe("Shift+1");
    expect(getTabModes("equity_research").map((mode) => mode.id)).toEqual([
      "overview",
      "scope_analysis",
      "comparables",
      "scenario_context",
      "saved_equity_research",
    ]);
    expect(getModeByShortcutIndex("equity_research", 1)?.id).toBe("overview");
    expect(getModeShortcutHint("equity_research", "scope_analysis")).toBe("Shift+2");
    expect(getModeShortcutHint("equity_research", "saved_equity_research")).toBe("Shift+5");
    expect(getTabModes("strategy_lab").map((mode) => mode.id)).toEqual([
      "composer",
      "backtest_analyze",
      "regime_stress",
      "imports",
      "saved_runs",
    ]);
    expect(getTabModes("macro").map((mode) => mode.id)).toEqual([
      "snapshot",
      "cross_asset",
      "rates_policy",
      "events_regimes",
      "trade_partners",
      "country_compare",
    ]);
    expect(getModeByShortcutIndex("macro", 2)?.id).toBe("cross_asset");
    expect(getModeShortcutHint("crypto", "flows_liquidity")).toBe("Shift+3");
    expect(getTabModes("iv").map((mode) => mode.id)).toEqual([
      "overview",
      "chain",
      "surface",
      "realized_implied",
      "distribution",
      "strategies",
    ]);
    expect(getModeByShortcutIndex("iv", 2)?.id).toBe("chain");
    expect(getModeShortcutHint("iv", "distribution")).toBe("Shift+5");
    expect(getTabModes("risk").map((mode) => mode.id)).toEqual([
      "overview",
      "exposures",
      "drawdowns",
      "correlation",
      "scenarios",
      "optimization",
    ]);
    expect(getModeByShortcutIndex("risk", 6)?.id).toBe("optimization");
    expect(getModeShortcutHint("risk", "scenarios")).toBe("Shift+5");
  });

  it("resolves slash navigation paths to tabs and modes", () => {
    const orderState = normalizeWorkspaceTabOrderState(null);

    expect(resolveNavigationPath("research", orderState, "/Research")?.tab.id).toBe("equity_research");
    expect(resolveNavigationPath("research", orderState, "/Research/Scope")?.mode?.id).toBe("scope_analysis");
    expect(resolveNavigationPath("research", orderState, "/Research/Comparables")?.tab.id).toBe("equity_research");
    expect(resolveNavigationPath("research", orderState, "/Research/Comparables")?.mode?.id).toBe("comparables");
    expect(resolveNavigationPath("research", orderState, "/Research/Strategy")?.tab.id).toBe("strategy_lab");
    expect(resolveNavigationPath("research", orderState, "/Strategy Lab/Imports")?.mode?.id).toBe("imports");
    expect(resolveNavigationPath("research", orderState, "/Rearch/Scope")?.mode?.id).toBe("scope_analysis");
    expect(resolveNavigationPath("research", orderState, "/macro/rates")?.mode?.id).toBe("rates_policy");
    expect(resolveNavigationPath("research", orderState, "/macro/trade")?.mode?.id).toBe("trade_partners");
    expect(resolveNavigationPath("research", orderState, "/macro/country")?.mode?.id).toBe("country_compare");
    expect(resolveNavigationPath("research", orderState, "/Prediction")?.tab.id).toBe("prediction_markets");
    expect(resolveNavigationPath("research", orderState, "/Research/Unknown")).toBeNull();
    expect(resolveNavigationPath("portfolio", orderState, "/Research/Scope")).toBeNull();
  });

  it("exposes a reusable mode registry snapshot for current mode-bearing tabs", () => {
    const snapshot = getModeRegistrySnapshot();

    expect(hasRegisteredModes("macro")).toBe(true);
    expect(hasRegisteredModes("equity_research")).toBe(true);
    expect(hasRegisteredModes("strategy_lab")).toBe(true);
    expect(hasRegisteredModes("copilot")).toBe(false);
    expect(Object.keys(snapshot).sort()).toEqual([
      "commodities",
      "crypto",
      "equity_research",
      "fundamentals",
      "iv",
      "macro",
      "maritime",
      "risk",
      "strategy_lab",
    ]);
    expect(snapshot.commodities?.map((mode) => mode.id)).toEqual([
      "overview",
      "energy",
      "metals",
      "curves_spreads",
      "inventories_fundamentals",
      "events_cross_domain",
    ]);
    expect(snapshot.fundamentals?.map((mode) => mode.id)).toEqual([
      "overview",
      "financials",
      "peers",
      "dcf",
      "reverse_valuation",
      "reference",
    ]);
    expect(snapshot.equity_research?.map((mode) => mode.id)).toEqual([
      "overview",
      "scope_analysis",
      "comparables",
      "scenario_context",
      "saved_equity_research",
    ]);
    expect(snapshot.strategy_lab?.map((mode) => mode.id)).toEqual([
      "composer",
      "backtest_analyze",
      "regime_stress",
      "imports",
      "saved_runs",
    ]);
    expect(snapshot.maritime?.map((mode) => mode.id)).toEqual([
      "live_map",
      "chokepoints",
      "trade_flows",
      "fleet_monitoring",
      "event_replay",
    ]);
    expect(snapshot.iv?.map((mode) => mode.id)).toEqual([
      "overview",
      "chain",
      "surface",
      "realized_implied",
      "distribution",
      "strategies",
    ]);
    expect(snapshot.risk?.map((mode) => mode.id)).toEqual([
      "overview",
      "exposures",
      "drawdowns",
      "correlation",
      "scenarios",
      "optimization",
    ]);
    expect(getTabLabel("sitrep")).toBe("SITREP");
    expect(getTabLabel("commodities")).toBe("COMMODITIES");
    expect(getTabLabel("maritime")).toBe("SEALANES");
    expect(getTabLabel("iv")).toBe("OPTIONS");
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

    expect(get(store).research).toEqual([
      "sitrep",
      "risk",
      "equity_research",
      "strategy_lab",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "commodities",
      "maritime",
      "copilot",
      "iv",
    ]);
    expect(get(store).portfolio).toEqual(DEFAULT_WORKSPACE_TAB_ORDER.portfolio);

    const reloadedStore = createWorkspaceTabOrderStore(storage);
    expect(get(reloadedStore).research).toEqual([
      "sitrep",
      "risk",
      "equity_research",
      "strategy_lab",
      "macro",
      "prediction_markets",
      "crypto",
      "fundamentals",
      "commodities",
      "maritime",
      "copilot",
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
