<script lang="ts">
  import type { DiagnosticsResponse } from "../lib/api/types";

  export let diagnostics: DiagnosticsResponse | null = null;
  export let loading = false;
  export let actionLoading = false;
  export let log: string[] = [];
  export let onRefresh: () => void;
  export let onRunDiagnostics: () => void;
  export let onForceSubscribe: () => void;
  export let onClearHistory: () => void;

  const fmtPct = (value: number | null | undefined) =>
    value == null ? "N/A" : `${(value * 100).toFixed(1)}%`;
</script>

<section class="panel diagnostics">
  <div class="header">
    <div>
      <p class="eyebrow">Diagnostics</p>
      <h2>System Visibility</h2>
      <p class="copy">Browser parity for the desktop diagnostics rail, backed by the shared API runtime.</p>
    </div>
    <div class="actions">
      <button on:click={onRunDiagnostics} disabled={actionLoading}>{actionLoading ? "Working..." : "Run Diagnostics"}</button>
      <button on:click={onForceSubscribe} disabled={actionLoading}>Force Subscribe</button>
      <button on:click={onClearHistory} disabled={actionLoading}>Clear History</button>
      <button on:click={onRefresh} disabled={loading}>{loading ? "Refreshing..." : "Refresh Diagnostics"}</button>
    </div>
  </div>

  <div class="grid">
    <article>
      <span>Generated</span>
      <strong>{diagnostics ? new Date(diagnostics.generated_at).toLocaleString() : "N/A"}</strong>
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
  </div>

  <div class="detail-grid">
    <article class="detail">
      <h3>Cache Stats</h3>
      <div class="list">
        <div><span>Hits</span><strong>{diagnostics?.history_cache.hits ?? 0}</strong></div>
        <div><span>Misses</span><strong>{diagnostics?.history_cache.misses ?? 0}</strong></div>
        <div><span>Hit Rate</span><strong>{fmtPct(diagnostics?.history_cache.hit_rate)}</strong></div>
        <div><span>Cached Symbols</span><strong>{diagnostics?.cached_symbols.length ?? 0}</strong></div>
      </div>
    </article>

    <article class="detail">
      <h3>Runtime Paths</h3>
      <div class="list mono">
        <div><span>Base Currency</span><strong>{diagnostics?.base_currency ?? "N/A"}</strong></div>
        <div><span>History Store</span><strong>{diagnostics?.local_history_path ?? "N/A"}</strong></div>
        <div><span>Research Scope</span><strong>{diagnostics?.research_scope_type ?? "none"}</strong></div>
        <div><span>Research Symbol</span><strong>{diagnostics?.research_primary_symbol ?? "N/A"}</strong></div>
      </div>
    </article>

    <article class="detail">
      <h3>Recent Errors</h3>
      {#if diagnostics?.recent_errors?.length}
        <div class="scroll">
          {#each diagnostics.recent_errors as error}
            <p>{error}</p>
          {/each}
        </div>
      {:else}
        <p class="muted">No recorded IB/runtime errors.</p>
      {/if}
    </article>
  </div>

  <div class="detail-grid bottom-grid">
    <article class="detail">
      <h3>IV Session</h3>
      <div class="list">
        <div><span>Running</span><strong>{diagnostics?.iv_running ? "yes" : "no"}</strong></div>
        <div><span>Status</span><strong>{diagnostics?.iv_status_text ?? "Idle"}</strong></div>
        <div><span>Active Symbol</span><strong>{diagnostics?.iv_active_symbol ?? "N/A"}</strong></div>
        <div><span>Synthetic Names</span><strong>{diagnostics?.research_synthetic_count ?? 0}</strong></div>
      </div>
    </article>

    <article class="detail span-2">
      <h3>Operator Log</h3>
      {#if log.length}
        <div class="scroll mono">
          {#each log as line}
            <p>{line}</p>
          {/each}
        </div>
      {:else}
        <p class="muted">No browser operator actions yet.</p>
      {/if}
    </article>
  </div>
</section>

<style>
  .diagnostics,
  .grid,
  .detail-grid,
  .list {
    display: grid;
    gap: 0.9rem;
  }

  .header {
    display: flex;
    justify-content: space-between;
    gap: 0.9rem;
    align-items: start;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.65rem;
    justify-content: flex-end;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background:
      linear-gradient(180deg, rgba(12, 18, 25, 0.98), rgba(6, 9, 13, 0.98)),
      radial-gradient(circle at top right, rgba(232, 178, 96, 0.12), transparent 42%);
    padding: 1rem;
    box-shadow: 0 16px 28px var(--shadow);
  }

  .eyebrow,
  span,
  p,
  .muted {
    color: var(--text-2);
  }

  .eyebrow {
    margin: 0 0 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.72rem;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  .copy {
    max-width: 44rem;
  }

  .grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .grid article,
  .detail {
    border: 1px solid rgba(19, 32, 44, 0.75);
    background: rgba(5, 8, 11, 0.82);
    padding: 0.85rem;
  }

  .detail-grid {
    grid-template-columns: 1fr 1fr 1.35fr;
  }

  .bottom-grid {
    margin-top: 0.9rem;
  }

  .span-2 {
    grid-column: span 2;
  }

  strong {
    color: var(--text-0);
    display: block;
    margin-top: 0.35rem;
  }

  .mono strong {
    font-family: "Consolas", "SFMono-Regular", monospace;
    word-break: break-all;
  }

  .scroll {
    max-height: 12rem;
    overflow: auto;
    display: grid;
    gap: 0.5rem;
  }

  button {
    background: #060a0e;
    border: 1px solid #1e2e3c;
    color: var(--text-0);
    padding: 0.75rem 0.9rem;
    font: inherit;
    cursor: pointer;
  }

  @media (max-width: 1080px) {
    .header,
    .grid,
    .detail-grid {
      grid-template-columns: 1fr;
    }

    .header {
      flex-direction: column;
    }

    .actions {
      justify-content: stretch;
    }

    .actions button,
    .span-2 {
      grid-column: auto;
      width: 100%;
    }
  }
</style>
