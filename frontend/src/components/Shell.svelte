<script lang="ts">
  export let title = "Gamma";
  export let copilotOpen = false;
  export let onToggleSidebar: () => void = () => {};
  export let onToggleCopilot: () => void = () => {};
</script>

<div class="shell">
  <header class="topbar">
    <div class="brand">
      <button class="hamburger" on:click={onToggleSidebar} aria-label="Toggle navigation">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M2.5 4h11M2.5 8h11M2.5 12h11" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
        </svg>
      </button>
      <img class="mark" src="/gamma-mark.svg" alt="" aria-hidden="true" />
      <h1>{title}</h1>
      <button
        class="copilot-trigger"
        class:open={copilotOpen}
        on:click={onToggleCopilot}
        aria-expanded={copilotOpen}
        aria-haspopup="dialog"
      >
        Copilot
      </button>
    </div>
    <div class="status-slot">
      <slot name="status" />
    </div>
  </header>

  <main class="content">
    <slot />
  </main>
</div>

<style>
  .shell {
    width: min(1600px, calc(100vw - 1.5rem));
    margin: 0 auto;
    padding: 0.5rem 0 1.1rem;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.6rem;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--panel-border);
    background: var(--bg-0);
  }

  .brand {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.45rem;
    min-width: 0;
  }

  .hamburger {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-1);
    padding: 0.2rem;
    cursor: pointer;
    border-radius: 2px;
    transition: color 120ms ease, border-color 120ms ease;
  }

  .hamburger:hover {
    color: var(--text-0);
    border-color: rgba(122, 166, 200, 0.32);
  }

  .mark {
    display: block;
    width: 1.15rem;
    height: auto;
    opacity: 0.85;
  }

  h1 {
    margin: 0;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .copilot-trigger {
    background: transparent;
    border: 1px solid transparent;
    color: var(--accent);
    font-size: 0.74rem;
    font-weight: 500;
    letter-spacing: 0.04em;
    padding: 0.12rem 0.35rem;
    cursor: pointer;
    border-radius: 2px;
    transition: border-color 120ms ease, color 120ms ease;
  }

  .copilot-trigger:hover {
    border-color: rgba(122, 166, 200, 0.32);
    color: var(--text-0);
  }

  .copilot-trigger.open {
    border-color: rgba(122, 166, 200, 0.42);
    color: var(--text-0);
  }

  .status-slot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-width: 0;
    padding-left: 0.6rem;
    border-left: 1px solid var(--divider);
  }

  .content {
    margin-top: 0.8rem;
  }

  @media (max-width: 960px) {
    .topbar,
    .brand {
      align-items: flex-start;
    }

    .topbar,
    .brand {
      flex-direction: column;
    }

    .topbar {
      display: flex;
      padding: 0.4rem 0.75rem;
    }

    .status-slot {
      width: 100%;
      justify-content: stretch;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.5rem;
    }
  }
</style>
