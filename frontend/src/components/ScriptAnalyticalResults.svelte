<script lang="ts">
  import { onDestroy } from "svelte";
  import {
    DEFAULT_BOOK_OPTIONS,
    inspectScriptAnalytics,
    openScriptAnalytics,
    type ScriptAnalyticalItem,
    type ScriptAnalyticalReport,
    type ScriptBookOptions,
    type ScriptWeightBook
  } from "../lib/api/research-scripts";
  import type { StrategyLabResult } from "../lib/api/types";
  import { getJson } from "../lib/api/client";

  export let runId: string | null;
  export let onOpen: ((result: StrategyLabResult) => void) | undefined = undefined;
  let report: ScriptAnalyticalReport | null = null;
  let busy = false;
  let error = "";
  let disposed = false;
  // Las opciones del libro forman parte del hash de la vista previa: se abre con las inspeccionadas.
  let bookOptions: ScriptBookOptions = { ...DEFAULT_BOOK_OPTIONS };
  let inspectedOptions: ScriptBookOptions | null = null;
  $: optionsDirty = Boolean(inspectedOptions) && (inspectedOptions?.execution_lag !== bookOptions.execution_lag || inspectedOptions?.cost_bps !== bookOptions.cost_bps);
  const pct = (value: number | null | undefined, digits = 2) =>
    typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
  function setOption(key: keyof ScriptBookOptions, event: Event) {
    const value = Number((event.currentTarget as HTMLInputElement).value);
    if (Number.isFinite(value)) bookOptions = { ...bookOptions, [key]: value };
  }
  let contract: { example_source: string; [key: string]: unknown } | null = null;
  async function inspectContract() {
    try { const value = await getJson<{ example_source: string; [key: string]: unknown }>("/research/strategy-lab/scripts/analytical-contract"); if (!disposed) contract = value; }
    catch (e) { if (!disposed) error = e instanceof Error ? e.message : String(e); }
  }
  onDestroy(() => { disposed = true; });

  async function inspect() {
    if (busy || !runId) return;
    busy = true; error = "";
    const options = { ...bookOptions };
    try {
      const next = await inspectScriptAnalytics(runId, options);
      if (!disposed) { report = next; inspectedOptions = options; }
    } catch (e) { if (!disposed) error = e instanceof Error ? e.message : String(e); }
    finally { if (!disposed) busy = false; }
  }

  async function openBook(outputId: string, book: ScriptWeightBook) {
    if (busy || !runId || !book.can_open || !onOpen || !inspectedOptions || optionsDirty) return;
    busy = true; error = "";
    try {
      const result = await openScriptAnalytics(runId, outputId, book.book_id, book.preview_sha256, inspectedOptions);
      if (!disposed) onOpen?.(result);
    } catch (e) { if (!disposed) error = e instanceof Error ? e.message : String(e); }
    finally { if (!disposed) busy = false; }
  }

  async function open(outputId: string, item: ScriptAnalyticalItem) {
    if (busy || !runId || !item.can_open || !onOpen) return;
    busy = true; error = "";
    try {
      const result = await openScriptAnalytics(runId, outputId, item.result.result_id, item.preview_sha256);
      if (!disposed) onOpen?.(result);
    } catch (e) { if (!disposed) error = e instanceof Error ? e.message : String(e); }
    finally { if (!disposed) busy = false; }
  }
</script>

