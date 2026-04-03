<script lang="ts">
  import type {
    CopilotResearchCardResult,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";

  export let open = false;
  export let available = false;
  export let contextLabel = "Macro";
  export let domainLabel = "Copilot";
  export let guidance = "Grounded in the current Gamma context.";
  export let thread: CopilotThreadState | null = null;
  export let loading = false;
  export let placeholder = "Optional angle or research question...";
  export let onClose: () => void = () => {};
  export let onGenerate: (prompt?: string) => Promise<unknown> | void;

  let promptText = "";
  let threadEntries: CopilotThreadEntry[] = [];
  let latestEntry: CopilotThreadEntry | null = null;
  let hasThread = false;
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

  function providerLabelFor(result: CopilotResearchCardResult) {
    return result.model ? `${result.provider} | ${result.model}` : result.provider ?? null;
  }

  function turnLabel(entry: CopilotThreadEntry) {
    return entry.turnIndex === 1 ? "Initial Brief" : `Follow-up ${entry.turnIndex}`;
  }

  function promptLabel(entry: CopilotThreadEntry) {
    return entry.turnIndex === 1 ? "Prompt" : "Follow-up Prompt";
  }

  function promptTextFor(entry: CopilotThreadEntry) {
    return entry.prompt || "Used the active Gamma context without an extra prompt.";
  }

  $: threadEntries = [...(thread?.entries ?? [])].reverse();
  $: latestEntry = threadEntries[0] ?? null;
  $: hasThread = threadEntries.length > 0;
  $: composerHint = !available
    ? ""
    : hasThread
      ? "Ctrl+Enter to follow up in this domain thread"
      : "Ctrl+Enter to start a research thread";
  $: composerPlaceholder = available
    ? hasThread
      ? "Ask a follow-up grounded in this thread..."
      : placeholder
    : guidance;
  $: composerButtonLabel = loading ? "Generating..." : hasThread ? "Follow Up" : "Generate";
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
        <section class="message-card neutral">
          <span>Fresh Thread</span>
          <p>Generate a research card from the current context. Follow-up prompts stay inside this tab until the grounding context changes.</p>
        </section>
      {:else}
        <section class="thread-summary">
          <div class="summary-copy">
            <span class="section-label">Active Thread</span>
            <p>{threadEntries.length === 1 ? "1 research card in this thread." : `${threadEntries.length} turns in this thread.`}</p>
          </div>
          <small>{latestEntry?.turnIndex === 1 ? "Latest result is the initial brief." : "Latest result is a follow-up."}</small>
        </section>

        {#each threadEntries as entry, index (entry.entryId)}
          <article class="thread-turn" class:latest={index === 0}>
            <div class="turn-head">
              <span class="turn-pill" class:follow-up={entry.turnIndex > 1}>{turnLabel(entry)}</span>
              {#if providerLabelFor(entry.result)}
                <small>{providerLabelFor(entry.result)}</small>
              {/if}
            </div>

            <section class="message-card neutral prompt-card">
              <span>{promptLabel(entry)}</span>
              <p>{promptTextFor(entry)}</p>
            </section>

            {#if entry.result.message}
              <section class="message-card {entry.result.status}">
                <span>Status</span>
                <p>{entry.result.message}</p>
              </section>
            {/if}

            {#if entry.result.card}
              <article class="assistant-card">
                <div class="assistant-header">
                  <div>
                    <span class="section-label">Research Card</span>
                    <h3>{entry.result.card.title}</h3>
                  </div>
                </div>

                <div class="hero-block">
                  <span class="section-label">Hypothesis</span>
                  <p>{entry.result.card.hypothesis}</p>
                </div>

                <div class="summary-grid">
                  <div class="section-block">
                    <span>Rationale</span>
                    <p>{entry.result.card.rationale}</p>
                  </div>
                  <div class="section-block">
                    <span>Proposed Test</span>
                    <p>{entry.result.card.proposed_test}</p>
                  </div>
                </div>

                <div class="list-grid">
                  <div class="list-block">
                    <span>Required Data</span>
                    {#if entry.result.card.required_data.length}
                      <ul>{#each entry.result.card.required_data as item}<li>{item}</li>{/each}</ul>
                    {:else}
                      <p>None specified.</p>
                    {/if}
                  </div>
                  <div class="list-block">
                    <span>Confounders</span>
                    {#if entry.result.card.confounders.length}
                      <ul>{#each entry.result.card.confounders as item}<li>{item}</li>{/each}</ul>
                    {:else}
                      <p>None specified.</p>
                    {/if}
                  </div>
                  <div class="list-block">
                    <span>Next Steps</span>
                    {#if entry.result.card.next_steps.length}
                      <ul>{#each entry.result.card.next_steps as item}<li>{item}</li>{/each}</ul>
                    {:else}
                      <p>None specified.</p>
                    {/if}
                  </div>
                  <div class="list-block">
                    <span>Caveats</span>
                    {#if entry.result.card.caveats.length}
                      <ul>{#each entry.result.card.caveats as item}<li>{item}</li>{/each}</ul>
                    {:else}
                      <p>None specified.</p>
                    {/if}
                  </div>
                </div>

                <div class="claims-grid">
                  <div class="claim-block">
                    <span>Source-Backed</span>
                    {#if entry.result.card.source_backed_claims.length}
                      {#each entry.result.card.source_backed_claims as claim}
                        <div class="claim-row">
                          <p>{claim.claim}</p>
                          <small>{claim.evidence_refs.join(" | ")}</small>
                        </div>
                      {/each}
                    {:else}
                      <p>No explicit source-backed claims returned.</p>
                    {/if}
                  </div>
                  <div class="claim-block">
                    <span>Inferred</span>
                    {#if entry.result.card.inferred_claims.length}
                      <ul>{#each entry.result.card.inferred_claims as item}<li>{item}</li>{/each}</ul>
                    {:else}
                      <p>No explicit inference block returned.</p>
                    {/if}
                  </div>
                </div>
              </article>
            {:else if !entry.result.message}
              <section class="message-card neutral">
                <p>No structured research card was returned for this turn.</p>
              </section>
            {/if}

            {#if entry.result.sources?.length}
              <section class="meta-block">
                <span>Sources</span>
                {#each entry.result.sources as source}
                  <div class="meta-row">
                    <strong>{source.source_id}</strong>
                    <small>{source.label} | {source.provider}</small>
                  </div>
                {/each}
              </section>
            {/if}

            {#if entry.result.tool_traces?.length}
              <section class="meta-block">
                <span>Tools Used</span>
                {#each entry.result.tool_traces as trace}
                  <div class="meta-row">
                    <strong>{trace.tool_name}</strong>
                    <small>{trace.summary}</small>
                    {#if trace.source_ids.length}
                      <small>{trace.source_ids.join(" | ")}</small>
                    {/if}
                  </div>
                {/each}
              </section>
            {/if}

            {#if entry.result.warnings?.length}
              <section class="meta-block">
                <span>Warnings</span>
                {#each entry.result.warnings as warning}
                  <div class="meta-row">
                    <small>{warning}</small>
                  </div>
                {/each}
              </section>
            {/if}
          </article>
        {/each}
      {/if}
    </div>
  </div>

  <footer class="composer">
    <textarea
      bind:value={promptText}
      rows={2}
      placeholder={composerPlaceholder}
      disabled={!available || loading}
      on:keydown={handleComposerKeydown}
    ></textarea>

    <div class="composer-footer">
      <small>{composerHint}</small>
      <button class="generate-btn" type="button" disabled={!available || loading} on:click={handleGenerate}>
        {composerButtonLabel}
      </button>
    </div>
  </footer>
</div>

<style>
  .thread,
  .thread-turn,
  .summary-grid,
  .list-grid,
  .claims-grid,
  .meta-block {
    display: grid;
    gap: 0.85rem;
  }

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
    background: rgba(8, 13, 18, 0.985);
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
    padding: 1rem 1rem 0.95rem;
    background: rgba(8, 13, 18, 0.98);
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
  .assistant-header,
  .composer-footer,
  .turn-head {
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

  .thread-summary,
  .thread-turn,
  .note-card,
  .message-card,
  .assistant-card,
  .section-block,
  .list-block,
  .claim-block,
  .meta-row {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.6);
    padding: 0.75rem;
  }

  .thread-summary,
  .assistant-card,
  .meta-block {
    display: grid;
    gap: 0.65rem;
  }

  .thread-turn.latest {
    border-color: rgba(122, 166, 200, 0.32);
    background: rgba(8, 13, 18, 0.72);
  }

  .summary-copy,
  .claim-row,
  .meta-row {
    display: grid;
    gap: 0.25rem;
  }

  .section-label,
  .message-card span,
  .section-block span,
  .list-block span,
  .claim-block span,
  .meta-block > span,
  .thread-summary .section-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.64rem;
  }

  .turn-pill,
  .context-pill {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.7);
    color: var(--text-2);
    padding: 0.32rem 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.65rem;
    white-space: nowrap;
  }

  .turn-pill.follow-up,
  .context-pill.active {
    border-color: rgba(122, 166, 200, 0.36);
    background: rgba(122, 166, 200, 0.08);
    color: var(--accent);
  }

  .context-summary {
    margin: 0;
    color: var(--text-0);
    font-size: 0.94rem;
    overflow-wrap: anywhere;
  }

  .thread-summary p,
  .thread-summary small,
  .message-card p,
  .note-card p,
  .section-block p,
  .list-block p,
  .claim-block p,
  .meta-row small,
  .composer-footer small {
    color: var(--text-2);
  }

  .message-card.error {
    border-color: rgba(214, 104, 104, 0.35);
  }

  .message-card.unavailable {
    border-color: rgba(214, 168, 83, 0.35);
  }

  .message-card.neutral {
    border-color: rgba(122, 166, 200, 0.18);
  }

  .prompt-card {
    background: rgba(15, 19, 25, 0.85);
  }

  .hero-block {
    display: grid;
    gap: 0.35rem;
    padding: 0.9rem;
    border: 1px solid rgba(122, 166, 200, 0.18);
    background: rgba(122, 166, 200, 0.06);
  }

  .summary-grid,
  .claims-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .list-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
    padding-left: 1rem;
  }

  textarea,
  button,
  .close-btn {
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
    width: 2.3rem;
    height: 2.3rem;
    padding: 0;
    border-color: transparent;
    background: transparent;
  }

  .close-btn:hover,
  button:hover:not(:disabled) {
    border-color: rgba(122, 166, 200, 0.32);
  }

  .generate-btn {
    padding: 0.38rem 0.9rem;
    font-size: 0.76rem;
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

  .meta-row strong {
    color: var(--text-1);
    font-size: 0.82rem;
  }

  .turn-head small,
  .context-summary,
  .meta-row small {
    overflow-wrap: anywhere;
  }

  @media (max-width: 980px) {
    .drawer {
      width: calc(100vw - 0.35rem);
      max-width: calc(100vw - 0.35rem);
    }

    .summary-grid,
    .list-grid,
    .claims-grid {
      grid-template-columns: 1fr;
    }

    .title-row,
    .assistant-header,
    .turn-head,
    .composer-footer {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
