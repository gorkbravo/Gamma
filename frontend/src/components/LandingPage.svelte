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
</script>

<section class="landing">
  <article class="card">
    <p class="eyebrow">Welcome</p>
    <h2>Welcome to StrataLab</h2>
    <p class="copy">Connect to IBKR or open the workspace you want to use.</p>

    <div class="meta">
      <strong>{connectedLabel(status)}</strong>
      <small>{status?.connection.status_text ?? "Waiting for backend status"}</small>
    </div>

    <div class="actions">
      <button
        class="primary apex"
        on:click={onConnect}
        disabled={busy || !status?.connection.action_enabled}
      >
        {busy ? "Working..." : connectionActionLabel(status)}
      </button>
      <button class="secondary" on:click={onEnterPortfolio}>Portfolio View</button>
      <button class="secondary" on:click={onEnterResearch}>Research View</button>
    </div>
  </article>
</section>

<style>
  .landing {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 1rem;
  }

  .card {
    width: min(28rem, calc(100vw - 2rem));
    display: grid;
    gap: 1rem;
    padding: 1.5rem;
    border: 1px solid rgba(90, 128, 162, 0.24);
    background:
      radial-gradient(circle at top, rgba(106, 168, 255, 0.16), transparent 48%),
      rgba(5, 10, 14, 0.92);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
  }

  .eyebrow,
  .copy,
  small {
    color: var(--text-2);
  }

  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.72rem;
    color: #87b7ff;
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    margin-top: -0.35rem;
    font-size: 1.45rem;
    line-height: 1.15;
  }

  .meta {
    display: grid;
    gap: 0.3rem;
  }

  strong {
    color: var(--text-0);
    font-size: 0.95rem;
  }

  small {
    line-height: 1.45;
  }

  .actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
    justify-items: center;
  }

  button {
    width: 100%;
    min-height: 3rem;
    background: #0b1219;
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.85rem 0.95rem;
    font: inherit;
    cursor: pointer;
    transition: border-color 0.12s ease, background 0.12s ease, transform 0.12s ease;
  }

  button:hover:enabled {
    border-color: rgba(122, 166, 200, 0.55);
    transform: translateY(-1px);
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.65;
  }

  .apex {
    grid-column: 1 / -1;
    max-width: 15rem;
  }

  .primary {
    border-color: rgba(106, 168, 255, 0.45);
    background: rgba(106, 168, 255, 0.14);
  }

  .secondary {
    max-width: 12.5rem;
  }

  @media (max-width: 640px) {
    .landing {
      place-items: center;
    }

    .card {
      width: min(28rem, 100%);
      padding: 1.2rem;
    }

    .actions {
      grid-template-columns: 1fr;
    }

    .apex,
    .secondary {
      max-width: none;
    }
  }
</style>
