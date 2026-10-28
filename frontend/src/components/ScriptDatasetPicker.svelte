<script lang="ts">
  import { onMount } from "svelte";
  import { listScriptDatasets, searchScriptDatasets, previewScriptDataset,
    type ExportResearchScriptInputPayload, type ScriptDatasetDefinition,
    type ScriptDatasetSelection, type ScriptDatasetPreview } from "../lib/api/research-scripts";

  export let scriptId: string | null = null;
  export let disabled = false;
  export let onAdd: (payload: ExportResearchScriptInputPayload) => Promise<unknown>;
  let definitions: ScriptDatasetDefinition[] = [];
  let domain = "equity_history";
  let query = "";
  let rows: ScriptDatasetSelection[] = [];
  let selected = "";
  let filename = "equity_history.json";
  let timeframe = "1Y";
  let days = 756;
  let frequency: "daily" | "weekly" | "monthly" = "daily";
  let preview: ScriptDatasetPreview | null = null;
  let inspected: ExportResearchScriptInputPayload | null = null;
  let busy = false;
  let error = "";
  let warnings: string[] = [];
  let searched = false;
  let generation = 0;
  $: selection = rows[Number(selected)] ?? null;
  $: selectionKey = JSON.stringify([scriptId, domain, selected, timeframe, days, frequency]);
  $: if (selectionKey) { preview = null; inspected = null; }
  $: ranges = domain === "crypto_history" ? ["30D", "90D", "1Y"]
    : domain === "prediction_history" ? ["1d", "1w", "1m", "3m", "1y", "max"]
    : ["1M", "3M", "6M", "1Y"];

  onMount(async () => {
    try { definitions = await listScriptDatasets(); }
    catch { error = "Dataset catalog unavailable. External files and the Python editor remain available."; }
  });

  function changeDomain() {
    generation += 1; busy = false; rows = []; selected = ""; searched = false;
    preview = null; inspected = null; warnings = []; error = ""; query = "";
    filename = `${domain}.json`;
    timeframe = domain === "crypto_history" ? "30D" : domain === "prediction_history" ? "1m" : "1Y";
  }

  async function search() {
    const ticket = ++generation;
    busy = true; error = ""; preview = null; inspected = null;
    try {
      const result = await searchScriptDatasets(domain, query);
      if (ticket !== generation) return;
      rows = result.items; warnings = result.warnings; searched = true;
      selected = rows.length ? "0" : "";
      if (result.status === "unavailable") error = "Discovery unavailable. Check provider status and retry.";
    } catch { if (ticket === generation) error = "Dataset search failed. Retry; existing inputs are unchanged."; }
    finally { if (ticket === generation) busy = false; }
  }

  function payload(): ExportResearchScriptInputPayload {
    return { domain, object_id: selection!.object_id, logical_filename: filename,
      region: selection?.region, outcome_id: selection?.outcome_id,
      timeframe: ["macro_series", "crypto_history", "prediction_history"].includes(domain) ? timeframe : undefined,
      lookback_days: domain === "equity_history" ? days : undefined,
      frequency: domain === "equity_history" ? frequency : undefined };
  }

  async function inspect() {
    if (!scriptId || !selection) return;
    const ticket = ++generation;
    const key = selectionKey;
    busy = true; error = ""; preview = null; inspected = null;
    const request = payload();
    try {
      const result = await previewScriptDataset(scriptId, request);
      if (ticket === generation && key === selectionKey) { preview = result; inspected = request; }
    } catch (e) { if (ticket === generation) error = e instanceof Error ? e.message : "Dataset preview unavailable."; }
    finally { if (ticket === generation) busy = false; }
  }

  async function add() {
    if (!preview || !inspected) return;
    busy = true;
    try { await onAdd({ ...inspected, logical_filename: filename, preview_id: preview.preview_id }); }
    finally { busy = false; }
  }
</script>

