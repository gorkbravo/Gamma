<script lang="ts">
  // «Report a problem» (beta, 2026-11-28): el tester ve el informe completo, lo copia o lo
  // guarda en local y lo envía él mismo. Gamma no manda nada a ningún sitio. El backend
  // (src/application/diagnostic_report.py) decide qué entra y sanea los mensajes.
  import { onDestroy, onMount } from "svelte";
  import type { DiagnosticReport, DiagnosticReportResponse } from "../lib/api/types";
  import {
    previewDiagnosticReport,
    saveDiagnosticReport,
    type DiagnosticReportRequest
  } from "../lib/stores/setup";
  import ModalFrame from "./ModalFrame.svelte";

  const NOTE_MAX = 2000;
  const PREVIEW_DELAY_MS = 400;

  // Contexto del cliente (pestaña activa, último error…); el backend lo filtra y lo sanea.
  export let client: Record<string, string> = {};
  export let onClose: () => void;
  // Inyectables para los tests; por defecto, la API y el portapapeles reales.
  export let preview: (request: DiagnosticReportRequest) => Promise<DiagnosticReportResponse> = previewDiagnosticReport;
  export let save: (request: DiagnosticReportRequest) => Promise<DiagnosticReportResponse> = saveDiagnosticReport;
  export let copyText: (text: string) => Promise<void> = copyToClipboard;

  let note = "";
  let report: DiagnosticReport | null = null;
  let previewError = "";
  let busy = false;
  let actionStatus = "";
  let actionFailed = false;
  let savedPath: string | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let requestSeq = 0;

  $: reportText = report ? JSON.stringify(report, null, 2) : "";

  onMount(() => {
    void refresh();
  });

  onDestroy(() => {
    if (timer) clearTimeout(timer);
  });

  // La API asíncrona del portapapeles puede no estar disponible (vista incrustada, permiso
  // denegado); el respaldo copia desde un textarea temporal con execCommand.
  async function copyToClipboard(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Se intenta el respaldo.
    }
    // El textarea temporal va junto al botón, dentro del diálogo, para no romper la trampa de foco.
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    (previous?.parentElement ?? document.body).appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } finally {
      area.remove();
      previous?.focus();
    }
    if (!copied) throw new Error("Clipboard unavailable");
  }

  function request(): DiagnosticReportRequest {
    return { note: note.trim() || null, client };
  }

  // Solo la respuesta más reciente actualiza la vista previa.
  async function refresh(): Promise<DiagnosticReport | null> {
    const seq = ++requestSeq;
    try {
      const response = await preview(request());
      if (seq === requestSeq) {
        report = response.report;
        previewError = "";
      }
      return response.report;
    } catch (error) {
      if (seq === requestSeq) {
        previewError = error instanceof Error ? error.message : String(error);
      }
      return null;
    }
  }

  function handleNoteInput() {
    actionStatus = "";
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void refresh(), PREVIEW_DELAY_MS);
  }

  async function copyReport() {
    if (busy) return;
    busy = true;
    actionStatus = "";
    if (timer) clearTimeout(timer);
    const current = await refresh();
    if (!current) {
      busy = false;
      return;
    }
    try {
      await copyText(JSON.stringify(current, null, 2));
      actionFailed = false;
      actionStatus = "Report copied. Paste it into your message to the Gamma team.";
    } catch {
      actionFailed = true;
      actionStatus = "Gamma could not copy to the clipboard. Select the text in Report preview and copy it, or use Save report.";
    }
    busy = false;
  }

  async function saveReport() {
    if (busy) return;
    busy = true;
    actionStatus = "";
    if (timer) clearTimeout(timer);
    try {
      const response = await save(request());
      report = response.report;
      savedPath = response.path;
      actionFailed = false;
      actionStatus = response.path ? "Report saved. Attach this file to your message to the Gamma team:" : "Report saved.";
    } catch (error) {
      actionFailed = true;
      savedPath = null;
      actionStatus = `Gamma could not save the report: ${error instanceof Error ? error.message : String(error)}`;
    }
    busy = false;
  }
</script>

