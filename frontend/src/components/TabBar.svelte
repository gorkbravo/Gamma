<script lang="ts">
  import type { TabId, WorkspaceMode } from "../lib/api/types";

  export let activeTab: TabId = "portfolio";
  export let mode: WorkspaceMode = "portfolio";
  export let onSelect: (tab: TabId) => void;
  let tabs: Array<{ id: TabId; label: string }> = [];

  $: tabs = [
    { id: mode === "portfolio" ? "portfolio" : "research", label: mode === "portfolio" ? "Portfolio" : "Research" },
    ...(mode === "research" ? [{ id: "prediction_markets" as TabId, label: "Prediction Markets" }] : []),
    { id: "risk", label: "Risk" },
    { id: "iv", label: "IV" }
  ] satisfies Array<{ id: TabId; label: string }>;
</script>

<nav class="tabs">
  <div class="tab-list">
    {#each tabs as tab}
      <button class:selected={tab.id === activeTab} on:click={() => onSelect(tab.id)}>
        {tab.label}
      </button>
    {/each}
  </div>
</nav>

<style>
  .tabs {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.55rem 0.75rem;
    border: 1px solid var(--panel-border);
    background: var(--surface-1);
  }

  .tab-list {
    display: flex;
    gap: 0.45rem;
    flex-wrap: wrap;
  }

  button {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    padding: 0.62rem 0.9rem;
    cursor: pointer;
    min-width: 6.5rem;
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
  @media (max-width: 900px) {
    .tabs {
      padding-inline: 0.65rem;
    }
  }
</style>
