<script lang="ts">
  import type { DiagnosticsResponse } from "../lib/api/types";

  export interface DiagnosticsEntry {
    label: string;
    message: string;
    tone: "info" | "warning" | "error" | "action";
  }

  export let diagnostics: DiagnosticsResponse | null = null;
  export let loading = false;
  export let actionLoading = false;
  export let log: string[] = [];
  export let entries: DiagnosticsEntry[] = [];
  export let onRefresh: () => void;
  export let onRunDiagnostics: () => void;
  export let onForceSubscribe: () => void;
  export let onClearHistory: () => void;

  const fmtPct = (value: number | null | undefined) =>
    value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;
</script>

<section class="console">
  <div class="header">
    <div class="title">
      <p class="eyebrow">Diagnostics Console</p>
      <h2>System Event Log</h2>
      <p class="copy">Warnings, broker/runtime errors, and operator actions are contained here instead of expanding the workspace panels.</p>
    </div>

    <div class="actions">
      <button on:click={onRunDiagnostics} disabled={actionLoading}>{actionLoading ? "Working..." : "Run Diagnostics"}</button>
      <button on:click={onForceSubscribe} disabled={actionLoading}>Force Subscribe</button>
      <button on:click={onClearHistory} disabled={actionLoading}>Clear History</button>
      <button on:click={onRefresh} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</button>
    </div>
  </div>

  <div class="summary">
    <article>
      <span>Generated</span>
      <strong>{diagnostics ? new Date(diagnostics.generated_at).toLocaleString("en-US") : "N/A"}</strong>
    </article>
    <article>
      <span>Connection</span>
      <strong>{diagnostics?.connection.status_text ?? "Status: Loading"}</strong>
    </article>
    <article>
      <span>Market Data</span>
      <strong>{diagnostics?.market_data_mode ?? "unknown"}</strong>
    </article>
    <article>
      <span>Local History</span>
      <strong>{diagnostics?.local_history_entries ?? 0} entries</strong>
    </article>
    <article>
      <span>Cache Hit Rate</span>
      <strong>{fmtPct(diagnostics?.history_cache.hit_rate)}</strong>
    </article>
    <article>
      <span>IV Session</span>
      <strong>{diagnostics?.iv_running ? "running" : "idle"}</strong>
    </article>
  </div>

  <div class="console-body">
    {#if entries.length || log.length}
      {#each entries as entry}
        <div class:warning={entry.tone === "warning"} class:error={entry.tone === "error"} class:action={entry.tone === "action"} class="line">
          <span class="tag">{entry.label}</span>
          <p>{entry.message}</p>
        </div>
      {/each}

      {#each log as line}
        <div class="line action">
          <span class="tag">Operator</span>
          <p>{line}</p>
        </div>
      {/each}
    {:else}
      <div class="empty">Console clear. No active diagnostics messages.</div>
    {/if}
  </div>
</section>

<style>
  .console {
    display: grid;
    gap: var(--space-6);
    grid-template-rows: auto auto minmax(0, 1fr);
    height: 17.5rem;
    border: 1px solid var(--panel-border);
    background: var(--surface-1);
    padding: var(--space-6) var(--space-6) var(--space-6);
  }

  .header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: start;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    justify-content: flex-end;
  }

  .eyebrow,
  span,
  p {
    color: var(--text-2);
  }

  .eyebrow {
    margin: 0 0 var(--space-3);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-sm);
  }

  h2,
  p {
    margin: 0;
  }

  .copy {
    max-width: 50rem;
  }

  .summary {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .summary article {
    border: 1px solid var(--divider);
    background: var(--surface-soft);
    padding: var(--space-5) var(--space-5);
  }

  strong {
    color: var(--text-0);
    display: block;
    margin-top: var(--space-2);
  }

  .console-body {
    overflow: auto;
    border: 1px solid var(--divider);
    background: rgba(6, 10, 14, 0.82);
  }

  .line {
    display: grid;
    grid-template-columns: 7.5rem minmax(0, 1fr);
    gap: var(--space-5);
    align-items: start;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid rgba(46, 60, 74, 0.58);
  }

  .tag {
    color: var(--text-1);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
  }

  .warning .tag,
  .warning p {
    color: var(--warning);
  }

  .error .tag,
  .error p {
    color: var(--negative);
  }

  .action .tag,
  .action p {
    color: var(--accent);
  }

  .empty {
    display: grid;
    place-items: center;
    min-height: 100%;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: var(--text-sm);
  }

  button {
    background: #0b1219;
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: var(--space-4) var(--space-5);
    font: inherit;
    cursor: pointer;
  }

  @media (max-width: 1080px) {
    .console {
      height: auto;
    }

    .header {
      flex-direction: column;
    }

    .summary {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .actions,
    .actions button,
    .line {
      width: 100%;
    }

    .line {
      grid-template-columns: 1fr;
    }
  }
</style>