<section class="picker" aria-label="Gamma dataset catalog">
  <label>Gamma dataset
    <select class="form-control" aria-label="Gamma export domain" bind:value={domain} on:change={changeDomain} disabled={busy}>
      {#each definitions as item}<option value={item.domain}>{item.label}</option>{/each}
    </select>
  </label>
  <form on:submit|preventDefault={search} class="search-row">
    <label>Search datasets<input class="form-control" aria-label="Search datasets" bind:value={query} maxlength="128" placeholder="Name or symbol" /></label>
    <button class="btn is-ghost" disabled={busy} type="submit">{busy ? "Loading…" : "Search"}</button>
  </form>
  {#if rows.length}
    <label>Dataset
      <select class="form-control" aria-label="Dataset" bind:value={selected} disabled={busy}>
        {#each rows as item, index}<option value={String(index)}>{item.label}</option>{/each}
      </select>
    </label>
    <div class="controls">
      {#if domain === "equity_history"}
        <label>Lookback days<input class="form-control" aria-label="Lookback days" type="number" min="20" max="3650" bind:value={days} disabled={busy} /></label>
        <label>Frequency<select class="form-control" bind:value={frequency} disabled={busy}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
      {:else if ["macro_series", "crypto_history", "prediction_history"].includes(domain)}
        <label>Timeframe<select class="form-control" aria-label="Dataset timeframe" bind:value={timeframe} disabled={busy}>{#each ranges as range}<option value={range}>{range}</option>{/each}</select></label>
      {/if}
    </div>
    <button class="btn is-ghost" on:click={inspect} disabled={disabled || busy || !selection}>Inspect dataset</button>
  {:else if searched && !error}<p role="status">No matching datasets. Try another search or add an external file.</p>{/if}
  {#if error}<p class="warning" role="alert">{error}</p>{/if}
  {#if warnings.length}<details><summary>Discovery warnings ({warnings.length})</summary>{#each warnings as warning}<p>{warning}</p>{/each}</details>{/if}
  {#if preview}
    <div class="preview" aria-label="Dataset schema and coverage">
      <p>{preview.byte_size.toLocaleString()} B · {preview.states.join(" · ") || "Freshness unknown"}</p>
      <p>Coverage: {preview.coverage_start ?? "Not specified"} → {preview.coverage_end ?? "Not specified"}</p>
      <p>Frequency: {preview.frequencies.join(", ") || "Snapshot / field-specific"}</p>
      <p>Units: {preview.units.join(", ") || "Field-specific / unspecified"}</p>
      <details><summary>Fields &amp; source ({preview.fields.length} fields)</summary>
        <p>Source: {preview.sources.join(", ") || "Unknown"}</p>
        <p>Retrieved: {preview.retrieval_times.join(", ") || "Unavailable"}</p>
        <p>Cache: {preview.cache_status === "cached" ? "Cached" : "Not reported by owning service"}</p>
        <p>{preview.field_notes}</p>
        <p>SHA256: {preview.sha256}</p>
        <div class="schema"><table class="data-table is-compact"><thead><tr><th>Field</th><th>Type / unit</th></tr></thead><tbody>
          {#each preview.fields as field}<tr><td>{field.name}</td><td>{field.type}{field.unit ? ` / ${field.unit}` : ""}</td></tr>{/each}
        </tbody></table></div>
      </details>
      {#each preview.warnings as warning}<p class="warning">{warning}</p>{/each}
      <label>Snapshot filename<input class="form-control" aria-label="Snapshot filename" bind:value={filename} /></label>
      <button class="btn is-ghost" on:click={add} disabled={disabled || busy || !filename.endsWith(".json")}>Add Gamma dataset</button>
      <p>Preview retained for 10 minutes. Add copies these exact inspected bytes.</p>
    </div>
  {/if}
  <details><summary>Coverage &amp; limitations</summary><p>{definitions.find((d) => d.domain === domain)?.limitations ?? "Catalog unavailable."}</p><p>Unsupported data is not synthesized. Provider failures leave your existing bundle intact.</p></details>
</section>

<style>
  .picker, label, .preview { display: grid; gap: var(--space-3); min-width: 0; }
  .picker { gap: var(--space-4); }
  label, p, summary { font-size: var(--text-xs); }
  label, summary { font-family: var(--display-font); color: var(--text-2); }
  p { margin: 0; color: var(--text-2); overflow-wrap: anywhere; line-height: var(--leading-normal); }
  /* Fields are .form-control and buttons .btn.is-ghost from primitives.css;
     `font: inherit` is left for V2. */
  input, select, button { min-width: 0; max-width: 100%; font: inherit; }
  input, select { width: 100%; box-sizing: border-box; }
  summary { cursor: pointer; }
  summary:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
  .search-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-3); align-items: end; }
  .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr)); gap: var(--space-3); }
  .preview { border-block: 1px solid var(--divider); padding-block: var(--space-4); }
  .schema { max-height: 18rem; overflow: auto; }
  /* Cells and header come from .data-table.is-compact in primitives.css. */
  .data-table td { font-size: var(--text-xs); overflow-wrap: anywhere; }
  summary { color: var(--accent); }
  .warning { color: var(--warning); }
</style>
