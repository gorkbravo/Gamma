<script lang="ts">
  import type { TabId } from "../lib/api/types";
  import type { TabBarItem } from "./TabBar.svelte";

  export let title = "Gamma";
  export let activeTab: TabId = "portfolio";
  export let tabs: TabBarItem[] = [];
  export let copilotOpen = false;
  export let onToggleSidebar: () => void = () => {};
  export let onToggleCopilot: () => void = () => {};
  export let onSelectTab: (tab: TabId) => void = () => {};

  let searchValue = "";
  let searchFocused = false;
  let previousActiveTab: TabId = activeTab;

  function normalizeSearchTerm(value: string) {
    return value.trim().toLowerCase().replace(/[_\s]+/g, " ");
  }

  $: normalizedSearchValue = normalizeSearchTerm(searchValue);
  $: matchingTabs =
    normalizedSearchValue.length === 0
      ? []
      : tabs.filter((tab) => {
          const label = normalizeSearchTerm(tab.label);
          const id = normalizeSearchTerm(tab.id);
          return label.includes(normalizedSearchValue) || id.includes(normalizedSearchValue);
        });
  $: showSearchResults = searchFocused && normalizedSearchValue.length > 0;
  $: if (activeTab !== previousActiveTab) {
    previousActiveTab = activeTab;
    searchValue = "";
    searchFocused = false;
  }

  function handleSearchSelect(tabId: TabId) {
    onSelectTab(tabId);
    searchValue = "";
    searchFocused = false;
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && matchingTabs.length > 0) {
      event.preventDefault();
      handleSearchSelect(matchingTabs[0].id);
      return;
    }

    if (event.key === "Escape") {
      searchValue = "";
      searchFocused = false;
    }
  }
</script>