<article class="panel">
  <h3>Optional analytical results</h3>
  <p>Inspect retained <code>gamma_analytics.json</code> from this run. Ordinary logs and files remain complete outcomes.</p>
  <details>
    <summary>Python output convention · v1</summary>
    <p>Use top-level Python and the standard <code>json</code> module to write <code>gamma_analytics.json</code> in the working directory. No Gamma imports or helper are required.</p>
    <p>Contract: <code>gamma-script-analytics.v1</code>. Specify exact instruments, meaning, methodology, assumptions, limitations and explicit units. See <code>docs/script_analytical_results.md</code> for the inspectable contract and complete example.</p>
    <button type="button" class="btn" on:click={() => void inspectContract()}>Inspect exact v1 JSON schema</button>
    {#if contract}
      <p>Ordinary top-level Python example · adapt identities, meaning and calculations to your research.</p>
      <pre>{contract.example_source}</pre>
      <details><summary>Full JSON schema and limits</summary><pre>{JSON.stringify(contract, null, 2)}</pre></details>
    {/if}
  </details>
  <button type="button" class="btn" on:click={() => void inspect()} disabled={busy || !runId}>{busy ? "Validating…" : "Inspect analytical output"}</button>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if report}
    <p>Execution: {report.execution_status} · {report.executes_source ? "Python runtime" : "non-executing preview"}</p>
    {#if !report.artifacts.length}<p>No optional analytical file retained. Standalone outputs are available in the output list.</p>{/if}
    {#each report.artifacts as artifact}
      <section>
        <p>{artifact.valid ? "Valid analytical contract" : "Invalid optional output"} · {artifact.eligible ? "executed run" : "handoff unavailable"}</p>
        {#each artifact.errors as message}<p role="alert">{message}</p>{/each}
        {#each artifact.warnings as warning}<p>{warning}</p>{/each}
        {#each artifact.results as item}
          <h4>{item.result.name} · {item.result.kind}</h4>
          <p>{item.result.meaning}</p>
          {#if item.unsupported_reason}<p>{item.unsupported_reason}</p>{/if}
          <details>
            <summary>Inspect exact result, mapping, coverage and assumptions</summary>
            <pre>{JSON.stringify({ result: item.result, mapping: item.mapping, provenance: artifact.provenance, instruments: artifact.instruments }, null, 2)}</pre>
          </details>
          <button type="button" class="btn" disabled={busy || !item.can_open || !onOpen} on:click={() => void open(artifact.output_id, item)}>Open temporary Strategy Lab analysis</button>
        {/each}
        {#if artifact.weight_book}
          {@const book = artifact.weight_book}
          <div class="book" aria-label="Causal weight book">
            <h4>Causal weight book · {book.instruments.length} instrument{book.instruments.length === 1 ? "" : "s"}</h4>
            <p>Gamma turns the signed NAV weight schedules ({book.weight_result_ids.join(", ")}) and each instrument's daily simple returns ({book.return_result_ids.join(", ") || "none"}) into one return stream: decisions apply only from a later period, holdings drift between decisions, residual cash earns 0% and weights are never normalized.</p>
            <div class="book-options">
              <label><span>Execution lag (periods)</span>
                <input class="form-control" type="number" aria-label="Book execution lag in periods" min="1" max="5" step="1" value={bookOptions.execution_lag} on:change={(event) => setOption("execution_lag", event)} disabled={busy} /></label>
              <label><span>Cost (bps per unit turnover)</span>
                <input class="form-control" type="number" aria-label="Book cost in basis points per unit turnover" min="0" max="1000" step="0.5" value={bookOptions.cost_bps} on:change={(event) => setOption("cost_bps", event)} disabled={busy} /></label>
              <button type="button" class="btn" on:click={() => void inspect()} disabled={busy || !optionsDirty}>Apply</button>
            </div>
            {#if optionsDirty}<p role="status">Options changed: apply them to recompute the exact book before opening it.</p>{/if}
            {#if book.unsupported_reason}<p class="reason">{book.unsupported_reason}</p>{/if}
            {#if book.mapping}
              {@const details = book.mapping.details}
              <dl class="book-summary">
                <div><dt>Book returns</dt><dd>{book.mapping.rows.length} · {book.mapping.rows[0]?.date ?? "—"} → {book.mapping.rows[book.mapping.rows.length - 1]?.date ?? "—"}</dd></div>
                <div><dt>Common calendar</dt><dd>{details.calendar_start} → {details.calendar_end}</dd></div>
                <div><dt>Rebalances</dt><dd>{details.rebalances.length}{details.superseded_decisions.length ? ` · ${details.superseded_decisions.length} superseded` : ""}{details.ignored_decisions.length ? ` · ${details.ignored_decisions.length} after data end` : ""}</dd></div>
                <div><dt>Turnover / cost drag</dt><dd>{details.total_turnover.toFixed(2)}× · {pct(details.total_cost_fraction, 3)}</dd></div>
                <div><dt>Max gross exposure</dt><dd>{pct(details.max_gross_exposure, 0)}</dd></div>
              </dl>
              {#each details.warnings as warning}<p class="reason">{warning}</p>{/each}
              <details>
                <summary>Inspect assumptions, rebalances and exact book rows</summary>
                <ul>{#each book.mapping.assumptions as assumption}<li>{assumption}</li>{/each}</ul>
                <pre>{JSON.stringify({ options: book.options, rebalances: details.rebalances.slice(0, 50), rows: book.mapping.rows }, null, 2)}</pre>
              </details>
            {/if}
            <button type="button" class="btn" disabled={busy || !book.can_open || !onOpen || optionsDirty} on:click={() => void openBook(artifact.output_id, book)}>Open causal book in Strategy Lab</button>
          </div>
        {/if}
      </section>
    {/each}
    <p>Opening performs no save. Use Save Strategy in the derived analysis to retain a research object separately.</p>
  {/if}
</article>

<style>
  .panel { background: var(--panel-bg); border: 1px solid var(--panel-border); border-radius: var(--radius-md); padding: var(--space-5); min-width: 0; display: grid; gap: var(--space-4); }
  h3, h4, summary, button { font-family: var(--display-font); }
  h3, h4, p { margin: 0; }
  h3 { font-size: var(--text-md); } h4 { font-size: var(--text-sm); }
  p { font-size: var(--text-xs); line-height: var(--leading-normal); color: var(--text-1); overflow-wrap: anywhere; }
  section { display: grid; gap: var(--space-4); border-top: 1px solid var(--divider); padding-top: var(--space-4); }
  details { min-width: 0; } summary { cursor: pointer; font-size: var(--text-xs); }
  pre { max-height: 320px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: var(--text-xs); }
  .book { display: grid; gap: var(--space-3); border: 1px solid var(--panel-strong); padding: var(--space-4); min-width: 0; }
  .book-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: var(--space-3); align-items: end; }
  .book-options label { display: grid; gap: var(--space-2); min-width: 0; }
  .book-options span, dt { color: var(--text-2); font-size: var(--text-2xs); letter-spacing: 0.1em; text-transform: uppercase; }
  .book-options input { width: 100%; min-height: 28px; border: 1px solid var(--panel-strong); background: var(--bg-1); color: var(--text-0); padding: var(--space-2); font-family: var(--app-font); font-size: var(--text-xs); }
  .book-summary { display: grid; gap: 0; margin: 0; }
  .book-summary div { display: flex; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) 0; border-bottom: 1px solid var(--divider); }
  dd { margin: 0; color: var(--text-1); font-family: var(--app-font); font-size: var(--text-xs); text-align: right; overflow-wrap: anywhere; }
  .reason { color: var(--warning); }
  ul { margin: var(--space-2) 0; padding-left: var(--space-5); font-size: var(--text-xs); color: var(--text-1); line-height: var(--leading-normal); }
  /* Buttons and fields are .btn and .form-control from primitives.css. */
  button { white-space: normal; font-size: var(--text-sm); }
  :focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
