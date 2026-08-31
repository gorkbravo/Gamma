<script lang="ts">
  import type { SystemStatus } from "../lib/api/types";

  export let status: SystemStatus | null = null;
  export let busy = false;
  export let onConnect: () => void;
  export let onEnterPortfolio: () => void;
  export let onEnterResearch: () => void;

  const connectedLabel = (status: SystemStatus | null) => {
    if (!status) {
      return "Checking connection";
    }
    if (status.connection.connected) {
      return status.connection.active_account
        ? `Connected: ${status.connection.active_account}`
        : "Connected";
    }
    return "Disconnected";
  };

  const connectionActionLabel = (status: SystemStatus | null) => {
    if (status?.connection.connected) {
      return "Disconnect from IBKR";
    }
    return "Connect to IBKR";
  };

  /* Everything here is already reported by /system/status. The old screen
     asked you to connect without saying what you were connecting to. */
  $: readout = status
    ? [
        { label: "Backend", value: status.backend, tone: status.healthy ? "ok" : "warn" },
        {
          label: "Data",
          value: status.mock_mode ? "Mock" : status.market_data_mode || "Live",
          tone: status.mock_mode ? "warn" : "ok"
        },
        { label: "Base currency", value: status.base_currency, tone: "" },
        {
          label: "Cached symbols",
          value: status.cached_symbols.length ? String(status.cached_symbols.length) : "None",
          tone: ""
        }
      ]
    : [];

  $: extraStatus =
    status?.connection.status_text &&
    status.connection.status_text !== `Status: ${connectedLabel(status)}`
      ? status.connection.status_text
      : null;
</script>

<section class="landing">
  <article class="card">
    <header class="identity">
      <span class="mark" aria-hidden="true">Γ</span>
      <div class="wordmark">
        <h2>Gamma</h2>
        <p class="descriptor">Research Terminal</p>
      </div>
      <p class="conn" class:live={status?.connection.connected}>
        <span class="status-dot" class:connected={status?.connection.connected} aria-hidden="true"></span>
        <strong>{connectedLabel(status)}</strong>
      </p>
    </header>

    {#if status}
      <dl class="readout">
        {#each readout as row}
          <div class="readout-row">
            <dt>{row.label}</dt>
            <dd class={row.tone}>{row.value}</dd>
          </div>
        {/each}
      </dl>
    {:else}
      <p class="status-note">Reading backend status…</p>
    {/if}

    {#if extraStatus}
      <p class="status-note">{extraStatus}</p>
    {/if}

    <div class="actions">
      <button
        class="primary"
        on:click={onConnect}
        disabled={busy || !status?.connection.action_enabled}
      >
        {busy ? "Working..." : connectionActionLabel(status)}
      </button>
      <button class="secondary" on:click={onEnterResearch}>
        Research View
        <small>Markets, macro, filings, options</small>
      </button>
      <button class="secondary" on:click={onEnterPortfolio}>
        Portfolio View
        <small>Positions, risk, attribution</small>
      </button>
    </div>

    <p class="boundary">Read-only. Gamma never places orders or moves funds.</p>
  </article>
</section>

<style>
  .landing {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: var(--space-7) var(--space-6);
  }

  .card {
    width: min(46rem, calc(100vw - 2rem));
    display: grid;
    gap: var(--space-6);
    padding: var(--space-7);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    box-shadow: 0 24px 56px var(--shadow);
  }

  .identity {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-5);
    padding-bottom: var(--space-5);
    border-bottom: 1px solid var(--panel-border);
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.4rem;
    height: 2.4rem;
    flex-shrink: 0;
    border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--panel-border));
    border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--accent) 12%, var(--surface-0));
    color: var(--accent);
    font-family: var(--display-font);
    font-size: var(--text-xl);
    font-weight: 700;
    line-height: 1;
  }

  .wordmark {
    display: grid;
    gap: var(--space-1);
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    font-size: var(--text-xl);
    line-height: 1.1;
    letter-spacing: 0.02em;
  }

  .descriptor {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-sm);
    letter-spacing: 0.04em;
  }

  .conn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    white-space: nowrap;
  }

  .conn strong {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .conn.live strong {
    color: var(--positive);
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-2);
    flex-shrink: 0;
  }

  .status-dot.connected {
    background: var(--positive);
  }

  .readout {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
    gap: 1px;
    margin: 0;
    background: var(--panel-border);
    border: 1px solid var(--panel-border);
  }

  .readout-row {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-4) var(--space-5);
    background: var(--surface-0);
  }

  dt {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-2xs);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  dd {
    margin: 0;
    color: var(--text-0);
    font-size: var(--text-base);
  }

  dd.ok {
    color: var(--positive);
  }

  dd.warn {
    color: var(--warning);
  }

  .status-note {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-sm);
    line-height: var(--leading-normal);
  }

  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
  }

  button {
    display: grid;
    gap: var(--space-2);
    justify-items: start;
    text-align: left;
    min-height: 2.5rem;
    background: var(--bg-1);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-sm);
    color: var(--text-0);
    padding: var(--space-5) var(--space-6);
    font: inherit;
    font-family: var(--display-font);
    font-weight: 500;
    cursor: pointer;
    transition: border-color var(--motion-fast) var(--ease), background var(--motion-fast) var(--ease);
  }

  button small {
    color: var(--text-2);
    font-size: var(--text-xs);
    font-weight: 400;
  }

  button:hover:enabled {
    border-color: color-mix(in srgb, var(--accent) 55%, var(--panel-strong));
    background: var(--hover-bg);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .primary {
    grid-column: 1 / -1;
    justify-items: center;
    text-align: center;
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    background: color-mix(in srgb, var(--accent) 14%, transparent);
  }

  .boundary {
    color: var(--text-2);
    font-family: var(--display-font);
    font-size: var(--text-xs);
    padding-top: var(--space-5);
    border-top: 1px solid var(--panel-border);
  }

  @media (max-width: 640px) {
    .card {
      width: min(28rem, 100%);
      padding: var(--space-6);
    }

    .identity {
      grid-template-columns: auto minmax(0, 1fr);
      row-gap: var(--space-4);
    }

    .conn {
      grid-column: 1 / -1;
    }

    .actions {
      grid-template-columns: 1fr;
    }
  }
</style>
