<script lang="ts">
  import { onMount } from "svelte";

  import type { ResearchScriptOutput } from "../lib/api/types";
  import { researchScriptOutputDownloadUrl } from "../lib/api/research-scripts";
  import ResearchScriptCodeEditor from "./ResearchScriptCodeEditor.svelte";
  import {
    createWorkspaceResearchScript,
    initializeResearchScriptWorkspace,
    loadResearchScript,
    persistResearchScriptRevision,
    researchScriptWorkspace,
    resolveStagedResearchScriptRevision,
    runSelectedResearchScript,
    selectResearchScriptRevision,
    selectResearchScriptRun,
    updateResearchScriptDraft,
    updateResearchScriptInput,
    type ResearchScriptWorkspaceState
  } from "../lib/stores/research-script";

  export let snapshot: ResearchScriptWorkspaceState | null = null;

  let newScriptTitle = "Research Script";

  $: workspace = snapshot ?? $researchScriptWorkspace;
  $: canonicalRevision = workspace.detail?.revisions.find(
    (item) => item.revision_id === workspace.detail?.script.canonical_revision_id
  ) ?? null;
  $: selectedRevision = workspace.detail?.revisions.find(
    (item) => item.revision_id === workspace.selectedRevisionId
  ) ?? null;
  $: stagedRevisions = (workspace.detail?.revisions ?? []).filter(
    (item) => item.status === "staged"
  );
  $: runnableRevisions = (workspace.detail?.revisions ?? []).filter(
    (item) => item.status === "canonical" || item.status === "superseded"
  );
  $: draftIsDirty = Boolean(canonicalRevision && workspace.sourceDraft !== canonicalRevision.source);
  $: selectedSourceIsDirty = Boolean(selectedRevision && workspace.sourceDraft !== selectedRevision.source);
  $: runtimeAvailable = workspace.capabilities?.available ?? true;
  $: executesSource = workspace.capabilities?.executes_source ?? false;

  onMount(() => {
    if (!snapshot) void initializeResearchScriptWorkspace();
  });

  const shortHash = (value: string | null | undefined) => value ? value.slice(0, 12) : "—";
  const shortDate = (value: string | null | undefined) => value
    ? new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";
  const cell = (value: unknown) => value === null || value === undefined
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
  const changedLineCount = (candidateSource: string, parentSource: string) => {
    const candidate = candidateSource.split("\n");
    const parent = parentSource.split("\n");
    const changed = Math.max(candidate.length, parent.length) === 0
      ? 0
      : Array.from({ length: Math.max(candidate.length, parent.length) })
          .filter((_, index) => candidate[index] !== parent[index]).length;
    return `${changed} changed line${changed === 1 ? "" : "s"}`;
  };

  function onInputFilename(event: Event) {
    updateResearchScriptInput(
      (event.currentTarget as HTMLInputElement).value,
      workspace.inputContent
    );
  }

  function onInputContent(event: Event) {
    updateResearchScriptInput(
      workspace.inputFilename,
      (event.currentTarget as HTMLTextAreaElement).value
    );
  }
</script>

