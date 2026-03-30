import { get, writable } from "svelte/store";
import type { TabId, WorkspaceMode, WorkspaceTabOrderState } from "../api/types";
import {
  getDefaultTabOrder,
  moveWorkspaceTab,
  normalizeWorkspaceTabOrderState,
} from "../navigation";

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem?(key: string): void;
}

const TAB_ORDER_STORAGE_KEY = "gamma.navigation.tab-order.v1";

function resolveBrowserStorage(): StorageLike | null {
  if (typeof window === "undefined" || !("localStorage" in window)) {
    return null;
  }
  return window.localStorage;
}

function readPersistedTabOrderState(storage: StorageLike | null): WorkspaceTabOrderState {
  if (!storage) {
    return normalizeWorkspaceTabOrderState(null);
  }

  const rawValue = storage.getItem(TAB_ORDER_STORAGE_KEY);
  if (!rawValue) {
    return normalizeWorkspaceTabOrderState(null);
  }

  try {
    return normalizeWorkspaceTabOrderState(JSON.parse(rawValue) as Partial<Record<WorkspaceMode, unknown[]>>);
  } catch {
    return normalizeWorkspaceTabOrderState(null);
  }
}

function persistTabOrderState(storage: StorageLike | null, value: WorkspaceTabOrderState) {
  if (!storage) {
    return;
  }
  storage.setItem(TAB_ORDER_STORAGE_KEY, JSON.stringify(value));
}

export function createWorkspaceTabOrderStore(storage: StorageLike | null = resolveBrowserStorage()) {
  const store = writable<WorkspaceTabOrderState>(readPersistedTabOrderState(storage));
  const canSyncWindowStorage = storage != null && typeof window !== "undefined" && storage === window.localStorage;

  const syncFromStorage = () => {
    store.set(readPersistedTabOrderState(storage));
  };

  const setState = (nextState: WorkspaceTabOrderState) => {
    const normalized = normalizeWorkspaceTabOrderState(nextState);
    store.set(normalized);
    persistTabOrderState(storage, normalized);
  };

  const handleStorageEvent = (event: StorageEvent) => {
    if (event.key !== TAB_ORDER_STORAGE_KEY) {
      return;
    }
    syncFromStorage();
  };

  if (canSyncWindowStorage) {
    window.addEventListener("storage", handleStorageEvent);
  }

  return {
    subscribe: store.subscribe,
    setWorkspaceOrder(mode: WorkspaceMode, order: readonly TabId[]) {
      const current = get(store);
      setState({
        ...current,
        [mode]: [...order],
      });
    },
    reorder(mode: WorkspaceMode, draggedTabId: TabId, dropIndex: number) {
      const current = get(store);
      setState({
        ...current,
        [mode]: moveWorkspaceTab(mode, current[mode], draggedTabId, dropIndex),
      });
    },
    reset(mode: WorkspaceMode) {
      const current = get(store);
      setState({
        ...current,
        [mode]: getDefaultTabOrder(mode),
      });
    },
    restore() {
      syncFromStorage();
    },
    destroy() {
      if (canSyncWindowStorage) {
        window.removeEventListener("storage", handleStorageEvent);
      }
    },
  };
}

const workspaceTabOrderStore = createWorkspaceTabOrderStore();

export const workspaceTabOrders = {
  subscribe: workspaceTabOrderStore.subscribe,
};

export const setWorkspaceTabOrder = workspaceTabOrderStore.setWorkspaceOrder;
export const reorderWorkspaceTab = workspaceTabOrderStore.reorder;
export const resetWorkspaceTabOrder = workspaceTabOrderStore.reset;
export const restoreWorkspaceTabOrders = workspaceTabOrderStore.restore;
