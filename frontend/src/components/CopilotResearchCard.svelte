<script lang="ts">
  import type {
    CopilotBaseDomain,
    CopilotReasoningEffort,
    CopilotResearchCardResult,
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

  let promptText = "";
  let roleMode: CopilotRoleMode = "agent";
  let reasoningEffort: CopilotReasoningEffort = "medium";
  let threadEntries: CopilotThreadEntry[] = [];
  let hasThread = false;
  let composerHint = "";
  let composerPlaceholder = "";
  let composerButtonLabel = "Generate";

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

  function providerLabelFor(result: CopilotResearchCardResult) {
    return result.model ? `${result.provider} · ${result.model}` : result.provider ?? null;
  }

  function resultMetaParts(result: CopilotResearchCardResult) {
    const parts: string[] = [];
    const provider = providerLabelFor(result);
    if (provider) parts.push(provider);
    if (result.sources.length) parts.push(`Sources (${result.sources.length})`);
    if (result.tool_traces.length) parts.push(`Tools (${result.tool_traces.length})`);
    if (result.warnings.length) parts.push(`Warnings (${result.warnings.length})`);
    return parts;
  }

  function hasGroundingMeta(result: CopilotResearchCardResult) {
    return result.sources.length > 0 || result.tool_traces.length > 0 || result.warnings.length > 0;
  }

  function cardlessStatusLabel(result: CopilotResearchCardResult) {
    return result.status === "ready" ? "No renderable card" : result.status.replaceAll("_", " ");
  }

  function cardLabelFor(entry: CopilotThreadEntry) {
    return entry.result.domain === "synthesis" ? "Grounded Research" : "Research Card";
  }

  function scopeTooltip(option: CopilotGroundingScopeOption) {
    const parts = [option.contextLabel, option.fingerprintLabel];
    if (option.freshnessLabel) parts.push(option.freshnessLabel);
    if (option.warningLabel) parts.push(option.warningLabel);
    if (option.disabledReason) parts.push(option.disabledReason);
    return parts.join(" · ");
  }

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

            {#if entry.result.message || !entry.result.card}
              <div class="bubble assistant-bubble status-bubble {entry.result.status}">
                <div class="bubble-head">
                  <span class="section-label">{cardlessStatusLabel(entry.result)}</span>
                  {#if providerLabelFor(entry.result)}
                    <small title={providerLabelFor(entry.result)}>{providerLabelFor(entry.result)}</small>
                  {/if}
                </div>
                <p>{entry.result.message ?? "Copilot returned no renderable card."}</p>
                {#if !entry.result.card && hasGroundingMeta(entry.result)}
                  <details class="meta-details" class:warning={entry.result.warnings?.length}>
                    <summary>
                      {#each resultMetaParts(entry.result) as part}<span>{part}</span>{/each}
                    </summary>
                    <div class="meta-body">
                      {#if entry.result.sources?.length}
                        <div class="meta-group">
                          <span class="inline-label">Sources</span>
                          {#each entry.result.sources as source}
                            <div class="meta-row">
                              <strong>{source.source_id}</strong>
                              <small>{source.label} / {source.provider}</small>
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
                                <small>{trace.source_ids.join(" / ")}</small>
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
    <div class="role-row" role="tablist" aria-label="Copilot role">
      <button type="button" class:active={roleMode === "agent"} on:click={() => setRoleMode("agent")}>
        Research Agent
      </button>
      <button type="button" class:active={roleMode === "operator"} on:click={() => setRoleMode("operator")}>
        Research Operator
      </button>
    </div>

    <div class="scope-row">
      <span class="scope-row-label">Context</span>
      {#if scopeOptions.length}
        <div class="scope-chips">
          {#each scopeOptions as option (option.tabId)}
            <button
              class="scope-chip"
              class:selected={option.domain != null && selectedScopeDomains.includes(option.domain)}
              class:unavailable={!option.supported}
              type="button"
              title={scopeTooltip(option)}
              disabled={!option.supported || option.domain == null}
              on:click={() => option.domain != null && onToggleScope(option.domain)}
            >
              <span>{option.label}</span>
              {#if !option.supported && option.disabledReason}
                <small>{option.disabledReason}</small>
              {/if}
            </button>
          {/each}
        </div>
      {:else}
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

  .status-bubble p {
    color: var(--text-2);
    font-size: var(--text-base);
  }

  .status-bubble.error p {
    color: var(--negative);
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
    gap: var(--space-5);
  }

  .field {
    display: grid;
    gap: var(--space-2);
  }

  .field + .field {
    padding-top: var(--space-4);
    border-top: 1px solid rgba(46, 60, 74, 0.42);
  }

  .bubble .field p.emphasis {
    color: var(--text-0);
    font-size: var(--text-base);
  }

  .meta-details {
    margin-top: var(--space-3);
    padding-top: var(--space-4);
    border-top: 1px solid rgba(46, 60, 74, 0.42);
  }

  .meta-details summary {
    cursor: pointer;
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
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
    gap: var(--space-4);
    margin-top: var(--space-4);
  }

  .meta-group {
    display: grid;
    gap: var(--space-2);
  }

  .claim-row {
    display: grid;
    gap: var(--space-2);
  }

  .claim-row + .claim-row {
    padding-top: var(--space-4);
    margin-top: var(--space-2);
    border-top: 1px solid rgba(46, 60, 74, 0.3);
  }

  .meta-row {
    display: grid;
    gap: var(--space-2);
  }

  .meta-row strong {
    color: var(--text-1);
    font-size: var(--text-sm);
  }

  .section-label,
  .inline-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
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
  .meta-row small,
  .composer-footer small,
  .meta-group small {
    color: var(--text-2);
  }

  .bubble h3 {
    color: var(--text-0);
    font-size: var(--text-md);
    font-weight: 600;
  }

  .bubble .field p,
  .bubble .field li {
    color: var(--text-1);
    font-size: var(--text-base);
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
    padding-left: var(--space-6);
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
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  .scope-row-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .scope-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .scope-chip {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-sm);
    color: var(--text-2);
    background: var(--surface-0);
    border: 1px solid rgba(46, 60, 74, 0.52);
  }

  .scope-chip.selected {
    color: var(--accent);
    border-color: rgba(122, 166, 200, 0.42);
    background: rgba(122, 166, 200, 0.08);
  }

  .scope-chip.unavailable {
    opacity: 0.48;
  }

  .scope-chip small {
    color: var(--text-2);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
    text-align: left;
    white-space: normal;
  }

  .scope-empty {
    color: var(--text-2);
    font-size: var(--text-sm);
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
