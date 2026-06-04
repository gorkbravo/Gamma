<script lang="ts">
  import type { TabId } from "../lib/api/types";
  import { getDropIndexFromPointer } from "../lib/tab-reorder";

  export interface TabBarItem {
    id: TabId;
    label: string;
    pinned: boolean;
  }

  export let activeTab: TabId = "portfolio";
  export let open = false;
  export let tabs: TabBarItem[] = [];
  export let onSelect: (tab: TabId) => void;
  export let onClose: () => void = () => {};
  export let onReset: () => void = () => {};
  export let onReorder: (draggedTabId: TabId, dropIndex: number) => void = () => {};

  let tabListElement: HTMLDivElement | null = null;
  let draggingTabId: TabId | null = null;
  let dropIndex: number | null = null;
  let dragPointerId: number | null = null;
  let dragStartIndex: number | null = null;
  let dragStartY: number | null = null;
  let pointerMoved = false;

  function handleSelect(tab: TabId) {
    onSelect(tab);
    onClose();
  }

  function clearDragState() {
    draggingTabId = null;
    dropIndex = null;
    dragPointerId = null;
    dragStartIndex = null;
    dragStartY = null;
    pointerMoved = false;
  }

  function measureDropIndex(clientY: number) {
    if (!tabListElement) {
      return tabs.length;
    }

    const rows = Array.from(tabListElement.querySelectorAll<HTMLElement>(".tab-row")).map((row) => {
      const rect = row.getBoundingClientRect();
      return { top: rect.top, bottom: rect.bottom };
    });

    return getDropIndexFromPointer(rows, clientY, tabs.length);
  }

  function handlePointerStart(event: PointerEvent, tabId: TabId) {
    event.preventDefault();
    draggingTabId = tabId;
    dragPointerId = event.pointerId;
    dragStartIndex = tabs.findIndex((tab) => tab.id === tabId);
    dragStartY = event.clientY;
    dropIndex = dragStartIndex;
    pointerMoved = false;
  }

  function handlePointerMove(event: PointerEvent) {
    if (!draggingTabId || dragPointerId !== event.pointerId) {
      return;
    }

    pointerMoved = pointerMoved || (dragStartY != null && Math.abs(event.clientY - dragStartY) > 3);
    dropIndex = measureDropIndex(event.clientY);
  }

  function commitPointerReorder() {
    if (!draggingTabId || dropIndex == null) {
      clearDragState();
      return;
    }

    if (pointerMoved && dropIndex !== dragStartIndex) {
      onReorder(draggingTabId, dropIndex);
    }

    clearDragState();
  }

  function handlePointerEnd(event: PointerEvent) {
    if (dragPointerId !== event.pointerId) {
      return;
    }

    commitPointerReorder();
  }

  function handlePointerCancel(event: PointerEvent) {
    if (dragPointerId !== event.pointerId) {
      return;
    }

    clearDragState();
  }
</script>

<svelte:window on:pointermove={handlePointerMove} on:pointerup={handlePointerEnd} on:pointercancel={handlePointerCancel} />

{#if open}
  <div class="backdrop" on:click={onClose} on:keydown={(event) => event.key === "Escape" && onClose()} role="presentation"></div>
{/if}

<nav class="sidebar" data-open={open ? "true" : "false"} aria-label="Workspace navigation">
  <div class="sidebar-header">
    <div>
      <span class="sidebar-title">Navigation</span>
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
    bind:this={tabListElement}
    class="tab-list"
    role="list"
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
      >
        <div class="tab-row-main">
          {#if tab.pinned}
            <span class="tab-pin" aria-label="Pinned">
              <svg width="10" height="10" viewBox="0 0 16 16" fill="none">
                <path d="M10 1L6 5H3l-1 1 4 4-1 1v3l1-1 4-4 1 1v-3L8 3z" fill="currentColor" opacity="0.55" />
              </svg>
            </span>
          {:else}
            <button
              class="drag-handle"
              type="button"
              aria-label={`Reorder ${tab.label}`}
              on:pointerdown={(event) => handlePointerStart(event, tab.id)}
            >
              <span></span>
              <span></span>
              <span></span>
            </button>
          {/if}

          <button class="tab-button" class:selected={tab.id === activeTab} type="button" on:click={() => handleSelect(tab.id)}>
            <span class="tab-label">{tab.label}</span>
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
    background: color-mix(in srgb, var(--bg-0) 45%, transparent);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 50;
    width: 248px;
    height: 100vh;
    background: color-mix(in srgb, var(--bg-0) 98%, var(--accent) 2%);
    border-right: 1px solid var(--panel-border);
    transform: translateX(-100%);
    transition: transform 180ms ease;
    display: flex;
    flex-direction: column;
    padding: 0;
  }

  .sidebar[data-open="true"] {
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

  .sidebar-actions {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .header-btn,
  .close-btn,
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
  .tab-button:hover {
    color: var(--text-0);
    border-color: color-mix(in srgb, var(--accent) 32%, transparent);
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
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    cursor: grab;
    border-radius: 2px;
    touch-action: none;
  }

  .drag-handle span {
    display: block;
    width: 0.55rem;
    height: 1.5px;
    border-radius: 2px;
    background: currentColor;
    opacity: 0.45;
  }

  .tab-row.dragging .drag-handle,
  .drag-handle:active {
    cursor: grabbing;
  }

  .tab-pin {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 0.35rem;
    color: var(--text-2);
  }

  .tab-button {
    display: flex;
    align-items: center;
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
    background: color-mix(in srgb, var(--accent) 8%, transparent);
    border-color: color-mix(in srgb, var(--accent) 36%, transparent);
    color: var(--text-0);
  }

  .tab-label {
    display: inline-block;
  }

  .insertion-marker {
    height: 2px;
    margin-left: 2rem;
    background: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 18%, transparent);
  }
</style>
