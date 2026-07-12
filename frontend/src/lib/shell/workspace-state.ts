import { getTabModes, isWorkspaceTab } from "../navigation";
import type { TabId, WorkspaceMode } from "../api/types";

export const WORKSPACE_STATE_STORAGE_KEY = "gamma.workspace.state.v1";

export type PersistedWorkspaceState = {
  workspaceMode: WorkspaceMode;
  activeTab: TabId;
  modes?: Partial<Record<TabId, string>>;
};

export function loadPersistedWorkspaceState(): PersistedWorkspaceState | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const parsed = JSON.parse(localStorage.getItem(WORKSPACE_STATE_STORAGE_KEY) ?? "null") as Partial<PersistedWorkspaceState> | null;
    if (
      !parsed ||
      (parsed.workspaceMode !== "portfolio" && parsed.workspaceMode !== "research") ||
      typeof parsed.activeTab !== "string" ||
      !isWorkspaceTab(parsed.workspaceMode, parsed.activeTab)
    ) return null;
    return {
      workspaceMode: parsed.workspaceMode,
      activeTab: parsed.activeTab,
      modes: parsed.modes && typeof parsed.modes === "object" ? parsed.modes : {}
    };
  } catch {
    return null;
  }
}

export function persistedMode<T extends string>(state: PersistedWorkspaceState | null, tabId: TabId, fallback: T): T {
  const modeId = state?.modes?.[tabId];
  return modeId && getTabModes(tabId).some((mode) => mode.id === modeId) ? (modeId as T) : fallback;
}

export function persistWorkspaceState(state: PersistedWorkspaceState | null): void {
  if (typeof localStorage === "undefined") return;
  try {
    if (!state) localStorage.removeItem(WORKSPACE_STATE_STORAGE_KEY);
    else localStorage.setItem(WORKSPACE_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Reload recovery is best-effort; live navigation state remains authoritative.
  }
}
