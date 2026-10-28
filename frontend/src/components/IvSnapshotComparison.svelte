<script lang="ts">
  import type { IvSurface } from "../lib/api/types";
  import { captureIvSnapshot, compareIvSnapshots, listIvSnapshots, readIvSnapshot,
    type IvSnapshot, type IvSnapshotSummary } from "../lib/iv-snapshots";
  export let surface: IvSurface | null = null;
  export let symbol = "";
  let activeSymbol = "";
  let snapshots: IvSnapshotSummary[] = [];
  let beforeId = "", afterId = "";
  let before: IvSnapshot | null = null, after: IvSnapshot | null = null;
  let listLoading = false, readLoading = false, saving = false, error = "", notice = "";
  let reloadVersion = 0;
  let storageWarnings: string[] = [];
  let listGeneration = 0, readGeneration = 0;
  $: normalizedSymbol = symbol.trim().toUpperCase();
  $: if (normalizedSymbol !== activeSymbol) {
    activeSymbol = normalizedSymbol;
    void refresh(normalizedSymbol, true);
  }
  $: void loadSelection(beforeId, afterId, reloadVersion);
  $: loading = listLoading || readLoading;
  $: comparison = compareIvSnapshots(before?.surface ?? null, after?.surface ?? null);
  const percent = (value: number | null | undefined) => value == null ? "N/A" : `${(value * 100).toFixed(2)}%`;
  const change = (value: number | null | undefined) => value == null ? "N/A" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)} pp`;
  const time = (value: string) => new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).toLocaleString();
  const label = (row: IvSnapshotSummary) => `${time(row.timestamp)} · ${row.source_provider} · ${row.freshness_label}`;

  async function refresh(target: string, reset = false) {
    const generation = ++listGeneration;
    if (reset) { snapshots = []; beforeId = afterId = ""; before = after = null; notice = ""; storageWarnings = []; }
    if (!target) { listLoading = false; return; }
    listLoading = true; error = "";
    try {
      const response = await listIvSnapshots(target);
      if (generation !== listGeneration) return;
      snapshots = response.snapshots; storageWarnings = response.warnings;
      afterId = snapshots.some((s) => s.snapshot_id === afterId) ? afterId : snapshots[0]?.snapshot_id ?? "";
      beforeId = snapshots.some((s) => s.snapshot_id === beforeId) ? beforeId : snapshots[1]?.snapshot_id ?? "";
      reloadVersion += 1;
    } catch (e) { if (generation === listGeneration) error = e instanceof Error ? e.message : "Could not load Options captures."; }
    finally { if (generation === listGeneration) listLoading = false; }
  }
  async function loadSelection(oldId: string, newId: string, _reloadVersion: number) {
    const generation = ++readGeneration;
    before = after = null;
    if (!oldId || !newId) { readLoading = false; return; }
    readLoading = true; error = "";
    try {
      const [oldCapture, newCapture] = await Promise.all([readIvSnapshot(oldId), readIvSnapshot(newId)]);
      if (generation === readGeneration && oldCapture.surface.symbol === activeSymbol && newCapture.surface.symbol === activeSymbol) { before = oldCapture; after = newCapture; }
    } catch (e) { if (generation === readGeneration) error = e instanceof Error ? e.message : "Could not read Options captures."; }
    finally { if (generation === readGeneration) readLoading = false; }
  }
  async function capture() {
    if (!surface?.snapshot_available || surface.symbol !== activeSymbol || saving) return;
    const target = activeSymbol, frozen = surface;
    saving = true; error = ""; notice = "";
    try {
      const capture = await captureIvSnapshot(frozen);
      if (target !== activeSymbol) return;
      beforeId = afterId; afterId = capture.snapshot_id;
      await refresh(target);
      notice = `Captured ${target}. Saved locally across restarts.`;
    } catch (e) { if (target === activeSymbol) error = e instanceof Error ? e.message : "Could not save Options capture."; }
    finally { saving = false; }
  }
</script>

<article class="snapshot-panel" aria-label="Options snapshot comparison">
  <div class="controls">
    <h3>Snapshot comparison</h3>
    <button class="btn" on:click={capture} disabled={saving || !surface?.snapshot_available || !surface.points || surface.symbol !== activeSymbol}>{saving ? "Capturing…" : "Capture displayed surface"}</button>
    <button class="btn" on:click={() => refresh(activeSymbol)} disabled={loading || saving || !activeSymbol}>Reload captures</button>
  </div>
  <div class="selectors">
    <label>Baseline<select class="form-control" bind:value={beforeId} disabled={!snapshots.length}><option value="">Select capture</option>{#each snapshots as row}<option value={row.snapshot_id}>{label(row)}</option>{/each}</select></label>
    <label>Comparison<select class="form-control" bind:value={afterId} disabled={!snapshots.length}><option value="">Select capture</option>{#each snapshots as row}<option value={row.snapshot_id}>{label(row)}</option>{/each}</select></label>
  </div>
  {#if error}<p role="alert">{error} Use Reload captures to retry.</p>{/if}
  {#if notice}<p role="status">{notice}</p>{/if}
  {#if loading}<p role="status">Loading captures…</p>
  {:else if !before || !after}<p>Capture two {activeSymbol || "underlying"} surfaces to compare them. History starts with your first capture.</p>{/if}
  {#if before && after}
    <p>Observed IV only. The baseline’s nearest-to-spot strike and outer observed wings are held fixed. Changes are percentage points; expiry dates stay fixed as time to expiry falls.</p>
    {#if beforeId === afterId}<p>Both selectors use the same capture.</p>{/if}
    {#if new Date(before.captured_at) > new Date(after.captured_at)}<p>Comparison was captured before the baseline; changes follow the selected direction.</p>{/if}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users must be able to focus and scroll this wide evidence table.) -->
    <div class="table-scroll" tabindex="0" role="region" aria-label="IV and skew changes by expiry">
      <table class="data-table is-figures is-nowrap">
        <thead><tr><th>Expiry</th><th>ATM reference strike</th><th>Baseline IV</th><th>Comparison IV</th><th>IV change</th><th>Put wing</th><th>Put skew: baseline → comparison (change)</th><th>Call wing</th><th>Call skew: baseline → comparison (change)</th></tr></thead>
        <tbody>{#each comparison.rows as row}<tr><td>{row.expiry}</td><td>{row.strike ?? "N/A"}</td><td>{percent(row.before)}</td><td>{percent(row.after)}</td><td>{change(row.change)}</td><td>{row.putStrike ?? "N/A"}</td><td>{percent(row.putSkewBefore)} → {percent(row.putSkewAfter)} ({change(row.putSkewChange)})</td><td>{row.callStrike ?? "N/A"}</td><td>{percent(row.callSkewBefore)} → {percent(row.callSkewAfter)} ({change(row.callSkewChange)})</td></tr>{/each}</tbody>
      </table>
    </div>
    <details><summary>Capture evidence and pricing assumptions</summary>
      <div class="evidence">
        {#each [{ title: "Baseline", capture: before }, { title: "Comparison", capture: after }] as item}
          <div><h4>{item.title}</h4><p>Surface: {time(item.capture.surface.timestamp)} · Captured: {time(item.capture.captured_at)}</p>
            <p>{item.capture.surface.source_provider} · {item.capture.surface.freshness_label} at capture · {item.capture.surface.delayed ? "Delayed" : "Not marked delayed"} · Spot {item.capture.surface.spot ?? "N/A"}</p>
            <p>{item.capture.surface.quality?.observed_surface_cells ?? "N/A"} observed cells · {item.capture.surface.quality?.interpolated_surface_cells ?? "N/A"} fitted/interpolated cells · {item.capture.surface.surface_model_label ?? "N/A"} ({item.capture.surface.surface_model_status ?? "N/A"})</p>
            <p>Rate {percent(item.capture.surface.pricing_assumptions?.risk_free_rate)} · Dividend yield {percent(item.capture.surface.pricing_assumptions?.dividend_yield)}</p>
            <p>{item.capture.surface.collection?.market_data_mode ?? "Unknown market-data mode"} · {item.capture.surface.collection?.depth_preset ?? "Unknown collection depth"} · {item.capture.surface.quality?.contracts_with_provider_greeks ?? "N/A"} provider Greeks / {item.capture.surface.quality?.contracts_with_derived_greeks ?? "N/A"} derived Greeks</p>
            {#if item.capture.surface.pricing_assumptions?.fallback_greeks_methodology}<p>{item.capture.surface.pricing_assumptions.fallback_greeks_methodology}</p>{/if}
            {#if item.capture.surface.transformation_note}<p>{item.capture.surface.transformation_note}</p>{/if}
            {#each [...item.capture.surface.warnings, ...item.capture.surface.messages, ...(item.capture.surface.surface_model_notes ?? []), ...(item.capture.surface.pricing_assumptions?.notes ?? [])] as warning}<p>{warning}</p>{/each}
          </div>
        {/each}
      </div>
    </details>
  {/if}
  {#each [...storageWarnings, ...comparison.warnings] as warning}<p>{warning}</p>{/each}
</article>

<style>
  .snapshot-panel { background: var(--panel-bg); border: 1px solid var(--panel-border); border-radius: var(--radius-md); min-width: 0; }
  .controls, .selectors { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4); padding: var(--space-5); }
  h3 { margin: 0; font-size: var(--text-md); margin-right: auto; }
  /* Controls are .btn and .form-control from primitives.css. */
  label { display: grid; gap: var(--space-2); flex: 1 1 260px; min-width: 0; font-family: var(--font-label); font-size: var(--text-sm); }
  select { width: 100%; min-width: 0; font-family: var(--font-num), monospace; }
  p { margin: 0; padding: var(--space-3) var(--space-5); color: var(--text-1); font-size: var(--text-sm); overflow-wrap: anywhere; }
  .table-scroll { overflow-x: auto; }
  /* Cells come from .data-table.is-figures.is-nowrap in primitives.css. */
  details { border-top: 1px solid var(--divider); padding: var(--space-5); }
  summary { cursor: pointer; font-family: var(--font-ui); }
  .evidence { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: var(--space-4); }
  .evidence p { padding-left: 0; padding-right: 0; }
  h4 { margin: var(--space-4) 0; }
</style>
