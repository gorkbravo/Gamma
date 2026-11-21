<script lang="ts">
  // Notification center (Workstream 12, I2, decision 3): in-app only. Lists
  // criterion triggers and reviews due, each linking to its idea; Sitrep shows
  // the same items under "Your ideas". Nothing leaves the machine.
  import { onDestroy, tick } from "svelte";
  import type { IdeaNotification, IdeaNotificationsResponse } from "../lib/api/types";
  import { CRITERION_KIND_LABELS, notificationDetail, notificationTone } from "../lib/idea-criteria";

  export let notifications: IdeaNotificationsResponse | null = null;
  export let onOpenIdea: (ideaId: string) => void | Promise<void> = () => {};
  export let onAcknowledge: (ideaId: string, criterionId: string) => Promise<unknown> = async () => null;
  export let onRefresh: () => Promise<unknown> = async () => null;

  const WIDTH = 340;
  let trigger: HTMLButtonElement | null = null;
  let popover: HTMLDivElement | null = null;
  let open = false;
  let position = "";

  $: items = notifications?.items ?? [];
  $: count = items.length;
  $: triggered = notifications?.triggered ?? 0;
  $: buttonLabel = count ? `Idea notifications: ${triggered} triggered, ${notifications?.reviews_due ?? 0} reviews due` : "Idea notifications: none";

  function place() {
    if (!trigger || typeof window === "undefined") return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(WIDTH, window.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    position = `left: ${left}px; top: ${rect.bottom + 6}px; width: ${width}px;`;
  }

  async function show() {
    open = true;
    place();
    addListeners();
    // El popover se renderiza al final de <body>: se le da el foco para que el teclado llegue a él.
    await tick();
    popover?.focus();
    await onRefresh();
    await tick();
    place();
  }

  /**
   * Llevar el foco con Tab a otro elemento de la página cierra el popover.
   * Sin destino (p. ej. al reconocer un aviso y desaparecer su botón) se mantiene abierto.
   */
  function handleFocusOut(event: FocusEvent) {
    const next = event.relatedTarget as Node | null;
    if (!next || popover?.contains(next) || trigger?.contains(next)) return;
    hide(false);
  }

  function hide(returnFocus = true) {
    open = false;
    removeListeners();
    if (returnFocus) trigger?.focus();
  }

  function openItem(item: IdeaNotification) {
    hide(false);
    void onOpenIdea(item.idea_id);
  }

  function handlePointerDown(event: PointerEvent) {
    const node = event.target as Node;
    if (popover?.contains(node) || trigger?.contains(node)) return;
    hide(false);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      hide();
    }
  }

  function addListeners() {
    document.addEventListener("pointerdown", handlePointerDown, true);
    document.addEventListener("keydown", handleKeydown, true);
    window.addEventListener("resize", place);
  }

  function removeListeners() {
    if (typeof document === "undefined") return;
    document.removeEventListener("pointerdown", handlePointerDown, true);
    document.removeEventListener("keydown", handleKeydown, true);
    window.removeEventListener("resize", place);
  }

  onDestroy(removeListeners);

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }
</script>

<button
  bind:this={trigger}
  type="button"
  class="notice-trigger"
  class:has-items={count > 0}
  class:has-triggers={triggered > 0}
  aria-label={buttonLabel}
  title={buttonLabel}
  aria-haspopup="dialog"
  aria-expanded={open}
  on:click={() => (open ? hide() : show())}
>
  <span>Ideas</span>
  {#if count}<span class="notice-count">{count}</span>{/if}
</button>

{#if open}
  <div
    bind:this={popover}
    use:portal
    class="notice-popover"
    style={position}
    role="dialog"
    aria-label="Idea notifications"
    tabindex="-1"
    on:focusout={handleFocusOut}
  >
    <div class="notice-head">
      <strong>Idea notifications</strong>
      <span>{triggered} triggered · {notifications?.reviews_due ?? 0} reviews due</span>
    </div>
    {#if items.length}
      <ul class="notice-list">
        {#each items as item (item.notification_id)}
          <li>
            <button type="button" class="notice-item" on:click={() => openItem(item)}>
              <span class="notice-line">
                <span class="tag {notificationTone(item)}"
                  >{item.kind === "review_due" ? "Review" : CRITERION_KIND_LABELS[item.criterion_kind ?? "review"]}</span
                >
                <strong>{item.label}</strong>
              </span>
              <span class="notice-idea">{item.idea_title}</span>
              <span class="notice-detail">{notificationDetail(item)}</span>
            </button>
            {#if item.kind === "criterion_triggered" && item.criterion_id}
              <button
                type="button"
                class="btn is-small is-ghost notice-ack"
                on:click={() => item.criterion_id && onAcknowledge(item.idea_id, item.criterion_id)}>Acknowledge</button
              >
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="notice-empty">No triggered criteria or reviews due.</p>
    {/if}
    <p class="notice-foot">{notifications?.limitation ?? "Criteria are evaluated only while Gamma runs."}</p>
  </div>
{/if}

<style>
  .notice-trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    background: var(--tint);
    border: 1px solid transparent;
    color: var(--text-1);
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    font-weight: 500;
    padding: var(--space-1) var(--space-4);
    border-radius: var(--radius-control);
    cursor: pointer;
    white-space: nowrap;
  }

  .notice-trigger:hover,
  .notice-trigger[aria-expanded="true"] {
    border-color: var(--panel-strong);
    color: var(--text-0);
  }

  .notice-count {
    min-width: 1.1rem;
    padding: 0 var(--space-1);
    border-radius: var(--radius-pill);
    background: var(--accent-soft);
    color: var(--accent);
    font-family: var(--font-num);
    font-size: var(--text-xs);
    text-align: center;
  }

  .has-triggers .notice-count {
    background: var(--warning-soft);
    color: var(--warning);
  }

  .notice-popover {
    position: fixed;
    z-index: 80;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    box-sizing: border-box;
    gap: var(--space-3);
    max-height: min(70vh, 32rem);
    overflow-y: auto;
    padding: var(--space-5);
    border: 1px solid var(--panel-border);
    border-radius: var(--overlay-radius);
    background: var(--popover-bg);
    box-shadow: var(--overlay-shadow);
    color: var(--text-0);
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
  }

  .notice-head {
    display: grid;
    gap: var(--space-1);
  }

  .notice-head strong {
    font-size: var(--text-title);
    font-weight: 600;
  }

  .notice-head span,
  .notice-foot,
  .notice-empty {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .notice-list {
    display: grid;
    gap: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .notice-list li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
    gap: var(--space-3);
    padding: var(--space-3) 0;
    border-top: 1px solid var(--divider);
  }

  .notice-item {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    font-family: var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .notice-item:hover strong {
    color: var(--accent);
  }

  .notice-line {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .notice-line strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }

  .notice-idea {
    color: var(--text-1);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .notice-detail {
    color: var(--text-2);
    font-family: var(--font-num);
    font-size: var(--text-xs);
  }

  .notice-ack {
    flex: none;
  }
</style>
