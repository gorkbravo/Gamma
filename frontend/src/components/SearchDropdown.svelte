<script lang="ts">
  import { createEventDispatcher } from "svelte";

  export interface SearchDropdownItem {
    id: string;
    primary: string;
    secondary?: string | null;
    state?: string | null;
    selected?: boolean;
  }

  export let value = "";
  export let placeholder = "Search";
  export let ariaLabel = "Search";
  export let emptyLabel = "No matches";
  export let loading = false;
  export let loadingLabel = "LOADING...";
  export let stale = false;
  export let staleLabel = "STALE RESULTS | REFRESHING";
  export let results: SearchDropdownItem[] = [];
  export let enterBehavior: "select-first" | "submit" = "submit";
  export let clearOnEscape = false;

  const dispatch = createEventDispatcher<{
    select: SearchDropdownItem;
    submit: void;
  }>();

  let focused = false;
  let inputElement: HTMLInputElement | null = null;

  $: normalizedValue = value.trim().toLowerCase();
  $: showResults = focused && normalizedValue.length > 0;

  function selectResult(item: SearchDropdownItem) {
    dispatch("select", item);
    focused = false;
    inputElement?.blur();
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      if (clearOnEscape) {
        event.preventDefault();
        value = "";
      }
      focused = false;
      inputElement?.blur();
      return;
    }

    if (event.key !== "Enter") {
      return;
    }

    if (enterBehavior === "select-first" && results.length > 0) {
      event.preventDefault();
      selectResult(results[0]);
      return;
    }

    dispatch("submit");
  }
</script>

<div class="search-dropdown">
  <label class="search-input">
    <span class="search-icon" aria-hidden="true">
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
        <circle cx="7" cy="7" r="4.5" stroke="currentColor" stroke-width="1.2" />
        <path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
      </svg>
    </span>
    <input
      bind:this={inputElement}
      bind:value
      type="search"
      {placeholder}
      aria-label={ariaLabel}
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      spellcheck="false"
      on:focus={() => (focused = true)}
      on:blur={() => setTimeout(() => (focused = false), 120)}
      on:keydown={handleKeydown}
    />
  </label>

  {#if showResults}
    <div class="search-results" class:stale role="listbox" aria-label="Search results">
      {#if stale && results.length > 0}
        <div class="search-status">{staleLabel}</div>
      {/if}
      {#if results.length > 0}
        {#each results as item}
          <button
            class="search-result"
            class:selected={item.selected}
            class:stale-result={stale}
            type="button"
            on:mousedown|preventDefault={() => selectResult(item)}
          >
            <span class="result-copy">
              <strong>{item.primary}</strong>
              {#if item.secondary}
                <small>{item.secondary}</small>
              {/if}
            </span>
            {#if item.state}
              <span class="result-state">{item.state}</span>
            {/if}
          </button>
        {/each}
      {:else if loading}
        <div class="search-empty loading-state">{loadingLabel}</div>
      {:else}
        <div class="search-empty">{emptyLabel}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .search-dropdown {
    position: relative;
    width: 100%;
  }

  .search-input {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    width: 100%;
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--panel-border);
    border-radius: var(--radius-sm);
    transition: border-color 120ms ease;
    background: color-mix(in srgb, var(--bg-0) 70%, transparent);
    color: var(--text-1);
  }

  .search-input:focus-within {
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-border));
    color: var(--text-0);
  }

  .search-icon {
    display: flex;
    align-items: center;
    color: var(--text-2);
  }

  input {
    width: 100%;
    min-width: 0;
    min-height: 0;
    padding: 0;
    border: 0;
    outline: none;
    background: transparent;
    color: inherit;
    font: inherit;
  }

  input::-webkit-search-cancel-button {
    -webkit-appearance: none;
  }

  .search-results {
    position: absolute;
    top: calc(100% + 0.35rem);
    left: 0;
    right: 0;
    z-index: 20;
    display: grid;
    gap: var(--space-2);
    padding: var(--space-3);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  }

  .search-results.stale {
    border-color: color-mix(in srgb, var(--warning) 34%, var(--panel-border));
  }

  .search-status {
    padding: var(--space-2) var(--space-3);
    color: var(--warning);
    border-bottom: 1px solid var(--divider);
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .search-result,
  .search-empty {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    width: 100%;
    padding: var(--space-4) var(--space-4);
    border-radius: 3px;
    font-size: var(--text-sm);
  }

  .search-result {
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    cursor: pointer;
    text-align: left;
  }

  .search-result:hover,
  .search-result.selected {
    border-color: color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
    color: var(--text-0);
  }

  .search-result.stale-result {
    color: var(--text-2);
  }

  .loading-state {
    color: var(--accent);
  }

  .result-copy {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .result-copy strong,
  .result-copy small {
    overflow-wrap: anywhere;
  }

  .result-copy strong {
    color: inherit;
  }

  .result-copy small,
  .result-state,
  .search-empty {
    color: var(--text-2);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
  }

  .result-state,
  .search-empty {
    text-transform: uppercase;
  }
</style>