<div class="shell">
  <header class="topbar">
    <div class="brand">
      <button class="hamburger" on:click={onToggleSidebar} aria-label="Toggle navigation">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M2.5 4h11M2.5 8h11M2.5 12h11" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
        </svg>
      </button>
      <img class="mark" src="/gamma-mark.svg" alt="" aria-hidden="true" />
      <h1>{title}</h1>
      <span class="topbar-divider" aria-hidden="true"></span>
      <div class="tab-search">
        <label class="tab-search-input">
          <span class="search-icon" aria-hidden="true">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.2" />
              <path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
            </svg>
          </span>
          <input
            bind:value={searchValue}
            type="search"
            placeholder="Search tabs"
            aria-label="Search tabs"
            autocomplete="off"
            autocorrect="off"
            autocapitalize="off"
            spellcheck="false"
            on:focus={() => searchFocused = true}
            on:blur={() => setTimeout(() => searchFocused = false, 120)}
            on:keydown={handleSearchKeydown}
          />
        </label>

        {#if showSearchResults}
          <div class="tab-search-results" role="listbox" aria-label="Matching tabs">
            {#if matchingTabs.length > 0}
              {#each matchingTabs as tab}
                <button
                  class="tab-search-result"
                  class:selected={tab.id === activeTab}
                  type="button"
                  on:mousedown|preventDefault={() => handleSearchSelect(tab.id)}
                >
                  <span>{tab.label}</span>
                  {#if tab.id === activeTab}
                    <span class="tab-search-result-state">Current</span>
                  {/if}
                </button>
              {/each}
            {:else}
              <div class="tab-search-empty">No matching tabs</div>
            {/if}
          </div>
        {/if}
      </div>
      <button
        class="copilot-trigger"
        class:open={copilotOpen}
        on:click={onToggleCopilot}
        aria-expanded={copilotOpen}
        aria-haspopup="dialog"
      >
        Copilot
      </button>
    </div>
    <div class="status-slot">
      <slot name="status" />
    </div>
  </header>

  <main class="content">
    <slot />
  </main>
</div>

<style>
  .shell {
    width: min(1600px, calc(100vw - 1.5rem));
    margin: 0 auto;
    padding: 0.5rem 0 1.1rem;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.6rem;
    padding: 0.4rem 0.75rem;
    border: 1px solid var(--panel-border);
    border-radius: 0;
    background: var(--surface-0);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    min-width: 0;
  }

  .topbar-divider {
    width: 1px;
    align-self: stretch;
    background: var(--divider);
  }

  .tab-search {
    position: relative;
    flex: 1 1 17rem;
    min-width: 11rem;
    max-width: 24rem;
  }

  .tab-search-input {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    width: 100%;
    padding: 0.28rem 0.55rem;
    border: 1px solid var(--panel-border);
    border-radius: 3px;
    background: color-mix(in srgb, var(--bg-0) 70%, transparent);
    color: var(--text-1);
  }

  .tab-search-input:focus-within {
    border-color: rgba(122, 166, 200, 0.42);
    color: var(--text-0);
  }

  .search-icon {
    display: flex;
    align-items: center;
    color: var(--text-2);
  }

  .tab-search input {
    width: 100%;
    min-width: 0;
    padding: 0;
    border: 0;
    outline: none;
    background: transparent;
    color: inherit;
  }

  .tab-search input::-webkit-search-cancel-button {
    -webkit-appearance: none;
  }

  .tab-search-results {
    position: absolute;
    top: calc(100% + 0.35rem);
    left: 0;
    right: 0;
    z-index: 20;
    display: grid;
    gap: 0.2rem;
    padding: 0.35rem;
    border: 1px solid var(--panel-border);
    border-radius: 4px;
    background: rgba(8, 12, 16, 0.98);
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
  }

  .tab-search-result,
  .tab-search-empty {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    padding: 0.45rem 0.5rem;
    border-radius: 3px;
    font-size: 0.73rem;
  }

  .tab-search-result {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    cursor: pointer;
    text-align: left;
  }

  .tab-search-result:hover,
  .tab-search-result.selected {
    border-color: rgba(122, 166, 200, 0.28);
    background: rgba(122, 166, 200, 0.08);
    color: var(--text-0);
  }

  .tab-search-result-state,
  .tab-search-empty {
    color: var(--text-2);
    font-size: 0.68rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .hamburger {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-1);
    padding: 0.2rem;
    cursor: pointer;
    border-radius: 2px;
    transition: color 120ms ease, border-color 120ms ease;
  }

  .hamburger:hover {
    color: var(--text-0);
    border-color: rgba(122, 166, 200, 0.32);
  }

  .mark {
    display: block;
    width: 1.15rem;
    height: auto;
    opacity: 0.85;
  }

  h1 {
    margin: 0;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .copilot-trigger {
    background: transparent;
    border: 1px solid transparent;
    color: var(--accent);
    font-size: 0.74rem;
    font-weight: 500;
    letter-spacing: 0.04em;
    padding: 0.12rem 0.35rem;
    cursor: pointer;
    border-radius: 2px;
    transition: border-color 120ms ease, color 120ms ease;
  }

  .copilot-trigger:hover {
    border-color: rgba(122, 166, 200, 0.32);
    color: var(--text-0);
  }

  .copilot-trigger.open {
    border-color: rgba(122, 166, 200, 0.42);
    color: var(--text-0);
  }

  .status-slot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-width: 0;
    padding-left: 0.6rem;
    border-left: 1px solid var(--divider);
  }

  .content {
    margin-top: 0.8rem;
  }

  @media (max-width: 960px) {
    .topbar,
    .brand {
      align-items: flex-start;
    }

    .topbar {
      display: flex;
      flex-direction: column;
      padding: 0.4rem 0.75rem;
    }

    .brand {
      width: 100%;
      flex-wrap: wrap;
    }

    .topbar-divider {
      display: none;
    }

    .tab-search {
      min-width: 100%;
      max-width: none;
      order: 10;
    }

    .status-slot {
      width: 100%;
      justify-content: stretch;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.5rem;
    }
  }
</style>
