<script lang="ts">
  import { onMount } from "svelte";

  import type { ResearchScriptOutput } from "../lib/api/types";
  import {
    fetchResearchScriptOutput,
    fetchResearchScriptRunExport
  } from "../lib/api/research-scripts";
  import AuthenticatedResearchScriptImage from "./AuthenticatedResearchScriptImage.svelte";
  import ResearchScriptCodeEditor from "./ResearchScriptCodeEditor.svelte";
  import {
    cleanupResearchScriptRetainedOutputs,
    compareSelectedResearchScriptRun,
    createWorkspaceResearchScript,
    duplicateWorkspaceResearchScript,
    initializeResearchScriptWorkspace,
    loadResearchScript,
    persistResearchScriptRevision,
    prepareResearchScriptDomainInput,
    refreshResearchScriptWorkspace,
    researchScriptWorkspace,
    resolveStagedResearchScriptRevision,
    runSelectedResearchScript,
    selectResearchScriptRevision,
    selectResearchScriptRun,
    setResearchScriptArchivedVisibility,
    setWorkspaceResearchScriptArchived,
    updateResearchScriptDraft,
    updateResearchScriptInput,
    type ResearchScriptWorkspaceState
  } from "../lib/stores/research-script";

  export let snapshot: ResearchScriptWorkspaceState | null = null;

  let newScriptTitle = "Research Script";
  let exportDomain: "equity_history" | "macro_series" | "saved_research" = "equity_history";
  let exportObjectId = "SPY";
  let exportFilename = "spy-prices.csv";
  let exportRegion = "US";
  let exportTimeframe = "1Y";
  let exportLookbackDays = 756;
  let exportFrequency: "daily" | "weekly" | "monthly" = "daily";
  let comparisonRunId = "";
  let artifactActionError = "";

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
  $: selectedRunDuration = workspace.selectedRun?.completed_at
    ? Math.max(
        (new Date(workspace.selectedRun.completed_at).getTime() - new Date(workspace.selectedRun.started_at).getTime()) / 1000,
        0
      )
    : null;

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
  const usageValue = (value: unknown) => {
    return typeof value === "number" ? value.toLocaleString() : "—";
  };
  const exportObjectLabel = () => exportDomain === "equity_history"
    ? "Ticker"
    : exportDomain === "macro_series"
      ? "Series id"
      : "Saved research id";

  function onExportDomain(event: Event) {
    exportDomain = (event.currentTarget as HTMLSelectElement).value as typeof exportDomain;
    if (exportDomain === "equity_history") {
      exportObjectId = "SPY";
      exportFilename = "spy-prices.csv";
    } else if (exportDomain === "macro_series") {
      exportObjectId = "DGS10";
      exportFilename = "macro-series.csv";
    } else {
      exportObjectId = "";
      exportFilename = "saved-research.json";
    }
  }

  function prepareDomainExport() {
    void prepareResearchScriptDomainInput({
      domain: exportDomain,
      object_id: exportObjectId,
      logical_filename: exportFilename,
      region: exportDomain === "macro_series" ? exportRegion : undefined,
      timeframe: exportDomain === "macro_series" ? exportTimeframe : undefined,
      lookback_days: exportDomain === "equity_history" ? exportLookbackDays : undefined,
      frequency: exportDomain === "equity_history" ? exportFrequency : undefined
    });
  }

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

  function saveBlob(blob: Blob, filename: string) {
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }

  async function downloadOutput(output: ResearchScriptOutput) {
    if (!workspace.selectedRun) return;
    artifactActionError = "";
    try {
      const blob = await fetchResearchScriptOutput(workspace.selectedRun.run_id, output.output_id);
      saveBlob(blob, output.filename ?? `${output.output_id}.txt`);
    } catch (error) {
      artifactActionError = error instanceof Error ? error.message : String(error);
    }
  }

  async function downloadRunBundle() {
    if (!workspace.selectedRun) return;
    artifactActionError = "";
    try {
      const blob = await fetchResearchScriptRunExport(workspace.selectedRun.run_id);
      saveBlob(blob, `gamma-research-script-${workspace.selectedRun.run_id.slice(0, 12)}.zip`);
    } catch (error) {
      artifactActionError = error instanceof Error ? error.message : String(error);
    }
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
            <span class:failed={workspace.detail.script.status === "archived"} class="status">
              {workspace.detail.script.status}
            </span>
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
          disabled={!workspace.detail || workspace.detail.script.status === "archived" || !draftIsDirty || workspace.loading !== null}
        >
          {workspace.loading === "save" ? "Saving…" : "Save revision"}
        </button>
        <button
          type="button"
          class="run-button"
          on:click={() => void runSelectedResearchScript()}
          disabled={!workspace.detail || workspace.detail.script.status === "archived" || !selectedRevision || selectedSourceIsDirty || workspace.loading !== null || !runtimeAvailable}
        >
          {workspace.loading === "run" ? "Running…" : executesSource ? "Run immutable revision" : "Run safe preview"}
        </button>
      </div>

      {#if workspace.selectedRun}
        <div class="output-toolbar" aria-label="Run result actions">
          <button
            type="button"
            class="artifact-link"
            on:click={() => void downloadRunBundle()}
          >Export auditable run bundle</button>
          {#if workspace.runs.length > 1}
            <label class="inline-control">
              <span>Compare with</span>
              <select
                aria-label="Compare selected run with"
                bind:value={comparisonRunId}
                on:change={() => void compareSelectedResearchScriptRun(comparisonRunId)}
                disabled={workspace.loading !== null}
              >
                <option value="">Select retained run</option>
                {#each workspace.runs.filter((run) => run.run_id !== workspace.selectedRun?.run_id) as run}
                  <option value={run.run_id}>{shortDate(run.started_at)} · {run.status}</option>
                {/each}
              </select>
            </label>
          {/if}
        </div>
      {/if}

      {#if workspace.runComparison}
        <div class="comparison-table" aria-label="Retained run comparison">
          <table>
            <caption class="sr-only">Comparison between the selected Research Script runs</caption>
            <thead><tr><th>Check</th><th>Result / delta</th></tr></thead>
            <tbody>
              <tr><td>Revision</td><td>{workspace.runComparison.same_revision ? "Same immutable revision" : "Changed"}</td></tr>
              <tr><td>Input snapshot</td><td>{workspace.runComparison.same_input_snapshot ? "Same immutable snapshot" : "Changed"}</td></tr>
              <tr><td>Status</td><td>{workspace.runComparison.status_changed ? "Changed" : "Unchanged"}</td></tr>
              <tr><td>Duration</td><td>{workspace.runComparison.duration_delta_seconds === null ? "—" : `${workspace.runComparison.duration_delta_seconds.toFixed(2)} s`}</td></tr>
              <tr><td>Input tokens</td><td>{workspace.runComparison.input_token_delta ?? "—"}</td></tr>
              <tr><td>Output tokens</td><td>{workspace.runComparison.output_token_delta ?? "—"}</td></tr>
              <tr><td>Outputs</td><td>{workspace.runComparison.output_count_delta}</td></tr>
              <tr><td>Warnings</td><td>{workspace.runComparison.warning_count_delta}</td></tr>
            </tbody>
          </table>
        </div>
      {/if}
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
                    <caption class="sr-only">{output.filename ?? output.output_id}</caption>
                    <thead><tr>{#each output.columns as column}<th>{column}</th>{/each}</tr></thead>
                    <tbody>
                      {#each output.rows as row}
                        <tr>{#each output.columns as column}<td>{cell(row[column])}</td>{/each}</tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
                {#if output.artifact_ref && workspace.selectedRun}
                  <button type="button" class="artifact-link" on:click={() => void downloadOutput(output)}>
                    Download retained {output.filename ?? "table"}
                  </button>
                {/if}
              {:else if output.kind === "image"}
                <div class="artifact-preview" role="img" aria-label={output.alt_text ?? "Research script image output"}>
                  {#if output.artifact_ref && workspace.selectedRun}
                    <AuthenticatedResearchScriptImage
                      runId={workspace.selectedRun.run_id}
                      outputId={output.output_id}
                      alt={output.alt_text ?? "Generated research chart"}
                    />
                  {/if}
                  <span>IMAGE ARTIFACT</span>
                  <strong>{output.filename ?? output.output_id}</strong>
                  <small>{output.alt_text ?? "Gamma-retained generated image"}</small>
                </div>
                {#if output.artifact_ref && workspace.selectedRun}
                  <button type="button" class="artifact-link" on:click={() => void downloadOutput(output)}>
                    Download retained {output.filename ?? "image"}
                  </button>
                {/if}
              {:else if output.kind === "file"}
                <div class="file-output">
                  <span>FILE</span>
                  {#if output.artifact_ref && workspace.selectedRun}
                    <button type="button" class="artifact-link" on:click={() => void downloadOutput(output)}>
                      {output.filename ?? output.output_id}
                    </button>
                  {:else}
                    <strong>{output.filename ?? output.output_id}</strong>
                  {/if}
                  <small>{output.artifact_ref ?? "Persisted artifact reference"}</small>
                </div>
              {:else}
                <pre>{output.text ?? "No text retained."}</pre>
                {#if output.artifact_ref && workspace.selectedRun}
                  <button type="button" class="artifact-link" on:click={() => void downloadOutput(output)}>
                    Download full retained output
                  </button>
                {/if}
              {/if}

              {#if output.transformation_note}
                <details class="provenance-note">
                  <summary>Provenance</summary>
                  <p>{output.source_provider} · {output.origin}</p>
                  <p>{output.transformation_note}</p>
                </details>
              {/if}
            </section>
          {/each}
        </div>
      {/if}
      {#if artifactActionError}
        <p class="artifact-error" role="alert">Artifact action failed: {artifactActionError}</p>
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
            <option value={script.script_id}>{script.status === "archived" ? "[ARCHIVED] " : ""}{script.title}</option>
          {/each}
        </select>
      </label>
      <label class="check-row">
        <input
          type="checkbox"
          checked={workspace.includeArchived}
          on:change={(event) => void setResearchScriptArchivedVisibility((event.currentTarget as HTMLInputElement).checked)}
          disabled={workspace.loading !== null}
        />
        <span>Show archived scripts</span>
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
      {#if workspace.detail}
        <div class="lifecycle-actions" aria-label="Script lifecycle actions">
          <button
            type="button"
            on:click={() => void duplicateWorkspaceResearchScript()}
            disabled={workspace.loading !== null}
          >Duplicate</button>
          <button
            type="button"
            on:click={() => void setWorkspaceResearchScriptArchived(workspace.detail?.script.status !== "archived")}
            disabled={workspace.loading !== null}
          >{workspace.detail.script.status === "archived" ? "Restore" : "Archive"}</button>
          <button
            type="button"
            on:click={() => void refreshResearchScriptWorkspace()}
            disabled={workspace.loading !== null}
          >Recover / reload</button>
        </div>
      {/if}
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
      <div class="domain-export-grid">
        <label>
          <span>Gamma export</span>
          <select aria-label="Gamma export domain" value={exportDomain} on:change={onExportDomain}>
            <option value="equity_history">Equity history</option>
            <option value="macro_series">Macro series</option>
            <option value="saved_research">Saved research</option>
          </select>
        </label>
        <label>
          <span>{exportObjectLabel()}</span>
          <input bind:value={exportObjectId} aria-label={exportObjectLabel()} />
        </label>
        <label>
          <span>Snapshot filename</span>
          <input bind:value={exportFilename} aria-label="Snapshot filename" />
        </label>
        {#if exportDomain === "equity_history"}
          <label><span>Lookback days</span><input type="number" min="20" max="3650" bind:value={exportLookbackDays} /></label>
          <label>
            <span>Frequency</span>
            <select bind:value={exportFrequency}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
        {:else if exportDomain === "macro_series"}
          <label><span>Region</span><input bind:value={exportRegion} /></label>
          <label><span>Timeframe</span><input bind:value={exportTimeframe} /></label>
        {/if}
        <button
          type="button"
          class="ghost-button"
          on:click={prepareDomainExport}
          disabled={!workspace.detail || workspace.detail.script.status === "archived" || !exportObjectId.trim() || !exportFilename.trim() || workspace.loading !== null}
        >{workspace.loading === "input" ? "Preparing…" : "Prepare Gamma snapshot"}</button>
      </div>

      <div class="input-divider"><span>Optional user file</span></div>
      <label>
        <span>Logical filename</span>
        <input value={workspace.inputFilename} on:input={onInputFilename} placeholder="prices.csv" />
      </label>
      <label>
        <span>Text content</span>
        <textarea value={workspace.inputContent} on:input={onInputContent} rows="5" placeholder="date,close"></textarea>
      </label>
      <div class="stack compact-stack">
        <div class="row"><span>Files</span><strong>{workspace.preparedInputSnapshot?.files.length ?? (workspace.inputFilename.trim() ? 1 : 0)} / 20</strong></div>
        <div class="row">
          <span>Bundle</span>
          <strong>{(workspace.preparedInputSnapshot?.total_bytes ?? new TextEncoder().encode(workspace.inputContent).length).toLocaleString()} B / 64 MiB</strong>
        </div>
        <div class="row"><span>Manifest SHA</span><strong>{shortHash(workspace.preparedInputSnapshot?.manifest_sha256)}</strong></div>
      </div>
      {#if workspace.preparedInputSnapshot}
        <div class="manifest-files" aria-label="Prepared immutable input files">
          {#each workspace.preparedInputSnapshot.files as file}
            <div class="row">
              <span>{file.logical_filename}</span>
              <strong>{file.source_kind} · {file.byte_size.toLocaleString()} B</strong>
            </div>
          {/each}
        </div>
        {#if workspace.preparedInputSnapshot.warnings.length}
          <div class="warning-list">
            {#each workspace.preparedInputSnapshot.warnings as warning}<p>{warning}</p>{/each}
          </div>
        {/if}
      {/if}
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
        <div class="row"><span>Duration</span><strong>{selectedRunDuration === null ? "—" : `${selectedRunDuration.toFixed(2)} s`}</strong></div>
        <div class="row"><span>Input tokens</span><strong>{usageValue(workspace.selectedRun?.usage?.input_tokens)}</strong></div>
        <div class="row"><span>Output tokens</span><strong>{usageValue(workspace.selectedRun?.usage?.output_tokens)}</strong></div>
        <div class="row"><span>Token cost estimate</span><strong>{typeof workspace.selectedRun?.usage?.estimated_token_cost_usd === "number" ? `$${workspace.selectedRun.usage.estimated_token_cost_usd.toFixed(6)}` : "—"}</strong></div>
        <div class="row"><span>Network</span><strong>Disabled</strong></div>
        <div class="row"><span>Code execution</span><strong>{executesSource ? "Isolated" : "Disabled"}</strong></div>
        <div class="row"><span>Cancellation</span><strong>{workspace.capabilities?.supports_cancellation ? "Supported" : "Not supported"}</strong></div>
      </div>
      {#if workspace.capabilities && !workspace.capabilities.available}
        <div class="first-run-guidance" role="status">
          <p class="runtime-status">{workspace.capabilities.sanitized_provider_status.replaceAll("_", " ")}</p>
          <p>Configure the OpenAI runtime and `gpt-5.6-luna`, or keep the safe-preview runtime for offline research.</p>
        </div>
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
              <small>{shortDate(run.started_at)} · {shortHash(run.source_sha256)} · {run.outputs.length} outputs</small>
            </button>
          {/each}
        </div>
      {:else}
        <p class="muted">No stored runs for this script.</p>
      {/if}
    </article>

    <article class="panel diagnostics-panel">
      <div class="rail-header"><div><p class="eyebrow">Recovery</p><h3>Retained storage</h3></div></div>
      <div class="stack compact-stack">
        <div class="row"><span>Scripts / archived</span><strong>{workspace.diagnostics?.script_count ?? "—"} / {workspace.diagnostics?.archived_script_count ?? "—"}</strong></div>
        <div class="row"><span>Runs / snapshots</span><strong>{workspace.diagnostics?.run_count ?? "—"} / {workspace.diagnostics?.input_snapshot_count ?? "—"}</strong></div>
        <div class="row"><span>Retained outputs</span><strong>{workspace.diagnostics?.retained_output_count ?? "—"}</strong></div>
        <div class="row"><span>Retained bytes</span><strong>{workspace.diagnostics?.retained_output_bytes?.toLocaleString() ?? "—"}</strong></div>
        <div class="row"><span>Missing / orphaned</span><strong>{workspace.diagnostics?.missing_output_count ?? "—"} / {workspace.diagnostics?.orphan_output_count ?? "—"}</strong></div>
      </div>
      <button
        type="button"
        on:click={() => void cleanupResearchScriptRetainedOutputs()}
        disabled={workspace.loading !== null}
      >{workspace.loading === "cleanup" ? "Cleaning…" : "Clean orphaned outputs"}</button>
      {#if workspace.diagnostics?.storage_warnings.length}
        <details class="storage-warnings">
          <summary>{workspace.diagnostics.storage_warnings.length} storage warning{workspace.diagnostics.storage_warnings.length === 1 ? "" : "s"}</summary>
          {#each workspace.diagnostics.storage_warnings as warning}<p>{warning}</p>{/each}
        </details>
      {/if}
    </article>

    {#if workspace.error || workspace.notice}
      <article class:error-state={Boolean(workspace.error)} class="panel message-panel" role={workspace.error ? "alert" : "status"} aria-live="polite">
        <p class="eyebrow">{workspace.error ? "Action failed" : "Workspace status"}</p>
        <p>{workspace.error || workspace.notice}</p>
      </article>
    {/if}
  </aside>
</div>

<style>
  .script-workspace,
  .output-list,
  .stack,
  .new-script,
  .warning-list,
  .run-list,
  .domain-export-grid,
  .manifest-files {
    display: grid;
    gap: var(--space-4);
  }

  .script-workspace {
    grid-template-columns: minmax(0, 1fr) minmax(18rem, 0.34fr);
    align-items: start;
  }

  .safety-panel {
    grid-template-columns: minmax(12rem, 0.3fr) minmax(0, 1fr);
    align-items: center;
    border-color: var(--panel-border);
    background: var(--panel-bg);
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

  .rail-header,
  .output-head,
  .editor-footer,
  .action-row,
  .status-cluster,
  .row,
  .output-toolbar,
  .lifecycle-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

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
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-3);
    font: inherit;
  }

  input,
  select { min-height: 30px; }

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
    font-family: var(--app-font);
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
    min-height: 30px;
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
    border: 1px solid var(--panel-strong);
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
  .message-panel.error-state { border-color: var(--panel-strong); }

  pre {
    margin: 0;
    overflow: auto;
    white-space: pre-wrap;
    color: var(--text-1);
    font-family: var(--app-font);
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
    font-family: var(--app-font);
    font-size: var(--text-xl);
  }

  .metric-output span { color: var(--text-2); font-size: var(--text-sm); }

  .table-wrap { overflow: auto; }
  table { width: 100%; border-collapse: collapse; font-size: var(--text-xs); }
  th,
  td { border-bottom: 1px solid var(--divider); padding: var(--space-2) var(--space-3); text-align: left; }
  th { color: var(--text-2); font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; }
  td { color: var(--text-1); font-family: var(--app-font); }

  .artifact-preview,
  .file-output {
    display: grid;
    gap: var(--space-2);
    text-align: left;
  }

  .artifact-preview strong,
  .file-output strong { color: var(--text-0); }

  .artifact-link {
    width: fit-content;
    color: var(--accent);
    font-family: var(--app-font);
    font-size: var(--text-xs);
  }

  button.artifact-link {
    min-height: auto;
    border: 0;
    background: transparent;
    padding: 0;
    text-align: left;
  }

  .artifact-error {
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .runtime-status {
    color: var(--warning);
    font-family: var(--app-font);
    font-size: var(--text-xs);
    text-transform: uppercase;
  }

  .compact-stack { gap: 0; }
  .row { padding: var(--space-3) 0; border-bottom: 1px solid var(--divider); font-size: var(--text-xs); }
  .row:last-child { border-bottom: 0; }
  .row span { color: var(--text-2); }
  .row strong { color: var(--text-1); font-family: var(--app-font); font-weight: 500; text-align: right; }

  .output-toolbar,
  .lifecycle-actions {
    flex-wrap: wrap;
  }

  .output-toolbar {
    border-block: 1px solid var(--divider);
    padding-block: var(--space-3);
  }

  .inline-control {
    min-width: 13rem;
    grid-template-columns: auto minmax(9rem, 1fr);
    align-items: center;
  }

  .comparison-table {
    overflow: auto;
    border: 1px solid var(--divider);
  }

  .comparison-table table { min-width: 24rem; }

  .domain-export-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .domain-export-grid button { align-self: end; }

  .input-divider {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--text-2);
    font-size: var(--text-2xs);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .input-divider::after {
    content: "";
    flex: 1;
    border-top: 1px solid var(--divider);
  }

  .check-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .check-row input { width: auto; min-height: auto; }
  .check-row > span { margin: 0; }

  .provenance-note {
    border-top: 1px solid var(--divider);
    padding-top: var(--space-3);
  }

  .provenance-note summary,
  .storage-warnings summary {
    color: var(--accent);
    cursor: pointer;
    font-size: var(--text-xs);
  }

  .provenance-note p,
  .storage-warnings p,
  .first-run-guidance p:last-child {
    margin-top: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

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
    .action-row,
    .output-toolbar { align-items: stretch; flex-direction: column; }
    .action-row button { width: 100%; }
    .domain-export-grid { grid-template-columns: 1fr; }
  }
</style>
