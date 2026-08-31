<script lang="ts">
  import type { TabId } from "../lib/api/types";
  import type { WorkspaceMode, WorkspaceTabOrderState } from "../lib/api/types";
  import { DEFAULT_WORKSPACE_TAB_ORDER, resolveNavigationPath, type NavigationRouteMatch } from "../lib/navigation";
  import type { TabBarItem } from "./TabBar.svelte";
  import SearchDropdown from "./SearchDropdown.svelte";

  type SharedEquitySelection = {
    symbol: string;
    label: string | null;
    sourceTab: TabId | null;
    updatedAt: string;
  };

  type SelectedPortfolio = {
    variant: "live" | "research";
  };

  export let activeTab: TabId = "portfolio";
  export let workspaceMode: WorkspaceMode = "portfolio";
  export let workspaceTabOrders: WorkspaceTabOrderState = DEFAULT_WORKSPACE_TAB_ORDER;
  export let searchResetToken = 0;
  export let tabs: TabBarItem[] = [];
  export let selectedEquity: SharedEquitySelection | null = null;
  export let selectedPortfolio: SelectedPortfolio | null = null;
  export let copilotOpen = false;
  export let onToggleSidebar: () => void = () => {};
  export let onToggleCopilot: () => void = () => {};
  export let onSelectTab: (tab: TabId) => void = () => {};
  export let onSelectRoute: (route: NavigationRouteMatch) => void = () => {};
  export let onClearSelectedEquity: () => void = () => {};
  export let onClearSelectedPortfolio: () => void = () => {};

  let searchValue = "";
  let previousActiveTab: TabId = activeTab;
  let previousWorkspaceMode: WorkspaceMode = workspaceMode;
  let previousSearchResetToken = searchResetToken;

  function normalizeSearchTerm(value: string) {
    return value.trim().toLowerCase().replace(/[_\s]+/g, " ");
  }

  $: normalizedSearchValue = normalizeSearchTerm(searchValue);
  $: pathMatch = searchValue.trim().startsWith("/")
    ? resolveNavigationPath(workspaceMode, workspaceTabOrders, searchValue)
    : null;
  $: matchingTabs =
    searchValue.trim().startsWith("/")
      ? pathMatch
        ? [pathMatch]
        : []
      : normalizedSearchValue.length === 0
      ? []
      : tabs.filter((tab) => {
          const label = normalizeSearchTerm(tab.label);
          const id = normalizeSearchTerm(tab.id);
          return label.includes(normalizedSearchValue) || id.includes(normalizedSearchValue);
        });
  $: searchResults = matchingTabs.map((item) => {
    if ("mode" in item) {
      return {
        id: routeResultId(item),
        primary: item.tab.label,
        secondary: item.mode?.label ?? null,
        state: item.tab.id === activeTab ? "Current" : null,
        selected: item.tab.id === activeTab,
      };
    }

    return {
      id: item.id,
      primary: item.label,
      state: item.id === activeTab ? "Current" : null,
      selected: item.id === activeTab,
    };
  });
  $: if (activeTab !== previousActiveTab) {
    previousActiveTab = activeTab;
    searchValue = "";
  }
  $: if (workspaceMode !== previousWorkspaceMode) {
    previousWorkspaceMode = workspaceMode;
    searchValue = "";
  }
  $: if (searchResetToken !== previousSearchResetToken) {
    previousSearchResetToken = searchResetToken;
    searchValue = "";
  }

  function handleSearchSelect(tabId: TabId) {
    if (!tabs.some((tab) => tab.id === tabId)) {
      searchValue = "";
      return;
    }
    searchValue = "";
    onSelectTab(tabId);
  }

  function routeResultId(route: NavigationRouteMatch) {
    return `route:${route.tab.id}:${route.mode?.id ?? ""}`;
  }

  function handleSearchResultSelect(id: string) {
    const selectedResult = searchResults.find((result) => result.id === id);
    if (!selectedResult) {
      searchValue = "";
      return;
    }

    if (id.startsWith("route:")) {
      if (pathMatch && id === routeResultId(pathMatch)) {
        searchValue = "";
        onSelectRoute(pathMatch);
      } else {
        searchValue = "";
      }
      return;
    }

    handleSearchSelect(id as TabId);
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
      <span class="brand-mark" aria-hidden="true">Γ</span>
      <h1><strong>Gamma</strong><span>Research Terminal</span></h1>
      <span class="topbar-divider" aria-hidden="true"></span>
      <div class="tab-search">
        <SearchDropdown
          bind:value={searchValue}
          placeholder="Search tabs"
          ariaLabel="Search tabs"
          emptyLabel="No matching tabs"
          enterBehavior="select-first"
          clearOnEscape
          results={searchResults}
          on:select={(event) => handleSearchResultSelect(event.detail.id)}
        />
      </div>
      {#if selectedEquity}
        <div class="asset-chip" title="Equity in focus">
          <span>Equity</span>
          <strong>{selectedEquity.symbol}</strong>
          <button type="button" aria-label="Clear equity focus" on:click={onClearSelectedEquity}>×</button>
        </div>
      {:else if selectedPortfolio}
        <div class="asset-chip" title={selectedPortfolio.variant === "research" ? "Research scope portfolio" : "User portfolio (IBKR)"}>
          <span>Portfolio</span>
          <strong>{selectedPortfolio.variant === "research" ? "Scope" : "User"}</strong>
          <button type="button" aria-label={selectedPortfolio.variant === "research" ? "Clear research scope" : "Clear portfolio focus"} on:click={onClearSelectedPortfolio}>×</button>
        </div>
      {/if}
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
    padding: var(--space-4) 0 var(--space-6);
  }

  .topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-5);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius-md);
    background: var(--bg-0);
  }

  .brand-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.15rem;
    height: 1.15rem;
    flex-shrink: 0;
    border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--panel-border));
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--accent) 12%, var(--bg-0));
    color: var(--accent);
    font-family: var(--display-font);
    font-size: var(--text-sm);
    font-weight: 700;
    line-height: 1;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
  }

  .topbar-divider {
    width: 1px;
    align-self: stretch;
    background: var(--divider);
  }

  .tab-search {
    flex: 1 1 17rem;
    min-width: 11rem;
    max-width: 24rem;
  }

  .asset-chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    flex-shrink: 0;
    white-space: nowrap;
    height: 1.75rem;
    padding: var(--space-1) var(--space-1) var(--space-1) var(--space-4);
    border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--panel-border));
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--accent) 7%, var(--bg-0));
    color: var(--text-1);
  }

  .asset-chip span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
  }

  .asset-chip strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    line-height: 1;
  }

  .asset-chip button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 1.2rem;
    height: 1.2rem;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-md);
    line-height: 1;
    padding: 0;
    cursor: pointer;
  }

  .asset-chip button:hover {
    color: var(--text-0);
    border-color: color-mix(in srgb, var(--accent) 28%, transparent);
  }

  .hamburger {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-1);
    padding: var(--space-2);
    cursor: pointer;
    border-radius: 2px;
    transition: color 120ms ease, border-color 120ms ease;
  }

  .hamburger:hover {
    color: var(--text-0);
    border-color: color-mix(in srgb, var(--accent) 32%, transparent);
  }

  h1 {
    display: flex;
    align-items: baseline;
    gap: var(--space-3);
    margin: 0;
    font-size: var(--text-base);
    white-space: nowrap;
  }

  h1 strong {
    font-size: var(--text-base);
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text-0);
    text-transform: uppercase;
  }

  h1 span {
    font-size: var(--text-sm);
    font-weight: 400;
    letter-spacing: 0.02em;
    color: var(--text-2);
  }

  .copilot-trigger {
    background: transparent;
    border: 1px solid color-mix(in srgb, var(--accent) 22%, var(--panel-border));
    color: var(--accent);
    font-size: var(--text-sm);
    font-weight: 500;
    letter-spacing: 0.04em;
    padding: var(--space-1) var(--space-4);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: border-color 120ms ease, color 120ms ease, background 120ms ease;
  }

  .copilot-trigger:hover {
    background: var(--hover-bg);
  }

  .copilot-trigger:hover {
    border-color: color-mix(in srgb, var(--accent) 32%, transparent);
    color: var(--text-0);
  }

  .copilot-trigger.open {
    border-color: color-mix(in srgb, var(--accent) 42%, transparent);
    color: var(--text-0);
  }

  .status-slot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-width: 0;
    padding-left: var(--space-4);
    border-left: 1px solid var(--divider);
  }

  .content {
    margin-top: var(--space-4);
  }

  @media (max-width: 960px) {
    .topbar,
    .brand {
      align-items: flex-start;
    }

    .topbar {
      display: flex;
      flex-direction: column;
      padding: var(--space-3) var(--space-5);
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

    .asset-chip {
      flex: 1 1 auto;
      max-width: 100%;
    }

    .status-slot {
      width: 100%;
      justify-content: stretch;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: var(--space-4);
    }
  }
</style>