<div class="script-workspace">
  <div class="primary-column">
    <article class="panel safety-panel">
      <div>
        <p class="eyebrow">Runtime boundary</p>
        <h2>{executesSource ? "OpenAI Code Interpreter" : runtimeAvailable ? "Mock / Safe Preview" : "Runtime unavailable"}</h2>
      </div>
      <p>
        {#if executesSource}
          The selected immutable source and input manifest are SHA-256 verified immediately before dispatch.
          Execution is isolated in a disposable, network-disabled provider container and outputs are retained by Gamma.
        {:else if runtimeAvailable}
          Python source is persisted and SHA-256 bound to each run, but it is not executed.
          This preview has no network, host, provider, account, wallet, or trade-tool access.
        {:else}
          The configured provider/model cannot supply the required exact-source runtime. Select the mock runtime for offline use.
        {/if}
      </p>
    </article>

    <article class="panel editor-panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Canonical source</p>
          <h3>{workspace.detail?.script.title ?? "New research script"}</h3>
        </div>
        <div class="status-cluster">
          {#if workspace.detail}
            <span class="status">REV {canonicalRevision?.revision_number ?? "—"}</span>
          {/if}
          <span class:dirty={draftIsDirty} class="status">{draftIsDirty ? "UNSAVED" : "BOUND"}</span>
        </div>
      </div>

      <div class="source-field">
        <span>Python source</span>
        <ResearchScriptCodeEditor
          value={workspace.sourceDraft}
          disabled={workspace.loading !== null}
          onChange={updateResearchScriptDraft}
          ariaLabel="Python source"
        />
      </div>

      <div class="editor-footer">
        <span>{new TextEncoder().encode(workspace.sourceDraft).length.toLocaleString()} / 65,536 bytes</span>
        <span>SHA {shortHash(selectedRevision?.source_sha256)}</span>
      </div>

      <div class="action-row">
        <button
          type="button"
          on:click={() => void persistResearchScriptRevision()}
          disabled={!workspace.detail || !draftIsDirty || workspace.loading !== null}
        >
          {workspace.loading === "save" ? "Saving…" : "Save revision"}
        </button>
        <button
          type="button"
          class="run-button"
          on:click={() => void runSelectedResearchScript()}
          disabled={!workspace.detail || !selectedRevision || selectedSourceIsDirty || workspace.loading !== null || !runtimeAvailable}
        >
          {workspace.loading === "run" ? "Running…" : executesSource ? "Run immutable revision" : "Run safe preview"}
        </button>
      </div>
    </article>

    <article class="panel output-panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Typed outputs</p>
          <h3>Run result</h3>
        </div>
        {#if workspace.selectedRun}
          <span class:failed={workspace.selectedRun.status !== "completed"} class="status">
            {workspace.selectedRun.status}
          </span>
        {/if}
      </div>

      {#if workspace.loading === "run"}
        <div class="state-box">
          {executesSource
            ? "Running the selected immutable revision against its bounded input snapshot…"
            : "Preparing a deterministic mock result for the selected immutable revision…"}
        </div>
      {:else if !workspace.selectedRun}
        <div class="state-box">No run selected. Save a revision, then run the configured bounded runtime.</div>
      {:else if !workspace.selectedRun.outputs.length}
        <div class="state-box">This {workspace.selectedRun.status} run retained no output objects.</div>
      {:else}
        <div class="output-list">
          {#each workspace.selectedRun.outputs as output (output.output_id)}
            <section class:error-output={output.kind === "error"} class="output-card">
              <div class="output-head">
                <span>{output.kind}</span>
                <small>{output.generated ? "GENERATED / DERIVED" : "SOURCE"} · {output.media_type} · {output.byte_size.toLocaleString()} B</small>
              </div>

              {#if output.kind === "metric"}
                <div class="metric-output">
                  <strong>{output.metric_value ?? "—"}</strong>
                  <span>{output.metric_name ?? "Metric"}{output.unit ? ` · ${output.unit}` : ""}</span>
                </div>
              {:else if output.kind === "table"}
                <div class="table-wrap">
                  <table>
                    <thead><tr>{#each output.columns as column}<th>{column}</th>{/each}</tr></thead>
                    <tbody>
                      {#each output.rows as row}
                        <tr>{#each output.columns as column}<td>{cell(row[column])}</td>{/each}</tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
                {#if output.artifact_ref && workspace.selectedRun}
                  <a class="artifact-link" href={researchScriptOutputDownloadUrl(workspace.selectedRun.run_id, output.output_id)} download={output.filename ?? undefined}>
                    Download retained {output.filename ?? "table"}
                  </a>
                {/if}
              {:else if output.kind === "image"}
                <div class="artifact-preview" role="img" aria-label={output.alt_text ?? "Research script image output"}>
                  {#if output.artifact_ref && workspace.selectedRun}
                    <img
                      src={researchScriptOutputDownloadUrl(workspace.selectedRun.run_id, output.output_id)}
                      alt={output.alt_text ?? "Generated research chart"}
                    />
                  {/if}
                  <span>IMAGE ARTIFACT</span>
                  <strong>{output.filename ?? output.output_id}</strong>
                  <small>{output.alt_text ?? "Gamma-retained generated image"}</small>
                </div>
              {:else if output.kind === "file"}
                <div class="file-output">
                  <span>FILE</span>
                  {#if output.artifact_ref && workspace.selectedRun}
                    <a href={researchScriptOutputDownloadUrl(workspace.selectedRun.run_id, output.output_id)} download={output.filename ?? undefined}>
                      {output.filename ?? output.output_id}
                    </a>
                  {:else}
                    <strong>{output.filename ?? output.output_id}</strong>
                  {/if}
                  <small>{output.artifact_ref ?? "Persisted artifact reference"}</small>
                </div>
              {:else}
                <pre>{output.text ?? "No text retained."}</pre>
              {/if}

              {#if output.transformation_note}
                <p class="provenance-note">{output.transformation_note}</p>
              {/if}
            </section>
          {/each}
        </div>
      {/if}
    </article>
  </div>

  <aside class="support-column">
    <article class="panel control-panel">
      <div class="rail-header"><div><p class="eyebrow">Workspace</p><h3>Script controls</h3></div></div>
      <label>
        <span>Loaded script</span>
        <select
          aria-label="Loaded script"
          value={workspace.detail?.script.script_id ?? ""}
          on:change={(event) => void loadResearchScript((event.currentTarget as HTMLSelectElement).value)}
          disabled={workspace.loading !== null}
        >
          <option value="">Select a script</option>
          {#each workspace.scripts as script}
            <option value={script.script_id}>{script.title}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Selected revision</span>
        <select
          aria-label="Selected revision"
          value={workspace.selectedRevisionId ?? ""}
          on:change={(event) => selectResearchScriptRevision((event.currentTarget as HTMLSelectElement).value)}
          disabled={!workspace.detail || workspace.loading !== null}
        >
          <option value="">Select a revision</option>
          {#each [...runnableRevisions].reverse() as revision}
            <option value={revision.revision_id}>Rev {revision.revision_number} · {shortHash(revision.source_sha256)}</option>
          {/each}
        </select>
      </label>
      <div class="new-script">
        <label><span>New script title</span><input bind:value={newScriptTitle} /></label>
        <button
          type="button"
          class="ghost-button"
          on:click={() => void createWorkspaceResearchScript(newScriptTitle)}
          disabled={workspace.loading !== null}
        >{workspace.loading === "create" ? "Creating…" : "Create from editor"}</button>
      </div>
    </article>

    {#if stagedRevisions.length}
      <article class="panel candidate-panel">
        <div class="rail-header">
          <div><p class="eyebrow">Operator candidate</p><h3>Staged source diff</h3></div>
          <span class="status dirty">REVIEW</span>
        </div>
        <p class="muted">
          Canonical editor source is unchanged. Accept only after reviewing the candidate and parent hash.
        </p>
        {#each stagedRevisions as candidate (candidate.revision_id)}
          {@const parent = workspace.detail?.revisions.find((item) => item.revision_id === candidate.parent_revision_id)}
          <section class="candidate-card">
            <div class="row"><span>Candidate</span><strong>Rev {candidate.revision_number} · {shortHash(candidate.source_sha256)}</strong></div>
            <div class="row"><span>Parent</span><strong>{shortHash(candidate.expected_parent_sha256)}</strong></div>
            <div class="row"><span>Diff</span><strong>{changedLineCount(candidate.source, parent?.source ?? "")}</strong></div>
            <p>{candidate.change_summary ?? "Operator-authored candidate revision"}</p>
            <details>
              <summary>Inspect candidate source</summary>
              <pre>{candidate.source}</pre>
            </details>
            <div class="candidate-actions">
              <button
                type="button"
                class="run-button"
                on:click={() => void resolveStagedResearchScriptRevision(candidate.revision_id, "accept")}
                disabled={workspace.loading !== null}
              >Accept candidate</button>
              <button
                type="button"
                on:click={() => void resolveStagedResearchScriptRevision(candidate.revision_id, "reject")}
                disabled={workspace.loading !== null}
              >Reject</button>
            </div>
          </section>
        {/each}
      </article>
    {/if}

    <article class="panel input-panel">
      <div class="rail-header"><div><p class="eyebrow">Immutable inputs</p><h3>Input manifest</h3></div></div>
      <p class="muted">Optional UTF-8 text is copied into a hash-bound snapshot for each run.</p>
      <label>
        <span>Logical filename</span>
        <input value={workspace.inputFilename} on:input={onInputFilename} placeholder="prices.csv" />
      </label>
      <label>
        <span>Text content</span>
        <textarea value={workspace.inputContent} on:input={onInputContent} rows="5" placeholder="date,close"></textarea>
      </label>
      <div class="stack compact-stack">
        <div class="row"><span>Files</span><strong>{workspace.inputFilename.trim() ? 1 : 0} / 20</strong></div>
        <div class="row">
          <span>Bundle</span>
          <strong>{new TextEncoder().encode(workspace.inputContent).length.toLocaleString()} B / 64 MiB</strong>
        </div>
      </div>
    </article>

    <article class="panel runtime-panel">
      <div class="rail-header"><div><p class="eyebrow">Execution</p><h3>Runtime &amp; provenance</h3></div></div>
      <div class="stack compact-stack">
        <div class="row"><span>Provider</span><strong>{workspace.selectedRun?.runtime_provider ?? workspace.capabilities?.provider ?? "Gamma mock"}</strong></div>
        <div class="row"><span>Runtime</span><strong>{workspace.selectedRun?.runtime_kind ?? workspace.capabilities?.runtime_kind ?? "mock_safe_preview"}</strong></div>
        <div class="row"><span>Model</span><strong>{workspace.capabilities?.model ?? "—"}</strong></div>
        <div class="row">
          <span>Source SHA</span>
          <strong>{shortHash(workspace.selectedRun?.source_sha256 ?? selectedRevision?.source_sha256)}</strong>
        </div>
        <div class="row"><span>Input SHA</span><strong>{shortHash(workspace.selectedRun?.input_manifest_sha256)}</strong></div>
        <div class="row"><span>Network</span><strong>Disabled</strong></div>
        <div class="row"><span>Code execution</span><strong>{executesSource ? "Isolated" : "Disabled"}</strong></div>
        <div class="row"><span>Cancellation</span><strong>{workspace.capabilities?.supports_cancellation ? "Supported" : "Not supported"}</strong></div>
      </div>
      {#if workspace.capabilities && !workspace.capabilities.available}
        <p class="runtime-status">{workspace.capabilities.sanitized_provider_status.replaceAll("_", " ")}</p>
      {/if}
      {#if workspace.selectedRun?.warnings.length}
        <div class="warning-list">
          {#each workspace.selectedRun.warnings as warning}<p>{warning}</p>{/each}
        </div>
      {/if}
    </article>

    <article class="panel history-panel">
      <div class="rail-header"><div><p class="eyebrow">History</p><h3>Stored runs</h3></div></div>
      {#if workspace.runs.length}
        <div class="run-list">
          {#each workspace.runs as run}
            <button
              type="button"
              class:selected={workspace.selectedRun?.run_id === run.run_id}
              on:click={() => selectResearchScriptRun(run.run_id)}
            >
              <span>{run.status}</span>
              <small>{shortDate(run.started_at)} · {shortHash(run.source_sha256)}</small>
            </button>
          {/each}
        </div>
      {:else}
        <p class="muted">No stored runs for this script.</p>
      {/if}
    </article>

    {#if workspace.error || workspace.notice}
      <article class:error-state={Boolean(workspace.error)} class="panel message-panel" role={workspace.error ? "alert" : "status"}>
        <p class="eyebrow">{workspace.error ? "Action failed" : "Workspace status"}</p>
        <p>{workspace.error || workspace.notice}</p>
      </article>
    {/if}
  </aside>
</div>

<style>
  .script-workspace,
  .primary-column,
  .support-column,
  .output-list,
  .stack,
  .new-script,
  .warning-list,
  .run-list {
    display: grid;
    gap: var(--space-4);
  }

  .script-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.34fr);
    align-items: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
    display: grid;
    gap: var(--space-4);
  }

  .safety-panel {
    grid-template-columns: minmax(12rem, 0.3fr) minmax(0, 1fr);
    align-items: center;
    border-color: color-mix(in srgb, var(--warning) 45%, var(--panel-border));
    background: color-mix(in srgb, var(--warning) 4%, var(--panel-bg));
  }

  .safety-panel h2,
  .panel h3,
  p { margin: 0; }

  .safety-panel h2 {
    color: var(--warning);
    font-size: var(--text-lg);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .safety-panel > p,
  .muted,
  .provenance-note {
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .panel-header,
  .rail-header,
  .output-head,
  .editor-footer,
  .action-row,
  .status-cluster,
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .eyebrow,
  label > span,
  .source-field > span,
  .output-head > span,
  .file-output > span,
  .artifact-preview > span {
    color: var(--text-2);
    font-size: var(--text-2xs);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  label {
    display: grid;
    gap: var(--space-2);
  }

  input,
  select,
  textarea {
    width: 100%;
    border: 1px solid var(--panel-strong);
    background: color-mix(in srgb, var(--panel-bg) 86%, var(--text-0) 2%);
    color: var(--text-0);
    padding: var(--space-3);
    font: inherit;
  }

  .source-field { display: grid; gap: var(--space-2); }

  input:focus-visible,
  select:focus-visible,
  textarea:focus-visible,
  button:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: 1px;
  }

  .editor-footer,
  .output-head small,
  .run-list small {
    color: var(--text-2);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
  }

  button {
    width: auto;
    border: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-3) var(--space-5);
    font: inherit;
    cursor: pointer;
  }

  button:hover:not(:disabled),
  button.selected {
    border-color: var(--accent);
    color: var(--accent);
  }

  button:disabled { cursor: not-allowed; opacity: 0.45; }

  .run-button {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-color: var(--accent);
    color: var(--accent);
  }

  .status {
    border: 1px solid var(--panel-strong);
    color: var(--positive);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .status.dirty,
  .status.failed { color: var(--warning); }

  .state-box,
  .artifact-preview,
  .file-output {
    border: 1px dashed var(--panel-strong);
    padding: var(--space-6);
    color: var(--text-2);
    text-align: center;
  }

  .output-card {
    border: 1px solid var(--divider);
    padding: var(--space-4);
    display: grid;
    gap: var(--space-3);
    min-width: 0;
  }

  .candidate-card {
    border: 1px solid color-mix(in srgb, var(--warning) 38%, var(--divider));
    padding: var(--space-4);
    display: grid;
    gap: var(--space-3);
  }

  .candidate-card > p {
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: 1.4;
  }

  .candidate-card details {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
  }

  .candidate-card summary {
    color: var(--accent);
    cursor: pointer;
    font-size: var(--text-xs);
  }

  .candidate-card details pre {
    max-height: 18rem;
    margin-top: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--divider);
  }

  .candidate-actions {
    display: flex;
    gap: var(--space-2);
  }

  .output-card.error-output,
  .message-panel.error-state { border-color: color-mix(in srgb, var(--negative) 55%, var(--panel-border)); }

  pre {
    margin: 0;
    overflow: auto;
    white-space: pre-wrap;
    color: var(--text-1);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    line-height: 1.5;
  }

  .metric-output {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
  }

  .metric-output strong {
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: var(--text-xl);
  }

  .metric-output span { color: var(--text-2); font-size: var(--text-sm); }

  .table-wrap { overflow: auto; }
  table { width: 100%; border-collapse: collapse; font-size: var(--text-xs); }
  th,
  td { border-bottom: 1px solid var(--divider); padding: var(--space-2) var(--space-3); text-align: left; }
  th { color: var(--text-2); font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; }
  td { color: var(--text-1); font-family: var(--font-mono); }

  .artifact-preview,
  .file-output {
    display: grid;
    gap: var(--space-2);
    text-align: left;
  }

  .artifact-preview strong,
  .file-output strong { color: var(--text-0); }

  .artifact-preview img {
    width: 100%;
    max-height: 28rem;
    object-fit: contain;
    border: 1px solid var(--divider);
    background: var(--surface-0);
  }

  .artifact-link,
  .file-output a {
    width: fit-content;
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
  }

  .runtime-status {
    color: var(--warning);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-transform: uppercase;
  }

  .compact-stack { gap: 0; }
  .row { padding: var(--space-3) 0; border-bottom: 1px solid var(--divider); font-size: var(--text-xs); }
  .row:last-child { border-bottom: 0; }
  .row span { color: var(--text-2); }
  .row strong { color: var(--text-1); font-family: var(--font-mono); font-weight: 500; text-align: right; }

  .warning-list p {
    border-left: 2px solid var(--warning);
    padding-left: var(--space-3);
    color: var(--warning);
    font-size: var(--text-xs);
    line-height: 1.4;
  }

  .run-list { gap: var(--space-2); }
  .run-list button { display: grid; gap: var(--space-2); text-align: left; padding: var(--space-3); }
  .run-list button span { text-transform: uppercase; font-size: var(--text-xs); }

  .message-panel p:last-child { color: var(--text-1); line-height: 1.45; }
  .message-panel.error-state p:last-child { color: var(--negative); }

  @media (max-width: 1240px) {
    .script-workspace { grid-template-columns: 1fr; }
    .support-column { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 760px) {
    .support-column,
    .safety-panel { grid-template-columns: 1fr; }
    .panel-header,
    .action-row { align-items: stretch; flex-direction: column; }
    .action-row button { width: 100%; }
  }
</style>
