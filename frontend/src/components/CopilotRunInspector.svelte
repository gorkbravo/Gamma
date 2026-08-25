<script lang="ts">
  import type {
    CopilotDiagnostics,
    CopilotResearchCardResult,
    CopilotRunObservability,
    CopilotSafeProviderError,
    CopilotTurnRecord,
    CopilotUsageRecord,
    CopilotWorkingAnalysis
  } from "../lib/api/types";

  export let turn: CopilotTurnRecord | null = null;
  export let result: CopilotResearchCardResult | null = null;
  export let diagnostics: CopilotDiagnostics | null = null;
  export let workingAnalyses: CopilotWorkingAnalysis[] = [];
  export let onOpenWorkingAnalysis: (
    analysis: CopilotWorkingAnalysis
  ) => Promise<unknown> | void = () => {};
  export let onDiscardWorkingAnalysis: (
    analysis: CopilotWorkingAnalysis
  ) => Promise<unknown> | void = () => {};
  export let onClose: () => void = () => {};

  const unavailableUsage: CopilotUsageRecord = {
    input_tokens: null,
    output_tokens: null,
    reasoning_tokens: null,
    total_tokens: null,
    cache_read_tokens: null,
    cache_write_tokens: null,
    provider_calls: null,
    tool_calls: null,
    raw: {}
  };
  const unavailableObservability: CopilotRunObservability = {
    selected_profile: null,
    resolved_provider: null,
    resolved_model: null,
    model_policy_version: null,
    routing_reason: null,
    reasoning_mode: null,
    reasoning_effort: null,
    orchestration_path: null,
    total_latency_ms: null,
    provider_latency_ms: null,
    cancellation_outcome: null,
    cancellation_boundary: null,
    provider_error_category: null,
    diagnostic_id: null
  };

  let usage = unavailableUsage;
  let observability = unavailableObservability;
  let safeError: CopilotSafeProviderError | null = null;
  let copyState: "idle" | "copied" | "error" = "idle";
  let visibleWorkingAnalyses: CopilotWorkingAnalysis[] = [];

  $: usage = turn?.usage ?? result?.usage ?? unavailableUsage;
  $: observability =
    turn?.observability ?? result?.observability ?? unavailableObservability;
  $: safeError =
    turn?.safe_provider_error
    ?? result?.safe_provider_error
    ?? diagnostics?.last_error
    ?? null;
  $: visibleWorkingAnalyses = [...workingAnalyses].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at)
  );

  function metric(value: number | null | undefined, suffix = "") {
    return value == null ? "Unavailable" : `${value.toLocaleString()}${suffix}`;
  }

  function label(value: string | null | undefined) {
    return value?.trim() ? value.replaceAll("_", " ") : "Unavailable";
  }

  function compactDate(value: string | null | undefined) {
    return value
      ? new Date(value).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit"
        })
      : "No expiry";
  }

  async function copyDiagnosticId() {
    const diagnosticId = safeError?.diagnostic_id ?? observability.diagnostic_id;
    if (!diagnosticId || !navigator.clipboard?.writeText) {
      copyState = "error";
      return;
    }
    try {
      await navigator.clipboard.writeText(diagnosticId);
      copyState = "copied";
    } catch {
      copyState = "error";
    }
  }
</script>

