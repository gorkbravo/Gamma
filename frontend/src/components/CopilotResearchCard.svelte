<script lang="ts">
  import { onMount } from "svelte";
  import CopilotTranscriptResult from "./CopilotTranscriptResult.svelte";
  import type {
    CopilotBaseDomain,
    CopilotReasoningEffort,
    CopilotSourceRef,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";

  type CopilotRoleMode = "agent" | "operator";
  type CopilotGroundingScopeOption = {
    tabId: string;
    domain: CopilotBaseDomain | null;
    label: string;
    contextLabel: string;
    fingerprintLabel: string;
    freshnessLabel: string | null;
    warningLabel: string | null;
    supported: boolean;
    disabledReason: string | null;
  };

  export let open = false;
  export let available = false;
  export let contextLabel = "Macro";
  export let domainLabel = "Copilot";
  export let guidance = "Grounded in the current Gamma context.";
  export let thread: CopilotThreadState | null = null;
  export let loading = false;
  export let placeholder = "Optional angle or research question...";
  export let scopeOptions: CopilotGroundingScopeOption[] = [];
  export let selectedScopeDomains: CopilotBaseDomain[] = [];
  export let selectionMessage: string | null = null;
  export let onClose: () => void = () => {};
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};
  export let onGenerate: (prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void;
  export let onRunOperator: (prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onOpenSource: (source: CopilotSourceRef) => Promise<unknown> | void = () => {};

  let promptText = "";
  let roleMode: CopilotRoleMode = "agent";
  let reasoningEffort: CopilotReasoningEffort = "medium";
  let threadEntries: CopilotThreadEntry[] = [];
  let hasThread = false;
  let composerHint = "";
  let composerPlaceholder = "";
  let composerButtonLabel = "Generate";
  let contextMenuOpen = false;
  let contextPickerEl: HTMLDivElement | null = null;
  let selectedScopeOptions: CopilotGroundingScopeOption[] = [];
  let contextSummary = "Select context";

  function setRoleMode(nextMode: CopilotRoleMode) {
    roleMode = nextMode;
    reasoningEffort = nextMode === "operator" ? "low" : "medium";
  }

  async function handleGenerate() {
    if (!available || loading) {
      return;
    }
    const result =
      roleMode === "operator"
        ? await onRunOperator(promptText.trim(), reasoningEffort)
        : await onGenerate(promptText.trim(), reasoningEffort);
    if (result != null) {
      promptText = "";
    }
  }

  function handleComposerKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void handleGenerate();
    }
  }

  function scopeTooltip(option: CopilotGroundingScopeOption) {
    const parts = [option.contextLabel, option.fingerprintLabel];
    if (option.freshnessLabel) parts.push(option.freshnessLabel);
    if (option.warningLabel) parts.push(option.warningLabel);
    if (option.disabledReason) parts.push(option.disabledReason);
    return parts.join(" · ");
  }

  onMount(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (contextMenuOpen && contextPickerEl && !contextPickerEl.contains(event.target as Node)) {
        contextMenuOpen = false;
      }
    };
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") contextMenuOpen = false;
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeydown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeydown);
    };
  });

  $: threadEntries = thread?.entries ?? [];
  $: hasThread = threadEntries.length > 0;
  $: composerHint = !available
    ? ""
    : hasThread
      ? "Ctrl+Enter to follow up"
      : roleMode === "operator"
        ? "Ctrl+Enter to run operator"
        : "Ctrl+Enter to start a thread";
  $: composerPlaceholder = available
    ? hasThread
      ? "Ask a follow-up grounded in this context scope..."
      : placeholder
    : guidance;
  $: composerButtonLabel = loading
    ? roleMode === "operator"
      ? "Running..."
      : "Generating..."
    : roleMode === "operator"
      ? "Run Operator"
      : hasThread
        ? "Follow up"
        : "Generate";
  $: selectedScopeOptions = scopeOptions.filter(
    (option) => option.domain != null && option.supported && selectedScopeDomains.includes(option.domain)
  );
  $: contextSummary =
    selectedScopeOptions.length === 0
      ? "Select context"
      : selectedScopeOptions.length <= 2
        ? selectedScopeOptions.map((option) => option.label).join(", ")
        : `${selectedScopeOptions[0].label} +${selectedScopeOptions.length - 1}`;
  $: if (!open) contextMenuOpen = false;
</script>

