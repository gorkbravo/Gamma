import type {
  ActionKeybindingDefinition,
  TabId,
  WorkspaceMode,
  WorkspaceTabDefinition,
  WorkspaceTabOrderState,
} from "./api/types";

export const WORKSPACE_TAB_DEFINITIONS = {
  portfolio: [
    { id: "portfolio", label: "Portfolio", pinned: true, defaultIndex: 0 },
    { id: "risk", label: "Risk", pinned: false, defaultIndex: 1 },
    { id: "iv", label: "IV", pinned: false, defaultIndex: 2 },
  ],
  research: [
    { id: "research", label: "Research", pinned: true, defaultIndex: 0 },
    { id: "macro", label: "Macro", pinned: false, defaultIndex: 1 },
    { id: "prediction_markets", label: "Prediction Markets", pinned: false, defaultIndex: 2 },
    { id: "crypto", label: "Crypto", pinned: false, defaultIndex: 3 },
    { id: "fundamentals", label: "Fundamentals", pinned: false, defaultIndex: 4 },
    { id: "maritime", label: "Maritime", pinned: false, defaultIndex: 5 },
    { id: "risk", label: "Risk", pinned: false, defaultIndex: 6 },
    { id: "iv", label: "IV", pinned: false, defaultIndex: 7 },
  ],
} satisfies Record<WorkspaceMode, readonly WorkspaceTabDefinition[]>;

export interface TabModeDefinition {
  id: string;
  label: string;
  defaultIndex: number;
}

export const TAB_MODE_DEFINITIONS: Partial<Record<TabId, readonly TabModeDefinition[]>> = {
  research: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "scope_analysis", label: "Scope Analysis", defaultIndex: 1 },
    { id: "strategy_lab", label: "Strategy Lab", defaultIndex: 2 },
    { id: "compare_scenario", label: "Compare / Scenario", defaultIndex: 3 },
    { id: "saved_research", label: "Saved Research", defaultIndex: 4 },
  ]),
  macro: defineTabModes([
    { id: "snapshot", label: "Snapshot", defaultIndex: 0 },
    { id: "cross_asset", label: "Cross-Asset", defaultIndex: 1 },
    { id: "rates_policy", label: "Rates & Policy", defaultIndex: 2 },
    { id: "events_regimes", label: "Events / Regimes", defaultIndex: 3 },
  ]),
  crypto: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "deep_dive", label: "Deep Dive", defaultIndex: 1 },
    { id: "flows_liquidity", label: "Flows & Liquidity", defaultIndex: 2 },
  ]),
  fundamentals: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "financials", label: "Financials", defaultIndex: 1 },
    { id: "peers", label: "Peers", defaultIndex: 2 },
    { id: "dcf", label: "DCF", defaultIndex: 3 },
    { id: "reverse_valuation", label: "Reverse Valuation", defaultIndex: 4 },
    { id: "reference", label: "Reference / Filings", defaultIndex: 5 },
  ]),
  maritime: defineTabModes([
    { id: "live_map", label: "Live Map", defaultIndex: 0 },
    { id: "chokepoints", label: "Chokepoints", defaultIndex: 1 },
    { id: "trade_flows", label: "Trade Flows", defaultIndex: 2 },
    { id: "fleet_monitoring", label: "Fleet / Vessel", defaultIndex: 3 },
    { id: "event_replay", label: "Event Replay", defaultIndex: 4 },
  ]),
};

export const DEFAULT_WORKSPACE_TAB_ORDER = {
  portfolio: WORKSPACE_TAB_DEFINITIONS.portfolio.map((tab) => tab.id),
  research: WORKSPACE_TAB_DEFINITIONS.research.map((tab) => tab.id),
} satisfies WorkspaceTabOrderState;

