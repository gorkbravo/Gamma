<script lang="ts">
  import { apiInstantDate } from "../lib/time";
  import { onMount } from "svelte";

  import type { ResearchScriptRun } from "../lib/api/types";
  import type { ScriptParameters, ScriptSweep } from "../lib/api/research-scripts";
  import {
    createScriptSweep,
    evaluateSelectedSweep,
    loadScriptSweeps,
    parseSweepAxes,
    pendingSweepPoints,
    runSelectedWalkForward,
    runSweepPoints,
    scriptSweeps,
    selectScriptSweep,
    selectedSweep,
    stopSweepRun,
    updateSweepDraft,
    type ScriptSweepState
  } from "../lib/stores/script-sweeps";

  export let scriptId: string | null;
  export let revisionId: string | null;
  export let revisionNumber: number | null = null;
  export let inputSnapshotId: string | null;
  export let baseParameters: ScriptParameters | null;
  export let runs: ResearchScriptRun[] = [];
  export let disabled = false;
  /** Estado inyectado para pruebas; por defecto el store compartido. */
  export let snapshot: ScriptSweepState | null = null;

  // Solo en el navegador: el render del servidor (tests SSR) no debe llamar a la API.
  let mounted = false;
  onMount(() => { mounted = true; });
  $: state = snapshot ?? $scriptSweeps;
  $: if (mounted && !snapshot) void loadScriptSweeps(scriptId);
  $: sweep = selectedSweep(state);
  $: axes = parseSweepAxes(state.axesDraft);
  // Los ejes sustituyen a los parámetros de la ejecución con el mismo nombre; solo el resto queda fijo.
  $: fixedParameters = baseParameters && axes.ok
    ? Object.fromEntries(Object.entries(baseParameters).filter(([name]) => !axes.ok || !axes.axes.some((axis) => axis.name === name)))
    : baseParameters;
  $: pending = sweep ? pendingSweepPoints(sweep, runs) : [];
  $: busy = state.loading !== null;
  $: evaluation = state.evaluation?.sweep_id === sweep?.sweep_id ? state.evaluation : null;
  $: walk = state.walkForward?.sweep_id === sweep?.sweep_id ? state.walkForward : null;
  $: target = state.evaluationTarget;

  const short = (value: string | null | undefined) => (value ? value.slice(0, 12) : "—");
  const pct = (value: number | null | undefined, digits = 2) =>
    typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
  const num = (value: number | null | undefined, digits = 2) =>
    typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
  const tone = (value: number | null | undefined) =>
    typeof value === "number" && Number.isFinite(value) ? (value > 0 ? "positive" : value < 0 ? "negative" : "") : "";
  const params = (values: ScriptParameters | null | undefined) =>
    values && Object.keys(values).length ? Object.entries(values).map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(" · ") : "—";
  const axisValues = (item: ScriptSweep) => item.axes.map((axis) => `${axis.name}: ${axis.values.map((value) => JSON.stringify(value)).join(", ")}`).join(" × ");
  const metricLabel = (metric: string) => (metric === "sharpe" ? "Sharpe" : "Total return");
  const metricValue = (metric: string, value: number | null | undefined) => (metric === "sharpe" ? num(value) : pct(value));
  const stateLabel: Record<string, string> = {
    ready: "Ready", not_run: "Not run", run_failed: "Run failed", ineligible: "Not executed", invalid_output: "Invalid output",
    no_analytics: "No analytics file", result_missing: "Result missing", unsupported: "Unsupported", ambiguous: "Ambiguous",
    binding_mismatch: "Binding mismatch"
  };

  function create() {
    if (!scriptId || !revisionId || !inputSnapshotId) return;
    void createScriptSweep({ scriptId, revisionId, inputSnapshotId, baseParameters: baseParameters ?? {} });
  }

  function setTarget(patch: Partial<ScriptSweepState["evaluationTarget"]>) {
    updateSweepDraft({ evaluationTarget: { ...target, ...patch } });
  }

  function setWalk(patch: Partial<ScriptSweepState["walkForwardConfig"]>) {
    updateSweepDraft({ walkForwardConfig: { ...state.walkForwardConfig, ...patch } });
  }

  function numberFrom(event: Event, fallback: number) {
    const value = Number((event.currentTarget as HTMLInputElement).value);
    return Number.isFinite(value) ? value : fallback;
  }

  function exportWalkForward() {
    if (!walk) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(walk, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `gamma-walk-forward-${walk.sweep_id.slice(0, 12)}-${walk.report_sha256.slice(0, 12)}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }
</script>

<article class="panel sweep-panel" aria-labelledby="sweep-title">
  <div class="panel-header">
    <div>
      <p class="eyebrow">Parameters &amp; methodology</p>
      <h3 id="sweep-title">Parameter sweep &amp; walk-forward</h3>
    </div>
    {#if sweep}<span class="status">{sweep.points.length} points</span>{/if}
  </div>
  <p class="muted">
    A sweep runs one immutable revision on one input bundle; only <code>gamma_parameters.json</code> changes between points.
    Comparisons are in-sample and unranked. Walk-forward selects with past observations only and reports the out-of-sample result.
  </p>

  <div class="define-grid">
    <label class="axes-field">
      <span>Axes · one per line</span>
      <textarea class="form-control" rows="3" aria-label="Sweep axes" value={state.axesDraft} disabled={disabled || busy} spellcheck="false"
        aria-describedby="axes-help"
        on:input={(event) => updateSweepDraft({ axesDraft: (event.currentTarget as HTMLTextAreaElement).value })}></textarea>
      <small id="axes-help" class:invalid={!axes.ok}>
        {axes.ok ? `${axes.points} points · other run parameters stay fixed` : axes.error}
      </small>
    </label>
    <div class="binding">
      <div class="row"><span>Revision</span><strong>{revisionNumber ? `Rev ${revisionNumber}` : short(revisionId)}</strong></div>
      <div class="row"><span>Input bundle</span><strong>{short(inputSnapshotId)}</strong></div>
      <div class="row"><span>Fixed parameters</span><strong>{params(fixedParameters)}</strong></div>
      <button type="button" class="run-button btn is-ghost is-primary" on:click={create}
        disabled={disabled || busy || !axes.ok || !scriptId || !revisionId || !inputSnapshotId}>
        {state.loading === "create" ? "Creating…" : "Create sweep"}
      </button>
      {#if !inputSnapshotId}<p class="muted">Prepare an input bundle first; a sweep binds one exact bundle.</p>{/if}
    </div>
  </div>

  {#if state.sweeps.length}
    <label>
      <span>Sweep</span>
      <select class="form-control" aria-label="Selected sweep" value={state.selectedSweepId ?? ""} disabled={busy}
        on:change={(event) => selectScriptSweep((event.currentTarget as HTMLSelectElement).value)}>
        {#each state.sweeps as item}
          <option value={item.sweep_id}>{apiInstantDate(item.created_at)?.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} · {item.points.length} pts · {axisValues(item)}</option>
        {/each}
      </select>
    </label>
  {/if}

  {#if sweep}
    <div class="action-row">
      <span class="muted">{sweep.points.length - pending.length} / {sweep.points.length} points completed · definition {short(sweep.definition_sha256)}</span>
      <div class="buttons">
        {#if state.loading === "run"}
          <button type="button" class="btn is-ghost" on:click={stopSweepRun} disabled={state.stopRequested}>{state.stopRequested ? "Stopping after this point…" : "Stop after current point"}</button>
        {:else}
          <button type="button" class="run-button btn is-ghost is-primary" on:click={() => void runSweepPoints(pending)} disabled={disabled || busy || !pending.length}>
            Run {pending.length === sweep.points.length ? "all" : "remaining"} {pending.length} point{pending.length === 1 ? "" : "s"}
          </button>
          <button type="button" class="btn is-ghost" on:click={() => void runSweepPoints(sweep ? sweep.points.map((point) => point.index) : [])} disabled={disabled || busy || pending.length === sweep.points.length}>
            Rerun all
          </button>
        {/if}
      </div>
    </div>
    {#if state.progress}
      <div class="progress" role="status" aria-live="polite">
        <progress max={state.progress.total} value={state.progress.done}></progress>
        <span>Running point {state.progress.currentIndex} · {state.progress.done} / {state.progress.total} done</span>
      </div>
    {/if}

    <fieldset class="evaluation" disabled={busy}>
      <legend>Evaluate</legend>
      <label>
        <span>Return stream</span>
        <select class="form-control" aria-label="Evaluation target" value={target.target}
          on:change={(event) => setTarget({ target: (event.currentTarget as HTMLSelectElement).value as "weight_book" | "returns_result" })}>
          <option value="weight_book">Causal weight book (Gamma-enforced lag)</option>
          <option value="returns_result">Script returns result (author timing)</option>
        </select>
      </label>
      {#if target.target === "returns_result"}
        <label><span>result_id</span>
          <input class="form-control" aria-label="Returns result_id" value={target.result_id} placeholder="strategy" on:input={(event) => setTarget({ result_id: (event.currentTarget as HTMLInputElement).value })} /></label>
      {:else}
        <label><span>Execution lag (periods)</span>
          <input class="form-control" type="number" aria-label="Sweep execution lag in periods" min="1" max="5" step="1" value={target.execution_lag} on:change={(event) => setTarget({ execution_lag: numberFrom(event, 1) })} /></label>
        <label><span>Cost (bps / turnover)</span>
          <input class="form-control" type="number" aria-label="Sweep cost in basis points per unit turnover" min="0" max="1000" step="0.5" value={target.cost_bps} on:change={(event) => setTarget({ cost_bps: numberFrom(event, 0) })} /></label>
      {/if}
      <button type="button" class="btn is-ghost" on:click={() => void evaluateSelectedSweep()}>{state.loading === "evaluate" ? "Comparing…" : "Compare points"}</button>
    </fieldset>

    {#if evaluation}
      <section class="report" aria-label="Sweep comparison">
        <p class="label-note">{evaluation.in_sample_label}</p>
        {#if !evaluation.evaluation.timing.enforced_by_gamma}<p class="timing-note">{evaluation.evaluation.timing.note}</p>{/if}
        <div class="row-meta">
          <span>Trials <strong>{evaluation.trials}</strong></span>
          <span>Ready <strong>{evaluation.ready_points}</strong></span>
          <span>Common window <strong>{evaluation.common_window ? `${evaluation.common_window.start} → ${evaluation.common_window.end} · ${evaluation.common_window.observations} obs` : "—"}</strong></span>
        </div>
        <div class="table-wrap">
          <table class="data-table is-compact is-nowrap">
            <caption class="sr-only">In-sample descriptive metrics per sweep point, in sweep order</caption>
            <thead><tr><th>#</th><th>Parameters</th><th>State</th><th class="num">Total</th><th class="num">Ann. vol</th><th class="num">Sharpe</th><th class="num">Max DD</th></tr></thead>
            <tbody>
              {#each evaluation.points as point}
                <tr>
                  <td>{point.index}</td>
                  <td class="params">{params(point.parameters)}</td>
                  <td title={point.reason ?? ""} class:warn={point.state !== "ready"}>{stateLabel[point.state] ?? point.state}</td>
                  <td class="num {tone(point.metrics?.total_return)}">{pct(point.metrics?.total_return)}</td>
                  <td class="num">{pct(point.metrics?.annual_volatility)}</td>
                  <td class="num {tone(point.metrics?.sharpe_ratio)}">{num(point.metrics?.sharpe_ratio)}</td>
                  <td class="num negative">{pct(point.metrics?.max_drawdown)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#each evaluation.warnings as warning}<p class="warning">{warning}</p>{/each}
      </section>
    {/if}

    <fieldset class="evaluation" disabled={busy}>
      <legend>Walk-forward validation</legend>
      <label><span>Train obs</span>
        <input class="form-control" type="number" aria-label="Training observations per fold" min="10" step="1" value={state.walkForwardConfig.train_observations} on:change={(event) => setWalk({ train_observations: numberFrom(event, 60) })} /></label>
      <label><span>Test obs</span>
        <input class="form-control" type="number" aria-label="Test observations per fold" min="5" step="1" value={state.walkForwardConfig.test_observations} on:change={(event) => setWalk({ test_observations: numberFrom(event, 20) })} /></label>
      <label><span>Window</span>
        <select class="form-control" aria-label="Walk-forward window" value={state.walkForwardConfig.window} on:change={(event) => setWalk({ window: (event.currentTarget as HTMLSelectElement).value as "anchored" | "rolling" })}>
          <option value="rolling">Rolling</option><option value="anchored">Anchored (expanding)</option>
        </select></label>
      <label><span>Select by</span>
        <select class="form-control" aria-label="Selection metric" value={state.walkForwardConfig.selection_metric} on:change={(event) => setWalk({ selection_metric: (event.currentTarget as HTMLSelectElement).value as "sharpe" | "total_return" })}>
          <option value="sharpe">Sharpe (train window)</option><option value="total_return">Total return (train window)</option>
        </select></label>
      <button type="button" class="run-button btn is-ghost is-primary" on:click={() => void runSelectedWalkForward()} disabled={pending.length > 0}>
        {state.loading === "walk" ? "Validating…" : "Run walk-forward"}
      </button>
    </fieldset>
    {#if pending.length}<p class="muted">Walk-forward needs every point run; dropping points would hide trials.</p>{/if}

    {#if walk}
      <section class="report" aria-label="Walk-forward result">
        <div class="kpis">
          <div class="kpi primary"><span>OOS total return</span><strong class={tone(walk.out_of_sample.total_return)}>{pct(walk.out_of_sample.total_return)}</strong></div>
          <div class="kpi"><span>OOS Sharpe</span><strong class={tone(walk.out_of_sample.sharpe_ratio)}>{num(walk.out_of_sample.sharpe_ratio)}</strong></div>
          <div class="kpi"><span>OOS max DD</span><strong class="negative">{pct(walk.out_of_sample.max_drawdown)}</strong></div>
          <div class="kpi"><span>OOS obs / folds</span><strong>{walk.out_of_sample.observations} / {walk.folds.length}</strong></div>
          <div class="kpi"><span>Mean selected train {metricLabel(walk.config.selection_metric)}</span><strong>{metricValue(walk.config.selection_metric, walk.in_sample_selected_mean_metric)}</strong></div>
        </div>
        <p class="causal" class:failed={!walk.causality.verified}>
          {walk.causality.verified ? "Causal timing verified" : "Causal check failed"} · {walk.causality.rule}
          {walk.evaluation.timing.enforced_by_gamma ? ` Weight decisions apply after an execution lag of ${walk.evaluation.timing.execution_lag} period(s).` : ""}
        </p>
        {#if !walk.evaluation.timing.enforced_by_gamma}<p class="timing-note">{walk.evaluation.timing.note}</p>{/if}
        <div class="table-wrap">
          <table class="data-table is-compact is-nowrap">
            <caption class="sr-only">Walk-forward folds: training window, selected point and out-of-sample return</caption>
            <thead><tr><th>Fold</th><th>Train</th><th>Test (OOS)</th><th>Selected</th><th class="num">Train {metricLabel(walk.config.selection_metric)}</th><th class="num">OOS return</th></tr></thead>
            <tbody>
              {#each walk.folds as fold}
                <tr>
                  <td>{fold.fold}{fold.partial ? "*" : ""}</td>
                  <td>{fold.train_start} → {fold.train_end} · {fold.train_observations}</td>
                  <td>{fold.test_start} → {fold.test_end} · {fold.test_observations}</td>
                  <td class="params">#{fold.selected_point} · {params(fold.selected_parameters)}</td>
                  <td class="num">{metricValue(walk.config.selection_metric, fold.selected_train_metric)}</td>
                  <td class="num {tone(fold.test_return)}">{pct(fold.test_return)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <div class="reference">
          <p class="eyebrow">In-sample reference · not validation</p>
          <p>Point #{walk.in_sample_reference.point_index ?? "—"} · {params(walk.in_sample_reference.parameters)} · full-window {metricLabel(walk.in_sample_reference.metric)} {metricValue(walk.in_sample_reference.metric, walk.in_sample_reference.value)}</p>
          <p class="muted">{walk.in_sample_reference.label}</p>
        </div>
        {#each walk.warnings as warning}<p class="warning">{warning}</p>{/each}
        <div class="action-row">
          <span class="muted">Report {short(walk.report_sha256)} · sweep {short(walk.definition_sha256)} · {walk.trials} trials · nothing saved</span>
          <button type="button" class="btn is-ghost artifact-link" on:click={exportWalkForward}>Export walk-forward JSON</button>
        </div>
      </section>
    {/if}
  {:else if state.loading === "list"}
    <p class="muted" role="status">Loading sweeps…</p>
  {/if}

  {#if state.error}<p class="error" role="alert">{state.error}</p>{/if}
  {#if state.notice}<p class="muted" role="status">{state.notice}</p>{/if}
</article>

<style>
  .sweep-panel h3 { margin: 0; font-size: var(--text-md); }
  p { margin: 0; }
  .muted, small { color: var(--text-2); font-size: var(--text-xs); line-height: var(--leading-normal); }
  small.invalid, .error { color: var(--negative); }
  .error { font-size: var(--text-xs); }
  code { font-family: var(--font-code); font-size: var(--text-xs); }
  label { display: grid; gap: var(--space-2); min-width: 0; }
  label > span, legend {
    color: var(--text-2); font-size: var(--text-2xs); letter-spacing: 0.12em; text-transform: uppercase;
  }
  /* Fields are .form-control and buttons .btn.is-ghost from primitives.css
     (run actions add .is-primary); results keep 11px mono figures. */
  input, select, textarea {
    width: 100%; min-width: 0; font-family: var(--font-num); font-size: var(--text-xs);
  }
  button {
    font-family: var(--font-ui); font-size: var(--text-sm); white-space: nowrap;
  }
  .artifact-link { border: 0; padding: 0; min-height: auto; color: var(--accent); font-family: var(--font-num); font-size: var(--text-xs); }
  .status {
    border: 1px solid var(--panel-strong); color: var(--text-1); padding: var(--space-2) var(--space-3);
    font-size: var(--text-2xs); letter-spacing: 0.1em; text-transform: uppercase; white-space: nowrap;
  }
  .define-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: var(--space-5); align-items: start; }
  .binding { display: grid; gap: 0; }
  .binding button { margin-top: var(--space-3); justify-self: start; }
  .row { display: flex; justify-content: space-between; gap: var(--space-4); padding: var(--space-2) 0; border-bottom: 1px solid var(--divider); font-size: var(--text-xs); }
  .row span { color: var(--text-2); }
  .row strong { color: var(--text-1); font-family: var(--font-num); font-weight: 500; text-align: right; overflow-wrap: anywhere; }
  .action-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; }
  .buttons { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .progress { display: flex; align-items: center; gap: var(--space-4); font-size: var(--text-xs); color: var(--text-1); }
  progress { flex: 1; height: 6px; accent-color: var(--accent); }
  .evaluation {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: var(--space-4); align-items: end;
    margin: 0; padding: var(--space-4); border: 1px solid var(--divider); min-width: 0;
  }
  .evaluation legend { padding: 0 var(--space-2); }
  .evaluation button { justify-self: start; }
  .report { display: grid; gap: var(--space-3); min-width: 0; border-top: 1px solid var(--divider); padding-top: var(--space-4); }
  .label-note, .timing-note, .warning { font-size: var(--text-xs); line-height: var(--leading-normal); padding-left: var(--space-3); }
  .label-note { color: var(--text-1); border-left: 2px solid var(--panel-strong); }
  .timing-note, .warning { color: var(--warning); border-left: 2px solid var(--warning); }
  .row-meta { display: flex; flex-wrap: wrap; gap: var(--space-5); font-size: var(--text-xs); color: var(--text-2); }
  .row-meta strong { color: var(--text-1); font-family: var(--font-num); font-weight: 500; }
  .table-wrap { overflow: auto; border: 1px solid var(--divider); }
  /* Cells and header come from .data-table.is-compact.is-nowrap in primitives.css;
     script results keep 11px mono figures. */
  table { min-width: 36rem; }
  .data-table td { font-size: var(--text-xs); font-family: var(--font-num); }
  td.params { white-space: normal; overflow-wrap: anywhere; min-width: 10rem; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .positive { color: var(--positive); }
  .negative { color: var(--negative); }
  td.warn { color: var(--warning); }
  .kpis { display: flex; flex-wrap: wrap; border-left: 1px solid var(--divider); }
  .kpi { display: grid; gap: var(--space-1); padding: var(--space-2) var(--space-5); border-right: 1px solid var(--divider); min-width: 7rem; }
  .kpi span { color: var(--text-2); font-size: var(--text-2xs); letter-spacing: 0.1em; text-transform: uppercase; }
  .kpi strong { color: var(--text-0); font-family: var(--font-num); font-size: var(--text-md); font-weight: 600; }
  .kpi.primary strong { font-size: var(--text-lg); }
  .kpi strong.positive { color: var(--positive); }
  .kpi strong.negative { color: var(--negative); }
  .causal { color: var(--positive); font-size: var(--text-xs); line-height: var(--leading-normal); }
  .causal.failed { color: var(--negative); }
  .reference { display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px dashed var(--panel-strong); }
  .reference p:not(.eyebrow) { color: var(--text-1); font-size: var(--text-xs); overflow-wrap: anywhere; }
  .reference p.muted { color: var(--text-2); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  @media (max-width: 760px) {
    .define-grid { grid-template-columns: 1fr; }
    .action-row { align-items: stretch; flex-direction: column; }
    .buttons button, .evaluation button { width: 100%; }
  }
</style>
