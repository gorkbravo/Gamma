<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import CopilotTranscriptResult from "./CopilotTranscriptResult.svelte";
  import type {
    CopilotArtifact,
    CopilotResearchReport,
    CopilotSourceRef,
    CopilotTurnRecord
  } from "../lib/api/types";

  export let sessionId: string | null = null;
  export let turns: CopilotTurnRecord[] = [];
  export let artifacts: CopilotArtifact[] = [];
  export let activeArtifact: CopilotArtifact | null = null;
  export let saveState: "idle" | "saving" | "saved" | "error" = "idle";
  export let onSelect: (artifactId: string | null) => unknown = () => {};
  export let onCreate: (options: {
    artifactType: "memo" | "report";
    template: "concise_memo" | "research_report";
    title?: string | null;
    sourceTurnIds: string[];
  }) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onUpdate: (
    artifactId: string,
    options: { title?: string; body?: string; expectedUpdatedAt?: string | null }
  ) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onDuplicate: (
    artifactId: string,
    title?: string | null
  ) => Promise<CopilotArtifact | null> | CopilotArtifact | null = () => null;
  export let onDelete: (artifactId: string) => Promise<unknown> | unknown = () => {};
  export let onExport: (artifactId: string) => Promise<string | null> | string | null = () => null;
  export let onOpenSource: ((source: CopilotSourceRef) => Promise<unknown> | void) | null = null;
  export let onClose: () => void = () => {};

  type PanelMode = "edit" | "preview";

  let panelMode: PanelMode = "edit";
  let createTemplate: "concise_memo" | "research_report" = "concise_memo";
  let createTitle = "";
  let selectedTurnIds: string[] = [];
  let draftTitle = "";
  let draftBody = "";
  let loadedArtifactId: string | null = null;
  let expectedUpdatedAt: string | null = null;
  let deleteConfirmationOpen = false;
  let exportConfirmationOpen = false;
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let saveRevision = 0;

  function reportFromArtifact(artifact: CopilotArtifact): CopilotResearchReport {
    return {
      report_id: artifact.artifact_id,
      session_id: artifact.session_id,
      title: artifact.title,
      source_turn_ids: artifact.source_turn_ids,
      source_memo_ids: artifact.source_memo_ids,
      source_backed_claims: artifact.source_backed_claims,
      inferred_claims: artifact.inferred_claims,
      assumptions: artifact.assumptions,
      missing_data: artifact.missing_data,
      warnings: artifact.warnings,
      warning_provenance: artifact.warning_provenance,
      tool_trace_summary: artifact.tool_trace_summary,
      sources: artifact.sources,
      generated_at: artifact.updated_at,
      source_provider: artifact.source_provider,
      origin: artifact.origin,
      transformation_note: artifact.transformation_note
    };
  }

  function toggleTurn(turnId: string) {
    selectedTurnIds = selectedTurnIds.includes(turnId)
      ? selectedTurnIds.filter((id) => id !== turnId)
      : [...selectedTurnIds, turnId];
  }

  async function createArtifact() {
    if (!sessionId) return;
    const artifactType = createTemplate === "concise_memo" ? "memo" : "report";
    const created = await onCreate({
      artifactType,
      template: createTemplate,
      title: createTitle.trim() || null,
      sourceTurnIds: selectedTurnIds
    });
    if (created) {
      createTitle = "";
      selectedTurnIds = [];
      panelMode = "edit";
    }
  }

  function clearSaveTimer() {
    if (saveTimer != null) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
  }

  async function saveDraft(revision = saveRevision) {
    clearSaveTimer();
    if (!activeArtifact || revision !== saveRevision) return;
    const artifactId = activeArtifact.artifact_id;
    const updated = await onUpdate(artifactId, {
      title: draftTitle,
      body: draftBody,
      expectedUpdatedAt
    });
    if (updated && updated.artifact_id === artifactId) {
      expectedUpdatedAt = updated.updated_at;
    }
  }

  function scheduleSave() {
    if (!activeArtifact) return;
    saveRevision += 1;
    const revision = saveRevision;
    clearSaveTimer();
    saveTimer = setTimeout(() => void saveDraft(revision), 650);
  }

  async function duplicateSelected() {
    if (!activeArtifact) return;
    await onDuplicate(activeArtifact.artifact_id, `${draftTitle || activeArtifact.title} copy`);
  }

  async function deleteSelected() {
    if (!activeArtifact) return;
    const artifactId = activeArtifact.artifact_id;
    deleteConfirmationOpen = false;
    await onDelete(artifactId);
  }

  function markdownFilename(artifact: CopilotArtifact) {
    const slug = artifact.title
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 64);
    return `${slug || artifact.artifact_type}-${artifact.artifact_id.slice(0, 8)}.md`;
  }

  async function exportSelected() {
    if (!activeArtifact) return;
    exportConfirmationOpen = false;
    const markdown = await onExport(activeArtifact.artifact_id);
    if (markdown == null || typeof document === "undefined") return;
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = markdownFilename(activeArtifact);
    link.click();
    URL.revokeObjectURL(url);
  }

  function handleDocumentKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      if (deleteConfirmationOpen || exportConfirmationOpen) {
        deleteConfirmationOpen = false;
        exportConfirmationOpen = false;
      } else {
        onClose();
      }
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s" && activeArtifact) {
      event.preventDefault();
      saveRevision += 1;
      void saveDraft(saveRevision);
    }
  }

  onMount(() => {
    document.addEventListener("keydown", handleDocumentKeydown);
    return () => document.removeEventListener("keydown", handleDocumentKeydown);
  });

  onDestroy(clearSaveTimer);

  $: if (activeArtifact?.artifact_id !== loadedArtifactId) {
    clearSaveTimer();
    loadedArtifactId = activeArtifact?.artifact_id ?? null;
    draftTitle = activeArtifact?.title ?? "";
    draftBody = activeArtifact?.body ?? "";
    expectedUpdatedAt = activeArtifact?.updated_at ?? null;
    deleteConfirmationOpen = false;
    exportConfirmationOpen = false;
  }
  $: if (
    saveState === "error" &&
    activeArtifact?.artifact_id === loadedArtifactId &&
    activeArtifact.updated_at !== expectedUpdatedAt
  ) {
    expectedUpdatedAt = activeArtifact.updated_at;
  }
  $: previewReport = activeArtifact ? reportFromArtifact({ ...activeArtifact, title: draftTitle, body: draftBody }) : null;
