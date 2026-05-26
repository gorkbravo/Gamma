import type {
  ActionKeybindingDefinition,
  TabId,
  WorkspaceMode,
  WorkspaceTabDefinition,
  WorkspaceTabOrderState,
} from "./api/types";

export const WORKSPACE_TAB_DEFINITIONS = {
  portfolio: [
    { id: "portfolio", label: "PORTFOLIO", pinned: true, defaultIndex: 0 },
    { id: "risk", label: "RISK", pinned: false, defaultIndex: 1 },
    { id: "iv", label: "OPTIONS", pinned: false, defaultIndex: 2 },
  ],
  research: [
    { id: "sitrep", label: "SITREP", pinned: true, defaultIndex: 0 },
    { id: "equity_research", label: "EQUITY RESEARCH", pinned: false, defaultIndex: 1 },
    { id: "strategy_lab", label: "STRATEGY LAB", pinned: false, defaultIndex: 2 },
    { id: "macro", label: "MACRO", pinned: false, defaultIndex: 3 },
    { id: "prediction_markets", label: "PREDICTION MARKETS", pinned: false, defaultIndex: 4 },
    { id: "crypto", label: "CRYPTO", pinned: false, defaultIndex: 5 },
    { id: "fundamentals", label: "FUNDAMENTALS", pinned: false, defaultIndex: 6 },
    { id: "commodities", label: "COMMODITIES", pinned: false, defaultIndex: 7 },
    { id: "maritime", label: "SEALANES", pinned: false, defaultIndex: 8 },
    { id: "copilot", label: "COPILOT", pinned: false, defaultIndex: 9 },
    { id: "risk", label: "RISK", pinned: false, defaultIndex: 10 },
    { id: "iv", label: "OPTIONS", pinned: false, defaultIndex: 11 },
  ],
} satisfies Record<WorkspaceMode, readonly WorkspaceTabDefinition[]>;

export interface TabModeDefinition {
  id: string;
  label: string;
  defaultIndex: number;
}

export interface NavigationRouteMatch {
  tab: WorkspaceTabDefinition;
  mode: TabModeDefinition | null;
}

