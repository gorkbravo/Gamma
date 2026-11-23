<script lang="ts">
  // Attach to idea (Workstream 12, I4c): the one shared action that hands a
  // result from Strategy Lab or Risk to an idea. Unlike "Pin to idea", which
  // freezes what a panel shows as evidence, an attach asks the backend to
  // recompute the result into the idea (a test or risk snapshot, or a signal),
  // so it carries provenance and counts as a trial. Never copied per view.
  import { onDestroy, tick } from "svelte";
  import type { IdeaAttachTarget } from "../lib/idea-attach";
  import { createIdea, ideasError, lastPinnedIdeaId, loadIdeas, pinnableIdeas, requestOpenIdea } from "../lib/stores/ideas";

  /** What would be attached right now; null disables the action with ``disabledReason``. */
  export let target: IdeaAttachTarget | null = null;
  export let disabledReason = "Nothing to attach yet.";

  const NEW_IDEA = "__new__";
  const POPOVER_WIDTH = 320;

  let trigger: HTMLButtonElement | null = null;
  let popover: HTMLDivElement | null = null;
  let open = false;
  let frozen: IdeaAttachTarget | null = null;
  let choice = "";
  let newTitle = "";
  let saving = false;
  let error = "";
  let done: { ideaId: string; title: string } | null = null;
  let position = "";

  $: creating = choice === NEW_IDEA;
  $: canAttach = Boolean(frozen && !saving && (creating ? newTitle.trim() : choice));

  function place() {
    if (!trigger || typeof window === "undefined") return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(POPOVER_WIDTH, window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    const top = Math.min(rect.bottom + 4, Math.max(8, window.innerHeight - 40));
    position = `left: ${left}px; top: ${top}px; width: ${width}px;`;
  }

  async function openPicker() {
    if (!target) return;
    // Lo que se adjunta se fija al hacer clic: un refresco con el selector abierto no lo cambia.
    frozen = target;
    newTitle = "";
    error = "";
    done = null;
    open = true;
    place();
    addListeners();
    await loadIdeas();
    const ideas = $pinnableIdeas;
    const last = $lastPinnedIdeaId;
    choice = last && ideas.some((idea) => idea.idea_id === last) ? last : ideas[0]?.idea_id ?? NEW_IDEA;
    await tick();
    popover?.querySelector<HTMLElement>("select, input")?.focus();
  }

  function close(returnFocus = true) {
    open = false;
    frozen = null;
    removeListeners();
    if (returnFocus) trigger?.focus();
  }

  async function attach() {
    if (!frozen || !canAttach) return;
    saving = true;
    error = "";
    try {
      let ideaId = choice;
      let title = $pinnableIdeas.find((idea) => idea.idea_id === choice)?.title ?? "";
      if (creating) {
        const created = await createIdea({ title: newTitle.trim(), stance: "neutral" });
        if (!created) {
          error = $ideasError || "The idea could not be created.";
          return;
        }
        ideaId = created.idea_id;
        title = created.title;
        // Un reintento tras un fallo apunta a la idea ya creada, no a otra vacía.
        choice = ideaId;
      }
      const message = await frozen.attach(ideaId);
      if (message) {
        error = message;
        return;
      }
      lastPinnedIdeaId.set(ideaId);
      done = { ideaId, title };
    } finally {
      saving = false;
    }
  }

  function openIdea() {
    if (!done) return;
    const ideaId = done.ideaId;
    close(false);
    requestOpenIdea(ideaId);
  }

  function handlePointerDown(event: PointerEvent) {
    const node = event.target as Node;
    if (popover?.contains(node) || trigger?.contains(node)) return;
    close(false);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close();
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

  // El selector flota sobre todas las hojas: se monta al final de <body>.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }
</script>

<button
  bind:this={trigger}
  type="button"
  class="btn is-small is-ghost attach-trigger"
  disabled={!target}
  title={target ? target.summary : disabledReason}
  aria-haspopup="dialog"
  aria-expanded={open}
  on:click={() => (open ? close() : openPicker())}
>
  Attach to idea
</button>

{#if open && frozen}
  <div bind:this={popover} use:portal class="attach-popover" style={position} role="dialog" aria-label="Attach to idea">
    {#if done}
      <p class="attach-done" role="status">Attached to <strong>{done.title}</strong> as {frozen.kindLabel.toLowerCase()}.</p>
      <div class="attach-actions">
        <button type="button" class="btn is-small is-ghost" on:click={() => close()}>Done</button>
        <button type="button" class="btn is-small is-primary" on:click={openIdea}>Open idea</button>
      </div>
    {:else}
      <div class="attach-head">
        <strong>Attach to idea</strong>
        <span class="attach-subject">{frozen.kindLabel} · {frozen.label}</span>
      </div>
      <p class="attach-note">{frozen.summary}</p>
      <label class="attach-field">
        <span>Idea</span>
        <select class="form-control is-small" bind:value={choice}>
          {#each $pinnableIdeas as idea (idea.idea_id)}
            <option value={idea.idea_id}>{idea.title}</option>
          {/each}
          <option value={NEW_IDEA}>New idea…</option>
        </select>
      </label>
      {#if creating}
        <label class="attach-field">
          <span>New idea title</span>
          <input class="form-control is-small" bind:value={newTitle} maxlength="200" placeholder="One-line idea" />
        </label>
      {/if}
      {#if error}<p class="attach-error" role="alert">{error}</p>{/if}
      <div class="attach-actions">
        <button type="button" class="btn is-small is-ghost" on:click={() => close()}>Cancel</button>
        <button type="button" class="btn is-small is-primary" disabled={!canAttach} title={creating && !newTitle.trim() ? "Name the new idea first" : ""} on:click={attach}>
          {saving ? "Attaching…" : "Attach"}
        </button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .attach-trigger {
    flex: none;
    white-space: nowrap;
  }

  /* Superposición flotante: la excepción de elevación (§11). */
  .attach-popover {
    position: fixed;
    z-index: 70;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    box-sizing: border-box;
    gap: var(--space-4);
    padding: var(--space-5);
    border: 1px solid var(--panel-border);
    border-radius: var(--overlay-radius);
    background: var(--popover-bg);
    box-shadow: var(--overlay-shadow);
    color: var(--text-0);
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    text-transform: none;
    font-weight: 400;
    text-align: left;
    line-height: var(--leading-snug);
  }

  .attach-head {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .attach-head strong {
    font-size: var(--text-title);
    font-weight: 600;
  }

  .attach-subject {
    color: var(--text-2);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .attach-note {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-xs);
  }

  .attach-field {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .attach-field > span {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .attach-field :global(select),
  .attach-field :global(input) {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .attach-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .attach-done,
  .attach-error {
    margin: 0;
  }

  .attach-error {
    color: var(--negative);
  }
</style>
