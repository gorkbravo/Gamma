<script lang="ts">
  import type {
    CopilotBaseDomain,
    CopilotDomain,
    CrossTabHandoffEnvelope,
    CopilotResearchActionDefinition,
    CopilotMemo,
    CopilotOperatorPlan,
    CopilotResearchCardResult,
    CopilotResearchPlan,
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
  export let actionDefinitions: CopilotResearchActionDefinition[] = [];
  export let researchPlan: CopilotResearchPlan | null = null;
  export let operatorPlan: CopilotOperatorPlan | null = null;
  export let operatorResult: CopilotResearchCardResult | null = null;
  export let latestHandoff: CrossTabHandoffEnvelope | null = null;
  export let loading = false;
  export let onGenerate: (domain: CopilotDomain, prompt?: string) => Promise<unknown> | void;
  export let onPlan: (domain: CopilotDomain, prompt?: string) => Promise<unknown> | void = () => {};
  export let onOperatorPlan: (domain: CopilotDomain, prompt?: string) => Promise<unknown> | void = () => {};
  export let onRunOperator: (domain: CopilotDomain, prompt?: string) => Promise<unknown> | void = () => {};
  export let onCreateMemo: (title?: string, notes?: string) => Promise<unknown> | void = () => {};
  export let onUpdateMemo: (memoId: string, title: string, body: string) => Promise<unknown> | void = () => {};
  export let onArchiveSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onExportMemo: (memoId: string) => Promise<string | null | unknown> | string | null | void = () => null;
  export let onLoadSessions: () => Promise<unknown> | void = () => {};
  export let onSelectSession: (sessionId: string) => Promise<unknown> | void = () => {};
  export let onSearchSessions: (options?: { includeArchived?: boolean; search?: string }) => Promise<unknown> | void = () => {};
  export let onToggleScope: (domain: CopilotBaseDomain) => void = () => {};

  type FocusMode = "synthesis" | "active_tab";
  type CopilotRoleMode = "agent" | "operator";

  let focusMode: FocusMode = "synthesis";
  let roleMode: CopilotRoleMode = "agent";
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

  function activeTurns() {
    return activeSession?.turns ?? [];
  }

  function hasTurns() {
    return activeTurns().length > 0 || threadEntries.length > 0;
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

  function setFocusMode(nextMode: FocusMode) {
    focusMode = nextMode;
  }

  function setRoleMode(nextMode: CopilotRoleMode) {
    roleMode = nextMode;
  }

  async function handleGenerate() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onGenerate(surface.domain, promptText.trim());
    if (result != null) {
      // Keep the prompt draft recoverable when generation fails or times out.
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
      await onOperatorPlan(surface.domain, promptText.trim());
      return;
    }
    await onPlan(surface.domain, promptText.trim());
  }

  async function handleRunOperator() {
    if (!surface.supported || !surface.domain || loading) {
      return;
    }
    const result = await onRunOperator(surface.domain, promptText.trim());
    if (result != null) {
      const status = (result as { status?: string }).status;
      if (status === "ready") {
        promptText = "";
      }
      await onLoadSessions();
    }
  }

  async function handleCreateMemo() {
    if (loading || !hasTurns()) {
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

  function formatMs(value: number) {
    if (value >= 1000) {
      return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)}s`;
    }
    return `${value}ms`;
  }

  $: surface = focusMode === "synthesis" ? synthesisSurface : activeSurface;
  $: threadEntries = surface.thread?.entries ?? [];
  $: selectedCount = synthesisSurface.selectedScopeDomains.length;
  $: loadedCount = synthesisSurface.scopeOptions.length;
  $: displayedTurnCount = threadEntries.length || activeTurns().length || 0;
  $: operatorStepCount = operatorSteps().length;
  $: operatorCheckpointCount = operatorCheckpoints().length;
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
        <strong>{roleMode === "operator" ? "Operator" : focusMode === "synthesis" ? "Synthesis" : "Active Tab"}</strong>
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
        <span>Operator Steps</span>
        <strong>{operatorStepCount}</strong>
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

        <div class="role-tabs" role="tablist" aria-label="Copilot role">
          <button
            type="button"
            class:active={roleMode === "agent"}
            on:click={() => setRoleMode("agent")}
          >
            Research Agent
          </button>
          <button
            type="button"
            class:active={roleMode === "operator"}
            on:click={() => setRoleMode("operator")}
          >
            Research Operator
          </button>
        </div>

        <textarea
          bind:value={promptText}
          rows={5}
          placeholder={surface.supported ? surface.placeholder : surface.guidance}
          disabled={!surface.domain || loading}
          on:keydown={handleComposerKeydown}
        ></textarea>

        <div class="composer-footer">
          <span>{surface.selectionMessage ?? surface.guidance}</span>
          <div class="composer-actions">
            <button type="button" class="secondary" disabled={!surface.domain || loading} on:click={handlePlan}>
              {roleMode === "operator" ? "Operator Plan" : "Plan"}
            </button>
            {#if roleMode === "operator"}
              <button type="button" disabled={!surface.supported || loading} on:click={handleRunOperator}>
                {loading ? "Running..." : "Run Operator"}
              </button>
            {:else}
              <button type="button" disabled={!surface.supported || loading} on:click={handleGenerate}>
                {loading ? "Generating..." : threadEntries.length ? "Follow Up" : "Generate"}
              </button>
            {/if}
          </div>
        </div>

        {#if roleMode === "operator" && operatorPlan}
          <div class="plan-preview operator-preview">
            <div class="plan-preview-head">
              <span>{operatorPlan.role.replaceAll("_", " ")}</span>
              <strong>{operatorPlan.intent.replaceAll("_", " ")}</strong>
            </div>
            <div class="plan-budget">
              <span>{operatorPlan.max_tool_calls} tools max</span>
              <span>{operatorPlan.max_provider_calls} provider calls max</span>
              <span>{formatMs(operatorPlan.max_elapsed_ms)} guard</span>
              <span>{operatorCheckpointCount} checkpoints</span>
            </div>
            {#if operatorPlan.target_entities.length}
              <div class="entity-row">
                {#each operatorPlan.target_entities.slice(0, 4) as entity}
                  <span>{entity.kind}: {entity.label ?? entity.id}</span>
                {/each}
              </div>
            {/if}
            <div class="operator-steps">
              {#each operatorSteps() as step (step.step_id)}
                <div class:checkpoint={step.requires_confirmation}>
                  <span>{step.order}</span>
                  <strong>{step.title}</strong>
                  <small>{step.domain.replaceAll("_", " ")} / {step.action_type.replaceAll("_", " ")}</small>
                  <small>{actionPermissionLabel(step.tool_id, step.permission_policy)}</small>
                  <p>{step.rationale ?? "Operator step planned by Gamma."}</p>
                  <em>{expectedArtifactsLabel(step.expected_artifacts)}</em>
                </div>
              {/each}
            </div>
            {#if operatorCheckpoints().length}
              <div class="checkpoint-list">
                {#each operatorCheckpoints() as checkpoint (checkpoint.checkpoint_id)}
                  <div>
                    <strong>{checkpoint.default_policy.replaceAll("_", " ")}</strong>
                    <span>{checkpoint.required_for_tool_ids.join(" / ")}</span>
                    <p>{checkpoint.reason}</p>
                  </div>
                {/each}
              </div>
            {/if}
            {#if operatorWarnings().length}
              <p class="plan-warning">{operatorWarnings()[0]}</p>
            {/if}
          </div>
        {:else if roleMode === "agent" && researchPlan}
          <div class="plan-preview">
            <div class="plan-preview-head">
              <span>{researchPlan.depth_profile}</span>
              <strong>{researchPlan.intent.replaceAll("_", " ")}</strong>
            </div>
            <div class="plan-budget">
              <span>{researchPlan.max_tool_calls} tools max</span>
              <span>{researchPlan.max_provider_calls} provider calls max</span>
              <span>{formatMs(researchPlan.max_elapsed_ms)} guard</span>
            </div>
            {#if planEntities().length}
              <div class="entity-row">
                {#each planEntities().slice(0, 4) as entity}
                  <span>{entity.kind}: {entity.label ?? entity.id}</span>
                {/each}
              </div>
            {/if}
            <div class="domain-plan">
              {#each planDomains().slice(0, 5) as item}
                <div>
                  <strong>{item.domain.replaceAll("_", " ")}</strong>
                  <span>{item.depth} / {item.estimated_tool_calls}T / {item.estimated_provider_calls}P / {formatMs(item.estimated_latency_ms)}</span>
                  <p>{item.reason}</p>
                </div>
              {/each}
            </div>
            {#if planDecisions().length}
              <div class="domain-decisions">
                {#each planDecisions().slice(0, 6) as decision}
                  <div class:omitted={!decision.used}>
                    <strong>{decision.used ? "USED" : "SKIP"}</strong>
                    <span>{decision.domain.replaceAll("_", " ")}</span>
                    <p>{decision.reason}</p>
                  </div>
                {/each}
              </div>
            {/if}
            {#if planWarnings().length}
              <p class="plan-warning">{planWarnings()[0]}</p>
            {/if}
          </div>
        {/if}

        {#if roleMode === "operator" && operatorResult}
          <div class="operator-result">
            <strong>{operatorResult.status}</strong>
            <span>{operatorResult.message ?? "No operator execution message."}</span>
            <small>{operatorResult.tool_traces.length} tool traces / {operatorResult.sources.length} sources / {operatorResult.warnings.length} warnings</small>
          </div>
          {#if operatorEvents().length}
            <div class="operator-events">
              {#each operatorEvents() as event (event.event_id)}
                <div class:event-warning={event.event_type === "warning" || event.event_type === "confirmation-needed"}>
                  <span>{event.sequence}</span>
                  <strong>{operatorEventMeta(event.event_type)}</strong>
                  <small>{event.tool_id ?? event.step_id ?? event.run_id}</small>
                  <p>{event.message ?? event.title ?? "Operator event recorded."}</p>
                  <em>{event.source_ids.length} src / {event.warnings.length} warn</em>
                </div>
              {/each}
            </div>
          {/if}
        {/if}
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
        {:else if activeTurns().length}
          <div class="thread-list">
            {#each activeTurns() as turn (turn.turn_id)}
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
          <button type="button" disabled={loading || !hasTurns()} on:click={handleCreateMemo}>
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

  .composer-actions {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }

  .title-line {
    justify-content: flex-start;
    gap: 0.45rem;
  }

  .mode-tabs,
  .role-tabs {
    display: inline-flex;
    border: 1px solid var(--panel-strong);
    width: max-content;
  }

  .mode-tabs button,
  .role-tabs button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.28rem 0.65rem;
    font: inherit;
    font-size: 0.79rem;
    white-space: nowrap;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }

  .mode-tabs button:last-child { border-right: 0; }
  .role-tabs button:last-child { border-right: 0; }
  .mode-tabs button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .role-tabs button:hover { background: rgba(122, 166, 200, 0.06); color: var(--text-0); }
  .mode-tabs button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .role-tabs button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .mode-tabs button.active { background: rgba(122, 166, 200, 0.12); color: var(--accent); }
  .role-tabs button.active { background: rgba(122, 166, 200, 0.12); color: var(--accent); }

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

  .composer-footer button.secondary {
    color: var(--text-1);
    border-color: var(--panel-strong);
  }

  .plan-preview {
    display: grid;
    gap: 0;
    border: 1px solid var(--divider);
    background: var(--bg-0);
  }

  .plan-preview-head,
  .plan-budget,
  .entity-row,
  .domain-plan div,
  .domain-decisions div,
  .plan-warning {
    padding: 0.5rem 0.65rem;
    border-bottom: 1px solid var(--divider);
  }

  .plan-preview-head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    align-items: baseline;
  }

  .plan-preview-head span,
  .plan-budget span,
  .domain-plan span,
  .domain-decisions strong,
  .domain-decisions span,
  .entity-row span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0;
    font-size: 0.62rem;
  }

  .plan-preview-head strong,
  .domain-plan strong,
  .domain-decisions span {
    color: var(--text-0);
    text-transform: uppercase;
    letter-spacing: 0;
    font-size: 0.72rem;
  }

  .plan-budget {
    display: flex;
    flex-wrap: wrap;
    gap: 0.65rem;
  }

  .entity-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
  }

  .domain-plan {
    display: grid;
    gap: 0;
  }

  .operator-steps,
  .checkpoint-list,
  .operator-events {
    display: grid;
    gap: 0;
  }

  .operator-steps div,
  .checkpoint-list div,
  .operator-events div,
  .operator-result {
    display: grid;
    grid-template-columns: 2rem minmax(9rem, 0.32fr) minmax(7rem, 0.2fr) minmax(7rem, 0.2fr) minmax(0, 1fr) minmax(6rem, 0.16fr);
    gap: 0.55rem;
    align-items: start;
    padding: 0.5rem 0.65rem;
    border-bottom: 1px solid var(--divider);
  }

  .operator-steps div.checkpoint {
    border-left: 1px solid var(--warning);
    padding-left: 0.6rem;
  }

  .checkpoint-list div {
    grid-template-columns: minmax(8rem, 0.3fr) minmax(10rem, 0.3fr) minmax(0, 1fr);
  }

  .operator-result {
    grid-template-columns: minmax(7rem, 0.2fr) minmax(0, 1fr) auto;
    border: 1px solid var(--divider);
    background: var(--bg-0);
  }

  .operator-events {
    border: 1px solid var(--divider);
    border-top: 0;
  }

  .operator-events div {
    grid-template-columns: 2rem minmax(8rem, 0.22fr) minmax(10rem, 0.26fr) minmax(0, 1fr) minmax(5rem, 0.12fr);
  }

  .operator-events div.event-warning {
    border-left: 1px solid var(--warning);
    padding-left: 0.6rem;
  }

  .operator-steps span,
  .operator-steps small,
  .operator-steps em,
  .checkpoint-list strong,
  .checkpoint-list span,
  .operator-events span,
  .operator-events small,
  .operator-events em,
  .operator-result strong,
  .operator-result small {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0;
    font-size: 0.62rem;
    font-style: normal;
  }

  .operator-steps > div > span,
  .operator-events > div > span,
  .operator-result strong {
    color: var(--accent);
  }

  .operator-steps strong,
  .operator-events strong {
    color: var(--text-0);
    font-size: 0.74rem;
  }

  .operator-steps p,
  .checkpoint-list p,
  .operator-events p,
  .operator-result span {
    margin: 0;
    color: var(--text-1);
    line-height: 1.35;
    font-size: 0.76rem;
  }

  .domain-plan div,
  .domain-decisions div {
    display: grid;
    grid-template-columns: minmax(8rem, 0.35fr) minmax(7rem, 0.28fr) minmax(0, 1fr);
    gap: 0.6rem;
    align-items: start;
  }

  .domain-decisions div.omitted strong {
    color: var(--text-2);
  }

  .domain-plan div:last-child,
  .plan-warning {
    border-bottom: 0;
  }

  .domain-plan p,
  .domain-decisions p,
  .plan-warning {
    margin: 0;
    color: var(--text-1);
    line-height: 1.35;
    font-size: 0.76rem;
  }

  .plan-warning {
    color: var(--warning);
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

    .composer-actions,
    .domain-plan div,
    .domain-decisions div,
    .operator-steps div,
    .checkpoint-list div,
    .operator-events div,
    .operator-result {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
