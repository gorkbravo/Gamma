<script lang="ts">
  export let title = "StrataLab";
</script>

<div class="shell">
  <header class="topbar">
    <div class="brand">
      <div class="mark-frame" aria-hidden="true">
        <img class="mark" src="/stratalab-mark.svg" alt="" />
      </div>
      <div class="copy">
        <div class="title-row">
          <h1>{title}</h1>
          <span class="eyebrow">Quant Research Desk</span>
        </div>
      </div>
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
    padding: 0.75rem 0 1.25rem;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 0.9rem;
    padding: 0.8rem 1rem;
    border: 1px solid var(--panel-border);
    background: var(--surface-1);
  }

  .brand,
  .title-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .brand {
    min-width: 0;
  }

  .mark {
    display: block;
    width: 2.35rem;
    height: auto;
  }

  .mark-frame {
    display: grid;
    place-items: center;
    min-width: 3.3rem;
    min-height: 3.3rem;
    padding: 0.45rem;
    border: 1px solid rgba(122, 166, 200, 0.26);
    background:
      radial-gradient(circle at 50% 28%, rgba(106, 168, 255, 0.16), transparent 62%),
      linear-gradient(180deg, rgba(13, 22, 31, 0.96), rgba(7, 11, 16, 0.96));
    box-shadow: inset 0 0 0 1px rgba(244, 247, 251, 0.03);
  }

  .copy {
    min-width: 0;
  }

  .eyebrow {
    color: var(--accent-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.68rem;
    white-space: nowrap;
  }

  h1 {
    margin: 0;
  }

  h1 {
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .status-slot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-width: 0;
    min-height: 100%;
    padding-left: 0.9rem;
    border-left: 1px solid var(--divider);
  }

  .content {
    margin-top: 0.9rem;
  }

  @media (max-width: 960px) {
    .topbar,
    .brand,
    .title-row {
      align-items: flex-start;
    }

    .topbar,
    .brand {
      flex-direction: column;
    }

    .topbar {
      display: flex;
    }

    .status-slot {
      width: 100%;
      justify-content: stretch;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.85rem;
    }

    .eyebrow {
      white-space: normal;
    }
  }
</style>