</script>

<aside class="artifact-panel" aria-label="Copilot artifacts">
  <header class="panel-head">
    <div>
      <span class="eyebrow">Session artifacts</span>
      <strong>{artifacts.length} local</strong>
    </div>
    <button type="button" class="icon-button" on:click={onClose} aria-label="Close artifact inspector">×</button>
  </header>

  {#if !sessionId}
    <p class="empty">Select a persisted session to create memos or reports.</p>
  {:else}
    <section class="create-section" aria-label="Create artifact">
      <label>
        <span>Template</span>
        <select bind:value={createTemplate}>
          <option value="concise_memo">Concise memo</option>
          <option value="research_report">Research report</option>
        </select>
      </label>
      <label>
        <span>Title</span>
        <input bind:value={createTitle} placeholder="Generated from selected turns" />
      </label>
      <fieldset>
        <legend>Source turns <b>{selectedTurnIds.length} selected</b></legend>
        <div class="turn-list">
          {#each turns as turn (turn.turn_id)}
            <label class="turn-option">
              <input
                type="checkbox"
                checked={selectedTurnIds.includes(turn.turn_id)}
                on:change={() => toggleTurn(turn.turn_id)}
              />
              <span>
                <strong>#{turn.turn_index + 1} · {turn.role.replace("research_", "")}</strong>
                <small>{turn.prompt || turn.result.card?.title || "Untitled turn"}</small>
              </span>
            </label>
          {:else}
            <p class="empty compact">No source turns are available yet.</p>
          {/each}
        </div>
      </fieldset>
      <button type="button" class="primary-action" on:click={createArtifact} disabled={!turns.length}>
        Create {createTemplate === "concise_memo" ? "memo" : "report"}
      </button>
    </section>

    <nav class="artifact-list" aria-label="Saved session artifacts">
      {#each artifacts as artifact (artifact.artifact_id)}
        <button
          type="button"
          class:active={artifact.artifact_id === activeArtifact?.artifact_id}
          on:click={() => onSelect(artifact.artifact_id)}
        >
          <span class="artifact-type">{artifact.artifact_type}</span>
          <strong>{artifact.title}</strong>
          <small>{artifact.source_turn_ids.length} turns · {new Date(artifact.updated_at).toLocaleDateString()}</small>
        </button>
      {:else}
        <p class="empty compact">No memos or reports in this session.</p>
      {/each}
    </nav>

    {#if activeArtifact}
      <section class="editor" aria-label="Selected artifact editor">
        <div class="mode-tabs" role="tablist" aria-label="Artifact mode">
          <button type="button" class:active={panelMode === "edit"} on:click={() => (panelMode = "edit")}>Edit</button>
          <button type="button" class:active={panelMode === "preview"} on:click={() => (panelMode = "preview")}>Preview</button>
          <span class:error={saveState === "error"} aria-live="polite">
            {saveState === "saving" ? "saving…" : saveState === "saved" ? "saved" : saveState === "error" ? "save failed" : ""}
          </span>
        </div>

        {#if activeArtifact.unavailable_source_turn_ids.length}
          <p class="warning">
            {activeArtifact.unavailable_source_turn_ids.length} linked source turn
            {activeArtifact.unavailable_source_turn_ids.length === 1 ? " is" : "s are"} unavailable. The saved provenance snapshot is retained.
          </p>
        {/if}

        {#if panelMode === "edit"}
          <label>
            <span>Artifact title</span>
            <input bind:value={draftTitle} on:input={scheduleSave} />
          </label>
          <label class="body-field">
            <span>Markdown body</span>
            <textarea bind:value={draftBody} on:input={scheduleSave}></textarea>
          </label>
          {#if saveState === "error"}
            <button type="button" class="text-action" on:click={() => saveDraft(saveRevision)}>Retry save</button>
          {/if}
        {:else}
          <article class="preview">
            <h3>{draftTitle}</h3>
            <pre>{draftBody || "No body content."}</pre>
            {#if previewReport}
              <CopilotTranscriptResult
                result={null}
                report={previewReport}
                compact={true}
                cardLabel={null}
                {onOpenSource}
              />
            {/if}
          </article>
        {/if}

        <div class="artifact-actions">
          <button type="button" on:click={duplicateSelected}>Duplicate</button>
          <button type="button" on:click={() => (exportConfirmationOpen = true)}>Export Markdown</button>
          <button type="button" class="danger" on:click={() => (deleteConfirmationOpen = true)}>Delete</button>
        </div>

        {#if exportConfirmationOpen}
          <div class="confirmation" role="alertdialog" aria-label="Confirm Markdown export">
            <p>Download this Markdown snapshot? An existing file with the same name may be replaced by your browser.</p>
            <div>
              <button type="button" on:click={() => (exportConfirmationOpen = false)}>Cancel</button>
              <button type="button" class="primary-action" on:click={exportSelected}>Download</button>
            </div>
          </div>
        {/if}

        {#if deleteConfirmationOpen}
          <div class="confirmation danger-confirm" role="alertdialog" aria-label="Confirm artifact deletion">
            <p>Delete “{activeArtifact.title}”? The record is moved to recoverable local trash.</p>
            <div>
              <button type="button" on:click={() => (deleteConfirmationOpen = false)}>Cancel</button>
              <button type="button" class="danger" on:click={deleteSelected}>Confirm delete</button>
            </div>
          </div>
        {/if}
      </section>
    {/if}
  {/if}
</aside>

<style>
  .artifact-panel {
    display: grid;
    grid-template-rows: auto auto auto minmax(0, 1fr);
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
  }

  .panel-head,
  .mode-tabs,
  .artifact-actions,
  .confirmation > div {
    display: flex;
    align-items: center;
  }

  .panel-head {
    justify-content: space-between;
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  .panel-head > div {
    display: grid;
    gap: var(--space-1);
  }

  .eyebrow,
  label > span,
  legend,
  .artifact-type {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-2xs);
  }

  .panel-head strong {
    color: var(--text-0);
    font-size: var(--text-sm);
  }

  button,
  input,
  select,
  textarea {
    font: inherit;
  }

  button {
    cursor: pointer;
  }

  .icon-button,
  .mode-tabs button,
  .artifact-actions button,
  .confirmation button,
  .text-action {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-1);
    min-height: 1.75rem;
    padding: 0 var(--space-3);
    font-size: var(--text-xs);
  }

  .icon-button {
    width: 1.75rem;
    padding: 0;
    font-size: var(--text-md);
  }

  .create-section,
  .editor {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  label {
    display: grid;
    gap: var(--space-1);
  }

  input,
  select,
  textarea {
    width: 100%;
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
  }

  input:focus-visible,
  select:focus-visible,
  textarea:focus-visible,
  button:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: 1px;
  }

  fieldset {
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }

  legend {
    display: flex;
    justify-content: space-between;
    width: 100%;
    margin-bottom: var(--space-2);
  }

  legend b {
    color: var(--accent);
    font-weight: 500;
  }

  .turn-list {
    max-height: 7rem;
    overflow-y: auto;
    border: 1px solid var(--divider);
  }

  .turn-option {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--divider);
  }

  .turn-option:last-child {
    border-bottom: 0;
  }

  .turn-option input {
    width: 0.8rem;
    margin-top: 0.15rem;
    padding: 0;
  }

  .turn-option > span {
    display: grid;
    min-width: 0;
  }

  .turn-option strong,
  .artifact-list strong {
    color: var(--text-0);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .turn-option small,
  .artifact-list small {
    color: var(--text-2);
    font-size: var(--text-2xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .primary-action {
    border-color: color-mix(in srgb, var(--accent) 44%, var(--panel-strong)) !important;
    color: var(--accent) !important;
  }

  .primary-action:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .artifact-list {
    max-height: 10rem;
    overflow-y: auto;
    border-bottom: 1px solid var(--divider);
  }

  .artifact-list > button {
    display: grid;
    gap: var(--space-1);
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border: 0;
    border-bottom: 1px solid var(--divider);
    background: transparent;
    text-align: left;
  }

  .artifact-list > button:hover,
  .artifact-list > button.active {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .artifact-list > button.active .artifact-type {
    color: var(--accent);
  }

  .editor {
    min-height: 0;
    overflow-y: auto;
    border-bottom: 0;
  }

  .mode-tabs {
    gap: 0;
  }

  .mode-tabs button + button {
    border-left: 0;
  }

  .mode-tabs button.active {
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }

  .mode-tabs span {
    margin-left: auto;
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .mode-tabs span.error,
  .warning {
    color: var(--warning);
  }

  .body-field textarea {
    min-height: 12rem;
    resize: vertical;
    line-height: var(--leading-normal);
  }

  .preview {
    display: grid;
    gap: var(--space-4);
    min-width: 0;
  }

  .preview h3 {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-md);
  }

  .preview pre {
    margin: 0;
    color: var(--text-1);
    font: inherit;
    font-size: var(--text-sm);
    line-height: var(--leading-normal);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .artifact-actions {
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .danger {
    color: var(--negative) !important;
    border-color: color-mix(in srgb, var(--negative) 42%, var(--panel-strong)) !important;
  }

  .confirmation {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--warning);
    background: var(--bg-1);
  }

  .confirmation p,
  .warning,
  .empty {
    margin: 0;
    font-size: var(--text-xs);
    line-height: var(--leading-normal);
  }

  .confirmation p,
  .empty {
    color: var(--text-2);
  }

  .confirmation > div {
    justify-content: flex-end;
    gap: var(--space-2);
  }

  .danger-confirm {
    border-color: color-mix(in srgb, var(--negative) 58%, var(--panel-strong));
  }

  .empty {
    padding: var(--space-4);
  }

  .empty.compact {
    padding: var(--space-3);
  }
</style>
