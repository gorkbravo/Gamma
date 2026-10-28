<script lang="ts">
  import { onMount } from "svelte";
  import { deleteJson, getJson, postJson } from "../lib/api/client";
  import type { CommodityInstrument, CommodityCurveSnapshot, CommodityCoverageMetadata } from "../lib/api/types";
  import { captureLabel, curveNodeQuality, commodityCaptureTime, spreadPointNote, type CommodityCurveCapture, type CommodityCurveComparison,
    type CommodityCalendarSpread, type CommoditySpreadHistory, type CommodityCapturePayload } from "../lib/commodity-captures";

  export let instrumentId: string;
  export let instrument: CommodityInstrument | null = null;
  export let curve: CommodityCurveSnapshot | null = null;
  export let coverage: CommodityCoverageMetadata | null = null;
  export let providerLoading = false;
  let captures: CommodityCurveCapture[] = [], spreads: CommodityCalendarSpread[] = [];
  let baselineId = "", comparisonId = "", leftId = "", rightId = "", spreadId = "", spreadLabel = "";
  let retained: CommodityCurveCapture | null = null, comparison: CommodityCurveComparison | null = null;
  let history: CommoditySpreadHistory | null = null;
  let busy = false, error = "", notice = "", warnings: string[] = [];
  // Borrado en dos pasos: el primer clic arma la confirmación para ese registro concreto.
  let pendingDelete: { kind: "capture" | "spread"; id: string } | null = null;
  const number = (value: number | null | undefined) => value == null ? "N/A" : value.toFixed(3);
  const date = commodityCaptureTime;
  const status = (value: string) => value.replaceAll("_", " ");
  $: canCapture = instrument && curve && coverage && curve.nodes.some(node => node.price != null);
  $: retainedNodes = retained?.payload.curve.nodes ?? [];
  function clearComparison() { comparison = null; }
  function changeComparisonCapture() { comparison = null; retained = null; notice = ""; leftId = ""; rightId = ""; }
  async function run(work: () => Promise<void>) {
    if (busy) return;
    busy = true; error = "";
    try { await work(); } catch (e) { error = e instanceof Error ? e.message : "Commodity history request failed. Retry the action."; }
    finally { busy = false; }
  }
  async function load() {
    const results = await Promise.all([
      getJson<{ captures: CommodityCurveCapture[]; warnings: string[] }>(`/commodities/curve-captures?instrument_id=${encodeURIComponent(instrumentId)}`),
      getJson<{ spreads: CommodityCalendarSpread[]; warnings: string[] }>(`/commodities/calendar-spreads?instrument_id=${encodeURIComponent(instrumentId)}`)
    ]);
    captures = results[0].captures; spreads = results[1].spreads; warnings = [...results[0].warnings, ...results[1].warnings];
    if (!comparisonId) comparisonId = captures[0]?.id ?? "";
    if (!baselineId) baselineId = captures[1]?.id ?? captures[0]?.id ?? "";
    if (!spreadId) spreadId = spreads[0]?.id ?? "";
    if (history && spreadId) history = await getJson<CommoditySpreadHistory>(`/commodities/calendar-spreads/${spreadId}/history`);
  }
  onMount(() => { void run(load); });
  async function saveCapture() {
    if (!instrument || !curve || !coverage) return;
    const payload: CommodityCapturePayload = JSON.parse(JSON.stringify({ instrument, curve, coverage }));
    await run(async () => {
      const saved = await postJson<CommodityCurveCapture>("/commodities/curve-captures", payload);
      baselineId = comparisonId || saved.id; comparisonId = saved.id; comparison = null;
      adopt(saved);
      await load();
      notice = `Saved ${saved.payload.instrument.symbol} curve with ${saved.payload.curve.nodes.length} exact contracts. Captured observations are not settlement history.`;
    });
  }
  function adopt(capture: CommodityCurveCapture) {
    retained = capture; leftId = capture.payload.curve.nodes[0]?.contract.contract_id ?? "";
    rightId = capture.payload.curve.nodes[1]?.contract.contract_id ?? "";
  }
  async function reopen() { await run(async () => {
    const record = await getJson<CommodityCurveCapture>(`/commodities/curve-captures/${comparisonId}`);
    adopt(record); notice = "Reopened retained curve. Prices, contract identities and provider evidence are from this capture.";
  }); }
  async function compare() { await run(async () => {
    comparison = await postJson<CommodityCurveComparison>("/commodities/curve-captures/compare", { baseline_id: baselineId, comparison_id: comparisonId });
  }); }
  async function trackSpread() { await run(async () => {
    const spread = await postJson<CommodityCalendarSpread>("/commodities/calendar-spreads", {
      capture_id: retained?.id, left_contract_id: leftId, right_contract_id: rightId, label: spreadLabel
    });
    await load(); spreadId = spread.id;
    history = await getJson<CommoditySpreadHistory>(`/commodities/calendar-spreads/${spread.id}/history`);
    notice = "Tracking the exact contract pair. Missing or expired contracts remain gaps in later captures.";
  }); }
  async function loadSpread() { await run(async () => {
    history = await getJson<CommoditySpreadHistory>(`/commodities/calendar-spreads/${spreadId}/history`);
  }); }
  const armed = (kind: "capture" | "spread", id: string) => pendingDelete?.kind === kind && pendingDelete.id === id;
  $: captureDeleteArmed = pendingDelete?.kind === "capture" && pendingDelete.id === comparisonId;
  $: spreadDeleteArmed = pendingDelete?.kind === "spread" && pendingDelete.id === spreadId;
  async function deleteRecord(kind: "capture" | "spread", id: string) {
    if (!id) return;
    if (!armed(kind, id)) { pendingDelete = { kind, id }; return; }
    pendingDelete = null;
    await run(async () => {
      await deleteJson(kind === "capture" ? `/commodities/curve-captures/${id}` : `/commodities/calendar-spreads/${id}`);
      if (kind === "capture") {
        if (retained?.id === id) retained = null;
        if (comparisonId === id) comparisonId = "";
        if (baselineId === id) baselineId = "";
        comparison = null;
      } else {
        if (spreadId === id) spreadId = "";
        history = null;
      }
      await load();
      notice = kind === "capture" ? "Deleted the retained curve capture." : "Deleted the calendar spread definition; its source captures remain.";
    });
  }
