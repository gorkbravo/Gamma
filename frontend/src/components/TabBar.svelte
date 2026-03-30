<script lang="ts">
  import type { TabId } from "../lib/api/types";

  export interface TabBarItem {
    id: TabId;
    label: string;
    pinned: boolean;
    shortcutHint: string;
  }

  export let activeTab: TabId = "portfolio";
  export let open = false;
  export let tabs: TabBarItem[] = [];
  export let onSelect: (tab: TabId) => void;
  export let onClose: () => void = () => {};
  export let onReset: () => void = () => {};
  export let onReorder: (draggedTabId: TabId, dropIndex: number) => void = () => {};

  let draggingTabId: TabId | null = null;
  let dropIndex: number | null = null;

  function handleSelect(tab: TabId) {
    onSelect(tab);
    onClose();
  }

  function clearDragState() {
    draggingTabId = null;
    dropIndex = null;
  }

  function handleDragStart(event: DragEvent, tabId: TabId) {
    draggingTabId = tabId;
    dropIndex = tabs.findIndex((tab) => tab.id === tabId);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", tabId);
    }
  }

  function handleDragOver(event: DragEvent, index: number) {
    if (!draggingTabId) {
      return;
    }

    event.preventDefault();
    const row = event.currentTarget as HTMLElement;
    const rect = row.getBoundingClientRect();
    const nextDropIndex = event.clientY < rect.top + rect.height / 2 ? index : index + 1;
    dropIndex = Math.max(1, Math.min(nextDropIndex, tabs.length));
  }

  function handleListDragOver(event: DragEvent) {
    if (!draggingTabId) {
      return;
    }
    event.preventDefault();
    if (dropIndex == null) {
      dropIndex = tabs.length;
    }
  }

  function handleDrop(event: DragEvent) {
    if (!draggingTabId || dropIndex == null) {
      clearDragState();
      return;
    }
    event.preventDefault();
    onReorder(draggingTabId, dropIndex);
    clearDragState();
  }
</script>

{#if open}
  <div class="backdrop" on:click={onClose} on:keydown={(event) => event.key === "Escape" && onClose()} role="presentation"></div>
{/if}

<nav class="sidebar" class:open aria-label="Workspace navigation">
  <div class="sidebar-header">
    <div>
      <span class="sidebar-title">Navigation</span>
      <small class="sidebar-subtitle">Visual order controls `Ctrl+1...N`.</small>
    </div>
    <div class="sidebar-actions">
      <button class="header-btn" type="button" on:click={onReset}>Reset</button>
      <button class="close-btn" type="button" on:click={onClose} aria-label="Close navigation">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>
    </div>
  </div>

  <div
    class="tab-list"
    role="list"
    on:dragover={handleListDragOver}
    on:drop={handleDrop}
  >
    {#if draggingTabId && dropIndex === 1}
      <div class="insertion-marker" aria-hidden="true"></div>
    {/if}

    {#each tabs as tab, index}
      <div
        class="tab-row"
        class:selected={tab.id === activeTab}
        class:dragging={draggingTabId === tab.id}
        role="listitem"
        on:dragover={(event) => handleDragOver(event, index)}
        on:drop={handleDrop}
      >
        <div class="tab-row-main">
          {#if tab.pinned}
            <span class="tab-badge">Pinned</span>
          {:else}
            <button
              class="drag-handle"
              type="button"
              draggable="true"
              aria-label={`Reorder ${tab.label}`}
              on:dragstart={(event) => handleDragStart(event, tab.id)}
              on:dragend={clearDragState}
            >
              <span></span>
              <span></span>
              <span></span>
            </button>
          {/if}

          <button class="tab-button" class:selected={tab.id === activeTab} type="button" on:click={() => handleSelect(tab.id)}>
            <span class="tab-label">{tab.label}</span>
            <span class="tab-hint">{tab.shortcutHint}</span>
          </button>
        </div>
      </div>

      {#if draggingTabId && dropIndex === index + 1 && index + 1 < tabs.length}
        <div class="insertion-marker" aria-hidden="true"></div>
      {/if}
    {/each}

    {#if draggingTabId && dropIndex === tabs.length}
      <div class="insertion-marker" aria-hidden="true"></div>
    {/if}
  </div>
</nav>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: rgba(0, 0, 0, 0.45);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 50;
    width: 248px;
    height: 100vh;
    background: rgba(8, 13, 18, 0.98);
    border-right: 1px solid var(--panel-border);
    transform: translateX(-100%);
    transition: transform 180ms ease;
    display: flex;
    flex-direction: column;
    padding: 0;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.75rem;
    border-bottom: 1px solid var(--panel-border);
  }

  .sidebar-title {
    display: block;
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-2);
  }

  .sidebar-subtitle {
    display: block;
    margin-top: 0.2rem;
    color: var(--text-2);
    font-size: 0.7rem;
    line-height: 1.4;
  }

  .sidebar-actions {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .header-btn,
  .close-btn,
  .drag-handle,
  .tab-button {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    font: inherit;
  }

  .header-btn,
  .close-btn {
    cursor: pointer;
    border-radius: 2px;
    transition: color 120ms ease, border-color 120ms ease;
  }

  .header-btn {
    padding: 0.2rem 0.4rem;
    font-size: 0.72rem;
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.2rem;
  }

  .header-btn:hover,
  .close-btn:hover,
  .drag-handle:hover,
  .tab-button:hover {
    color: var(--text-0);
    border-color: rgba(122, 166, 200, 0.32);
  }

  .tab-list {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    padding: 0.55rem 0.5rem 0.8rem;
  }

  .tab-row {
    display: grid;
    gap: 0.18rem;
  }

  .tab-row-main {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 0.35rem;
    align-items: stretch;
  }

  .tab-row.dragging {
    opacity: 0.72;
  }

  .drag-handle {
    display: grid;
    align-content: center;
    gap: 0.14rem;
    padding: 0.45rem 0.35rem;
    cursor: grab;
    border-radius: 2px;
  }

  .drag-handle span {
    display: block;
    width: 0.7rem;
    height: 2px;
    border-radius: 99px;
    background: currentColor;
    opacity: 0.7;
  }

  .tab-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 3rem;
    padding: 0 0.45rem;
    border: 1px solid rgba(122, 166, 200, 0.28);
    color: var(--accent);
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .tab-button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    padding: 0.58rem 0.7rem;
    cursor: pointer;
    text-align: left;
    font-size: 0.82rem;
    border-radius: 2px;
    transition: border-color 120ms ease, background 120ms ease, color 120ms ease;
  }

  .tab-button.selected,
  .tab-row.selected .tab-button {
    background: rgba(122, 166, 200, 0.08);
    border-color: rgba(122, 166, 200, 0.36);
    color: var(--text-0);
  }

  .tab-label,
  .tab-hint {
    display: inline-block;
  }

  .tab-hint {
    color: var(--text-2);
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }

  .insertion-marker {
    height: 2px;
    margin-left: 3.35rem;
    background: linear-gradient(90deg, rgba(122, 166, 200, 0.85), rgba(122, 166, 200, 0.18));
    box-shadow: 0 0 0 1px rgba(122, 166, 200, 0.14);
  }
</style>