{#if open}
  <div class="backdrop" on:click={onClose} on:keydown={(event) => event.key === "Escape" && onClose()} role="presentation"></div>
{/if}

<div class="drawer" class:open aria-hidden={!open} aria-label="Gamma Copilot" aria-modal="true" role="dialog">
  <header class="drawer-header">
    <div class="header-copy">
      <div class="title-row">
        <h2>Copilot</h2>
        <span class="context-pill" class:active={available}>{domainLabel}</span>
      </div>
      <p class="context-summary">{contextLabel}</p>
    </div>

    <button class="close-btn" type="button" on:click={onClose} aria-label="Close Copilot">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
      </svg>
    </button>
  </header>

  <div class="drawer-body">
    <div class="thread">
      {#if !available}
        <section class="message-card neutral">
          <p>{guidance}</p>
        </section>
      {:else if !hasThread}
        <section class="message-card neutral empty-state">
          <p>Select one or more context tabs below. Follow-ups stay inside this context scope until it changes.</p>
        </section>
      {:else}
        {#each threadEntries as entry, index (entry.entryId)}
          <div class="turn">
            {#if entry.prompt}
              <div class="bubble user-bubble">
                <p>{entry.prompt}</p>
              </div>
            {/if}

            <div class="bubble assistant-bubble" class:first-turn={index === 0}>
              <CopilotTranscriptResult
                result={entry.result}
                compact
                cardLabel={index === 0 ? (entry.result.domain === "synthesis" ? "Grounded Research" : "Research Card") : null}
                {onOpenSource}
              />
            </div>
          </div>
        {/each}
      {/if}
    </div>
  </div>

  <footer class="composer">
    <div class="role-row" role="tablist" aria-label="Copilot role">
      <button type="button" class:active={roleMode === "agent"} on:click={() => setRoleMode("agent")}>
        Research Agent
      </button>
      <button type="button" class:active={roleMode === "operator"} on:click={() => setRoleMode("operator")}>
        Research Operator
      </button>
    </div>

    <div class="scope-row">
      {#if scopeOptions.length}
        <div class="context-picker" bind:this={contextPickerEl}>
          <button
            class="context-trigger"
            class:open={contextMenuOpen}
            type="button"
            aria-haspopup="listbox"
            aria-expanded={contextMenuOpen}
            on:click={() => (contextMenuOpen = !contextMenuOpen)}
          >
            <span class="scope-row-label">Context</span>
            <span class="context-value">{contextSummary}</span>
            <span class="caret" aria-hidden="true">▾</span>
          </button>
          {#if contextMenuOpen}
            <div class="context-menu" role="listbox" aria-label="Context scope" aria-multiselectable="true">
              {#each scopeOptions as option (option.domain ?? option.tabId)}
                <button
                  type="button"
                  role="option"
                  class="context-option"
                  class:selected={option.domain != null && selectedScopeDomains.includes(option.domain)}
                  aria-selected={option.domain != null && selectedScopeDomains.includes(option.domain)}
                  disabled={!option.supported || option.domain == null}
                  title={scopeTooltip(option)}
                  on:click={() => option.domain != null && onToggleScope(option.domain)}
                >
                  <span class="checkbox" aria-hidden="true"></span>
                  <span class="context-option-copy">
                    <span class="context-option-label">{option.label}</span>
                    {#if !option.supported && option.disabledReason}
                      <span class="context-option-reason">{option.disabledReason}</span>
                    {/if}
                  </span>
                  {#if option.warningLabel}
                    <span class="status-dot warn" title={option.warningLabel}></span>
                  {:else if option.freshnessLabel}
                    <span class="status-dot ok" title={option.freshnessLabel}></span>
                  {/if}
                </button>
              {/each}
            </div>
          {/if}
        </div>
      {:else}
        <span class="scope-row-label">Context</span>
        <small class="scope-empty">{selectionMessage ?? "Load a context to use Copilot."}</small>
      {/if}
    </div>

    <textarea
      bind:value={promptText}
      rows={2}
      placeholder={composerPlaceholder}
      disabled={!available || loading}
      on:keydown={handleComposerKeydown}
    ></textarea>

    <div class="composer-footer">
      <small>{composerHint}</small>
      <div class="composer-actions">
        <label class="effort-select">
          <span>Thinking</span>
          <select bind:value={reasoningEffort} disabled={!available || loading}>
            <option value="minimal">minimal</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="xhigh">xhigh</option>
          </select>
        </label>
        <button class="generate-btn" type="button" disabled={!available || loading} on:click={handleGenerate}>
          {composerButtonLabel}
        </button>
      </div>
    </div>
  </footer>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 44;
    background: rgba(0, 0, 0, 0.4);
  }

  .drawer {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 55;
    width: clamp(24rem, 38vw, 46rem);
    max-width: calc(100vw - 1rem);
    height: 100vh;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    background: var(--surface-0);
    border-right: 1px solid var(--panel-border);
    box-shadow: 28px 0 72px rgba(0, 0, 0, 0.4);
    transform: translateX(-100%);
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    transition: transform 180ms ease, opacity 180ms ease, visibility 180ms ease;
  }

  .drawer.open {
    transform: translateX(0);
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
  }

  .drawer-header,
  .composer {
    padding: var(--space-6) var(--space-6);
    background: var(--surface-0);
  }

  .drawer-header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-6);
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
  }

  .composer {
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    display: grid;
    gap: var(--space-4);
  }

  .header-copy {
    display: grid;
    gap: var(--space-3);
    min-width: 0;
  }

  .title-row,
  .composer-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .drawer-body {
    min-height: 0;
    overflow-y: auto;
    padding: var(--space-6);
  }

  .thread {
    display: grid;
    gap: var(--space-4);
  }

  .turn {
    display: grid;
    gap: var(--space-4);
  }

  .bubble {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-soft);
    padding: var(--space-5) var(--space-5);
    display: grid;
    gap: var(--space-4);
    max-width: 92%;
  }

  .user-bubble {
    justify-self: end;
    background: rgba(122, 166, 200, 0.1);
    border-color: rgba(122, 166, 200, 0.3);
    border-top-right-radius: 2px;
  }

  .user-bubble p {
    color: var(--text-0);
    font-size: var(--text-base);
  }

  .assistant-bubble {
    justify-self: start;
    border-top-left-radius: 2px;
  }

  .message-card {
    border: 1px solid rgba(122, 166, 200, 0.18);
    background: var(--surface-soft);
    padding: var(--space-5);
  }

  .empty-state p {
    color: var(--text-2);
    font-size: var(--text-base);
  }

  .context-pill {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-soft);
    color: var(--text-2);
    padding: var(--space-2) var(--space-4);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    white-space: nowrap;
  }

  .context-pill.active {
    border-color: rgba(122, 166, 200, 0.36);
    background: rgba(122, 166, 200, 0.08);
    color: var(--accent);
  }

  .context-summary {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-base);
    overflow-wrap: anywhere;
  }

  .bubble p,
  .composer-footer small {
    color: var(--text-2);
  }

  h2,
  p,
  small {
    margin: 0;
  }

  textarea,
  button,
  .close-btn,
  select {
    border: 1px solid var(--panel-strong);
    background: #0d0f12;
    color: var(--text-0);
    font: inherit;
  }

  textarea {
    resize: vertical;
    min-height: 3.2rem;
    padding: var(--space-4) var(--space-5);
    font-size: var(--text-base);
  }

  button {
    cursor: pointer;
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.1rem;
    height: 2.1rem;
    padding: 0;
    border-color: transparent;
    background: transparent;
  }

  .close-btn:hover,
  button:hover:not(:disabled) {
    border-color: rgba(122, 166, 200, 0.32);
  }

  .composer-actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .role-row {
    display: inline-flex;
    width: max-content;
    border: 1px solid var(--panel-strong);
  }

  .role-row button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
    white-space: nowrap;
  }

  .role-row button:last-child {
    border-right: 0;
  }

  .role-row button.active {
    color: var(--accent);
    background: rgba(122, 166, 200, 0.1);
  }

  .effort-select {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  .effort-select select {
    padding: var(--space-3) var(--space-4);
    padding-right: var(--space-7);
    font-size: var(--text-sm);
    text-transform: lowercase;
    letter-spacing: 0;
    color: var(--text-2);
    background-color: #0d0f12;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' stroke='%237a8a99' stroke-width='1.2' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>");
    background-repeat: no-repeat;
    background-position: right 0.45rem center;
    appearance: none;
    cursor: pointer;
  }

  .effort-select select:hover:not(:disabled) {
    border-color: rgba(122, 166, 200, 0.32);
    color: var(--text-1);
  }

  .effort-select select:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .generate-btn {
    padding: var(--space-3) var(--space-5);
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-color: rgba(122, 166, 200, 0.28);
    background: rgba(122, 166, 200, 0.08);
    color: var(--accent);
  }

  .generate-btn:hover:not(:disabled) {
    background: rgba(122, 166, 200, 0.14);
    border-color: rgba(122, 166, 200, 0.42);
  }

  .generate-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .scope-row {
    display: flex;
    align-items: center;
    min-height: 28px;
  }

  .scope-row-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .context-picker {
    position: relative;
    min-width: 0;
  }

  .context-trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    height: 28px;
    max-width: 100%;
    padding: 0 var(--space-4);
    font-size: var(--text-sm);
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
  }

  .context-trigger:hover:not(:disabled),
  .context-trigger.open {
    border-color: var(--accent);
  }

  .context-value {
    color: var(--text-0);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .caret {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .context-menu {
    position: absolute;
    bottom: calc(100% + 4px);
    left: 0;
    z-index: 60;
    width: min(22rem, calc(100vw - 2rem));
    max-height: min(22rem, 50vh);
    overflow-y: auto;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
  }

  .context-option {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border: 0;
    border-bottom: 1px solid var(--divider);
    background: transparent;
    color: var(--text-1);
    text-align: left;
    font-size: var(--text-sm);
  }

  .context-option:last-child {
    border-bottom: 0;
  }

  .context-option:hover:not(:disabled) {
    background: var(--hover-bg);
  }

  .context-option:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .checkbox {
    width: 13px;
    height: 13px;
    border: 1px solid var(--panel-strong);
    flex: none;
  }

  .context-option.selected .checkbox {
    background: var(--accent);
    border-color: var(--accent);
  }

  .context-option.selected .context-option-label {
    color: var(--text-0);
  }

  .context-option-copy {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
    flex: 1;
  }

  .context-option-reason {
    color: var(--text-2);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
    white-space: normal;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
  }

  .status-dot.ok {
    background: var(--positive);
  }

  .status-dot.warn {
    background: var(--warning);
  }

  .scope-empty {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  @media (max-width: 980px) {
    .drawer {
      width: calc(100vw - 0.35rem);
      max-width: calc(100vw - 0.35rem);
    }

    .title-row,
    .composer-footer {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
