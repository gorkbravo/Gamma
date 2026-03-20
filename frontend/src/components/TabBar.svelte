<script lang="ts">
  import type { TabId, WorkspaceMode } from "../lib/api/types";

  export let activeTab: TabId = "portfolio";
  export let mode: WorkspaceMode = "portfolio";
  export let open = false;
  export let onSelect: (tab: TabId) => void;
  export let onClose: () => void = () => {};
  let tabs: Array<{ id: TabId; label: string }> = [];

  $: tabs = [
    { id: mode === "portfolio" ? "portfolio" : "research", label: mode === "portfolio" ? "Portfolio" : "Research" },
    ...(mode === "research" ? [{ id: "macro" as TabId, label: "Macro" }] : []),
    ...(mode === "research" ? [{ id: "prediction_markets" as TabId, label: "Prediction Markets" }] : []),
    { id: "risk", label: "Risk" },
    { id: "iv", label: "IV" }
  ] satisfies Array<{ id: TabId; label: string }>;

  function handleSelect(tab: TabId) {
    onSelect(tab);
    onClose();
  }
</script>

{#if open}
  <div class="backdrop" on:click={onClose} on:keydown={e => e.key === 'Escape' && onClose()} role="presentation"></div>
{/if}

<nav class="sidebar" class:open aria-label="Workspace navigation">
  <div class="sidebar-header">
    <span class="sidebar-title">Navigation</span>
    <button class="close-btn" on:click={onClose} aria-label="Close navigation">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>
  </div>
  <div class="tab-list">
    {#each tabs as tab}
      <button class:selected={tab.id === activeTab} on:click={() => handleSelect(tab.id)}>
        {tab.label}
      </button>
    {/each}
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
    width: 220px;
    height: 100vh;
    background: rgba(8, 13, 18, 0.98);
    border-right: 1px solid var(--panel-border);
    transform: translateX(-100%);
    transition: transform 200ms ease;
    display: flex;
    flex-direction: column;
    padding: 0;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.65rem 0.75rem;
    border-bottom: 1px solid var(--panel-border);
  }

  .sidebar-title {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-2);
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-2);
    padding: 0.15rem;
    cursor: pointer;
    border-radius: 2px;
    transition: color 120ms ease, border-color 120ms ease;
  }

  .close-btn:hover {
    color: var(--text-0);
    border-color: rgba(122, 166, 200, 0.32);
  }

  .tab-list {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.5rem;
  }

  button {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    padding: 0.55rem 0.75rem;
    cursor: pointer;
    text-align: left;
    font-size: 0.82rem;
    transition: border-color 120ms ease, background 120ms ease, color 120ms ease;
  }

  button:hover {
    border-color: rgba(122, 166, 200, 0.32);
    color: var(--text-0);
  }

  .selected {
    background: rgba(122, 166, 200, 0.08);
    border-color: rgba(122, 166, 200, 0.36);
    color: var(--text-0);
  }
</style>