<aside class="inspector" aria-label="Copilot run inspector">
  <header>
    <div>
      <span>Run inspector</span>
      <strong>{turn?.terminal_status ?? result?.status ?? "No run selected"}</strong>
    </div>
    <button type="button" on:click={onClose} aria-label="Close Copilot run inspector">×</button>
  </header>

  <section>
    <h3>Routing</h3>
    <dl>
      <div><dt>Profile</dt><dd>{label(observability.selected_profile)}</dd></div>
      <div><dt>Provider</dt><dd>{label(observability.resolved_provider)}</dd></div>
      <div><dt>Model</dt><dd>{label(observability.resolved_model)}</dd></div>
      <div><dt>Policy</dt><dd>{label(observability.model_policy_version)}</dd></div>
      <div><dt>Reasoning</dt><dd>{label(observability.reasoning_effort ?? observability.reasoning_mode)}</dd></div>
      <div><dt>Path</dt><dd>{label(observability.orchestration_path)}</dd></div>
    </dl>
    <p>{observability.routing_reason ?? "Routing reason unavailable for this stored legacy turn."}</p>
  </section>

  <section>
    <h3>Usage & latency</h3>
    <dl>
      <div><dt>Total latency</dt><dd>{metric(observability.total_latency_ms, " ms")}</dd></div>
      <div><dt>Provider latency</dt><dd>{metric(observability.provider_latency_ms, " ms")}</dd></div>
      <div><dt>Input tokens</dt><dd>{metric(usage.input_tokens)}</dd></div>
      <div><dt>Output tokens</dt><dd>{metric(usage.output_tokens)}</dd></div>
      <div><dt>Reasoning tokens</dt><dd>{metric(usage.reasoning_tokens)}</dd></div>
      <div><dt>Cache read</dt><dd>{metric(usage.cache_read_tokens)}</dd></div>
      <div><dt>Cache write</dt><dd>{metric(usage.cache_write_tokens)}</dd></div>
      <div><dt>Provider calls</dt><dd>{metric(usage.provider_calls)}</dd></div>
      <div><dt>Tool calls</dt><dd>{metric(usage.tool_calls)}</dd></div>
    </dl>
  </section>

  {#if visibleWorkingAnalyses.length}
    <section aria-label="Session working analyses">
      <h3>Working analyses</h3>
      <div class="working-list">
        {#each visibleWorkingAnalyses as analysis}
          <article class:inactive={analysis.status !== "active"} class="working-analysis">
            <div class="working-heading">
              <span class="temporary-label">Temporary</span>
              <span class="working-status">{label(analysis.status)}</span>
            </div>
            <strong>{analysis.title}</strong>
            <p>
              {label(analysis.owning_tab)} / {label(analysis.owning_mode)} · expires
              {compactDate(analysis.expires_at)}
            </p>
            <small>Session scoped. Opening does not save a DCF model.</small>
            <div class="working-actions">
              <button
                type="button"
                disabled={analysis.status !== "active"}
                on:click={() => onOpenWorkingAnalysis(analysis)}
              >Open in Fundamentals</button>
              <button
                type="button"
                disabled={analysis.status === "discarded"}
                on:click={() => onDiscardWorkingAnalysis(analysis)}
              >Discard</button>
            </div>
          </article>
        {/each}
      </div>
    </section>
  {/if}

  <section>
    <h3>Retention & cancellation</h3>
    <p><strong>Gamma local</strong> {diagnostics?.local_storage ?? "Local replay metadata unavailable."}</p>
    <p>
      <strong>Provider</strong>
      {diagnostics?.provider_storage.reason
        ?? turn?.model_resolution?.provider_storage.reason
        ?? result?.model_resolution?.provider_storage.reason
        ?? "Provider storage policy unavailable."}
    </p>
    <dl>
      <div><dt>Outcome</dt><dd>{label(observability.cancellation_outcome)}</dd></div>
      <div><dt>Boundary</dt><dd>{label(observability.cancellation_boundary)}</dd></div>
    </dl>
  </section>

  {#if safeError}
    <section class="diagnostic" aria-label="Safe provider diagnostic">
      <h3>Provider diagnostic</h3>
      <strong>{label(safeError.category)}</strong>
      <p>{safeError.message}</p>
      <p>{safeError.guidance}</p>
      <div class="diagnostic-id">
        <code>{safeError.diagnostic_id}</code>
        <button
          type="button"
          on:click={copyDiagnosticId}
          aria-label={`Copy diagnostic ID ${safeError.diagnostic_id}`}
        >
          {copyState === "copied" ? "Copied" : copyState === "error" ? "Unavailable" : "Copy ID"}
        </button>
      </div>
    </section>
  {/if}
</aside>

<style>
  .inspector {
    min-width: 0;
    min-height: 0;
    overflow-y: auto;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
  }

  header {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-4);
    border-bottom: 1px solid var(--divider);
    background: var(--panel-bg);
  }

  header div,
  section {
    display: grid;
    gap: var(--space-3);
  }

  header span,
  h3,
  dt {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  header strong {
    color: var(--text-0);
    font-size: var(--text-sm);
    text-transform: capitalize;
  }

  button {
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-1);
    padding: var(--space-2) var(--space-3);
    font: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
  }

  button:hover {
    border-color: color-mix(in srgb, var(--accent) 42%, var(--panel-strong));
    color: var(--accent);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }

  section {
    padding: var(--space-4);
    border-bottom: 1px solid var(--divider);
  }

  h3,
  p,
  dl {
    margin: 0;
  }

  p {
    color: var(--text-1);
    font-size: var(--text-xs);
    line-height: 1.5;
  }

  p strong {
    color: var(--text-0);
  }

  dl {
    display: grid;
    gap: var(--space-2);
  }

  dl div {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
    gap: var(--space-3);
    align-items: baseline;
  }

  dd {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-xs);
    text-align: right;
    overflow-wrap: anywhere;
    text-transform: capitalize;
  }

  .diagnostic {
    border-left: 2px solid var(--warning);
  }

  .diagnostic > strong {
    color: var(--warning);
    font-size: var(--text-xs);
    text-transform: capitalize;
  }

  .diagnostic-id {
    display: grid;
    gap: var(--space-2);
  }

  .working-list,
  .working-analysis {
    display: grid;
    gap: var(--space-2);
  }

  .working-analysis {
    padding: var(--space-3);
    border: 1px solid var(--panel-strong);
    background: transparent;
  }

  .working-analysis.inactive {
    opacity: 0.62;
  }

  .working-heading,
  .working-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }

  .working-actions {
    justify-content: flex-start;
  }

  .working-analysis > strong {
    color: var(--text-0);
    font-size: var(--text-sm);
  }

  .working-analysis small,
  .working-status {
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .temporary-label {
    color: var(--accent);
    font-size: var(--text-2xs);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  code {
    display: block;
    padding: var(--space-3);
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--accent);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }
</style>