export const TAB_MODE_DEFINITIONS: Partial<Record<TabId, readonly TabModeDefinition[]>> = {
  equity_research: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "scope_analysis", label: "Scope Analysis", defaultIndex: 1 },
    { id: "comparables", label: "Comparables", defaultIndex: 2 },
    { id: "scenario_context", label: "Scenario / Context", defaultIndex: 3 },
    { id: "saved_equity_research", label: "Saved Equity Research", defaultIndex: 4 },
  ]),
  strategy_lab: defineTabModes([
    { id: "composer", label: "Composer", defaultIndex: 0 },
    { id: "backtest_analyze", label: "Backtest / Analyze", defaultIndex: 1 },
    { id: "regime_stress", label: "Regime / Stress", defaultIndex: 2 },
    { id: "imports", label: "Imports", defaultIndex: 3 },
    { id: "saved_runs", label: "Saved Runs", defaultIndex: 4 },
  ]),
  macro: defineTabModes([
    { id: "snapshot", label: "Snapshot", defaultIndex: 0 },
    { id: "cross_asset", label: "Cross-Asset", defaultIndex: 1 },
    { id: "rates_policy", label: "Rates & Policy", defaultIndex: 2 },
    { id: "events_regimes", label: "Events / Regimes", defaultIndex: 3 },
    { id: "trade_partners", label: "Trade Partners", defaultIndex: 4 },
    { id: "country_compare", label: "Country Compare", defaultIndex: 5 },
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
  commodities: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "energy", label: "Energy", defaultIndex: 1 },
    { id: "metals", label: "Metals", defaultIndex: 2 },
    { id: "curves_spreads", label: "Curves & Spreads", defaultIndex: 3 },
    { id: "inventories_fundamentals", label: "Inventories & Fundamentals", defaultIndex: 4 },
    { id: "events_cross_domain", label: "Events / Cross-Domain", defaultIndex: 5 },
  ]),
  maritime: defineTabModes([
    { id: "live_map", label: "Live Map", defaultIndex: 0 },
    { id: "chokepoints", label: "Chokepoints", defaultIndex: 1 },
    { id: "trade_flows", label: "Trade Flows", defaultIndex: 2 },
    { id: "fleet_monitoring", label: "Fleet / Vessel", defaultIndex: 3 },
    { id: "event_replay", label: "Event Replay", defaultIndex: 4 },
  ]),
  iv: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "chain", label: "Chain", defaultIndex: 1 },
    { id: "surface", label: "Surface", defaultIndex: 2 },
    { id: "realized_implied", label: "Realized vs IV", defaultIndex: 3 },
    { id: "distribution", label: "Implied Distribution", defaultIndex: 4 },
    { id: "strategies", label: "Strategies", defaultIndex: 5 },
  ]),
  risk: defineTabModes([
    { id: "overview", label: "Overview", defaultIndex: 0 },
    { id: "exposures", label: "Exposures", defaultIndex: 1 },
    { id: "drawdowns", label: "Drawdowns", defaultIndex: 2 },
    { id: "correlation", label: "Correlation", defaultIndex: 3 },
    { id: "scenarios", label: "Scenarios", defaultIndex: 4 },
    { id: "optimization", label: "Optimization", defaultIndex: 5 },
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
  {
    id: "previous_tab",
    label: "Previous tab",
    description: "Move to the previous tab in the current workspace order.",
    combos: [{ id: "previous-tab-primary", label: "Ctrl+Left", key: "arrowleft", ctrl: true }],
  },
  {
    id: "next_tab",
    label: "Next tab",
    description: "Move to the next tab in the current workspace order.",
    combos: [{ id: "next-tab-primary", label: "Ctrl+Right", key: "arrowright", ctrl: true }],
  },
  {
    id: "previous_mode",
    label: "Previous mode",
    description: "Move to the previous mode inside the active tab.",
    combos: [{ id: "previous-mode-primary", label: "Shift+Left", key: "arrowleft", shift: true }],
  },
  {
    id: "next_mode",
    label: "Next mode",
    description: "Move to the next mode inside the active tab.",
    combos: [{ id: "next-mode-primary", label: "Shift+Right", key: "arrowright", shift: true }],
  },
] as const;

const WORKSPACE_TAB_LOOKUP: Record<WorkspaceMode, Map<TabId, WorkspaceTabDefinition>> = {
  portfolio: new Map(WORKSPACE_TAB_DEFINITIONS.portfolio.map((tab) => [tab.id, tab])),
  research: new Map(WORKSPACE_TAB_DEFINITIONS.research.map((tab) => [tab.id, tab])),
};

const LEGACY_TAB_ALIASES: Partial<Record<WorkspaceMode, Record<string, TabId>>> = {
  research: {
    research: "equity_research",
  },
};

type ResearchSplitTabId = "equity_research" | "strategy_lab";

const LEGACY_RESEARCH_MODE_ALIASES: Record<string, { tabId: ResearchSplitTabId; modeId: string }> = {
  overview: { tabId: "equity_research", modeId: "overview" },
  scope: { tabId: "equity_research", modeId: "scope_analysis" },
  scope_analysis: { tabId: "equity_research", modeId: "scope_analysis" },
  strategy: { tabId: "strategy_lab", modeId: "imports" },
  strategy_lab: { tabId: "strategy_lab", modeId: "imports" },
  compare: { tabId: "strategy_lab", modeId: "backtest_analyze" },
  compare_scenario: { tabId: "strategy_lab", modeId: "backtest_analyze" },
  saved: { tabId: "strategy_lab", modeId: "saved_runs" },
  saved_research: { tabId: "strategy_lab", modeId: "saved_runs" },
};

function normalizeLegacyTabId(mode: WorkspaceMode, tabId: unknown): unknown {
  if (typeof tabId !== "string") return tabId;
  return LEGACY_TAB_ALIASES[mode]?.[tabId] ?? tabId;
}

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

  for (const rawTabId of candidate ?? []) {
    const tabId = normalizeLegacyTabId(mode, rawTabId);
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

export function normalizeNavigationSearchTerm(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/['’]/g, "")
    .replace(/&/g, " and ")
    .replace(/[_\-/]+/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function matchesNavigationSegment(definition: { id: string; label: string }, segment: string) {
  const normalizedSegment = normalizeNavigationSearchTerm(segment);
  if (!normalizedSegment) {
    return false;
  }
  const normalizedLabel = normalizeNavigationSearchTerm(definition.label);
  const normalizedId = normalizeNavigationSearchTerm(definition.id);
  return (
    normalizedLabel === normalizedSegment ||
    normalizedId === normalizedSegment ||
    normalizedLabel.includes(normalizedSegment) ||
    normalizedId.includes(normalizedSegment) ||
    isCloseNavigationSegment(normalizedLabel, normalizedSegment) ||
    isCloseNavigationSegment(normalizedId, normalizedSegment)
  );
}

function isCloseNavigationSegment(candidate: string, segment: string) {
  if (segment.length < 4 || Math.abs(candidate.length - segment.length) > 2) {
    return false;
  }
  return boundedEditDistance(candidate, segment, 2) <= 2;
}

function boundedEditDistance(left: string, right: string, maxDistance: number) {
  let previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    const current = [leftIndex];
    let rowMinimum = current[0];
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitutionCost = left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1;
      const value = Math.min(
        previous[rightIndex] + 1,
        current[rightIndex - 1] + 1,
        previous[rightIndex - 1] + substitutionCost
      );
      current[rightIndex] = value;
      rowMinimum = Math.min(rowMinimum, value);
    }
    if (rowMinimum > maxDistance) {
      return maxDistance + 1;
    }
    previous = current;
  }
  return previous[right.length];
}

export function resolveNavigationPath(
  mode: WorkspaceMode,
  orders: WorkspaceTabOrderState,
  path: string
): NavigationRouteMatch | null {
  const trimmed = path.trim();
  if (!trimmed.startsWith("/")) {
    return null;
  }

  const [tabSegment, modeSegment] = trimmed
    .split("/")
    .slice(1)
    .map((segment) => segment.trim())
    .filter(Boolean);

  if (!tabSegment) {
    return null;
  }

  if (mode === "research" && matchesNavigationSegment({ id: "research", label: "Research" }, tabSegment)) {
    const tab = WORKSPACE_TAB_LOOKUP.research.get("equity_research");
    if (!tab) {
      return null;
    }
    if (!modeSegment) {
      return { tab, mode: null };
    }

    const legacyModeKey = normalizeNavigationSearchTerm(modeSegment ?? "").replace(/\s+/g, "_");
    const mapped = LEGACY_RESEARCH_MODE_ALIASES[legacyModeKey];
    if (mapped) {
      const mappedTab = WORKSPACE_TAB_LOOKUP.research.get(mapped.tabId);
      const routeMode = getTabModes(mapped.tabId).find((candidate) => candidate.id === mapped.modeId) ?? null;
      return mappedTab ? { tab: mappedTab, mode: routeMode } : null;
    }

    const equityMode = getTabModes("equity_research").find((candidate) => matchesNavigationSegment(candidate, modeSegment));
    return equityMode ? { tab, mode: equityMode } : null;
  }

  const tab = getOrderedWorkspaceTabs(mode, orders).find((candidate) => matchesNavigationSegment(candidate, tabSegment));
  if (!tab) {
    return null;
  }

  if (!modeSegment) {
    return { tab, mode: null };
  }

  const tabMode = getTabModes(tab.id).find((candidate) => matchesNavigationSegment(candidate, modeSegment));
  return tabMode ? { tab, mode: tabMode } : null;
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
