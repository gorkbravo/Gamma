<script lang="ts">
  import type { TabId } from "../lib/api/types";

  export let activeTab: TabId = "portfolio";
  export let onSelect: (tab: TabId) => void;

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "portfolio", label: "Portfolio" },
    { id: "research", label: "Research" },
    { id: "risk", label: "Risk" },
    { id: "iv", label: "IV" }
  ];
</script>

<nav class="tabs">
  {#each tabs as tab}
    <button class:selected={tab.id === activeTab} on:click={() => onSelect(tab.id)}>
      {tab.label}
    </button>
  {/each}
</nav>

<style>
  .tabs {
    display: flex;
    gap: 0.4rem;
    padding: 0.45rem;
    border: 1px solid var(--panel-border);
    background: rgba(7, 11, 15, 0.88);
    margin-bottom: 1rem;
  }

  button {
    border: 1px solid var(--panel-border);
    background: #070b0f;
    color: var(--text-1);
    padding: 0.7rem 1rem;
    cursor: pointer;
    min-width: 7rem;
    transition: border-color 120ms ease, background 120ms ease, color 120ms ease;
  }

  button:hover {
    border-color: #56748e;
    color: var(--text-0);
  }

  .selected {
    background: var(--bg-3);
    border-color: #355672;
    color: var(--text-0);
  }
</style>