</script>

<article class="history-panel" aria-label="Commodity curve history">
  <header><h3>Saved curves & calendar spreads</h3><span aria-live="polite">{busy ? "Updating…" : `${captures.length} captures`}</span><button on:click={() => run(load)} disabled={busy}>Refresh Saved</button>
    <button on:click={saveCapture} disabled={busy || providerLoading || !canCapture}>Save Current Curve</button></header>
  {#if notice}<p role="status">{notice}</p>{/if}
  {#if error}<p role="alert">{error} Check the data or connection and retry.</p>{/if}
  {#each warnings as warning}<p class="warning">{warning}</p>{/each}
  <div class="controls">
    <label><span>Baseline capture</span><select aria-label="Baseline capture" bind:value={baselineId} on:change={clearComparison} disabled={busy}>
      <option value="">Select capture</option>{#each captures as capture}<option value={capture.id}>{captureLabel(capture)}</option>{/each}</select></label>
    <label><span>Comparison capture</span><select aria-label="Comparison capture" bind:value={comparisonId} on:change={changeComparisonCapture} disabled={busy}>
      <option value="">Select capture</option>{#each captures as capture}<option value={capture.id}>{captureLabel(capture)}</option>{/each}</select></label>
    <button on:click={reopen} disabled={busy || !comparisonId}>Reopen Capture</button>
    <button on:click={compare} disabled={busy || !baselineId || !comparisonId}>Compare Captures</button>
    <button on:click={() => deleteRecord("capture", comparisonId)} disabled={busy || !comparisonId}>{captureDeleteArmed ? "Confirm Delete Capture" : "Delete Capture"}</button>
  </div>
  {#if !captures.length}<p>{busy ? "Loading retained curves…" : "No saved curves for this instrument. Save the displayed curve to start a history."}</p>{/if}
  {#if comparison}
    <h4>Exact-contract changes · {comparison.unit} · {comparison.currency}</h4>
    <p>{date(comparison.baseline.payload.curve.as_of)} → {date(comparison.comparison.payload.curve.as_of)}</p>
    <div class="table-wrap"><table class="data-table is-figures is-nowrap"><thead><tr><th>Contract / ID</th><th>Month</th><th>Baseline</th><th>Comparison</th><th>Change</th><th>Coverage</th></tr></thead><tbody>
      {#each comparison.rows as row}<tr><td>{row.contract.symbol}<small>{row.contract_id}</small></td><td>{row.contract.contract_month}</td>
        <td title={curveNodeQuality(row.baseline)}>{number(row.baseline?.price)}</td><td title={curveNodeQuality(row.comparison)}>{number(row.comparison?.price)}</td>
        <td>{number(row.change)}</td><td>{status(row.status)}</td></tr>{/each}
    </tbody></table></div>
    {#each comparison.warnings as warning}<p>{warning}</p>{/each}
  {/if}
  {#if retained}
    <h4>Retained {retained.payload.instrument.symbol} curve · {retained.payload.instrument.quote_unit} · {retained.payload.instrument.currency}</h4>
    <p>Capture {retained.id.slice(0, 6)} · Observed {date(retained.payload.curve.as_of)} · Saved {date(retained.captured_at)} · {retained.payload.coverage.coverage_status} coverage</p>
    <div class="table-wrap"><table class="data-table is-figures is-nowrap"><thead><tr><th>Contract / ID</th><th>Month / Expiry</th><th>Price</th><th>Provider / Quality</th></tr></thead><tbody>
      {#each retainedNodes as node}<tr><td>{node.contract.symbol}<small>{node.contract.contract_id}{node.contract.is_front_month ? " · captured front" : ""}</small></td>
        <td>{node.contract.contract_month}<small>{node.contract.expiry_date?.slice(0, 10) ?? "Expiry unavailable"}</small></td><td>{number(node.price)}</td><td>{curveNodeQuality(node)}</td></tr>{/each}
    </tbody></table></div>
    <details><summary>Capture warnings and provenance</summary>
      <p>{retained.payload.curve.origin} · {retained.payload.coverage.freshness_label}</p>
      {#each [...retained.payload.curve.warnings, ...retained.payload.coverage.caveats] as warning}<p>{warning}</p>{/each}
    </details>
    <div class="controls">
      <label><span>Left contract</span><select aria-label="Left contract" bind:value={leftId} disabled={busy}>{#each retainedNodes as node}<option value={node.contract.contract_id}>{node.contract.symbol} · {node.contract.contract_month} · {node.contract.contract_id}</option>{/each}</select></label>
      <label><span>Right contract</span><select aria-label="Right contract" bind:value={rightId} disabled={busy}>{#each retainedNodes as node}<option value={node.contract.contract_id}>{node.contract.symbol} · {node.contract.contract_month} · {node.contract.contract_id}</option>{/each}</select></label>
      <label><span>Spread name</span><input bind:value={spreadLabel} maxlength="160" placeholder="Exact calendar pair" /></label>
      <button on:click={trackSpread} disabled={busy || !leftId || !rightId || leftId === rightId}>Track Calendar Spread</button>
    </div>
  {/if}
  <div class="controls">
    <label><span>Saved calendar spread</span><select aria-label="Saved calendar spread" bind:value={spreadId} on:change={() => history = null} disabled={busy}>
      <option value="">Select spread</option>{#each spreads as spread}<option value={spread.id}>{spread.payload.label}</option>{/each}</select></label>
    <button on:click={loadSpread} disabled={busy || !spreadId}>Load Spread History</button>
    <button on:click={() => deleteRecord("spread", spreadId)} disabled={busy || !spreadId}>{spreadDeleteArmed ? "Confirm Delete Spread" : "Delete Spread"}</button>
  </div>
  {#if history}
    <h4>{history.spread.payload.label} · Left − Right · {history.spread.payload.unit}</h4>
    <p>{history.spread.payload.left_contract.symbol} ({history.spread.payload.left_contract.contract_id}) − {history.spread.payload.right_contract.symbol} ({history.spread.payload.right_contract.contract_id})</p>
    <div class="table-wrap"><table class="data-table is-figures is-nowrap"><thead><tr><th>Observed / Saved</th><th>Left</th><th>Right</th><th>Spread</th><th>Coverage</th></tr></thead><tbody>
      {#each history.points as point}<tr><td>{date(point.as_of)}<small>{date(point.captured_at)}</small></td><td title={curveNodeQuality(point.left)}>{number(point.left?.price)}</td><td title={curveNodeQuality(point.right)}>{number(point.right?.price)}</td><td>{number(point.value)}</td><td title={spreadPointNote(point)}>{status(point.status)}{#if spreadPointNote(point)}<small>{spreadPointNote(point)}</small>{/if}</td></tr>{/each}
    </tbody></table></div>
    {#each history.warnings as warning}<p>{warning}</p>{/each}
  {/if}
</article>

<style>
  .history-panel { min-width: 0; font-family: var(--display-font); background: var(--panel-bg); border: 1px solid var(--panel-border); border-radius: var(--radius-md); }
  header, .controls { display: flex; flex-wrap: wrap; align-items: end; gap: var(--space-4); padding: var(--space-5); }
  header { align-items: center; border-bottom: 1px solid var(--divider); }
  h3 { font-size: var(--text-md); margin: 0 auto 0 0; } h4 { font-size: var(--text-sm); margin: 0; padding: var(--space-5); border-top: 1px solid var(--divider); }
  p { padding: var(--space-3) var(--space-5); margin: 0; color: var(--text-1); font-size: var(--text-sm); overflow-wrap: anywhere; }
  [role=alert], .warning { color: var(--warning); }
  label { display: grid; gap: var(--space-2); min-width: 0; flex: 1 1 220px; font-size: var(--text-sm); }
  button, input, select { min-height: 28px; color: var(--text-0); background: var(--bg-1); border: 1px solid var(--panel-strong); border-radius: var(--radius-sm); padding: var(--space-2) var(--space-4); font: inherit; }
  input, select { min-width: 0; width: 100%; box-sizing: border-box; } button:disabled { opacity: 0.5; }
  /* Cells come from .data-table.is-figures.is-nowrap in primitives.css; the
     last column here is a label (coverage, provider), so it reads left. */
  .table-wrap { overflow-x: auto; } table { font-family: var(--app-font), monospace; }
  th:last-child, td:last-child { text-align: left; }
  small { display: block; color: var(--text-2); font-size: var(--text-xs); }
  details { padding: var(--space-4) var(--space-5); font-size: var(--text-sm); } summary { cursor: pointer; }
</style>
