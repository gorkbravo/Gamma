<script lang="ts">
  import { afterUpdate, onMount } from "svelte";
  import type {
    CopilotBaseDomain,
    CopilotDomain,
    CopilotReasoningEffort,
    CrossTabHandoffEnvelope,
    CopilotResearchActionDefinition,
    CopilotOperatorPlan,
    CopilotResearchCardResult,
    CopilotResearchPlan,
    CopilotSessionDetail,
    CopilotSessionSummary,
    CopilotThreadEntry,
    CopilotThreadState
  } from "../lib/api/types";

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
  export let actionDefinitions: CopilotResearchActionDefinition[] = [];
  export let researchPlan: CopilotResearchPlan | null = null;
  export let operatorPlan: CopilotOperatorPlan | null = null;
  export let operatorResult: CopilotResearchCardResult | null = null;
  export let latestHandoff: CrossTabHandoffEnvelope | null = null;
  export let loading = false;
  export let onGenerate: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void;
  export let onPlan: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onOperatorPlan: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onRunOperator: (domain: CopilotDomain, prompt?: string, reasoningEffort?: CopilotReasoningEffort) => Promise<unknown> | void = () => {};
  export let onArchiveSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onLoadSessions: () => Promise<unknown> | void = () => {};
  export let onSelectSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onSearchSessions: (options?: { includeArchived?: boolean; search?: string }) => Promise<unknown> | void = () => {};
  export let onNewSession: () => Promise<unknown> | void = () => {};
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};

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

  const reduceMotion =
    typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Typewriter reveal for the most recent assistant message.
  let typewriterId = "";
  let typewriterShown = "";
  let typewriterTyping = false;
  let typewriterTimer: ReturnType<typeof setInterval> | null = null;
  let lastSeenTurnId: string | null = null;

  function activeTurns() {
    return activeSession?.turns ?? [];
  }

  function planEntities() {
    return researchPlan?.target_entities ?? [];
  }

  function planDomains() {
    return researchPlan?.domain_plan ?? [];
  }

  function planDecisions() {
    return researchPlan?.domain_decisions ?? [];
  }

  function planWarnings() {
    return researchPlan?.warnings ?? [];
  }

  function operatorSteps() {
    return operatorPlan?.steps ?? [];
  }

  function operatorCheckpoints() {
    return operatorPlan?.confirmation_checkpoints ?? [];
  }

  function operatorWarnings() {
    return operatorPlan?.warnings ?? [];
  }

  function operatorEvents() {
    return operatorResult?.operator_events ?? [];
  }

  function operatorEventMeta(eventType: string) {
    return eventType.replaceAll("-", " ");
  }

  function actionDefinition(toolId: string | null) {
    if (!toolId) {
      return null;
    }
    return actionDefinitions.find((definition) => definition.tool_id === toolId) ?? null;
  }

  function actionPermissionLabel(toolId: string | null, fallback: string) {
    const definition = actionDefinition(toolId);
    return definition?.permission_policy ?? fallback;
  }

  function expectedArtifactsLabel(items: string[]) {
    return items.length ? items.slice(0, 3).join(" / ") : "trace";
  }

  function setRoleMode(nextMode: CopilotRoleMode) {
    roleMode = nextMode;
    reasoningEffort = nextMode === "operator" ? "low" : "medium";
  }

  function clearTypewriter() {
    if (typewriterTimer) {
      clearInterval(typewriterTimer);
      typewriterTimer = null;
    }
    typewriterTyping = false;
  }

  function startTypewriter(turn: ChatTurn) {
    clearTypewriter();
    const full = turn.result.message ?? "";
    typewriterId = turn.id;
    if (reduceMotion || !full) {
      typewriterShown = full;
      return;
    }
    typewriterShown = "";
    typewriterTyping = true;
    const step = Math.max(1, Math.round(full.length / 140));
    let cursor = 0;
    typewriterTimer = setInterval(() => {
      cursor += step;
      typewriterShown = full.slice(0, cursor);
      if (scrollEl) {
        scrollEl.scrollTop = scrollEl.scrollHeight;
      }
      if (cursor >= full.length) {
        typewriterShown = full;
        clearTypewriter();
      }
    }, 16);
  }

  function maybeAnimate(turns: ChatTurn[], isLive: boolean) {
    const last = turns[turns.length - 1];
    const id = last?.id ?? null;
    if (lastSeenTurnId === null && id !== null) {
      // Skip animating content that was already present on first render.
      lastSeenTurnId = id;
      typewriterId = id;
      typewriterShown = last?.result.message ?? "";
      return;
    }
    if (id && id !== lastSeenTurnId && isLive && last?.result.message) {
      startTypewriter(last);
    }
    lastSeenTurnId = id;
  }

  function messageText(turn: ChatTurn, isLast: boolean) {
    if (isLast && turn.id === typewriterId) {
      return typewriterShown;
    }
    return turn.result.message ?? "";
  }

  async function handleGenerate() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onGenerate(surface.domain, promptText.trim(), reasoningEffort);
    if (result != null) {
      const status = (result as { status?: string }).status;
      if (status === "ready") {
        promptText = "";
      }
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
      const status = (result as { status?: string }).status;
      if (status === "ready") {
        promptText = "";
      }
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
    if (loading) {
      return;
    }
    await onNewSession();
    await onLoadSessions();
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

  async function handleSearchSessions() {
    await onSearchSessions({ includeArchived: includeArchivedSessions, search: sessionSearch });
  }

  async function handleSelectSession(sessionId: string) {
    if (!sessionId || loading) {
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

  function providerLabel(result: CopilotResearchCardResult) {
    return result.model ? `${result.provider} / ${result.model}` : result.provider;
  }

  function sourceSummary(result: CopilotResearchCardResult) {
    const parts: string[] = [];
    if (result.sources.length) parts.push(`${result.sources.length} sources`);
    if (result.tool_traces.length) parts.push(`${result.tool_traces.length} tools`);
    if (result.warnings.length) parts.push(`${result.warnings.length} warnings`);
    return parts.join(" / ");
  }

  function sessionStatusLabel(session: CopilotSessionSummary) {
    return session.archived_at ? "archived" : session.active_domain ?? "mixed";
  }

  function formatMs(value: number) {
    if (value >= 1000) {
      return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}s`;
    }
    return `${value}ms`;
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
      }
    };
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
      clearTypewriter();
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
  $: chatTurns = threadEntries.length
    ? threadEntries.map((entry) => ({
        id: entry.entryId,
        index: entry.turnIndex,
        prompt: entry.prompt,
        result: entry.result
      }))
    : activeTurns().map((turn) => ({
        id: turn.turn_id,
        index: turn.turn_index,
        prompt: turn.prompt,
        result: turn.result
      }));
  $: maybeAnimate(chatTurns, threadEntries.length > 0);
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
  $: hasPlanMessage =
    (roleMode === "agent" && researchPlan != null) ||
    (roleMode === "operator" && (operatorPlan != null || operatorResult != null));
  // Re-scroll to the bottom whenever the transcript or in-flight state changes.
  $: if (chatTurns || loading || hasPlanMessage) {
    shouldScroll = true;
  }
</script>

<section class="copilot">
  <aside class="sidebar">
    <div class="sidebar-head">
      <button type="button" class="new-chat" on:click={handleNewSession} disabled={loading}>
        <span aria-hidden="true">+</span> New chat
      </button>
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
        {#each sessions as session (session.session_id)}
          <button
            type="button"
            class="session-row"
            class:active={session.session_id === activeSessionId}
            class:archived={session.archived_at != null}
            on:click={() => handleSelectSession(session.session_id)}
          >
            <span class="session-title">{session.title}</span>
            <span class="session-meta">
              {session.turn_count} turn{session.turn_count === 1 ? "" : "s"} · {sessionStatusLabel(session)}
            </span>
            {#if session.archived_at == null}
              <span
                class="session-archive"
                role="button"
                tabindex="0"
                title="Archive conversation"
                on:click={(event) => handleArchiveSession(session.session_id, event)}
                on:keydown={(event) => event.key === "Enter" && handleArchiveSession(session.session_id, event as unknown as MouseEvent)}
              >Archive</span>
            {/if}
          </button>
        {/each}
      {:else}
        <p class="sidebar-empty">No conversations yet.</p>
      {/if}
    </div>
  </aside>

  <main class="chat">
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
                  <span class="context-option-label">{option.label}</span>
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

    <div class="transcript" bind:this={scrollEl}>
      {#if !surface.supported && chatTurns.length === 0}
        <div class="empty-chat">
          <h2>Grounded Research Copilot</h2>
          <p>Select a context to ground the conversation, then ask anything across your Gamma tabs.</p>
        </div>
      {:else if chatTurns.length === 0 && !hasPlanMessage}
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
                {#if turn.result.message}
                  <p class="assistant-text {turn.result.status}">
                    {messageText(turn, index === chatTurns.length - 1)}{#if typewriterTyping && index === chatTurns.length - 1 && turn.id === typewriterId}<span class="caret-blink">▍</span>{/if}
                  </p>
                {/if}
                {#if turn.result.card}
                  <div class="research-card">
                    <h4>{turn.result.card.title}</h4>
                    <div class="card-field"><span>Hypothesis</span><p>{turn.result.card.hypothesis}</p></div>
                    <div class="card-field"><span>Rationale</span><p>{turn.result.card.rationale}</p></div>
                    <div class="card-field"><span>Proposed test</span><p>{turn.result.card.proposed_test}</p></div>
                  </div>
                {/if}
                <div class="assistant-meta">
                  <span>{providerLabel(turn.result)}</span>
                  {#if sourceSummary(turn.result)}<span>{sourceSummary(turn.result)}</span>{/if}
                </div>
              </div>
            </div>
          {/each}

          {#if roleMode === "agent" && researchPlan}
            <div class="msg assistant">
              <div class="role-tag">PLAN</div>
              <div class="assistant-body">
                <div class="plan-block">
                  <div class="plan-head">
                    <strong>{researchPlan.intent.replaceAll("_", " ")}</strong>
                    <span>{researchPlan.depth_profile}</span>
                  </div>
                  <div class="plan-budget">
                    <span>{researchPlan.max_tool_calls} tools</span>
                    <span>{researchPlan.max_provider_calls} provider calls</span>
                    <span>{formatMs(researchPlan.max_elapsed_ms)} guard</span>
                  </div>
                  {#if planEntities().length}
                    <div class="chip-row">
                      {#each planEntities().slice(0, 4) as entity}
                        <span class="chip">{entity.kind}: {entity.label ?? entity.id}</span>
                      {/each}
                    </div>
                  {/if}
                  {#if planDomains().length}
                    <table class="plan-table">
                      <thead><tr><th>Domain</th><th>Depth</th><th>Reason</th></tr></thead>
                      <tbody>
                        {#each planDomains().slice(0, 5) as item}
                          <tr>
                            <td>{item.domain.replaceAll("_", " ")}</td>
                            <td class="muted">{item.depth} · {item.estimated_tool_calls}T/{item.estimated_provider_calls}P</td>
                            <td>{item.reason}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  {/if}
                  {#if planDecisions().length}
                    <div class="decision-row">
                      {#each planDecisions().slice(0, 6) as decision}
                        <span class="chip" class:skip={!decision.used}>
                          {decision.used ? "USE" : "SKIP"} {decision.domain.replaceAll("_", " ")}
                        </span>
                      {/each}
                    </div>
                  {/if}
                  {#if planWarnings().length}
                    <p class="plan-warning">{planWarnings()[0]}</p>
                  {/if}
                </div>
              </div>
            </div>
          {:else if roleMode === "operator" && operatorPlan}
            <div class="msg assistant">
              <div class="role-tag">OPERATOR PLAN</div>
              <div class="assistant-body">
                <div class="plan-block">
                  <div class="plan-head">
                    <strong>{operatorPlan.intent.replaceAll("_", " ")}</strong>
                    <span>{operatorPlan.role.replaceAll("_", " ")}</span>
                  </div>
                  <div class="plan-budget">
                    <span>{operatorPlan.max_tool_calls} tools</span>
                    <span>{operatorPlan.max_provider_calls} provider calls</span>
                    <span>{formatMs(operatorPlan.max_elapsed_ms)} guard</span>
                    <span>{operatorCheckpoints().length} checkpoints</span>
                  </div>
                  {#if operatorSteps().length}
                    <table class="plan-table">
                      <thead><tr><th>#</th><th>Step</th><th>Action</th><th>Policy</th></tr></thead>
                      <tbody>
                        {#each operatorSteps() as step (step.step_id)}
                          <tr class:checkpoint={step.requires_confirmation}>
                            <td class="muted">{step.order}</td>
                            <td>{step.title}</td>
                            <td class="muted">{step.domain.replaceAll("_", " ")} / {step.action_type.replaceAll("_", " ")}</td>
                            <td class="muted">{actionPermissionLabel(step.tool_id, step.permission_policy)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  {/if}
                  {#if operatorWarnings().length}
                    <p class="plan-warning">{operatorWarnings()[0]}</p>
                  {/if}
                </div>
              </div>
            </div>
          {/if}

          {#if roleMode === "operator" && operatorResult}
            <div class="msg assistant">
              <div class="role-tag">OPERATOR RUN</div>
              <div class="assistant-body">
                <p class="assistant-text {operatorResult.status}">{operatorResult.message ?? "No operator execution message."}</p>
                {#if operatorEvents().length}
                  <table class="plan-table">
                    <thead><tr><th>#</th><th>Event</th><th>Detail</th></tr></thead>
                    <tbody>
                      {#each operatorEvents() as event (event.event_id)}
                        <tr class:checkpoint={event.event_type === "warning" || event.event_type === "confirmation-needed"}>
                          <td class="muted">{event.sequence}</td>
                          <td>{operatorEventMeta(event.event_type)}</td>
                          <td>{event.message ?? event.title ?? "Operator event recorded."}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                {/if}
                <div class="assistant-meta">
                  <span>{operatorResult.tool_traces.length} tools · {operatorResult.sources.length} sources · {operatorResult.warnings.length} warnings</span>
                </div>
              </div>
            </div>
          {/if}

          {#if loading}
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
          <button type="button" class="secondary" disabled={!surface.domain || loading} on:click={handlePlan}>
            {roleMode === "operator" ? "Operator Plan" : "Plan"}
          </button>
          <button type="button" class="primary" disabled={!surface.supported || loading} on:click={handleSubmit}>
            {#if loading}
              {roleMode === "operator" ? "Running…" : "Generating…"}
            {:else if roleMode === "operator"}
              Run Operator
            {:else}
              {chatTurns.length ? "Follow Up" : "Send"}
            {/if}
          </button>
        </div>
      </div>
    </footer>
  </main>
</section>

<style>
  .copilot {
    display: grid;
    grid-template-columns: 16rem minmax(0, 1fr);
    gap: 0.5rem;
    /* The Gamma shell scrolls naturally, so anchor the chat to the viewport to
       get a fixed transcript scroll region with a pinned composer. Offset =
       topbar + shell paddings (~63px top + ~18px bottom). */
    height: calc(100vh - 5.5rem);
    min-height: 32rem;
    min-width: 0;
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
    padding: 0.5rem;
    border-bottom: 1px solid var(--divider);
  }

  .new-chat {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    height: 30px;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
  }

  .new-chat span {
    color: var(--accent);
    font-size: 0.95rem;
    line-height: 1;
  }

  .new-chat:hover:not(:disabled) {
    border-color: var(--accent);
  }

  .sidebar-filter {
    display: grid;
    gap: 0.4rem;
    padding: 0.5rem;
    border-bottom: 1px solid var(--divider);
  }

  .archived-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.64rem;
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
    position: relative;
    display: grid;
    gap: 0.15rem;
    width: 100%;
    padding: 0.5rem 0.6rem;
    border: 0;
    border-bottom: 1px solid var(--divider);
    background: transparent;
    text-align: left;
    cursor: pointer;
  }

  .session-row:hover {
    background: rgba(122, 166, 200, 0.06);
  }

  .session-row.active {
    background: rgba(122, 166, 200, 0.12);
  }

  .session-row.active .session-title {
    color: var(--accent);
  }

  .session-row.archived .session-title {
    color: var(--text-2);
  }

  .session-title {
    color: var(--text-0);
    font-size: 0.82rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .session-meta {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.62rem;
  }

  .session-archive {
    position: absolute;
    top: 0.45rem;
    right: 0.5rem;
    display: none;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.6rem;
    cursor: pointer;
  }

  .session-archive:hover {
    color: var(--accent);
  }

  .session-row:hover .session-archive {
    display: inline;
  }

  .sidebar-empty,
  .context-empty {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.68rem;
    padding: 0.6rem;
    margin: 0;
  }

  /* ---- Chat pane ---- */
  .chat {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    min-height: 0;
    min-width: 0;
  }

  .chat-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--divider);
    flex-wrap: wrap;
  }

  .context-picker {
    position: relative;
  }

  .context-trigger {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    height: 28px;
    padding: 0 0.6rem;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-0);
    font: inherit;
    font-size: 0.78rem;
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
    font-size: 0.62rem;
  }

  .context-value {
    color: var(--text-0);
  }

  .caret {
    color: var(--text-2);
    font-size: 0.6rem;
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
    gap: 0.5rem;
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: 0;
    border-bottom: 1px solid var(--divider);
    background: transparent;
    color: var(--text-1);
    font: inherit;
    font-size: 0.78rem;
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

  .context-option-label {
    flex: 1;
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
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .handoff-chip {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.62rem;
    border: 1px solid var(--divider);
    padding: 0.15rem 0.4rem;
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
    padding: 0.28rem 0.7rem;
    font: inherit;
    font-size: 0.76rem;
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
    gap: 0.4rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.62rem;
  }

  .effort-select select {
    height: 28px;
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: 0.74rem;
    padding: 0 0.4rem;
    text-transform: lowercase;
  }

  /* ---- Transcript ---- */
  .transcript {
    overflow-y: auto;
    min-height: 0;
    padding: 0.85rem;
  }

  .empty-chat {
    height: 100%;
    display: grid;
    align-content: center;
    justify-items: center;
    gap: 0.4rem;
    text-align: center;
    padding: 2rem;
  }

  .empty-chat h2 {
    margin: 0;
    color: var(--text-0);
    font-size: 1.05rem;
  }

  .empty-chat p {
    margin: 0;
    color: var(--text-2);
    font-size: 0.82rem;
    max-width: 28rem;
    line-height: 1.5;
  }

  .messages {
    display: grid;
    gap: 1rem;
    max-width: 52rem;
    margin: 0 auto;
  }

  .msg.user {
    display: flex;
    justify-content: flex-end;
  }

  .msg.user .bubble {
    max-width: 80%;
    padding: 0.55rem 0.75rem;
    border: 1px solid rgba(122, 166, 200, 0.34);
    border-radius: 6px;
    background: rgba(122, 166, 200, 0.1);
    color: var(--text-0);
    font-size: 0.86rem;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .msg.assistant {
    display: grid;
    gap: 0.35rem;
  }

  .role-tag {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.6rem;
  }

  .assistant-body {
    display: grid;
    gap: 0.55rem;
  }

  .assistant-text {
    margin: 0;
    color: var(--text-0);
    font-size: 0.88rem;
    line-height: 1.6;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .assistant-text.error {
    color: var(--negative);
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

  .research-card {
    display: grid;
    gap: 0.4rem;
    border: 1px solid var(--panel-border);
    border-left: 2px solid var(--accent);
    padding: 0.6rem 0.7rem;
  }

  .research-card h4 {
    margin: 0;
    color: var(--text-0);
    font-size: 0.86rem;
  }

  .card-field {
    display: grid;
    gap: 0.15rem;
  }

  .card-field span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
  }

  .card-field p {
    margin: 0;
    color: var(--text-1);
    font-size: 0.82rem;
    line-height: 1.5;
  }

  .assistant-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.6rem;
  }

  /* ---- Plan / operator chat blocks ---- */
  .plan-block {
    display: grid;
    gap: 0.5rem;
    border: 1px solid var(--panel-border);
    border-left: 2px solid var(--accent);
    padding: 0.6rem 0.7rem;
  }

  .plan-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .plan-head strong {
    color: var(--text-0);
    text-transform: uppercase;
    font-size: 0.78rem;
  }

  .plan-head span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.62rem;
  }

  .plan-budget,
  .chip-row,
  .decision-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .plan-budget span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 0.62rem;
  }

  .chip {
    border: 1px solid var(--divider);
    padding: 0.1rem 0.4rem;
    color: var(--text-1);
    font-size: 0.66rem;
  }

  .chip.skip {
    color: var(--text-2);
  }

  .plan-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.74rem;
  }

  .plan-table th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
    font-weight: 500;
    padding: 0.25rem 0.45rem;
    border-bottom: 1px solid var(--divider);
  }

  .plan-table td {
    color: var(--text-1);
    padding: 0.3rem 0.45rem;
    border-bottom: 1px solid var(--divider);
    vertical-align: top;
    line-height: 1.4;
  }

  .plan-table td.muted {
    color: var(--text-2);
  }

  .plan-table tr.checkpoint td:first-child {
    border-left: 2px solid var(--warning);
  }

  .plan-warning {
    margin: 0;
    color: var(--warning);
    font-size: 0.74rem;
    line-height: 1.4;
  }

  /* ---- Thinking ---- */
  .thinking {
    display: inline-flex;
    gap: 0.3rem;
    padding: 0.3rem 0;
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

  /* ---- Composer ---- */
  .composer {
    display: grid;
    gap: 0.4rem;
    padding: 0.6rem;
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
    padding: 0.55rem 0.65rem;
    font: inherit;
    font-size: 0.86rem;
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
    gap: 0.75rem;
  }

  .composer-hint {
    color: var(--text-2);
    font-size: 0.7rem;
    line-height: 1.3;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .composer-buttons {
    display: flex;
    gap: 0.4rem;
    flex: none;
  }

  .composer-buttons button {
    height: 30px;
    padding: 0 0.85rem;
    border: 1px solid var(--panel-strong);
    border-radius: 2px;
    background: var(--bg-1);
    color: var(--text-1);
    font: inherit;
    font-size: 0.76rem;
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

  .composer-buttons button:disabled {
    opacity: 0.45;
    cursor: default;
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
  }
</style>
