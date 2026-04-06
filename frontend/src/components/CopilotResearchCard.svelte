<script lang="ts">
  import type {
    CopilotBaseDomain,
    CopilotResearchCardResult,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";

  type CopilotDrawerMode = "active_tab" | "synthesis";
  type CopilotGroundingScopeOption = {
    domain: CopilotBaseDomain;
    label: string;
    contextLabel: string;
    fingerprintLabel: string;
    freshnessLabel: string | null;
    warningLabel: string | null;
  };

  export let open = false;
  export let available = false;
  export let mode: CopilotDrawerMode = "active_tab";
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
  export let onSetMode: (mode: CopilotDrawerMode) => void = () => {};
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};
  export let onGenerate: (prompt?: string) => Promise<unknown> | void;

  let promptText = "";
  let threadEntries: CopilotThreadEntry[] = [];
  let hasThread = false;
  let isSynthesisMode = false;
  let composerHint = "";
  let composerPlaceholder = "";
  let composerButtonLabel = "Generate";

  async function handleGenerate() {
    if (!available || loading) {
      return;
    }
    const result = await onGenerate(promptText.trim());
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

  function handleModeChange(event: Event) {
    const value = (event.target as HTMLSelectElement).value as CopilotDrawerMode;
    onSetMode(value);
  }

  function providerLabelFor(result: CopilotResearchCardResult) {
    return result.model ? `${result.provider} · ${result.model}` : result.provider ?? null;
  }

  function cardLabelFor(entry: CopilotThreadEntry) {
    return entry.result.domain === "synthesis" ? "Research Synthesis" : "Research Card";
  }

  function scopeTooltip(option: CopilotGroundingScopeOption) {
    const parts = [option.contextLabel, option.fingerprintLabel];
    if (option.freshnessLabel) parts.push(option.freshnessLabel);
    if (option.warningLabel) parts.push(option.warningLabel);
    return parts.join(" · ");
  }

  $: threadEntries = thread?.entries ?? [];
  $: hasThread = threadEntries.length > 0;
  $: isSynthesisMode = mode === "synthesis";
  $: composerHint = !available
    ? ""
    : hasThread
      ? "Ctrl+Enter to follow up"
      : isSynthesisMode
        ? "Ctrl+Enter to start a synthesis"
        : "Ctrl+Enter to start a thread";
  $: composerPlaceholder = available
    ? hasThread
      ? isSynthesisMode
        ? "Ask a follow-up grounded in this synthesis scope..."
        : "Ask a follow-up grounded in this thread..."
      : placeholder
    : guidance;
  $: composerButtonLabel = loading ? "Generating..." : hasThread ? "Follow up" : "Generate";
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
          <p>
            {#if isSynthesisMode}
              Select contexts below and generate a synthesis card. Follow-ups stay in this scope until it changes.
            {:else}
              Generate a research card from the current context. Follow-ups stay inside this tab until the grounding changes.
            {/if}
          </p>
        </section>
      {:else}
        {#each threadEntries as entry, index (entry.entryId)}
          <div class="turn">
            {#if entry.prompt}
              <div class="bubble user-bubble">
                <p>{entry.prompt}</p>
              </div>
            {/if}

            {#if entry.result.message}
              <div class="bubble assistant-bubble status-bubble {entry.result.status}">
                <p>{entry.result.message}</p>
              </div>
            {/if}

            {#if entry.result.card}
              <div class="bubble assistant-bubble" class:first-turn={index === 0}>
                {#if index === 0}
                  <div class="bubble-head">
                    <span class="section-label">{cardLabelFor(entry)}</span>
                    {#if providerLabelFor(entry.result)}
                      <small title={providerLabelFor(entry.result)}>{providerLabelFor(entry.result)}</small>
                    {/if}
                  </div>
                {/if}
                <h3>{entry.result.card.title}</h3>

                <div class="field">
                  <span class="inline-label">Hypothesis</span>
                  <p class="emphasis">{entry.result.card.hypothesis}</p>
                </div>

                <div class="field">
                  <span class="inline-label">Rationale</span>
                  <p>{entry.result.card.rationale}</p>
                </div>
                <div class="field">
                  <span class="inline-label">Proposed test</span>
                  <p>{entry.result.card.proposed_test}</p>
                </div>

                {#if entry.result.card.required_data.length}
                  <div class="field">
                    <span class="inline-label">Required data</span>
                    <ul>{#each entry.result.card.required_data as item}<li>{item}</li>{/each}</ul>
                  </div>
                {/if}
                {#if entry.result.card.confounders.length}
                  <div class="field">
                    <span class="inline-label">Confounders</span>
                    <ul>{#each entry.result.card.confounders as item}<li>{item}</li>{/each}</ul>
                  </div>
                {/if}
                {#if entry.result.card.next_steps.length}
                  <div class="field">
                    <span class="inline-label">Next steps</span>
                    <ul>{#each entry.result.card.next_steps as item}<li>{item}</li>{/each}</ul>
                  </div>
                {/if}
                {#if entry.result.card.caveats.length}
                  <div class="field">
                    <span class="inline-label">Caveats</span>
                    <ul>{#each entry.result.card.caveats as item}<li>{item}</li>{/each}</ul>
                  </div>
                {/if}

                {#if entry.result.card.source_backed_claims.length}
                  <div class="field">
                    <span class="inline-label">Source-backed</span>
                    {#each entry.result.card.source_backed_claims as claim}
                      <div class="claim-row">
                        <p>{claim.claim}</p>
                        <small>{claim.evidence_refs.join(" · ")}</small>
                      </div>
                    {/each}
                  </div>
                {/if}
                {#if entry.result.card.inferred_claims.length}
                  <div class="field">
                    <span class="inline-label">Inferred</span>
                    <ul>{#each entry.result.card.inferred_claims as item}<li>{item}</li>{/each}</ul>
                  </div>
                {/if}

                {#if entry.result.sources?.length || entry.result.tool_traces?.length || entry.result.warnings?.length}
                  <details class="meta-details" class:warning={entry.result.warnings?.length}>
                    <summary>
                      {#if entry.result.sources?.length}<span>Sources ({entry.result.sources.length})</span>{/if}
                      {#if entry.result.tool_traces?.length}<span>Tools ({entry.result.tool_traces.length})</span>{/if}
                      {#if entry.result.warnings?.length}<span class="warning-label">Warnings ({entry.result.warnings.length})</span>{/if}
                    </summary>
                    <div class="meta-body">
                      {#if entry.result.sources?.length}
                        <div class="meta-group">
                          <span class="inline-label">Sources</span>
                          {#each entry.result.sources as source}
                            <div class="meta-row">
                              <strong>{source.source_id}</strong>
                              <small>{source.label} · {source.provider}</small>
                            </div>
                          {/each}
                        </div>
                      {/if}
                      {#if entry.result.tool_traces?.length}
                        <div class="meta-group">
                          <span class="inline-label">Tools used</span>
                          {#each entry.result.tool_traces as trace}
                            <div class="meta-row">
                              <strong>{trace.tool_name}</strong>
                              <small>{trace.summary}</small>
                              {#if trace.source_ids.length}
                                <small>{trace.source_ids.join(" · ")}</small>
                              {/if}
                            </div>
                          {/each}
                        </div>
                      {/if}
                      {#if entry.result.warnings?.length}
                        <div class="meta-group">
                          <span class="inline-label">Warnings</span>
                          {#each entry.result.warnings as warning}
                            <small>{warning}</small>
                          {/each}
                        </div>
                      {/if}
                    </div>
                  </details>
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  </div>

  <footer class="composer">
    {#if isSynthesisMode}
      <div class="scope-row">
        <span class="scope-row-label">Scope</span>
        {#if scopeOptions.length}
          <div class="scope-chips">
            {#each scopeOptions as option (option.domain)}
              <button
                class="scope-chip"
                class:selected={selectedScopeDomains.includes(option.domain)}
                type="button"
                title={scopeTooltip(option)}
                on:click={() => onToggleScope(option.domain)}
              >
                {option.label}
              </button>
            {/each}
          </div>
        {:else}
          <small class="scope-empty">{selectionMessage ?? "Load two or more contexts to synthesize."}</small>
        {/if}
      </div>
    {/if}

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
        <label class="mode-select">
          <span class="visually-hidden">Copilot mode</span>
          <select
            value={mode}
            on:change={handleModeChange}
            disabled={!available || loading}
          >
            <option value="active_tab">Active tab</option>
            <option value="synthesis">Synthesis</option>
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
    padding: 0.9rem 1rem;
    background: var(--surface-0);
  }

  .drawer-header {
    display: flex;
    justify-content: space-between;
    gap: 0.9rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
  }

  .composer {
    border-top: 1px solid rgba(46, 60, 74, 0.52);
    display: grid;
    gap: 0.5rem;
  }

  .header-copy {
    display: grid;
    gap: 0.35rem;
    min-width: 0;
  }

  .title-row,
  .composer-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .drawer-body {
    min-height: 0;
    overflow-y: auto;
    padding: 1rem;
  }

  .thread {
    display: grid;
    gap: 1rem;
  }

  .turn {
    display: grid;
    gap: 0.5rem;
  }

  .bubble {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-soft);
    padding: 0.7rem 0.85rem;
    display: grid;
    gap: 0.55rem;
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
    font-size: 0.82rem;
  }

  .assistant-bubble {
    justify-self: start;
    border-top-left-radius: 2px;
  }

  .status-bubble p {
    color: var(--text-2);
    font-size: 0.82rem;
  }

  .status-bubble.error {
    border-color: rgba(214, 104, 104, 0.35);
  }

  .status-bubble.unavailable {
    border-color: rgba(214, 168, 83, 0.35);
  }

  .bubble-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .field {
    display: grid;
    gap: 0.25rem;
  }

  .field + .field {
    padding-top: 0.55rem;
    border-top: 1px solid rgba(46, 60, 74, 0.42);
  }

  .bubble .field p.emphasis {
    color: var(--text-0);
    font-size: 0.85rem;
  }

  .meta-details {
    margin-top: 0.4rem;
    padding-top: 0.55rem;
    border-top: 1px solid rgba(46, 60, 74, 0.42);
  }

  .meta-details summary {
    cursor: pointer;
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.62rem;
  }

  .meta-details summary::-webkit-details-marker {
    display: none;
  }

  .meta-details summary::before {
    content: "▸";
    display: inline-block;
    width: 0.75rem;
    transition: transform 120ms ease;
    color: var(--text-2);
  }

  .meta-details[open] summary::before {
    transform: rotate(90deg);
  }

  .meta-details summary:hover {
    color: var(--text-1);
  }

  .meta-details .warning-label {
    color: rgba(214, 168, 83, 0.85);
  }

  .meta-body {
    display: grid;
    gap: 0.6rem;
    margin-top: 0.55rem;
  }

  .meta-group {
    display: grid;
    gap: 0.3rem;
  }

  .claim-row {
    display: grid;
    gap: 0.2rem;
  }

  .claim-row + .claim-row {
    padding-top: 0.45rem;
    margin-top: 0.25rem;
    border-top: 1px solid rgba(46, 60, 74, 0.3);
  }

  .meta-row {
    display: grid;
    gap: 0.2rem;
  }

  .meta-row strong {
    color: var(--text-1);
    font-size: 0.78rem;
  }

  .section-label,
  .inline-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .message-card {
    border: 1px solid rgba(122, 166, 200, 0.18);
    background: var(--surface-soft);
    padding: 0.85rem;
  }

  .empty-state p {
    color: var(--text-2);
    font-size: 0.82rem;
  }

  .context-pill {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: var(--surface-soft);
    color: var(--text-2);
    padding: 0.28rem 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.64rem;
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
    font-size: 0.88rem;
    overflow-wrap: anywhere;
  }

  .bubble p,
  .meta-row small,
  .composer-footer small,
  .meta-group small {
    color: var(--text-2);
  }

  .bubble h3 {
    color: var(--text-0);
    font-size: 0.92rem;
    font-weight: 600;
  }

  .bubble .field p,
  .bubble .field li {
    color: var(--text-1);
    font-size: 0.81rem;
    line-height: 1.45;
  }

  h2,
  h3,
  p,
  small,
  ul,
  li {
    margin: 0;
  }

  ul {
    padding-left: 1.05rem;
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
    padding: 0.55rem 0.7rem;
    font-size: 0.82rem;
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
    gap: 0.4rem;
  }

  .mode-select select {
    padding: 0.32rem 0.5rem;
    padding-right: 1.4rem;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-2);
    background-color: #0d0f12;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' stroke='%237a8a99' stroke-width='1.2' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>");
    background-repeat: no-repeat;
    background-position: right 0.45rem center;
    appearance: none;
    cursor: pointer;
  }

  .mode-select select:hover:not(:disabled) {
    border-color: rgba(122, 166, 200, 0.32);
    color: var(--text-1);
  }

  .mode-select select:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .generate-btn {
    padding: 0.35rem 0.85rem;
    font-size: 0.74rem;
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
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .scope-row-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
  }

  .scope-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }

  .scope-chip {
    padding: 0.25rem 0.55rem;
    font-size: 0.72rem;
    color: var(--text-2);
    background: var(--surface-0);
    border: 1px solid rgba(46, 60, 74, 0.52);
  }

  .scope-chip.selected {
    color: var(--accent);
    border-color: rgba(122, 166, 200, 0.42);
    background: rgba(122, 166, 200, 0.08);
  }

  .scope-empty {
    color: var(--text-2);
    font-size: 0.74rem;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
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
