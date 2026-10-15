<script lang="ts">
  import { onDestroy } from "svelte";
  import { inspectScriptAnalytics, openScriptAnalytics, type ScriptAnalyticalReport, type ScriptAnalyticalItem } from "../lib/api/research-scripts";
  import type { StrategyLabResult } from "../lib/api/types";
  import { getJson } from "../lib/api/client";

  export let runId: string | null;
  export let onOpen: ((result: StrategyLabResult) => void) | undefined = undefined;
  let report: ScriptAnalyticalReport | null = null;
  let busy = false;
  let error = "";
  let disposed = false;
  let contract: { example_source: string; [key: string]: unknown } | null = null;
  async function inspectContract() {
    try { const value = await getJson<{ example_source: string; [key: string]: unknown }>("/research/strategy-lab/scripts/analytical-contract"); if (!disposed) contract = value; }
    catch (e) { if (!disposed) error = e instanceof Error ? e.message : String(e); }
  }
  onDestroy(() => { disposed = true; });

  async function inspect() {
    if (busy || !runId) return;
    busy = true; error = "";
    try {
      const next = await inspectScriptAnalytics(runId);
      if (!disposed) report = next;
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
    <button type="button" on:click={() => void inspectContract()}>Inspect exact v1 JSON schema</button>
    {#if contract}
      <p>Ordinary top-level Python example · adapt identities, meaning and calculations to your research.</p>
      <pre>{contract.example_source}</pre>
      <details><summary>Full JSON schema and limits</summary><pre>{JSON.stringify(contract, null, 2)}</pre></details>
    {/if}
  </details>
  <button type="button" on:click={() => void inspect()} disabled={busy || !runId}>{busy ? "Validating…" : "Inspect analytical output"}</button>
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
          <button type="button" disabled={busy || !item.can_open || !onOpen} on:click={() => void open(artifact.output_id, item)}>Open temporary Strategy Lab analysis</button>
        {/each}
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
  button { min-height: 28px; white-space: normal; background: var(--bg-1); border: 1px solid var(--panel-strong); border-radius: var(--radius-sm); color: var(--text-0); padding: var(--space-2) var(--space-4); font-size: var(--text-sm); cursor: pointer; }
  button:disabled { color: var(--text-2); cursor: default; }
  :focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
