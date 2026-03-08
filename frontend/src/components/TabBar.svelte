<script lang="ts">
  import type { TabId, WorkspaceMode } from "../lib/api/types";

  export let activeTab: TabId = "portfolio";
  export let mode: WorkspaceMode = "portfolio";
  export let onSelect: (tab: TabId) => void;
  export let onSwitchWorkspace: () => void;
  let tabs: Array<{ id: TabId; label: string }> = [];

  $: tabs = [
    { id: mode === "portfolio" ? "portfolio" : "research", label: mode === "portfolio" ? "Portfolio" : "Research" },
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
  <button class="switcher" on:click={onSwitchWorkspace}>Switch View</button>
</nav>

<style>
  .tabs {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.4rem;
    padding: 0.45rem;
    border: 1px solid var(--panel-border);
    background: rgba(7, 11, 15, 0.88);
    margin-bottom: 1rem;
  }

  .tab-list {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
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

  .switcher {
    min-width: auto;
    white-space: nowrap;
  }

  @media (max-width: 900px) {
    .tabs {
      flex-direction: column;
      align-items: stretch;
    }

    .switcher {
      width: 100%;
    }
  }
</style>