export const ACTION_KEYBINDINGS: readonly ActionKeybindingDefinition[] = [
  {
    id: "toggle_sidebar",
    label: "Toggle sidebar",
    description: "Open or close the workspace navigation surface.",
    combos: [
      { id: "toggle-sidebar-primary", label: "Ctrl+B", key: "b", ctrl: true },
      { id: "toggle-sidebar-secondary", label: "`", key: "`" },
    ],
  },
  {
    id: "refresh_view",
    label: "Refresh active view",
    description: "Run Gamma's existing refresh flow for the active workspace view.",
    combos: [
      { id: "refresh-primary", label: "Ctrl+R", key: "r", ctrl: true },
      { id: "refresh-secondary", label: "F5", key: "f5" },
    ],
  },
  {
    id: "open_settings",
    label: "Open settings",
    description: "Open the settings surface from the app shell.",
    combos: [{ id: "open-settings-primary", label: "Ctrl+,", key: ",", ctrl: true }],
  },
  {
    id: "dismiss_surface",
    label: "Dismiss sidebar or popover",
    description: "Close the sidebar and lightweight overlays.",
    combos: [{ id: "dismiss-primary", label: "Escape", key: "escape" }],
  },
  {
    id: "switch_portfolio_workspace",
    label: "Switch to Portfolio workspace",
    description: "Jump to the Portfolio workspace home tab.",
    combos: [{ id: "switch-portfolio-primary", label: "Ctrl+Shift+P", key: "p", ctrl: true, shift: true }],
  },
  {
    id: "switch_research_workspace",
    label: "Switch to Research workspace",
    description: "Jump to the Research workspace home tab.",
    combos: [{ id: "switch-research-primary", label: "Ctrl+Shift+R", key: "r", ctrl: true, shift: true }],
  },
] as const;

const WORKSPACE_TAB_LOOKUP = {
  portfolio: new Map(WORKSPACE_TAB_DEFINITIONS.portfolio.map((tab) => [tab.id, tab])),
  research: new Map(WORKSPACE_TAB_DEFINITIONS.research.map((tab) => [tab.id, tab])),
} satisfies Record<WorkspaceMode, Map<TabId, WorkspaceTabDefinition>>;

export function getWorkspaceHomeTab(mode: WorkspaceMode): TabId {
  return DEFAULT_WORKSPACE_TAB_ORDER[mode][0];
}

export function getWorkspaceLabel(mode: WorkspaceMode) {
  return mode === "portfolio" ? "Portfolio View" : "Research View";
}

export function getTabLabel(tabId: TabId) {
  for (const definitions of Object.values(WORKSPACE_TAB_DEFINITIONS)) {
    const match = definitions.find((tab) => tab.id === tabId);
    if (match) {
      return match.label;
    }
  }
  return tabId;
}

export function isWorkspaceTab(mode: WorkspaceMode, tabId: unknown): tabId is TabId {
  return typeof tabId === "string" && WORKSPACE_TAB_LOOKUP[mode].has(tabId as TabId);
}

export function getDefaultTabOrder(mode: WorkspaceMode): TabId[] {
  return [...DEFAULT_WORKSPACE_TAB_ORDER[mode]];
}

export function normalizeWorkspaceTabOrder(mode: WorkspaceMode, candidate: readonly unknown[] | null | undefined): TabId[] {
  const defaultOrder = DEFAULT_WORKSPACE_TAB_ORDER[mode];
  const nextOrder: TabId[] = [defaultOrder[0]];
  const seen = new Set<TabId>(nextOrder);

  for (const tabId of candidate ?? []) {
    if (!isWorkspaceTab(mode, tabId) || seen.has(tabId)) {
      continue;
    }
    nextOrder.push(tabId);
    seen.add(tabId);
  }

  for (const tabId of defaultOrder.slice(1)) {
    if (seen.has(tabId)) {
      continue;
    }
    nextOrder.push(tabId);
    seen.add(tabId);
  }

  return nextOrder;
}

export function normalizeWorkspaceTabOrderState(
  candidate: Partial<Record<WorkspaceMode, readonly unknown[] | null | undefined>> | null | undefined
): WorkspaceTabOrderState {
  return {
    portfolio: normalizeWorkspaceTabOrder("portfolio", candidate?.portfolio),
    research: normalizeWorkspaceTabOrder("research", candidate?.research),
  };
}

