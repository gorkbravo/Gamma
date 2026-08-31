<script lang="ts">
  import { workspaceTabOrders } from "./lib/stores/navigation";
  import {
    ACTION_KEYBINDINGS,
    getModeShortcutHintForIndex,
    getOrderedWorkspaceTabs,
    getShortcutHintForIndex,
    getTabModes,
  } from "./lib/navigation";
  import type { WorkspaceMode } from "./lib/api/types";

  const workspaceLabels: Record<WorkspaceMode, string> = {
    portfolio: "Portfolio Workspace",
    research: "Research Workspace",
  };

  const workspaceModes: WorkspaceMode[] = ["portfolio", "research"];

  $: workspaceSections = workspaceModes.map((mode) => ({
    mode,
    label: workspaceLabels[mode],
    tabs: getOrderedWorkspaceTabs(mode, $workspaceTabOrders).map((tab, index) => ({
      ...tab,
      shortcut: getShortcutHintForIndex(index),
    })),
  }));
  $: modeSections = workspaceModes.flatMap((workspaceMode) =>
    getOrderedWorkspaceTabs(workspaceMode, $workspaceTabOrders)
      .map((tab) => ({
        ...tab,
        modes: getTabModes(tab.id).map((mode, index) => ({
          ...mode,
          shortcut: getModeShortcutHintForIndex(index),
        })),
      }))
      .filter((tab) => tab.modes.length > 0)
  );
</script>

<svelte:head>
  <title>Gamma Key Bindings</title>
</svelte:head>

<main class="page">
  <section class="hero panel">
    <p class="eyebrow">Navigation</p>
    <h1>Key Bindings</h1>
    <p class="copy">
      Gamma keeps app actions explicit and derives tab shortcuts directly from each workspace's saved sidebar order.
    </p>
  </section>

  <section class="panel">
    <div class="section-head">
      <div>
        <p class="eyebrow">App Actions</p>
        <h2>Default and Effective</h2>
      </div>
      <p class="annotation">Current action bindings match the explicit defaults in this phase.</p>
    </div>

    <div class="table">
      <div class="row header">
        <span>Action</span>
        <span>Default</span>
        <span>Effective</span>
        <span>Source</span>
      </div>
      {#each ACTION_KEYBINDINGS as binding}
        <div class="row">
          <div>
            <strong>{binding.label}</strong>
            <small>{binding.description}</small>
          </div>
          <span>{binding.combos.map((combo) => combo.label).join(" or ")}</span>
          <span>{binding.combos.map((combo) => combo.label).join(" or ")}</span>
          <span>Explicit</span>
        </div>
      {/each}
    </div>
  </section>

  <section class="panel">
    <div class="section-head">
      <div>
        <p class="eyebrow">Derived Shortcuts</p>
        <h2>Workspace Tab Order</h2>
      </div>
      <p class="annotation">`Ctrl+1` through `Ctrl+N` always follow the live visual order shown here.</p>
    </div>

    <div class="binding-columns">
      {#each workspaceSections as workspace}
        <article class="workspace-card">
          <div class="workspace-card-head">
            <h3>{workspace.label}</h3>
            <small>{workspace.tabs.length} tabs</small>
          </div>
          <div class="table compact">
            <div class="row header">
              <span>Tab</span>
              <span>Effective</span>
              <span>Source</span>
            </div>
            {#each workspace.tabs as tab}
              <div class="row">
                <div>
                  <strong>{tab.label}</strong>
                  {#if tab.pinned}
                    <small>Pinned home tab</small>
                  {/if}
                </div>
                <span>{tab.shortcut}</span>
                <span>{tab.pinned ? "Derived / pinned" : "Derived"}</span>
              </div>
            {/each}
          </div>
        </article>
      {/each}
    </div>
  </section>

  <section class="panel">
    <div class="section-head">
      <div>
        <p class="eyebrow">Mode Shortcuts</p>
        <h2>Active Tab Modes</h2>
      </div>
      <p class="annotation">`Shift+1` through `Shift+N` follow the active tab's mode bar when modes are registered.</p>
    </div>

    <div class="binding-columns">
      {#each modeSections as tab}
        <article class="workspace-card">
          <div class="workspace-card-head">
            <h3>{tab.label}</h3>
            <small>{tab.modes.length} modes</small>
          </div>
          <div class="table compact">
            <div class="row header">
              <span>Mode</span>
              <span>Effective</span>
              <span>Source</span>
            </div>
            {#each tab.modes as mode}
              <div class="row">
                <div>
                  <strong>{mode.label}</strong>
                </div>
                <span>{mode.shortcut}</span>
                <span>Derived</span>
              </div>
            {/each}
          </div>
        </article>
      {/each}
    </div>
  </section>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: var(--app-font), monospace;
    background: var(--bg-0);
    color: var(--text-0);
  }

  .page {
    width: min(1080px, calc(100vw - 2rem));
    margin: 0 auto;
    padding: 1.25rem 0 1.5rem;
    display: grid;
    gap: 0.5rem;
  }

  .hero h1,
  .section-head h2,
  .workspace-card-head h3 {
    margin: 0;
  }

  .hero {
    display: grid;
    gap: 0.4rem;
  }

  .copy,
  .annotation,
  small {
    color: var(--text-2);
  }

  .copy,
  .annotation {
    margin: 0;
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .section-head,
  .workspace-card-head {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
    margin-bottom: 0.8rem;
  }

  .table {
    display: grid;
  }

  .row {
    display: grid;
    grid-template-columns: minmax(0, 2.2fr) minmax(0, 1.2fr) minmax(0, 1.2fr) minmax(0, 0.9fr);
    gap: 0.5rem;
    align-items: center;
    padding: 0.7rem 0;
    border-top: 1px solid var(--divider);
  }

  .compact .row {
    grid-template-columns: minmax(0, 1.6fr) minmax(0, 0.8fr) minmax(0, 1fr);
  }

  .header {
    padding-top: 0;
    border-top: 0;
    font-size: var(--text-2xs);
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-2);
  }

  strong {
    display: block;
    color: var(--text-0);
    font-size: var(--text-base);
  }

  small {
    display: block;
    margin-top: 0.14rem;
    font-size: var(--text-xs);
  }

  .binding-columns {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .workspace-card {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.9rem;
  }

  @media (max-width: 820px) {
    .page {
      width: min(100vw, calc(100vw - 1rem));
      padding: 0.75rem 0 1rem;
    }

    .section-head,
    .workspace-card-head,
    .row,
    .compact .row,
    .binding-columns {
      grid-template-columns: 1fr;
    }

    .row {
      gap: 0.35rem;
    }
  }
</style>
