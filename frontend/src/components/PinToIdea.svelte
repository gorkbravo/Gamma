<script lang="ts">
  // Pin to idea (Workstream 12, I1): the one shared panel-title action that
  // freezes what a panel shows into an idea's evidence. A panel passes a
  // draft (values on screen, provenance, reopen handoff); the user picks an
  // idea or creates one, then the stance. Never copied per view.
  import { onDestroy, tick } from "svelte";
  import type { IdeaEvidenceStance, IdeaPinDraft } from "../lib/api/types";
  import {
    EVIDENCE_STANCE_LABELS,
    IDEA_EVIDENCE_STANCES,
    capturedMetricPairs,
    capturedValuesExtraCount,
  } from "../lib/ideas";
  import {
    createIdea,
    ideasError,
    lastPinnedIdeaId,
    loadIdeas,
    pinEvidence,
    pinnableIdeas,
    requestOpenIdea,
  } from "../lib/stores/ideas";

  /** What this panel would pin right now; null disables the action. */
  export let draft: IdeaPinDraft | null = null;
  export let disabledReason = "Nothing on this panel to pin yet.";

  const NEW_IDEA = "__new__";
  const POPOVER_WIDTH = 320;

  let trigger: HTMLButtonElement | null = null;
  let popover: HTMLDivElement | null = null;
  let open = false;
  let snapshot: IdeaPinDraft | null = null;
  let target = "";
  let newTitle = "";
  let stance: IdeaEvidenceStance | null = null;
  let note = "";
  let saving = false;
  let error = "";
  let result: { ideaId: string; title: string; stance: IdeaEvidenceStance } | null = null;
  let position = "";
  const titleId = `pin-to-idea-${Math.random().toString(36).slice(2, 9)}`;

  $: preview = snapshot ? capturedMetricPairs(snapshot.captured_values, 4) : [];
  $: previewExtra = snapshot ? capturedValuesExtraCount(snapshot.captured_values, 4) : 0;
  $: creating = target === NEW_IDEA;
  $: canPin = Boolean(snapshot && stance && !saving && (creating ? newTitle.trim() : target));
  $: pinHint = !stance ? "Choose a stance first" : creating && !newTitle.trim() ? "Name the new idea first" : "";

  function place() {
    if (!trigger || typeof window === "undefined") return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(POPOVER_WIDTH, window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    const top = Math.min(rect.bottom + 4, Math.max(8, window.innerHeight - 40));
    position = `left: ${left}px; top: ${top}px; width: ${width}px;`;
  }

  async function openPicker() {
    if (!draft) return;
    // Freeze the capture at the click: a refresh while the picker is open
    // must not change what gets pinned.
    snapshot = JSON.parse(JSON.stringify(draft)) as IdeaPinDraft;
    stance = null;
    note = "";
    newTitle = "";
    error = "";
    result = null;
    open = true;
    place();
    addListeners();
    await loadIdeas();
    const ideas = $pinnableIdeas;
    const last = $lastPinnedIdeaId;
    target = last && ideas.some((idea) => idea.idea_id === last) ? last : ideas[0]?.idea_id ?? NEW_IDEA;
    await tick();
    popover?.querySelector<HTMLElement>("select, input")?.focus();
  }

  function close(returnFocus = true) {
    open = false;
    snapshot = null;
    removeListeners();
    if (returnFocus) trigger?.focus();
  }

  async function pin() {
    if (!snapshot || !stance || !canPin) return;
    saving = true;
    error = "";
    try {
      let ideaId = target;
      let title = $pinnableIdeas.find((idea) => idea.idea_id === target)?.title ?? "";
      if (creating) {
        const created = await createIdea({ title: newTitle.trim(), stance: "neutral" });
        if (!created) {
          error = $ideasError || "The idea could not be created.";
          return;
        }
        ideaId = created.idea_id;
        title = created.title;
      }
      const response = await pinEvidence(ideaId, { ...snapshot, stance, note: note.trim() });
      if (!response) {
        error = $ideasError || "The evidence could not be pinned.";
        return;
      }
      lastPinnedIdeaId.set(ideaId);
      result = { ideaId, title, stance };
    } finally {
      saving = false;
    }
  }

  function openIdea() {
    if (!result) return;
    const ideaId = result.ideaId;
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

  // The picker floats above every sheet: render it at the end of <body>, where
  // no panel's stacking context (transform, isolation) can paint over it.
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
  class="btn is-small is-ghost pin-trigger"
  disabled={!draft}
  title={draft ? `Pin “${draft.title}” to an idea` : disabledReason}
  aria-haspopup="dialog"
  aria-expanded={open}
  on:click={() => (open ? close() : openPicker())}
>
  Pin to idea
</button>

{#if open && snapshot}
  <div bind:this={popover} use:portal class="pin-popover" style={position} role="dialog" aria-label="Pin to idea">
    {#if result}
      <p class="pin-done" role="status">
        Pinned to <strong>{result.title}</strong> as {EVIDENCE_STANCE_LABELS[result.stance].toLowerCase()}.
      </p>
      <div class="pin-actions">
        <button type="button" class="btn is-small is-ghost" on:click={() => close()}>Done</button>
        <button type="button" class="btn is-small is-primary" on:click={openIdea}>Open idea</button>
      </div>
    {:else}
      <div class="pin-head">
        <strong>Pin to idea</strong>
        <span class="pin-subject">{snapshot.title}</span>
      </div>

      {#if preview.length}
        <dl class="pin-values">
          {#each preview as pair}
            <dt>{pair.label}</dt>
            <dd>{pair.display}</dd>
          {/each}
          {#if previewExtra}<dt class="pin-more">+{previewExtra} more</dt><dd></dd>{/if}
        </dl>
      {/if}

      <label class="pin-field">
        <span>Idea</span>
        <select class="form-control is-small" bind:value={target}>
          {#each $pinnableIdeas as idea (idea.idea_id)}
            <option value={idea.idea_id}>{idea.title}</option>
          {/each}
          <option value={NEW_IDEA}>New idea…</option>
        </select>
      </label>

      {#if creating}
        <label class="pin-field">
          <span>Title</span>
          <input class="form-control is-small" bind:value={newTitle} maxlength="200" placeholder="One-line idea" />
        </label>
      {/if}

      <div class="pin-field">
        <span id={`${titleId}-stance`}>Stance</span>
        <div class="segmented" role="radiogroup" aria-labelledby={`${titleId}-stance`}>
          {#each IDEA_EVIDENCE_STANCES as option}
            <button
              type="button"
              role="radio"
              aria-checked={stance === option}
              class:selected={stance === option}
              on:click={() => (stance = option)}>{EVIDENCE_STANCE_LABELS[option]}</button
            >
          {/each}
        </div>
      </div>

      <label class="pin-field">
        <span>Note</span>
        <input class="form-control is-small" bind:value={note} maxlength="2000" placeholder="Optional" />
      </label>

      {#if error}<p class="pin-error" role="alert">{error}</p>{/if}

      <div class="pin-actions">
        <button type="button" class="btn is-small is-ghost" on:click={() => close()}>Cancel</button>
        <button type="button" class="btn is-small is-primary" disabled={!canPin} title={pinHint} on:click={pin}>
          {saving ? "Pinning…" : "Pin"}
        </button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .pin-trigger {
    flex: none;
    white-space: nowrap;
  }

  /* A floating overlay: the elevation exception (§11). Svelte scopes these
     rules by class hash, so they still apply after the portal moves the node. */
  .pin-popover {
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

  .pin-head {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .pin-head strong {
    font-size: var(--text-title);
    font-weight: 600;
  }

  .pin-subject {
    color: var(--text-2);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .pin-values {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--space-1) var(--space-4);
    margin: 0;
  }

  .pin-values dt {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .pin-values dd {
    margin: 0;
    font-family: var(--font-num);
    text-align: right;
    white-space: nowrap;
  }

  .pin-field {
    display: grid;
    gap: var(--space-1);
  }

  .pin-field > span {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .pin-field {
    min-width: 0;
  }

  .pin-field .segmented {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .pin-field .segmented > button {
    flex: 1 1 0;
    justify-content: center;
    min-width: 0;
    padding-inline: var(--space-2);
  }

  .pin-field :global(select),
  .pin-field :global(input) {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
  }

  .pin-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .pin-done,
  .pin-error {
    margin: 0;
    line-height: var(--leading-snug);
  }

  .pin-error {
    color: var(--negative);
  }
</style>
