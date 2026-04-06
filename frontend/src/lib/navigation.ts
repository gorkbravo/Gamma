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
    { id: "risk", label: "Risk", pinned: false, defaultIndex: 4 },
    { id: "iv", label: "IV", pinned: false, defaultIndex: 5 },
  ],
} satisfies Record<WorkspaceMode, readonly WorkspaceTabDefinition[]>;

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

export function getTabShortcutHint(mode: WorkspaceMode, orders: WorkspaceTabOrderState, tabId: TabId) {
  const orderedTabs = normalizeWorkspaceTabOrder(mode, orders[mode]);
  const index = orderedTabs.indexOf(tabId);
  return index >= 0 ? getShortcutHintForIndex(index) : "";
}

export function getTabByShortcutIndex(mode: WorkspaceMode, orders: WorkspaceTabOrderState, shortcutIndex: number): TabId | null {
  const orderedTabs = normalizeWorkspaceTabOrder(mode, orders[mode]);
  return orderedTabs[shortcutIndex - 1] ?? null;
}
