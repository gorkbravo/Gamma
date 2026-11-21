<script lang="ts">
  // "What is this?" (Workstream 12, I2): one shared popover over the backend's
  // explanation registry. Three parts: what it measures, why it matters for
  // this idea's stance, and how Gamma computes it (with the live provenance of
  // the reading when there is one). It sits behind an icon so it never turns
  // into a static interpretive note on a data surface.
  import { onDestroy, tick } from "svelte";
  import type { IdeaProvenanceRecord, IdeaStance } from "../lib/api/types";
  import { IDEA_STANCE_LABELS } from "../lib/ideas";
  import { toProvenanceBadge } from "../lib/provenance";
  import { ensureIdeaExplanations, ideaExplanations } from "../lib/stores/ideas";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";

  /** Registry key, e.g. "observable.equity_close" or "state.unavailable". */
  export let key: string;
  export let stance: IdeaStance = "neutral";
  /** The reading this popover explains, when there is one. */
  export let provenance: IdeaProvenanceRecord | null = null;
  /** Extra line under "How Gamma computes it", e.g. the reason a reading is unavailable. */
  export let note = "";

  const WIDTH = 300;
  let trigger: HTMLButtonElement | null = null;
  let popover: HTMLDivElement | null = null;
  let open = false;
  let position = "";

  $: entry = $ideaExplanations[key] ?? null;
  $: accessibleName = `What is this? ${entry?.title ?? key.split(".").pop()?.replaceAll("_", " ") ?? ""}`.trim();

  function place() {
    if (!trigger || typeof window === "undefined") return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(WIDTH, window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const top = Math.min(rect.bottom + 4, Math.max(8, window.innerHeight - 60));
    position = `left: ${left}px; top: ${top}px; width: ${width}px;`;
  }

  async function show() {
    open = true;
    place();
    addListeners();
    await ensureIdeaExplanations();
    await tick();
    place();
  }

  function hide(returnFocus = true) {
    open = false;
    removeListeners();
    if (returnFocus) trigger?.focus();
  }

  function handlePointerDown(event: PointerEvent) {
    const node = event.target as Node;
    if (popover?.contains(node) || trigger?.contains(node)) return;
    hide(false);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      hide();
    }
  }

  function addListeners() {
    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("keydown", handleKeydown, true);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
  }

  function removeListeners() {
    if (typeof document === "undefined") return;
    document.removeEventListener("pointerdown", handlePointerDown, true);
    document.removeEventListener("keydown", handleKeydown, true);
    window.removeEventListener("resize", place);
    window.removeEventListener("scroll", place, true);
  }

  onDestroy(removeListeners);

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return {
      destroy() {
        node.remove();
      },
    };
  }
</script>

<button
  bind:this={trigger}
  type="button"
  class="what-trigger"
  aria-label={accessibleName}
  aria-haspopup="dialog"
  aria-expanded={open}
  on:click|stopPropagation={() => (open ? hide() : show())}
>?</button>

{#if open}
  <div bind:this={popover} use:portal class="what-popover" style={position} role="dialog" aria-label={accessibleName}>
    {#if entry}
      <strong class="what-title">{entry.title}</strong>
      <dl>
        <dt>What it measures</dt>
        <dd>{entry.measures}</dd>
        <dt>Why it matters for a {IDEA_STANCE_LABELS[stance].toLowerCase()} idea</dt>
        <dd>{entry.why[stance]}</dd>
        <dt>How Gamma computes it</dt>
        <dd>
          {entry.computed}
          {#if note}<span class="what-note">{note}</span>{/if}
        </dd>
      </dl>
      {#if provenance}
        <div class="what-source">
          <ProvenanceBadge data={toProvenanceBadge(provenance)} />
        </div>
      {:else if entry.source}
        <span class="what-plain-source">Source: {entry.source}</span>
      {/if}
    {:else}
      <span class="what-plain-source">Loading…</span>
    {/if}
  </div>
{/if}

<style>
  .what-trigger {
    display: inline-grid;
    place-items: center;
    flex: none;
    width: 14px;
    height: 14px;
    padding: 0;
    margin-left: var(--space-1);
    border: 1px solid var(--panel-strong);
    border-radius: var(--radius-pill);
    background: transparent;
    color: var(--text-2);
    font-family: var(--font-ui);
    font-size: var(--text-2xs);
    font-weight: 600;
    line-height: 1;
    vertical-align: middle;
    cursor: help;
  }

  .what-trigger:hover,
  .what-trigger[aria-expanded="true"] {
    border-color: var(--accent);
    color: var(--accent);
  }

  /* A floating overlay: the elevation exception (§11). */
  .what-popover {
    position: fixed;
    z-index: 75;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    box-sizing: border-box;
    gap: var(--space-3);
    padding: var(--space-5);
    border: 1px solid var(--panel-border);
    border-radius: var(--overlay-radius);
    background: var(--popover-bg);
    box-shadow: var(--overlay-shadow);
    color: var(--text-0);
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    font-weight: 400;
    line-height: var(--leading-snug);
    text-align: left;
    text-transform: none;
    white-space: normal;
  }

  .what-title {
    font-size: var(--text-title);
    font-weight: 600;
  }

  dl {
    display: grid;
    gap: var(--space-1);
    margin: 0;
  }

  dt {
    margin-top: var(--space-2);
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  dt:first-child {
    margin-top: 0;
  }

  dd {
    margin: 0;
    color: var(--text-1);
  }

  .what-note {
    display: block;
    margin-top: var(--space-1);
    color: var(--text-0);
  }

  .what-source {
    display: flex;
    min-width: 0;
  }

  .what-plain-source {
    color: var(--text-2);
    font-size: var(--text-xs);
  }
</style>
