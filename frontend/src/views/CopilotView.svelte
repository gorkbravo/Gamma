<script lang="ts">
  import { afterUpdate, onMount } from "svelte";
  import CopilotArtifactsPanel from "../components/CopilotArtifactsPanel.svelte";
  import CopilotTranscriptResult from "../components/CopilotTranscriptResult.svelte";
  import type {
    CopilotArtifact,
    CopilotBaseDomain,
    CopilotDomain,
    CopilotReasoningEffort,
    CrossTabHandoffEnvelope,
    CopilotOperatorPlan,
    CopilotResearchCardResult,
    CopilotResearchPlan,
    CopilotSourceRef,
    CopilotSessionDetail,
    CopilotSessionSummary,
    CopilotStorageStatus,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";
  import type { CopilotRunState } from "../lib/copilot-run";
  import {
    describeCopilotSession,
    resolveComposerDraft,
    resolveInFlightPrompt,
    summarizeCopilotStorageRecovery,
    type CopilotComposerSubmission
  } from "../lib/copilot-workspace";

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

  type ChatTurn = {
    id: string;
    index: number;
    prompt: string;
    result: CopilotResearchCardResult;
  };

  export let synthesisSurface: CopilotWorkspaceSurface;
  export let sessions: CopilotSessionSummary[] = [];
  export let activeSession: CopilotSessionDetail | null = null;
  export let artifacts: CopilotArtifact[] = [];
  export let activeArtifact: CopilotArtifact | null = null;
  export let artifactSaveState: "idle" | "saving" | "saved" | "error" = "idle";
  export let storageStatus: CopilotStorageStatus | null = null;
  export let researchPlan: CopilotResearchPlan | null = null;
  export let operatorPlan: CopilotOperatorPlan | null = null;
  export let operatorResult: CopilotResearchCardResult | null = null;
  export let latestHandoff: CrossTabHandoffEnvelope | null = null;
  export let loading = false;
  export let activeRun: CopilotRunState | null = null;
  /** Sessions with a non-terminal run, including ones the user switched away from. */
  export let runningSessionIds: string[] = [];
  /** The latest composer submission and whether the server accepted it. */
  export let lastSubmission: CopilotComposerSubmission | null = null;
  export let creatingSession = false;
  export let sessionCreateError: string | null = null;
  export let onCancelRun: () => Promise<unknown> | void = () => {};
  export let onGenerate: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void;
  export let onPlan: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onOperatorPlan: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onRunOperator: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onArchiveSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onRestoreSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onRenameSession: (
    sessionId: string,
    title: string,
    expectedUpdatedAt?: string | null
  ) => Promise<unknown> | void = () => {};
  export let onDeleteSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onLoadSessions: () => Promise<unknown> | void = () => {};
  export let onSelectSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onSearchSessions: (options?: { includeArchived?: boolean; search?: string }) => Promise<unknown> | void = () => {};
  export let onNewSession: () =>
    | Promise<CopilotSessionSummary | null>
    | CopilotSessionSummary
    | null = () => null;
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};
  export let onOpenSource: (source: CopilotSourceRef) => Promise<unknown> | void = () => {};
  export let onSelectArtifact: (artifactId: string | null) => unknown = () => {};
  export let onCreateArtifact: (
    options: {
      artifactType: "memo" | "report";
      template: "concise_memo" | "research_report";
      title?: string | null;
      sourceTurnIds: string[];
    }
  ) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onUpdateArtifact: (
    artifactId: string,
    options: { title?: string; body?: string; expectedUpdatedAt?: string | null }
  ) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onDuplicateArtifact: (
    artifactId: string,
    title?: string | null
  ) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onDeleteArtifact: (artifactId: string) => Promise<unknown> | unknown = () => {};
  export let onExportArtifact: (artifactId: string) => Promise<string | null> | string | null = () => null;

  type CopilotRoleMode = "agent" | "operator";

  let roleMode: CopilotRoleMode = "agent";
  let reasoningEffort: CopilotReasoningEffort = "medium";
  let promptText = "";
  let surface: CopilotWorkspaceSurface = synthesisSurface;
  let threadEntries: CopilotThreadEntry[] = [];
  let sessionSearch = "";
  let includeArchivedSessions = false;
  let contextMenuOpen = false;
  let contextEl: HTMLDivElement | null = null;
  let scrollEl: HTMLDivElement | null = null;
  let shouldScroll = false;
  let artifactInspectorOpen = false;
  let renamingSessionId: string | null = null;
  let renameTitle = "";
  let deleteSessionId: string | null = null;
  let restoredSessionId: string | null = null;
  let newSessionPending = false;
  let handledSubmissionId = 0;
  let storageNoticeDismissed = false;
  let storageDetailsOpen = false;

  function applyAcceptedSubmission(submission: CopilotComposerSubmission | null) {
    const resolved = resolveComposerDraft({ draft: promptText, handledSubmissionId }, submission);
    promptText = resolved.draft;
    handledSubmissionId = resolved.handledSubmissionId;
  }

  function setRoleMode(nextMode: CopilotRoleMode) {
    roleMode = nextMode;
    reasoningEffort = nextMode === "operator" ? "low" : "medium";
  }

  async function handleGenerate() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    // The composer is cleared by the accepted-submission contract below, not by
    // the final status: a quota, refusal, or provider failure after acceptance
    // is already persisted as a retryable turn.
    const result = await onGenerate(surface.domain, promptText.trim(), reasoningEffort);
    if (result != null) {
      await onLoadSessions();
    }
  }

  async function handlePlan() {
    if (!surface.domain || loading) {
      return;
    }
    if (roleMode === "operator") {
      await onOperatorPlan(surface.domain, promptText.trim(), reasoningEffort);
      return;
    }
    await onPlan(surface.domain, promptText.trim(), reasoningEffort);
  }

  async function handleRunOperator() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onRunOperator(surface.domain, promptText.trim(), reasoningEffort);
    if (result != null) {
      await onLoadSessions();
    }
  }

  async function handleSubmit() {
    if (roleMode === "operator") {
      await handleRunOperator();
    } else {
      await handleGenerate();
    }
  }

  async function handleNewSession() {
    // A running conversation must not block a new one, and a second activation
    // while the create is in flight must not produce a second blank session.
    if (creatingSession || newSessionPending) {
      return;
    }
    newSessionPending = true;
    try {
      const created = await onNewSession();
      if (created == null) {
        return;
      }
      promptText = "";
      sessionSearch = "";
      await onLoadSessions();
    } finally {
      newSessionPending = false;
    }
  }

  async function handleArchiveSession(sessionId: string, event: MouseEvent) {
    event.stopPropagation();
    if (!sessionId || loading) {
      return;
    }
    const result = await onArchiveSession(sessionId);
    if (result != null) {
      await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
    }
  }

  async function handleRestoreSession(sessionId: string, event: MouseEvent) {
    event.stopPropagation();
    if (!sessionId || loading) return;
    const result = await onRestoreSession(sessionId);
    if (result != null) {
      await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
    }
  }

  function beginRenameSession(session: CopilotSessionSummary, event: MouseEvent) {
    event.stopPropagation();
    renamingSessionId = session.session_id;
    renameTitle = session.title;
  }

  async function finishRenameSession(session: CopilotSessionSummary) {
    const title = renameTitle.trim();
    if (!title || title === session.title) {
      renamingSessionId = null;
      return;
    }
    const result = await onRenameSession(session.session_id, title, session.updated_at);
    if (result != null) {
      renamingSessionId = null;
      await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
    }
  }

  function requestDeleteSession(sessionId: string, event: MouseEvent) {
    event.stopPropagation();
    deleteSessionId = sessionId;
  }

  async function confirmDeleteSession() {
    if (!deleteSessionId) return;
    const sessionId = deleteSessionId;
    deleteSessionId = null;
    const result = await onDeleteSession(sessionId);
    if (result != null) {
      await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
    }
  }

  async function handleSearchSessions() {
    await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
  }

  async function handleSelectSession(sessionId: string) {
    // Switching conversations does not cancel a server-owned run; the source
    // session keeps its running indicator and reconciles through replay.
    if (!sessionId) {
      return;
    }
    await onSelectSession(sessionId);
  }

  function handleComposerKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  }

  function sessionStatusLabel(session: CopilotSessionSummary) {
    // Archive state now lives in the lifecycle state label, so this stays a
    // grounding descriptor.
    if (session.turn_count === 0) {
      return "empty";
    }
    return session.active_domain ?? "mixed";
  }

  onMount(() => {
    const onDocClick = (event: MouseEvent) => {
      if (contextMenuOpen && contextEl && !contextEl.contains(event.target as Node)) {
        contextMenuOpen = false;
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        contextMenuOpen = false;
        renamingSessionId = null;
        deleteSessionId = null;
        storageDetailsOpen = false;
      }
    };
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  });

  afterUpdate(() => {
    if (shouldScroll && scrollEl) {
      scrollEl.scrollTop = scrollEl.scrollHeight;
      shouldScroll = false;
    }
  });

  $: surface = synthesisSurface;
  $: threadEntries = surface.thread?.entries ?? [];
  // Referenced directly so the transcript re-renders when a replayed session
  // arrives; a function call here would hide the dependency from Svelte.
  $: persistedTurns = activeSession?.turns ?? [];
  $: chatTurns = threadEntries.length
    ? threadEntries.map((entry) => ({
        id: entry.entryId,
        index: entry.turnIndex,
        prompt: entry.prompt,
        result: entry.result
      }))
    : persistedTurns.map((turn) => ({
        id: turn.turn_id,
        index: turn.turn_index,
        prompt: turn.prompt,
        result: turn.result
      }));
  $: selectedScopeOptions = synthesisSurface.scopeOptions.filter(
    (option) =>
      option.domain != null && option.supported && synthesisSurface.selectedScopeDomains.includes(option.domain)
  );
  $: contextSummary =
    selectedScopeOptions.length === 0
      ? "Select context"
      : selectedScopeOptions.length <= 2
        ? selectedScopeOptions.map((option) => option.label).join(", ")
        : `${selectedScopeOptions[0].label} +${selectedScopeOptions.length - 1}`;
  $: activeSessionId = activeSession?.session.session_id ?? null;
  $: if (activeSessionId && restoredSessionId !== activeSessionId) {
    restoredSessionId = activeSessionId;
    const persistedTurn = activeSession?.turns[activeSession.turns.length - 1];
    if (persistedTurn) {
      roleMode = persistedTurn.role === "research_operator" ? "operator" : "agent";
      reasoningEffort = (persistedTurn.reasoning_effort as CopilotReasoningEffort | null) ?? "medium";
    }
  }
  // Clearing is driven by acceptance, not by the final status, so a prompt that
  // was persisted as a turn never lingers in the textarea. The helper keeps
  // `promptText` out of this statement's dependency set.
  $: applyAcceptedSubmission(lastSubmission);
  $: sessionPresentations = sessions.map((session) =>
    describeCopilotSession(session, { selectedSessionId: activeSessionId, runningSessionIds })
  );
  $: storageRecovery = summarizeCopilotStorageRecovery(storageStatus);
  $: storageNoticeVisible = storageRecovery != null && !storageNoticeDismissed;
  $: hasPlanMessage =
    (roleMode === "agent" && researchPlan != null) ||
    (roleMode === "operator" && (operatorPlan != null || operatorResult != null));
  $: runStreaming = activeRun != null && (activeRun.phase === "pending" || activeRun.phase === "streaming");
  $: inFlightPrompt = resolveInFlightPrompt(promptText, lastSubmission);
  $: lastTurn = chatTurns.length ? chatTurns[chatTurns.length - 1] : null;
  $: retryPrompt =
    !runStreaming && !loading && lastTurn != null && lastTurn.result.status !== "ready" && lastTurn.prompt
      ? lastTurn.prompt
      : null;
  // Re-scroll to the bottom whenever the transcript or in-flight state changes.
  $: if (chatTurns || loading || hasPlanMessage || activeRun) {
    shouldScroll = true;
  }

  async function handleStop() {
    await onCancelRun();
  }

  async function handleRetry() {
    if (!retryPrompt || !surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onGenerate(surface.domain, retryPrompt, reasoningEffort);
    if (result != null) {
      await onLoadSessions();
    }
  }
</script>

<section class="copilot" class:inspector-open={artifactInspectorOpen}>
  <aside class="sidebar">
    <div class="sidebar-head">
      <button
        type="button"
        class="new-chat"
        on:click={handleNewSession}
        disabled={creatingSession || newSessionPending}
        aria-busy={creatingSession || newSessionPending}
        aria-label="Start a new Copilot conversation"
      >
        <span aria-hidden="true">+</span>
        {creatingSession || newSessionPending ? "Starting…" : "New chat"}
      </button>
      {#if sessionCreateError}
        <p class="new-chat-error" role="alert">New chat failed: {sessionCreateError}</p>
      {/if}
    </div>
    <div class="sidebar-filter">
      <input
        bind:value={sessionSearch}
        placeholder="Search conversations"
        on:keydown={(event) => event.key === "Enter" && handleSearchSessions()}
      />
      <label class="archived-toggle">
        <input type="checkbox" bind:checked={includeArchivedSessions} on:change={handleSearchSessions} />
        Archived
      </label>
    </div>
    <div class="session-list">
      {#if sessions.length}
        {#each sessions as session, sessionIndex (session.session_id)}
          {@const state = sessionPresentations[sessionIndex]}
          <div
            class="session-row"
            class:active={state.selected}
            class:archived={state.archived}
            class:running={state.running}
          >
            {#if renamingSessionId === session.session_id}
              <form class="session-rename" on:submit|preventDefault={() => finishRenameSession(session)}>
                <input bind:value={renameTitle} aria-label="Session title" maxlength="96" />
                <button type="submit">Save</button>
                <button type="button" on:click={() => (renamingSessionId = null)}>Cancel</button>
              </form>
            {:else}
              <button
                type="button"
                class="session-select"
                aria-current={state.selected ? "true" : undefined}
                aria-label={state.accessibleLabel}
                on:click={() => handleSelectSession(session.session_id)}
              >
                <span class="session-title">
                  {session.title}
                  {#if state.running}
                    <span class="running-dot" title="A run is still streaming in this conversation" aria-hidden="true"></span>
                  {/if}
                </span>
                <span class="session-meta">
                  <span class="session-state" class:selected={state.selected} class:running={state.running}>{state.stateLabel}</span>
                  · {session.turn_count} turn{session.turn_count === 1 ? "" : "s"} · {session.artifact_count} artifact{session.artifact_count === 1 ? "" : "s"} · {sessionStatusLabel(session)}
                </span>
              </button>
              <div class="session-actions">
                <button type="button" on:click={(event) => beginRenameSession(session, event)}>Rename</button>
                {#if session.archived_at == null}
                  <button type="button" on:click={(event) => handleArchiveSession(session.session_id, event)}>Archive</button>
                {:else}
                  <button type="button" on:click={(event) => handleRestoreSession(session.session_id, event)}>Restore</button>
                {/if}
                <button type="button" class="danger-link" on:click={(event) => requestDeleteSession(session.session_id, event)}>Delete</button>
              </div>
            {/if}
          </div>
        {/each}
      {:else}
        <p class="sidebar-empty">No conversations yet.</p>
      {/if}
    </div>
  </aside>

  <main class="chat">
    <div class="chat-top">
    <header class="chat-head">
      <div class="context-picker" bind:this={contextEl}>
        <button
          type="button"
          class="context-trigger"
          class:open={contextMenuOpen}
          on:click={() => (contextMenuOpen = !contextMenuOpen)}
        >
          <span class="context-label">Context</span>
          <span class="context-value">{contextSummary}</span>
          <span class="caret" aria-hidden="true">▾</span>
        </button>
        {#if contextMenuOpen}
          <div class="context-menu" role="listbox" aria-label="Context scope">
            {#if synthesisSurface.scopeOptions.length}
              {#each synthesisSurface.scopeOptions as option (option.tabId)}
                <button
                  type="button"
                  class="context-option"
                  class:selected={option.domain != null && synthesisSurface.selectedScopeDomains.includes(option.domain)}
                  disabled={!option.supported || option.domain == null}
                  title={option.disabledReason ?? option.contextLabel}
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
                    <span class="dot warn" title={option.warningLabel}></span>
                  {:else if option.freshnessLabel}
                    <span class="dot ok" title={option.freshnessLabel}></span>
                  {/if}
                </button>
              {/each}
            {:else}
              <p class="context-empty">Load Gamma contexts from the workspace first.</p>
            {/if}
          </div>
        {/if}
      </div>

      <div class="head-controls">
        <button
          type="button"
          class="artifact-trigger"
          class:active={artifactInspectorOpen}
          on:click={() => (artifactInspectorOpen = !artifactInspectorOpen)}
          aria-expanded={artifactInspectorOpen}
        >
          Artifacts <span>{artifacts.length}</span>
        </button>
        {#if storageRecovery}
          <button
            type="button"
            class="storage-trigger"
            class:active={storageDetailsOpen}
            aria-expanded={storageDetailsOpen}
            aria-controls="copilot-storage-recovery"
            aria-label={`Storage recovery diagnostics — ${storageRecovery.headline}`}
            on:click={() => {
              storageDetailsOpen = !storageDetailsOpen;
              if (storageDetailsOpen) {
                storageNoticeDismissed = false;
              }
            }}
          >
            Storage <span>{storageRecovery.count}</span>
          </button>
        {/if}
        {#if latestHandoff}
          <span class="handoff-chip" title="Opened from a cross-tab handoff">
            {latestHandoff.source_tab} → {latestHandoff.intended_target_tab}
          </span>
        {/if}
        <div class="role-tabs" role="tablist" aria-label="Copilot role">
          <button type="button" class:active={roleMode === "agent"} on:click={() => setRoleMode("agent")}>
            Agent
          </button>
          <button type="button" class:active={roleMode === "operator"} on:click={() => setRoleMode("operator")}>
            Operator
          </button>
        </div>
        <label class="effort-select">
          <span>Thinking</span>
          <select bind:value={reasoningEffort} disabled={loading}>
            <option value="minimal">minimal</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="xhigh">xhigh</option>
          </select>
        </label>
      </div>
    </header>

    {#if storageRecovery && (storageNoticeVisible || storageDetailsOpen)}
      <section
        id="copilot-storage-recovery"
        class="storage-strip"
        role="status"
        aria-live="polite"
        aria-label="Copilot storage recovery"
      >
        <div class="storage-summary">
          <span class="storage-badge" aria-hidden="true">RECOVERY</span>
          <p>
            <strong>{storageRecovery.headline}.</strong>
            {storageRecovery.explanation}
          </p>
          <div class="storage-actions">
            <button
              type="button"
              aria-expanded={storageDetailsOpen}
              on:click={() => (storageDetailsOpen = !storageDetailsOpen)}
            >
              {storageDetailsOpen ? "Hide records" : "Inspect records"}
            </button>
            <button
              type="button"
              on:click={() => {
                storageNoticeDismissed = true;
                storageDetailsOpen = false;
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
        {#if storageDetailsOpen}
          <ul class="storage-details">
            {#each storageRecovery.details as detail (detail.warningId)}
              <li>
                <span class="storage-detail-label">{detail.label}</span>
                <span class="storage-detail-message">{detail.message}</span>
              </li>
            {/each}
          </ul>
          <p class="storage-footnote">
            Original records were preserved in the local Copilot store. Dismissing this notice keeps the
            recovery history — reopen it from the Storage control above.
          </p>
        {/if}
      </section>
    {/if}
    </div>

    <div class="transcript" bind:this={scrollEl}>
      {#if !surface.supported && chatTurns.length === 0}
        <div class="empty-chat">
          <h2>Grounded Research Copilot</h2>
          <p>Select a context to ground the conversation, then ask anything across your Gamma tabs.</p>
        </div>
      {:else if chatTurns.length === 0 && !hasPlanMessage && !runStreaming && !loading}
        <div class="empty-chat">
          <h2>Ask anything</h2>
          <p>Grounded in {contextSummary}. Gamma stays read-only and Copilot preserves provenance and warnings.</p>
        </div>
      {:else}
        <div class="messages">
          {#each chatTurns as turn, index (turn.id)}
            {#if turn.prompt}
              <div class="msg user">
                <div class="bubble">{turn.prompt}</div>
              </div>
            {/if}
            <div class="msg assistant">
              <div class="role-tag">GAMMA</div>
              <div class="assistant-body">
                <CopilotTranscriptResult result={turn.result} {onOpenSource} />
              </div>
            </div>
          {/each}

          {#if roleMode === "agent" && researchPlan}
            <div class="msg assistant">
              <div class="role-tag">PLAN</div>
              <div class="assistant-body">
                <CopilotTranscriptResult result={null} {researchPlan} {onOpenSource} />
              </div>
            </div>
          {:else if roleMode === "operator" && operatorPlan}
            <div class="msg assistant">
              <div class="role-tag">OPERATOR PLAN</div>
              <div class="assistant-body">
                <CopilotTranscriptResult result={operatorResult} {operatorPlan} {onOpenSource} />
              </div>
            </div>
          {:else if roleMode === "operator" && operatorResult}
            <div class="msg assistant">
              <div class="role-tag">OPERATOR RUN</div>
              <div class="assistant-body">
                <CopilotTranscriptResult result={operatorResult} {onOpenSource} />
              </div>
            </div>
          {/if}

          {#if runStreaming && inFlightPrompt}
            <div class="msg user">
              <div class="bubble">{inFlightPrompt}</div>
            </div>
          {/if}
          {#if runStreaming && activeRun}
            <div class="msg assistant">
              <div class="role-tag">GAMMA</div>
              <div class="assistant-body">
                {#if activeRun.toolNotes.length}
                  <div class="run-tools">
                    {#each activeRun.toolNotes as note, noteIndex (noteIndex)}
                      <span class="run-tool" class:done={note.state === "done"} title={note.summary ?? note.toolName}>
                        {note.state === "running" ? "⋯" : "✓"} {note.toolName}
                      </span>
                    {/each}
                  </div>
                {/if}
                {#if activeRun.provisionalText}
                  <pre class="run-provisional" aria-label="Provisional streamed output">{activeRun.provisionalText}<span class="caret-blink">▍</span></pre>
                  <small class="run-provisional-note">provisional stream — the final structured card replaces this on completion</small>
                {:else}
                  <div class="thinking" aria-label="Generating">
                    <span></span><span></span><span></span>
                  </div>
                {/if}
                {#if activeRun.warnings.length}
                  <p class="run-status-detail">{activeRun.warnings[activeRun.warnings.length - 1]}</p>
                {/if}
                {#if activeRun.statusDetail}
                  <p class="run-status-detail">{activeRun.statusDetail}</p>
                {/if}
              </div>
            </div>
          {:else if loading}
            <div class="msg assistant">
              <div class="role-tag">GAMMA</div>
              <div class="assistant-body">
                <div class="thinking" aria-label="Generating">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <footer class="composer">
      <textarea
        bind:value={promptText}
        rows={1}
        placeholder={surface.supported ? surface.placeholder : surface.guidance}
        disabled={!surface.domain || loading}
        on:keydown={handleComposerKeydown}
      ></textarea>
      <div class="composer-actions">
        <span class="composer-hint">{surface.selectionMessage ?? surface.guidance}</span>
        <div class="composer-buttons">
          {#if retryPrompt}
            <button type="button" class="secondary" disabled={!surface.supported} on:click={handleRetry} title="Resend the last prompt">
              Retry
            </button>
          {/if}
          <button type="button" class="secondary" disabled={!surface.domain || loading} on:click={handlePlan}>
            {roleMode === "operator" ? "Operator Plan" : "Plan"}
          </button>
          {#if runStreaming}
            <button type="button" class="primary stop" on:click={handleStop} title="Cancel the streaming run">
              Stop
            </button>
          {:else}
            <button type="button" class="primary" disabled={!surface.supported || loading} on:click={handleSubmit}>
              {#if loading}
                {roleMode === "operator" ? "Running…" : "Generating…"}
              {:else if roleMode === "operator"}
                Run Operator
              {:else}
                {chatTurns.length ? "Follow Up" : "Send"}
              {/if}
            </button>
          {/if}
        </div>
      </div>
    </footer>
  </main>

  {#if artifactInspectorOpen}
    <CopilotArtifactsPanel
      sessionId={activeSessionId}
      turns={activeSession?.turns ?? []}
      {artifacts}
      {activeArtifact}
      saveState={artifactSaveState}
      onSelect={onSelectArtifact}
      onCreate={onCreateArtifact}
      onUpdate={onUpdateArtifact}
      onDuplicate={onDuplicateArtifact}
      onDelete={onDeleteArtifact}
      onExport={onExportArtifact}
      {onOpenSource}
      onClose={() => (artifactInspectorOpen = false)}
    />
  {/if}

  {#if deleteSessionId}
    <div class="session-confirm-backdrop">
      <div class="session-confirm" role="alertdialog" aria-label="Confirm session deletion">
        <strong>Delete this Copilot session?</strong>
        <p>The transcript, snapshots, and artifacts move to recoverable local trash. Archiving is a separate, non-destructive action.</p>
        <div>
          <button type="button" on:click={() => (deleteSessionId = null)}>Cancel</button>
          <button type="button" class="danger-confirm-button" on:click={confirmDeleteSession}>Confirm delete</button>
        </div>
      </div>
    </div>
  {/if}

</section>

<style>
  .copilot {
    position: relative;
    display: grid;
    grid-template-columns: 16rem minmax(0, 1fr);
    gap: var(--space-4);
    /* The Gamma shell scrolls naturally, so anchor the chat to the viewport to
       get a fixed transcript scroll region with a pinned composer. Offset =
       topbar + shell paddings (~63px top + ~18px bottom). */
    height: calc(100vh - 5.5rem);
    min-height: 32rem;
    min-width: 0;
  }

  .copilot.inspector-open {
    grid-template-columns: 14rem minmax(28rem, 1fr) minmax(18rem, 22rem);
  }

  /* ---- Sidebar ---- */
  .sidebar {
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    min-height: 0;
  }

  .sidebar-head {
    padding: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .new-chat {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    height: 30px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    font-size: var(--text-base);
    cursor: pointer;
  }

  .new-chat span {
    color: var(--accent);
    font-size: var(--text-md);
    line-height: 1;
  }

  .new-chat:hover:not(:disabled) {
    border-color: var(--accent);
  }

  .sidebar-filter {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .sidebar-filter > input {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-2) var(--space-4);
    font: inherit;
    font-size: var(--text-sm);
    min-height: 1.75rem;
    border-radius: var(--radius-sm);
  }

  .sidebar-filter > input:focus-visible {
    outline: none;
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-strong));
  }

  .archived-toggle {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .archived-toggle input {
    width: 13px;
    height: 13px;
    padding: 0;
  }

  .session-list {
    overflow-y: auto;
    min-height: 0;
  }

  .session-row {
    display: grid;
    gap: var(--space-1);
    width: 100%;
    border-bottom: 1px solid var(--divider);
    background: transparent;
  }

  .session-row:hover,
  .session-row.active {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .session-row.active {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .session-row.active .session-title {
    color: var(--accent);
  }

  .session-row.archived .session-title {
    color: var(--text-2);
  }

  .session-select {
    display: grid;
    gap: var(--space-1);
    width: 100%;
    padding: var(--space-4);
    border: 0;
    background: transparent;
    text-align: left;
    cursor: pointer;
  }

  .session-title {
    color: var(--text-0);
    font-size: var(--text-base);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .session-meta {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
  }

  .session-actions,
  .session-rename {
    display: flex;
    gap: var(--space-2);
    padding: 0 var(--space-4) var(--space-3);
  }

  .session-actions button,
  .session-rename button {
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--text-2);
    font: inherit;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
  }

  .session-actions button:hover,
  .session-rename button:hover {
    color: var(--accent);
  }

  .session-actions .danger-link {
    color: var(--negative);
    margin-left: auto;
  }

  .session-rename {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    padding-top: var(--space-3);
  }

  .session-rename input {
    min-width: 0;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    font-size: var(--text-sm);
    padding: var(--space-2);
  }

  .sidebar-empty,
  .context-empty {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-xs);
    padding: var(--space-4);
    margin: 0;
  }

  /* ---- Chat pane ---- */
  .chat {
    display: grid;
    /* chat top (header + optional status strip) · transcript · pinned composer */
    grid-template-rows: auto minmax(0, 1fr) auto;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    min-height: 0;
    min-width: 0;
  }

  .chat-top {
    min-width: 0;
  }

  .chat-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    flex-wrap: wrap;
  }

  .context-picker {
    position: relative;
  }

  .context-trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    height: 28px;
    padding: 0 var(--space-4);
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .context-trigger:hover,
  .context-trigger.open {
    border-color: var(--accent);
  }

  .context-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .context-value {
    color: var(--text-0);
  }

  .caret {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .context-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 20;
    min-width: 15rem;
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
    font: inherit;
    font-size: var(--text-sm);
    text-align: left;
    cursor: pointer;
  }

  .context-option:last-child {
    border-bottom: 0;
  }

  .context-option:hover:not(:disabled) {
    background: rgba(122, 166, 200, 0.06);
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

  .context-option-label {
    min-width: 0;
  }

  .context-option-reason {
    color: var(--text-2);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
    white-space: normal;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
  }

  .dot.ok {
    background: var(--positive);
  }

  .dot.warn {
    background: var(--warning);
  }

  .head-controls {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    flex-wrap: wrap;
  }

  .artifact-trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-3);
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .artifact-trigger span {
    color: var(--accent);
    font-size: var(--text-xs);
  }

  .artifact-trigger.active {
    border-color: var(--accent);
    color: var(--text-0);
  }

  .handoff-chip {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
    border: 1px solid var(--divider);
    padding: var(--space-1) var(--space-3);
  }

  .role-tabs {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
  }

  .role-tabs button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-2) var(--space-5);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .role-tabs button:last-child {
    border-right: 0;
  }

  .role-tabs button:hover {
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-0);
  }

  .role-tabs button.active {
    background: rgba(122, 166, 200, 0.12);
    color: var(--accent);
  }

  .effort-select {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .effort-select select {
    height: 28px;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    padding: 0 var(--space-3);
    text-transform: lowercase;
  }

  /* ---- Transcript ---- */
  .transcript {
    overflow-y: auto;
    min-height: 0;
    padding: var(--space-5);
  }

  .empty-chat {
    height: 100%;
    display: grid;
    align-content: center;
    justify-items: center;
    gap: var(--space-3);
    text-align: center;
    padding: var(--space-7);
  }

  .empty-chat h2 {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-lg);
  }

  .empty-chat p {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-base);
    max-width: 28rem;
    line-height: 1.5;
  }

  .messages {
    display: grid;
    gap: var(--space-6);
    max-width: 52rem;
    margin: 0 auto;
  }

  .msg.user {
    display: flex;
    justify-content: flex-end;
  }

  .msg.user .bubble {
    max-width: 80%;
    padding: var(--space-4) var(--space-5);
    border: 1px solid rgba(122, 166, 200, 0.34);
    border-radius: 6px;
    background: rgba(122, 166, 200, 0.1);
    color: var(--text-0);
    font-size: var(--text-base);
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .msg.assistant {
    display: grid;
    gap: var(--space-3);
  }

  .role-tag {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
  }

  .assistant-body {
    display: grid;
    gap: var(--space-4);
  }

  .caret-blink {
    color: var(--accent);
    animation: caret 1s steps(1) infinite;
  }

  @keyframes caret {
    50% {
      opacity: 0;
    }
  }

  /* ---- Thinking ---- */
  .thinking {
    display: inline-flex;
    gap: var(--space-2);
    padding: var(--space-2) 0;
  }

  .thinking span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-2);
    animation: thinking 1.2s ease-in-out infinite;
  }

  .thinking span:nth-child(2) {
    animation-delay: 0.15s;
  }

  .thinking span:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes thinking {
    0%, 60%, 100% {
      opacity: 0.25;
      transform: translateY(0);
    }
    30% {
      opacity: 1;
      transform: translateY(-3px);
    }
  }

  /* ---- Live streamed run ---- */
  .run-provisional {
    margin: 0;
    padding: var(--space-3) var(--space-4);
    border: 1px dashed var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: var(--text-sm);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 14rem;
    overflow-y: auto;
  }

  .run-provisional-note {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .run-tools {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .run-tool {
    border: 1px solid var(--panel-strong);
    padding: 1px var(--space-3);
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .run-tool.done {
    color: var(--text-1);
    border-color: color-mix(in srgb, var(--accent) 36%, var(--panel-strong));
  }

  .run-status-detail {
    margin: 0;
    color: var(--warning);
    font-size: var(--text-sm);
  }

  /* ---- Composer ---- */
  .composer {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4);
    border-top: 1px solid var(--divider);
  }

  .composer textarea {
    width: 100%;
    min-height: 2.4rem;
    max-height: 12rem;
    resize: vertical;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-4) var(--space-5);
    font: inherit;
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .composer textarea:focus {
    outline: none;
    border-color: var(--accent);
  }

  .composer-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .composer-hint {
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.3;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .composer-buttons {
    display: flex;
    gap: var(--space-3);
    flex: none;
  }

  .composer-buttons button {
    height: 30px;
    padding: 0 var(--space-5);
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
    white-space: nowrap;
  }

  .composer-buttons button:hover:not(:disabled) {
    border-color: var(--accent);
  }

  .composer-buttons button.primary {
    color: var(--accent);
    border-color: rgba(122, 166, 200, 0.34);
  }

  .composer-buttons button.primary.stop {
    color: var(--negative);
    border-color: color-mix(in srgb, var(--negative) 40%, var(--panel-strong));
  }

  .composer-buttons button:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .session-confirm-backdrop {
    position: absolute;
    inset: 0;
    z-index: 40;
    display: grid;
    place-items: center;
    padding: var(--space-5);
    background: color-mix(in srgb, var(--bg-0) 82%, transparent);
  }

  .session-confirm {
    display: grid;
    gap: var(--space-4);
    width: min(28rem, 100%);
    padding: var(--space-5);
    border: 1px solid color-mix(in srgb, var(--negative) 52%, var(--panel-strong));
    background: var(--bg-1);
  }

  .session-confirm strong {
    color: var(--text-0);
  }

  .session-confirm p {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: var(--leading-normal);
  }

  .session-confirm > div {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .session-confirm button {
    min-height: 1.8rem;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-xs);
    padding: 0 var(--space-4);
  }

  .session-confirm .danger-confirm-button {
    color: var(--negative);
    border-color: color-mix(in srgb, var(--negative) 48%, var(--panel-strong));
  }

  /* ---- Storage recovery status ----
     Rendered in the chat grid flow so it can never cover the composer, the
     artifact inspector, or any confirmation control. */
  .storage-strip {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .storage-summary {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .storage-badge {
    flex: none;
    padding: var(--space-1) var(--space-3);
    border: 1px solid color-mix(in srgb, var(--warning) 52%, var(--panel-strong));
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .storage-summary p {
    margin: 0;
    flex: 1 1 18rem;
    min-width: 0;
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .storage-summary strong {
    color: var(--text-1);
  }

  .storage-actions {
    display: flex;
    gap: var(--space-2);
    flex: none;
  }

  .storage-actions button {
    min-height: 1.6rem;
    padding: 0 var(--space-3);
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-2);
    font: inherit;
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    cursor: pointer;
  }

  .storage-actions button:hover {
    border-color: var(--accent);
    color: var(--text-1);
  }

  .storage-details {
    display: grid;
    gap: var(--space-2);
    max-height: 9rem;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
    border: 1px solid var(--divider);
  }

  .storage-details li {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--divider);
    min-width: 0;
  }

  .storage-details li:last-child {
    border-bottom: 0;
  }

  .storage-detail-label {
    color: var(--warning);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: var(--text-2xs);
    overflow-wrap: anywhere;
  }

  .storage-detail-message {
    color: var(--text-2);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
    overflow-wrap: anywhere;
  }

  .storage-footnote {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
  }

  .storage-trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    height: 28px;
    padding: 0 var(--space-3);
    border: 1px solid color-mix(in srgb, var(--warning) 42%, var(--panel-strong));
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    cursor: pointer;
  }

  .storage-trigger span {
    color: var(--warning);
    font-size: var(--text-xs);
  }

  .storage-trigger.active {
    border-color: var(--warning);
    color: var(--text-0);
  }

  .new-chat-error {
    margin: var(--space-2) 0 0;
    color: var(--negative);
    font-size: var(--text-2xs);
    line-height: var(--leading-snug);
  }

  .running-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    margin-left: var(--space-2);
    border-radius: 50%;
    background: var(--accent);
    vertical-align: middle;
  }

  .session-state.selected {
    color: var(--accent);
  }

  .session-state.running {
    color: var(--warning);
  }

  @media (max-width: 1180px) {
    .copilot.inspector-open {
      grid-template-columns: 16rem minmax(0, 1fr);
    }

    .copilot.inspector-open :global(.artifact-panel) {
      position: absolute;
      inset: 0 0 0 auto;
      z-index: 35;
      width: min(24rem, calc(100% - 2rem));
      background: var(--bg-1);
    }
  }

  @media (max-width: 820px) {
    .copilot {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto minmax(0, 1fr);
    }

    .sidebar {
      grid-template-rows: auto;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
    }

    .session-list {
      display: none;
    }

    .composer-hint {
      display: none;
    }

    .copilot.inspector-open :global(.artifact-panel) {
      inset: 0;
      width: 100%;
    }
  }
</style>