<ModalFrame titleId="report-problem-title" title="Report a problem" eyebrow="Beta feedback" closeLabel="Close report a problem" {onClose}>
  <p class="lead">
    Describe what happened, then copy or save the report and send it to the Gamma team yourself.
    <strong>Gamma does not send it anywhere.</strong>
  </p>

  <label class="field">
    <span class="field-label">What happened?</span>
    <textarea
      class="form-control"
      rows="4"
      maxlength={NOTE_MAX}
      placeholder="What you did, what you expected and what you saw instead. Avoid personal or account details."
      bind:value={note}
      on:input={handleNoteInput}
    ></textarea>
    <small>{note.length} / {NOTE_MAX}</small>
  </label>

  {#if report}
    <section class="excluded" aria-labelledby="report-excluded-title">
      <h3 id="report-excluded-title">Never included</h3>
      <ul>
        {#each report.excluded as item}
          <li>{item}</li>
        {/each}
      </ul>
      <p class="note">Error messages are shortened and stripped of links, emails, account numbers and key-like values; IBKR messages are left out.</p>
    </section>
  {/if}

  <section class="preview" aria-labelledby="report-preview-title">
    <h3 id="report-preview-title">Report preview</h3>
    {#if previewError}
      <p class="notice warning" role="alert">Gamma could not build the report: {previewError}</p>
    {:else if report}
      <pre tabindex="0" aria-label="Report contents">{reportText}</pre>
    {:else}
      <p class="note" aria-live="polite">Building the report…</p>
    {/if}
  </section>

  {#if actionStatus}
    <div class="notice" class:warning={actionFailed} class:ok={!actionFailed} role="status">
      <p>{actionStatus}</p>
      {#if savedPath && !actionFailed}<p class="mono path">{savedPath}</p>{/if}
    </div>
  {/if}

  <!-- Los botones no se desactivan mientras trabajan: un botón con foco que pasa a disabled
       lo pierde hacia el body y Escape deja de cerrar el diálogo. busy evita la repetición. -->
  <svelte:fragment slot="footer">
    <span class="foot-note">Stored only on this computer when you save it.</span>
    <div class="actions">
      <button type="button" class="btn is-ghost" on:click={() => void saveReport()} disabled={!!previewError}>Save report</button>
      <button type="button" class="btn is-primary" on:click={() => void copyReport()} disabled={!!previewError}>
        {busy ? "Working…" : "Copy report"}
      </button>
    </div>
  </svelte:fragment>
</ModalFrame>

<style>
  p {
    margin: 0;
  }

  .lead strong {
    color: var(--text-0);
    font-weight: 500;
  }

  .field {
    display: grid;
    gap: var(--space-2);
  }

  .field-label,
  h3 {
    margin: 0;
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 400;
    letter-spacing: 0;
    text-transform: var(--label-case);
  }

  textarea {
    resize: vertical;
    min-height: 5rem;
    font-family: var(--font-ui);
    font-size: var(--text-sm);
  }

  .field small {
    justify-self: end;
    color: var(--text-2);
    font-family: var(--font-num);
    font-size: var(--text-xs);
  }

  .excluded,
  .preview {
    display: grid;
    gap: var(--space-3);
  }

  .excluded ul {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding-left: var(--space-6);
    font-size: var(--text-sm);
  }

  .note,
  .foot-note {
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  pre {
    max-height: 16rem;
    margin: 0;
    padding: var(--space-4) var(--space-5);
    overflow: auto;
    border-radius: var(--panel-radius);
    background: var(--tint);
    color: var(--text-1);
    font-family: var(--font-num);
    font-size: var(--text-xs);
    line-height: var(--leading-snug);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .notice {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-4) var(--space-5);
    border-radius: var(--panel-radius);
    font-size: var(--text-sm);
  }

  .notice.ok {
    background: var(--tint);
    color: var(--text-0);
  }

  .notice.warning {
    background: var(--warning-soft);
    color: var(--warning);
  }

  .mono {
    font-family: var(--font-num);
  }

  .path {
    word-break: break-all;
  }

  .actions {
    display: flex;
    gap: var(--space-3);
  }

  button {
    font-family: var(--font-ui);
    font-size: var(--text-sm);
    font-weight: 500;
  }
</style>
