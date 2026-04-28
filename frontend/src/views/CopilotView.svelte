<script lang="ts">
  import type {
    CopilotBaseDomain,
    CopilotDomain,
    CrossTabHandoffEnvelope,
    CopilotMemo,
    CopilotSessionDetail,
    CopilotSessionSummary,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";

  type CopilotGroundingScopeOption = {
    domain: CopilotBaseDomain;
    label: string;
    contextLabel: string;
    fingerprintLabel: string;
    freshnessLabel: string | null;
    warningLabel: string | null;
  };

  type CopilotWorkspaceSurface = {
    supported: boolean;
    domain: CopilotDomain | null;
    contextLabel: string;
    domainLabel: string;
    guidance: string;
    placeholder: string;
    thread: CopilotThreadState | null;
    scopeOptions: CopilotGroundingScopeOption[];
    selectedScopeDomains: CopilotBaseDomain[];
    selectionMessage: string | null;
  };

  export let activeSurface: CopilotWorkspaceSurface;
  export let synthesisSurface: CopilotWorkspaceSurface;
  export let sessions: CopilotSessionSummary[] = [];
  export let activeSession: CopilotSessionDetail | null = null;
  export let memos: CopilotMemo[] = [];
  export let latestHandoff: CrossTabHandoffEnvelope | null = null;
  export let loading = false;
  export let onGenerate: (domain: CopilotDomain, prompt?: string) => Promise<unknown> | void;
  export let onCreateMemo: (title?: string, notes?: string) => Promise<unknown> | void = () => {};
  export let onUpdateMemo: (memoId: string, title: string, body: string) => Promise<unknown> | void = () => {};
  export let onArchiveSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onExportMemo: (memoId: string) => Promise<string | null | unknown> | string | null | void = () => null;
  export let onLoadSessions: () => Promise<unknown> | void = () => {};
  export let onSelectSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onSearchSessions: (options?: { includeArchived?: boolean; search?: string }) => Promise<unknown> | void = () => {};
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};

  type FocusMode = "synthesis" | "active_tab";

  let focusMode: FocusMode = "synthesis";
  let promptText = "";
  let surface: CopilotWorkspaceSurface = synthesisSurface;
  let threadEntries: CopilotThreadEntry[] = [];
  let selectedCount = 0;
  let loadedCount = 0;
  let displayedTurnCount = 0;
  let memoTitle = "";
  let memoNotes = "";
  let memoEditId = "";
  let memoEditTitle = "";
  let memoEditBody = "";
  let sessionSearch = "";
  let includeArchivedSessions = false;

  function setFocusMode(nextMode: FocusMode) {
    focusMode = nextMode;
  }

  async function handleGenerate() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onGenerate(surface.domain, promptText.trim());
    if (result != null) {
      promptText = "";
      await onLoadSessions();
    }
  }

  async function handleCreateMemo() {
    if (loading || !(activeSession?.turns.length || threadEntries.length)) {
      return;
    }
    const result = await onCreateMemo(memoTitle.trim(), memoNotes.trim());
    if (result != null) {
      memoTitle = "";
      memoNotes = "";
      await onLoadSessions();
    }
  }

  async function handleUpdateMemo() {
    if (!memoEditId || loading) {
      return;
    }
    const result = await onUpdateMemo(memoEditId, memoEditTitle.trim(), memoEditBody);
    if (result != null) {
      await onLoadSessions();
    }
  }

  async function handleArchiveSession(sessionId: string) {
    if (!sessionId || loading) {
      return;
    }
    const result = await onArchiveSession(sessionId);
    if (result != null) {
      await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
    }
  }

  async function handleSearchSessions() {
    await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
  }

  async function handleSelectSession(sessionId: string) {
    if (!sessionId || loading) {
      return;
    }
    await onSelectSession(sessionId);
  }

  async function handleExportMemo() {
    if (!memoEditId) {
      return;
    }
    const markdown = await onExportMemo(memoEditId);
    if (typeof markdown !== "string" || !markdown.trim()) {
      return;
    }
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${slugify(memoEditTitle || "copilot-memo")}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function selectMemo(memo: CopilotMemo) {
    memoEditId = memo.memo_id;
    memoEditTitle = memo.title;
    memoEditBody = memo.body;
  }

  function handleComposerKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void handleGenerate();
    }
  }

  function providerLabel(entry: CopilotThreadEntry) {
    const result = entry.result;
    return result.model ? `${result.provider} / ${result.model}` : result.provider;
  }

  function sourceSummary(entry: CopilotThreadEntry) {
    const sourceCount = entry.result.sources.length;
    const toolCount = entry.result.tool_traces.length;
    const warningCount = entry.result.warnings.length;
    const parts = [];
    if (sourceCount) parts.push(`${sourceCount} sources`);
    if (toolCount) parts.push(`${toolCount} tools`);
    if (warningCount) parts.push(`${warningCount} warnings`);
    return parts.join(" / ") || "No source trace";
  }

  function slugify(value: string) {
    const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
    return slug || "copilot-memo";
  }

  function sessionStatusLabel(session: CopilotSessionSummary) {
    return session.archived_at ? "ARCHIVED" : session.active_domain ?? "mixed";
  }

  $: surface = focusMode === "synthesis" ? synthesisSurface : activeSurface;
  $: threadEntries = surface.thread?.entries ?? [];
  $: selectedCount = synthesisSurface.selectedScopeDomains.length;
  $: loadedCount = synthesisSurface.scopeOptions.length;
  $: displayedTurnCount = threadEntries.length || activeSession?.turns.length || 0;
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-main">
      <p class="eyebrow">COPILOT WORKSPACE</p>
      <h2>Grounded Research Copilot</h2>
      <p>{surface.contextLabel}</p>
    </div>
    <div class="header-kpis" aria-label="Copilot workspace status">
      <div>
        <span>Primary</span>
        <strong>{focusMode === "synthesis" ? "Synthesis" : "Active Tab"}</strong>
      </div>
      <div>
        <span>Loaded Contexts</span>
        <strong>{loadedCount}</strong>
      </div>
      <div>
        <span>Selected Scope</span>
        <strong>{selectedCount}</strong>
      </div>
      <div>
        <span>Thread Turns</span>
        <strong>{displayedTurnCount}</strong>
      </div>
    </div>
  </article>

  <div class="workspace-grid">
    <div class="primary-column">
      <article class="panel composer-panel">
        <div class="mode-tabs" role="tablist" aria-label="Copilot focus">
          <button
            type="button"
            class:active={focusMode === "synthesis"}
            on:click={() => setFocusMode("synthesis")}
          >
            Synthesis
          </button>
          <button
            type="button"
            class:active={focusMode === "active_tab"}
            on:click={() => setFocusMode("active_tab")}
          >
            Active Tab
          </button>
        </div>

        <textarea
          bind:value={promptText}
          rows={5}
          placeholder={surface.supported ? surface.placeholder : surface.guidance}
          disabled={!surface.supported || loading}
          on:keydown={handleComposerKeydown}
        ></textarea>

        <div class="composer-footer">
          <span>{surface.selectionMessage ?? surface.guidance}</span>
          <button type="button" disabled={!surface.supported || loading} on:click={handleGenerate}>
            {loading ? "Generating..." : threadEntries.length ? "Follow Up" : "Generate"}
          </button>
        </div>
      </article>

      <article class="panel thread-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Session</p><h3>{surface.domainLabel}</h3></div>
          <span>{surface.supported ? "READY" : "CONTEXT REQUIRED"}</span>
        </div>

        {#if threadEntries.length}
          <div class="thread-list">
            {#each threadEntries as entry (entry.entryId)}
              <section class="turn-row">
                <div class="turn-meta">
                  <span>TURN {entry.turnIndex + 1}</span>
                  <small>{providerLabel(entry)}</small>
                  <small>{sourceSummary(entry)}</small>
                </div>
                <div class="turn-body">
                  {#if entry.prompt}
                    <p class="prompt">{entry.prompt}</p>
                  {/if}
                  {#if entry.result.message}
                    <p class="message {entry.result.status}">{entry.result.message}</p>
                  {/if}
                  {#if entry.result.card}
                    <h4>{entry.result.card.title}</h4>
                    <p><strong>Hypothesis</strong>{entry.result.card.hypothesis}</p>
                    <p><strong>Rationale</strong>{entry.result.card.rationale}</p>
                    <p><strong>Proposed test</strong>{entry.result.card.proposed_test}</p>
                  {/if}
                </div>
              </section>
            {/each}
          </div>
        {:else if activeSession?.turns.length}
          <div class="thread-list">
            {#each activeSession.turns as turn (turn.turn_id)}
              <section class="turn-row">
                <div class="turn-meta">
                  <span>TURN {turn.turn_index + 1}</span>
                  <small>{turn.result.model ? `${turn.result.provider} / ${turn.result.model}` : turn.result.provider}</small>
                  <small>{turn.result.sources.length} sources / {turn.result.tool_traces.length} tools</small>
                </div>
                <div class="turn-body">
                  {#if turn.prompt}
                    <p class="prompt">{turn.prompt}</p>
                  {/if}
                  {#if turn.result.message}
                    <p class="message {turn.result.status}">{turn.result.message}</p>
                  {/if}
                  {#if turn.result.card}
                    <h4>{turn.result.card.title}</h4>
                    <p><strong>Hypothesis</strong>{turn.result.card.hypothesis}</p>
                    <p><strong>Rationale</strong>{turn.result.card.rationale}</p>
                    <p><strong>Proposed test</strong>{turn.result.card.proposed_test}</p>
                  {/if}
                </div>
              </section>
            {/each}
          </div>
        {:else}
          <p class="empty-state">No dedicated Copilot workspace thread yet.</p>
        {/if}
      </article>
    </div>

    <aside class="support-column">
      <article class="panel scope-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Grounding</p><h3>Synthesis Scope</h3></div>
          <span>{selectedCount}/{loadedCount}</span>
        </div>
        {#if synthesisSurface.scopeOptions.length}
          <div class="scope-list">
            {#each synthesisSurface.scopeOptions as option (option.domain)}
              <button
                type="button"
                class:selected={synthesisSurface.selectedScopeDomains.includes(option.domain)}
                on:click={() => onToggleScope(option.domain)}
              >
                <strong>{option.label}</strong>
                <span>{option.contextLabel}</span>
                <small>
                  {option.fingerprintLabel}
                  {#if option.freshnessLabel} / {option.freshnessLabel}{/if}
                  {#if option.warningLabel} / {option.warningLabel}{/if}
                </small>
              </button>
            {/each}
          </div>
        {:else}
          <p class="empty-state">Load Gamma contexts from the research workspace before synthesis.</p>
        {/if}
      </article>

      <article class="panel plan-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Memos</p><h3>Session Memo</h3></div>
        </div>
        <div class="memo-form">
          <input bind:value={memoTitle} placeholder="Memo title" disabled={loading} />
          <textarea bind:value={memoNotes} rows={3} placeholder="Optional memo note" disabled={loading}></textarea>
          <button type="button" disabled={loading || !(activeSession?.turns.length || threadEntries.length)} on:click={handleCreateMemo}>
            Create Memo
          </button>
        </div>
        <div class="memo-list">
          {#if memos.length}
            {#each memos.slice(0, 4) as memo}
              <button type="button" class:selected={memo.memo_id === memoEditId} on:click={() => selectMemo(memo)}>
                <strong>{memo.source_turn_ids.length}</strong><span>{memo.title}</span>
              </button>
            {/each}
          {:else}
            <div><strong>0</strong><span>No saved Copilot memos for the active session.</span></div>
          {/if}
        </div>
        {#if memoEditId}
          <div class="memo-editor">
            <input bind:value={memoEditTitle} placeholder="Memo title" disabled={loading} />
            <textarea bind:value={memoEditBody} rows={8} placeholder="Memo body" disabled={loading}></textarea>
            <div class="button-row">
              <button type="button" disabled={loading || !memoEditBody.trim()} on:click={handleUpdateMemo}>Save</button>
              <button type="button" class="secondary" disabled={loading} on:click={handleExportMemo}>Export Md</button>
            </div>
          </div>
        {/if}
      </article>

      <article class="panel plan-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Sessions</p><h3>Persisted Threads</h3></div>
          <span>{sessions.length}</span>
        </div>
        <div class="session-filter">
          <input bind:value={sessionSearch} placeholder="Search sessions" on:keydown={(event) => event.key === "Enter" && handleSearchSessions()} />
          <label><input type="checkbox" bind:checked={includeArchivedSessions} on:change={handleSearchSessions} /> Archived</label>
          <button type="button" on:click={handleSearchSessions} disabled={loading}>Filter</button>
        </div>
        <div class="session-list">
          {#if sessions.length}
            {#each sessions.slice(0, 6) as session}
              <div>
                <strong>{session.turn_count}</strong>
                <span>{session.title} / {sessionStatusLabel(session)} / {session.memo_count} memos</span>
                <div class="session-actions">
                  <button type="button" disabled={loading} on:click={() => handleSelectSession(session.session_id)}>Open</button>
                  <button type="button" disabled={loading || session.archived_at != null} on:click={() => handleArchiveSession(session.session_id)}>Archive</button>
                </div>
              </div>
            {/each}
          {:else}
            <div><strong>0</strong><span>No persisted Copilot sessions yet.</span></div>
          {/if}
        </div>
      </article>

      <article class="panel handoff-panel">
        <div class="panel-head">
          <div class="title-line"><p class="eyebrow">Handoff</p><h3>Latest Context</h3></div>
        </div>
        {#if latestHandoff}
          <div class="handoff-grid">
            <div><span>Source</span><strong>{latestHandoff.source_tab}</strong></div>
            <div><span>Target</span><strong>{latestHandoff.intended_target_tab}</strong></div>
            <div><span>Entity</span><strong>{latestHandoff.selected_entity?.label ?? "N/A"}</strong></div>
            <div><span>Mode</span><strong>{latestHandoff.source_mode ?? "N/A"}</strong></div>
          </div>
          {#if latestHandoff.warnings.length}
            <p class="handoff-warning">{latestHandoff.warnings[0]}</p>
          {/if}
        {:else}
          <p class="empty-state">No explicit cross-tab handoff has opened this workspace yet.</p>
        {/if}
      </article>
    </aside>
  </div>
</section>

<style>
  .view,
  .primary-column,
  .support-column {
    display: grid;
    gap: 0.5rem;
    align-content: start;
    min-width: 0;
  }

  .panel {
    display: grid;
    gap: 0.5rem;
    align-content: start;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
  }

  .header-panel {
    grid-template-columns: minmax(0, 1fr) minmax(24rem, 0.7fr);
    align-items: stretch;
    padding: 0;
    gap: 0;
  }

  .header-main {
    display: grid;
    gap: 0.25rem;
    padding: 0.85rem;
    border-right: 1px solid var(--divider);
  }

  .header-main p:last-child {
    color: var(--text-1);
  }

  .header-kpis {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .header-kpis div {
    display: grid;
    gap: 0.2rem;
    padding: 0.75rem;
    border-right: 1px solid var(--divider);
  }

  .header-kpis div:last-child {
    border-right: 0;
  }

  .header-kpis span,
  .panel-head span,
  .eyebrow,
  .turn-meta span,
  .turn-meta small {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
  }

  .header-kpis strong {
    color: var(--text-0);
    font-size: 0.86rem;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(26rem, 0.42fr);
    gap: 0.5rem;
  }

  .panel-head,
  .title-line,
  .composer-footer {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
    min-width: 0;
  }

  .title-line {
    justify-content: flex-start;
    gap: 0.45rem;
  }

  .mode-tabs {
    display: flex;
    border: 1px solid var(--divider);
  }

  .mode-tabs button {
    flex: 1;
    border: 0;
    border-right: 1px solid var(--divider);
    background: transparent;
    color: var(--text-2);
    padding: 0.42rem 0.75rem;
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .mode-tabs button:last-child {
    border-right: 0;
  }

  .mode-tabs button.active {
    color: var(--accent);
    background: rgba(122, 166, 200, 0.08);
  }

  textarea {
    min-height: 8rem;
    resize: vertical;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0.65rem;
    font: inherit;
    font-size: 0.84rem;
  }

  input {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0.45rem 0.55rem;
    font: inherit;
    font-size: 0.8rem;
  }

  button {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    cursor: pointer;
  }

  button:hover:not(:disabled) {
    border-color: var(--accent);
  }

  button:disabled {
    cursor: default;
    opacity: 0.45;
  }

  .composer-footer span {
    color: var(--text-2);
    line-height: 1.35;
  }

  .composer-footer button {
    padding: 0.42rem 0.9rem;
    color: var(--accent);
    border-color: rgba(122, 166, 200, 0.34);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.74rem;
    white-space: nowrap;
  }

  .thread-list,
  .scope-list,
  .plan-list,
  .memo-list,
  .session-list {
    display: grid;
    gap: 0;
    border-top: 1px solid var(--divider);
  }

  .turn-row {
    display: grid;
    grid-template-columns: 9rem minmax(0, 1fr);
    gap: 0.75rem;
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .turn-meta,
  .turn-body {
    display: grid;
    gap: 0.3rem;
    min-width: 0;
  }

  .turn-body h4 {
    margin: 0;
    color: var(--text-0);
    font-size: 0.9rem;
  }

  .turn-body p {
    color: var(--text-1);
    line-height: 1.45;
  }

  .turn-body p strong {
    display: block;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.62rem;
    margin-bottom: 0.16rem;
  }

  .prompt {
    color: var(--accent) !important;
  }

  .message.error {
    color: var(--negative);
  }

  .scope-list button {
    display: grid;
    gap: 0.2rem;
    padding: 0.6rem 0;
    border: 0;
    border-bottom: 1px solid var(--divider);
    background: transparent;
    text-align: left;
  }

  .scope-list button.selected strong,
  .memo-list button.selected span {
    color: var(--accent);
  }

  .scope-list strong {
    color: var(--text-0);
  }

  .scope-list span,
  .scope-list small,
  .memo-list span,
  .session-list span,
  .session-filter label,
  .handoff-grid span {
    color: var(--text-2);
    line-height: 1.35;
  }

  .memo-list button,
  .memo-list > div,
  .session-list > div {
    display: grid;
    grid-template-columns: 2rem minmax(0, 1fr);
    gap: 0.5rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .memo-list button {
    border: 0;
    background: transparent;
    text-align: left;
  }

  .session-list > div {
    grid-template-columns: 2rem minmax(0, 1fr) auto;
    align-items: center;
  }

  .session-actions {
    display: flex;
    gap: 0.35rem;
  }

  .session-list button,
  .session-filter button {
    padding: 0.32rem 0.55rem;
    color: var(--text-1);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.68rem;
  }

  .memo-form,
  .memo-editor,
  .session-filter {
    display: grid;
    gap: 0.4rem;
  }

  .memo-form textarea {
    min-height: 4.5rem;
  }

  .memo-editor textarea {
    min-height: 11rem;
  }

  .session-filter {
    grid-template-columns: minmax(0, 1fr) auto auto;
    align-items: center;
  }

  .session-filter label {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.68rem;
  }

  .session-filter input[type="checkbox"] {
    width: 13px;
    height: 13px;
    padding: 0;
  }

  .button-row {
    display: flex;
    gap: 0.4rem;
  }

  .memo-form button,
  .memo-editor button {
    padding: 0.42rem 0.65rem;
    color: var(--accent);
    border-color: rgba(122, 166, 200, 0.34);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
  }

  .memo-editor button.secondary {
    color: var(--text-1);
    border-color: var(--panel-strong);
  }

  .memo-list strong,
  .session-list strong,
  .handoff-grid strong {
    color: var(--accent);
  }

  .handoff-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-top: 1px solid var(--divider);
  }

  .handoff-grid div {
    display: grid;
    gap: 0.2rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--divider);
  }

  .handoff-warning {
    margin: 0;
    color: var(--warning);
    font-size: 0.74rem;
    line-height: 1.35;
  }

  .empty-state {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
    margin: 0;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.08rem;
  }

  h3 {
    font-size: 0.92rem;
  }

  @media (max-width: 1180px) {
    .header-panel,
    .workspace-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .header-main {
      border-right: 0;
      border-bottom: 1px solid var(--divider);
    }
  }

  @media (max-width: 780px) {
    .header-kpis {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .turn-row {
      grid-template-columns: minmax(0, 1fr);
    }

    .panel-head,
    .composer-footer {
      display: grid;
      justify-content: stretch;
    }
  }
</style>