export function getOrderedWorkspaceTabs(mode: WorkspaceMode, orders: WorkspaceTabOrderState): WorkspaceTabDefinition[] {
  return normalizeWorkspaceTabOrder(mode, orders[mode]).map((tabId) => {
    const definition = WORKSPACE_TAB_LOOKUP[mode].get(tabId);
    if (!definition) {
      throw new Error(`Unknown ${mode} workspace tab: ${tabId}`);
    }
    return definition;
  });
}

export function moveWorkspaceTab(mode: WorkspaceMode, order: readonly TabId[], draggedTabId: TabId, dropIndex: number): TabId[] {
  const currentOrder = normalizeWorkspaceTabOrder(mode, order);
  const fromIndex = currentOrder.indexOf(draggedTabId);
  if (fromIndex <= 0) {
    return currentOrder;
  }

  const boundedDropIndex = Math.max(1, Math.min(dropIndex, currentOrder.length));
  const nextOrder = currentOrder.filter((tabId) => tabId !== draggedTabId);
  const insertionIndex = fromIndex < boundedDropIndex ? boundedDropIndex - 1 : boundedDropIndex;
  nextOrder.splice(insertionIndex, 0, draggedTabId);
  return nextOrder;
}

export function getShortcutHintForIndex(index: number) {
  return `Ctrl+${index + 1}`;
}

export function getModeShortcutHintForIndex(index: number) {
  return `Shift+${index + 1}`;
}

export function getTabShortcutHint(mode: WorkspaceMode, orders: WorkspaceTabOrderState, tabId: TabId) {
  const orderedTabs = normalizeWorkspaceTabOrder(mode, orders[mode]);
  const index = orderedTabs.indexOf(tabId);
  return index >= 0 ? getShortcutHintForIndex(index) : "";
}

export function getTabByShortcutIndex(mode: WorkspaceMode, orders: WorkspaceTabOrderState, shortcutIndex: number): TabId | null {
  const orderedTabs = normalizeWorkspaceTabOrder(mode, orders[mode]);
  return orderedTabs[shortcutIndex - 1] ?? null;
}

export function getTabModes(tabId: TabId): TabModeDefinition[] {
  return [...(TAB_MODE_DEFINITIONS[tabId] ?? [])].sort((left, right) => left.defaultIndex - right.defaultIndex);
}

export function getModeShortcutHint(tabId: TabId, modeId: string) {
  const modes = getTabModes(tabId);
  const index = modes.findIndex((mode) => mode.id === modeId);
  return index >= 0 ? getModeShortcutHintForIndex(index) : "";
}

export function getModeByShortcutIndex(tabId: TabId, shortcutIndex: number): TabModeDefinition | null {
  return getTabModes(tabId)[shortcutIndex - 1] ?? null;
}

export function defineTabModes(modes: readonly TabModeDefinition[]): readonly TabModeDefinition[] {
  const seenIds = new Set<string>();
  const seenIndexes = new Set<number>();
  for (const mode of modes) {
    if (!mode.id || seenIds.has(mode.id)) {
      throw new Error(`Duplicate or empty tab mode id: ${mode.id}`);
    }
    if (seenIndexes.has(mode.defaultIndex)) {
      throw new Error(`Duplicate tab mode defaultIndex: ${mode.defaultIndex}`);
    }
    seenIds.add(mode.id);
    seenIndexes.add(mode.defaultIndex);
  }
  return [...modes].sort((left, right) => left.defaultIndex - right.defaultIndex);
}

export function hasRegisteredModes(tabId: TabId) {
  return getTabModes(tabId).length > 0;
}

export function getModeRegistrySnapshot() {
  return Object.fromEntries(
    Object.entries(TAB_MODE_DEFINITIONS).map(([tabId, modes]) => [
      tabId,
      [...(modes ?? [])].map((mode) => ({ ...mode })),
    ])
  ) as Partial<Record<TabId, TabModeDefinition[]>>;
}
