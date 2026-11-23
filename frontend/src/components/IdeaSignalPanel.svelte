<script lang="ts">
  // Signal and validation (Workstream 12, I4a). The quant layer of an idea: a
  // Script run or imported CSV rows, its out-of-sample validation and the trial
  // count, collapsed by default. A positions or weights signal is one frozen
  // book that drives tracking; a returns signal is validation only. Gamma never
  // runs a Script from here and nothing is routed anywhere.
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import type { Idea, IdeaSignalOutputKind, IdeaSignalPayload, IdeaTrackingResponse } from "../lib/api/types";
  import { formatTrackingReturn, returnTone, sessionTime } from "../lib/idea-tracking";
  import { formatIdeaInstant } from "../lib/ideas";
  import { formatRatio } from "../lib/idea-analysis";
  import {
    buildImportPayload,
    buildScriptPayload,
    cashShare,
    currentSignal,
    formatShare,
    guessDateColumn,
    importColumns,
    legCost,
    outputKindText,
    signalSourceText,
    sourceIdRows,
    trialsTag,
    trialsText,
    validationCostText,
    validationSplitText,
    weightBasisText,
    type SignalImportDraft,
    type SignalScriptDraft,
  } from "../lib/idea-signals";
  import { toProvenanceBadge } from "../lib/provenance";

  export let idea: Idea;
  export let tracking: IdeaTrackingResponse | null = null;
  export let busy = false;
  export let error = "";
  export let onAttach: (ideaId: string, payload: IdeaSignalPayload) => Promise<unknown> | void = () => {};
  export let onDetach: (ideaId: string) => Promise<unknown> | void = () => {};

  export let expanded = false;
  let formOpen = false;
  let formSource: "import" | "script" = "import";
  let confirmDetach = false;
  let importDraft: SignalImportDraft = {
    outputKind: "weights",
    csv: "",
    dateColumn: "",
    valueColumn: "",
    valueKind: "return",
    label: "",
    instruments: {},
  };
  let scriptDraft: SignalScriptDraft = {
    outputKind: "weights",
    runId: "",
    resultId: "",
    label: "",
    instrumentMap: "",
    sweepId: "",
    trainObservations: "",
    testObservations: "",
    window: "anchored",
  };
  let shownIdeaId = "";

  // Otra idea: se cierra el formulario y se olvida el borrador.
  $: if (idea.idea_id !== shownIdeaId) {
    shownIdeaId = idea.idea_id;
    formOpen = false;
    confirmDetach = false;
  }
  $: signal = currentSignal(idea);
  $: trialCount = idea.trial_count ?? (idea.trials ?? []).length;
  $: canAttach = idea.status === "draft" || idea.status === "active";
  $: validation = signal?.validation ?? null;
  $: cash = signal ? cashShare(signal) : null;
  $: attachedText = signal ? [`attached ${formatIdeaInstant(signal.attached_at)}`, signal.as_of ? `as of ${signal.as_of}` : ""].filter(Boolean).join(" · ") : "";
  // El estado vacío de la validación ya lo dice; no se repite como aviso.
  $: shownWarnings = (signal?.warnings ?? []).filter((item) => !item.startsWith("No out-of-sample validation"));
  $: summary = signal
    ? [signal.label, outputKindText(signal.output_kind), validation ? `out-of-sample ${formatTrackingReturn(validation.out_of_sample.total_return)}` : ""]
        .filter(Boolean)
        .join(" · ")
    : "No signal";
  // Columnas efectivas derivadas del CSV, sin reescribir el borrador (evita un ciclo reactivo).
  $: csvColumns = importColumns({ csv: importDraft.csv, dateColumn: "" });
  $: effectiveDate = csvColumns.columns.includes(importDraft.dateColumn) ? importDraft.dateColumn : guessDateColumn(csvColumns.columns);
  $: parsed = { ...csvColumns, instrumentColumns: csvColumns.columns.filter((column) => column !== effectiveDate) };
  $: effectiveValue = parsed.instrumentColumns.includes(importDraft.valueColumn) ? importDraft.valueColumn : (parsed.instrumentColumns[0] ?? "");
  $: importBuild = buildImportPayload({ ...importDraft, dateColumn: effectiveDate, valueColumn: effectiveValue });
  $: scriptBuild = buildScriptPayload(scriptDraft);
  $: build = formSource === "import" ? importBuild : scriptBuild;
  $: validationSeries = validation ? curveSeries(validation.oos_curve, "Out-of-sample") : [];
  $: suppliedSeries = signal?.supplied ? curveSeries(signal.supplied.curve, "Supplied") : [];

  function curveSeries(points: Array<[string, number]>, label: string): ChartSeries[] {
    if (!points.length) return [];
    return [
      {
        id: label.toLowerCase(),
        label,
        color: "var(--chart-primary)",
        type: "area",
        valueFormat: "percent",
        data: points.map(([day, value]) => ({ time: sessionTime(day), value: value * 100 })),
      },
    ];
  }

  function setInstrument(column: string, patch: { symbol?: string; entity_type?: "equity" | "etf" | "crypto" }) {
    const current = importDraft.instruments[column] ?? { symbol: column, entity_type: "equity" as const };
    importDraft = { ...importDraft, instruments: { ...importDraft.instruments, [column]: { ...current, ...patch } } };
  }

  function setOutputKind(kind: IdeaSignalOutputKind) {
    importDraft = { ...importDraft, outputKind: kind };
  }

  async function submit() {
    if (!build.payload || busy) return;
    const result = await onAttach(idea.idea_id, build.payload);
    if (result) {
      formOpen = false;
      expanded = true;
    }
  }

  async function detach() {
    if (!confirmDetach) {
      confirmDetach = true;
      return;
    }
    confirmDetach = false;
    await onDetach(idea.idea_id);
  }
</script>

<article class="panel is-flush signal-panel" aria-label="Signal and validation">
  <div class="panel-title">
    <h3>
      <button type="button" class="disclosure" aria-expanded={expanded} on:click={() => (expanded = !expanded)}>
        <span class="caret" aria-hidden="true">{expanded ? "▾" : "▸"}</span>Signal and validation
      </button>
    </h3>
    <div class="title-actions">
      <span class="header-meta">{summary}</span>
      {#if trialCount}<span class="tag accent" title="Distinct things tried for this idea; the count never goes down">{trialsTag(trialCount, idea.trials_lower_bound)}</span>{/if}
      <button
        type="button"
        class="btn is-small is-ghost"
        disabled={!canAttach || busy}
        title={canAttach ? "Attach a Script run or CSV rows" : "Signals attach to a draft or active idea"}
        on:click={() => {
          formOpen = !formOpen;
          expanded = true;
        }}>{formOpen ? "Cancel" : signal ? "Change signal" : "Attach signal"}</button
      >
      {#if signal && canAttach}
        <button type="button" class="btn is-small" class:is-danger={confirmDetach} class:is-ghost={!confirmDetach} disabled={busy} on:click={detach}
          >{confirmDetach ? "Confirm detach" : "Detach"}</button
        >
      {/if}
    </div>
  </div>

  {#if error}<p class="signal-error" role="alert">{error}</p>{/if}

  {#if expanded}
    {#if formOpen}
      <form class="signal-form" on:submit|preventDefault={submit} aria-label="Attach a signal">
        <div class="form-row">
          <div class="segmented" role="radiogroup" aria-label="Signal source">
            <button type="button" role="radio" aria-checked={formSource === "import"} class:selected={formSource === "import"} on:click={() => (formSource = "import")}>Import CSV</button>
            <button type="button" role="radio" aria-checked={formSource === "script"} class:selected={formSource === "script"} on:click={() => (formSource = "script")}>Script run</button>
          </div>
          {#if formSource === "import"}
            <label class="field">
              <span>Holds</span>
              <select class="form-control is-small" value={importDraft.outputKind} on:change={(event) => setOutputKind(event.currentTarget.value as IdeaSignalOutputKind)}>
                <option value="weights">Weights (share of NAV)</option>
                <option value="positions">Positions (units)</option>
                <option value="returns">Returns (validation only)</option>
              </select>
            </label>
          {:else}
            <label class="field">
              <span>Holds</span>
              <select class="form-control is-small" bind:value={scriptDraft.outputKind}>
                <option value="weights">Weights (drives tracking)</option>
                <option value="returns">Returns (validation only)</option>
              </select>
            </label>
          {/if}
          <label class="field grow">
            <span>Label</span>
            {#if formSource === "import"}
              <input class="form-control is-small" bind:value={importDraft.label} maxlength="200" placeholder="Optional" />
            {:else}
              <input class="form-control is-small" bind:value={scriptDraft.label} maxlength="200" placeholder="Optional" />
            {/if}
          </label>
        </div>

        {#if formSource === "import"}
          <label class="field">
            <span>CSV rows, header first</span>
            <textarea class="form-control csv-input" rows="4" bind:value={importDraft.csv} placeholder={"date,AAPL,MSFT\n2026-01-09,0.6,-0.2"} spellcheck="false"></textarea>
          </label>
          {#if parsed.columns.length}
            <div class="form-row">
              <label class="field">
                <span>Date column</span>
                <select class="form-control is-small" value={effectiveDate} on:change={(event) => (importDraft = { ...importDraft, dateColumn: event.currentTarget.value })}>
                  {#each parsed.columns as column (column)}<option value={column}>{column}</option>{/each}
                </select>
              </label>
              {#if importDraft.outputKind === "returns"}
                <label class="field">
                  <span>Returns column</span>
                  <select class="form-control is-small" value={effectiveValue} on:change={(event) => (importDraft = { ...importDraft, valueColumn: event.currentTarget.value })}>
                    {#each parsed.instrumentColumns as column (column)}<option value={column}>{column}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>Values are</span>
                  <select class="form-control is-small" bind:value={importDraft.valueKind}>
                    <option value="return">Returns</option>
                    <option value="level">Levels</option>
                  </select>
                </label>
              {/if}
            </div>
            {#if importDraft.outputKind !== "returns" && parsed.instrumentColumns.length}
              <div class="table-scroll">
                <table class="data-table is-compact mapping-table">
                  <thead><tr><th>Column</th><th>Ticker or CoinGecko id</th><th>Type</th></tr></thead>
                  <tbody>
                    {#each parsed.instrumentColumns as column (column)}
                      <tr>
                        <td><strong>{column}</strong></td>
                        <td>
                          <input
                            class="form-control is-small"
                            aria-label={`Ticker for ${column}`}
                            value={importDraft.instruments[column]?.symbol ?? column}
                            on:input={(event) => setInstrument(column, { symbol: event.currentTarget.value })}
                          />
                        </td>
                        <td>
                          <select
                            class="form-control is-small"
                            aria-label={`Type of ${column}`}
                            value={importDraft.instruments[column]?.entity_type ?? "equity"}
                            on:change={(event) => setInstrument(column, { entity_type: event.currentTarget.value as "equity" | "etf" | "crypto" })}
                          >
                            <option value="equity">Equity</option>
                            <option value="etf">ETF</option>
                            <option value="crypto">Crypto</option>
                          </select>
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          {/if}
          {#each parsed.warnings.slice(0, 3) as warning (warning)}<p class="form-note warning">{warning}</p>{/each}
        {:else}
          <div class="form-row">
            <label class="field grow">
              <span>Run id</span>
              <input class="form-control is-small" bind:value={scriptDraft.runId} placeholder="From Strategy Lab · Script runs" spellcheck="false" />
            </label>
            {#if scriptDraft.outputKind === "returns"}
              <label class="field">
                <span>Returns result id</span>
                <input class="form-control is-small" bind:value={scriptDraft.resultId} placeholder="If the run has several" spellcheck="false" />
              </label>
            {/if}
          </div>
          {#if scriptDraft.outputKind === "weights"}
            <label class="field">
              <span>Instrument map, one per line</span>
              <textarea class="form-control csv-input" rows="2" bind:value={scriptDraft.instrumentMap} placeholder="research:asset = SPY etf" spellcheck="false"></textarea>
            </label>
          {/if}
          <div class="form-row">
            <label class="field grow">
              <span>Validation sweep id</span>
              <input class="form-control is-small" bind:value={scriptDraft.sweepId} placeholder="Optional · E5 sweep of the same script" spellcheck="false" />
            </label>
            <label class="field">
              <span>Train</span>
              <input class="form-control is-small obs-input" bind:value={scriptDraft.trainObservations} inputmode="numeric" placeholder="obs." disabled={!scriptDraft.sweepId.trim()} />
            </label>
            <label class="field">
              <span>Test</span>
              <input class="form-control is-small obs-input" bind:value={scriptDraft.testObservations} inputmode="numeric" placeholder="obs." disabled={!scriptDraft.sweepId.trim()} />
            </label>
            <label class="field">
              <span>Window</span>
              <select class="form-control is-small" bind:value={scriptDraft.window} disabled={!scriptDraft.sweepId.trim()}>
                <option value="anchored">Anchored</option>
                <option value="rolling">Rolling</option>
              </select>
            </label>
          </div>
          <p class="form-note">Gamma reads the run's retained results; it never starts a Script run. Every completed run of the script counts as a trial.</p>
        {/if}
        <div class="form-actions">
          <span class="form-note">{build.reason}</span>
          <button type="submit" class="btn is-small is-primary" disabled={!build.payload || busy}>{busy ? "Attaching…" : "Attach signal"}</button>
        </div>
      </form>
    {/if}

    {#if signal}
      <section class="snapshot" aria-label="Current signal">
        <div class="snapshot-head">
          <strong>{signal.label}</strong>
          <span class="tag">{signalSourceText(signal)} · {outputKindText(signal.output_kind)}</span>
          {#if signal.drives_tracking}
            <span class="tag accent">Drives tracking</span>
            <span class="tag">Hypothetical, not executed</span>
          {:else}
            <span class="tag warning">Validation only</span>
          {/if}
          <span class="tag accent">{trialsTag(signal.trial_count, signal.trial_count_lower_bound)}</span>
          <span class="header-meta">{attachedText}</span>
          <ProvenanceBadge data={signal.provenance ? toProvenanceBadge({ ...signal.provenance, warnings: signal.warnings }) : null} variant="dot" />
        </div>
        <dl class="source-ids">
          {#each sourceIdRows(signal) as [label, value] (label)}
            <div><dt>{label}</dt><dd>{value}</dd></div>
          {/each}
        </dl>
        {#if signal.legs.length}
          <div class="table-scroll">
            <table class="data-table is-compact book-table">
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th class="num">Weight {weightBasisText(signal)}</th>
                  {#if signal.output_kind === "positions"}<th class="num">Units</th><th class="num">Valued at</th>{/if}
                  <th class="num">Cost per side</th>
                  <th>Source column</th>
                </tr>
              </thead>
              <tbody>
                {#each signal.legs as leg (leg.key)}
                  {@const cost = legCost(tracking, leg.key)}
                  <tr>
                    <td><strong>{leg.entity.label}</strong></td>
                    <td class="num {returnTone(leg.weight)}">{formatShare(leg.weight)}</td>
                    {#if signal.output_kind === "positions"}
                      <td class="num">{leg.units ?? "N/A"}</td>
                      <td class="num">{leg.price != null ? `${leg.price.toFixed(2)} · ${leg.price_date}` : "N/A"}</td>
                    {/if}
                    <td class="num" class:absent={cost.bp == null}>{cost.bp != null ? `${cost.bp} bp${cost.source === "leg" ? " · edited" : ""}` : "N/A"}</td>
                    <td class="meta-cell">{leg.instrument_id || "N/A"}</td>
                  </tr>
                {/each}
                {#if cash != null && Math.abs(cash) > 1e-9}
                  <tr>
                    <td>Cash at 0%</td>
                    <td class="num">{formatShare(cash)}</td>
                    <td class="num">N/A</td>
                    <td class="meta-cell">Residual</td>
                  </tr>
                {/if}
              </tbody>
            </table>
          </div>
        {/if}
        {#if signal.supplied}
          <div class="snapshot-head">
            <strong>{signal.supplied.label}</strong>
            <span class="tag warning">In-sample</span>
            <span class="header-meta">{signal.supplied.window_start ?? "N/A"} → {signal.supplied.window_end ?? "N/A"} · {signal.supplied.observations} observations</span>
          </div>
          <div class="snapshot-stats">
            <div class="stat"><span>Total return</span><strong class={returnTone(signal.supplied.metrics.total_return)}>{formatTrackingReturn(signal.supplied.metrics.total_return)}</strong></div>
            <div class="stat"><span>Annual return</span><strong class={returnTone(signal.supplied.metrics.annual_return)}>{formatTrackingReturn(signal.supplied.metrics.annual_return)}</strong></div>
            <div class="stat"><span>Sharpe</span><strong class:absent={signal.supplied.metrics.sharpe_ratio == null}>{formatRatio(signal.supplied.metrics.sharpe_ratio)}</strong></div>
            <div class="stat"><span>Max drawdown</span><strong class:negative={(signal.supplied.metrics.max_drawdown ?? 0) < 0}>{formatTrackingReturn(signal.supplied.metrics.max_drawdown)}</strong></div>
            <div class="stat"><span>Trials</span><strong>{trialsText(signal.trial_count, signal.trial_count_lower_bound)}</strong></div>
          </div>
          <TimeSeriesChart series={suppliedSeries} height={120} emptyMessage="No curve" />
        {/if}
      </section>

      <section class="snapshot" aria-label="Out-of-sample validation">
        <div class="snapshot-head">
          <strong>Out-of-sample validation</strong>
          {#if validation}
            <span class="tag accent">Out-of-sample</span>
            <span class="tag" class:warning={validation.costs_included !== true}>{validationCostText(validation)}</span>
            <span class="tag accent">{validation.trials} sweep trials</span>
            {#if !validation.causality_verified}<span class="tag negative">Causality not verified</span>{/if}
            <span class="header-meta">{validationSplitText(validation)} · {validation.oos_start ?? "N/A"} → {validation.oos_end ?? "N/A"}</span>
            <ProvenanceBadge data={validation.provenance ? toProvenanceBadge({ ...validation.provenance, warnings: validation.warnings }) : null} variant="dot" />
          {/if}
        </div>
        {#if validation}
          <div class="snapshot-stats">
            <div class="stat"><span>Total return</span><strong class={returnTone(validation.out_of_sample.total_return)}>{formatTrackingReturn(validation.out_of_sample.total_return)}</strong></div>
            <div class="stat"><span>Annual return</span><strong class={returnTone(validation.out_of_sample.annual_return)}>{formatTrackingReturn(validation.out_of_sample.annual_return)}</strong></div>
            <div class="stat"><span>Sharpe</span><strong class:absent={validation.out_of_sample.sharpe_ratio == null}>{formatRatio(validation.out_of_sample.sharpe_ratio)}</strong></div>
            <div class="stat"><span>Max drawdown</span><strong class:negative={(validation.out_of_sample.max_drawdown ?? 0) < 0}>{formatTrackingReturn(validation.out_of_sample.max_drawdown)}</strong></div>
            <div class="stat">
              <span>Best in-sample {validation.selection_metric === "sharpe" ? "Sharpe" : "return"}</span>
              <strong>{validation.selection_metric === "sharpe" ? formatRatio(validation.in_sample_value) : formatTrackingReturn(validation.in_sample_value)}</strong>
              <small title={validation.in_sample_label}>biased upward, not validation</small>
            </div>
            <div class="stat"><span>Trials</span><strong>{trialsText(signal.trial_count, signal.trial_count_lower_bound)}</strong></div>
          </div>
          <TimeSeriesChart series={validationSeries} height={140} emptyMessage="No out-of-sample curve" />
          <div class="table-scroll">
            <table class="data-table is-compact folds-table">
              <thead><tr><th class="num">Fold</th><th class="num">Train</th><th class="num">Test</th><th class="num">Selected point</th><th class="num">Test return</th></tr></thead>
              <tbody>
                {#each validation.folds as fold (fold.fold)}
                  <tr>
                    <td class="num">{fold.fold}{fold.partial ? " · partial" : ""}</td>
                    <td class="num">{fold.train_start} → {fold.train_end}</td>
                    <td class="num">{fold.test_start} → {fold.test_end}</td>
                    <td class="num">{fold.selected_point}</td>
                    <td class="num {returnTone(fold.test_return)}">{formatTrackingReturn(fold.test_return)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="snapshot-empty">No out-of-sample validation. {signal.source === "script" ? "Attach the run again with an E5 sweep to add a walk-forward." : "An import carries no walk-forward split."}</p>
        {/if}
      </section>

      {#if shownWarnings.length}
        <ul class="signal-warnings">
          {#each shownWarnings as warning (warning)}<li>{warning}</li>{/each}
        </ul>
      {/if}
    {:else if !formOpen}
      <p class="snapshot-empty">
        {canAttach ? "No signal. Attach a Script run or CSV rows to drive tracking with its book, or a return stream to validate." : "Signals attach to a draft or active idea."}
      </p>
    {/if}
  {/if}
</article>

<style>
  /* En pantallas estrechas el título conserva su línea y las acciones pasan debajo. */
  .signal-panel > .panel-title {
    flex-wrap: wrap;
  }

  .disclosure {
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    font-family: var(--font-ui);
    cursor: pointer;
  }

  .disclosure:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
    border-radius: var(--radius-control);
  }

  .caret {
    width: 0.8em;
    color: var(--text-2);
  }

  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    min-width: 0;
  }

  .header-meta {
    color: var(--text-2);
    font-size: var(--text-xs);
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .signal-error {
    margin: 0;
    padding: 0 var(--space-5) var(--space-2);
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .signal-form {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-5) var(--space-4);
  }

  .form-row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-3);
  }

  .field {
    display: grid;
    gap: var(--space-1);
    min-width: 0;
  }

  .field > span {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
    font-weight: 500;
  }

  .field.grow {
    flex: 1 1 12rem;
  }

  .csv-input {
    width: 100%;
    font-family: var(--font-code);
    font-size: var(--text-sm);
    resize: vertical;
  }

  .obs-input {
    width: 5rem;
  }

  .form-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .form-note {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .form-note.warning {
    color: var(--warning);
  }

  .snapshot {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-2) 0 var(--space-4);
  }

  .snapshot + .snapshot,
  .signal-form + .snapshot {
    border-top: 1px solid var(--divider);
  }

  .snapshot-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
    padding: 0 var(--space-5);
    font-size: var(--text-sm);
  }

  .snapshot-head strong {
    font-weight: 600;
  }

  .source-ids {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-6);
    margin: 0;
    padding: 0 var(--space-5);
  }

  .source-ids div {
    display: grid;
    min-width: 0;
  }

  .source-ids dt {
    color: var(--text-2);
    font-family: var(--font-label);
    font-size: var(--text-xs);
  }

  .source-ids dd {
    margin: 0;
    font-family: var(--font-num);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .snapshot-stats {
    display: flex;
    flex-wrap: wrap;
    padding: 0 var(--space-5);
  }

  .snapshot-stats .stat {
    padding-inline: 0 var(--space-6);
  }

  .snapshot-stats small {
    white-space: nowrap;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .meta-cell {
    color: var(--text-2);
  }

  .snapshot-empty {
    margin: 0;
    padding: var(--space-2) var(--space-5) var(--space-4);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .book-table,
  .folds-table {
    min-width: 28rem;
  }

  .mapping-table {
    min-width: 22rem;
  }

  .signal-warnings {
    margin: 0;
    padding: 0 var(--space-5) var(--space-4) calc(var(--space-5) + var(--space-4));
    color: var(--text-2);
    font-size: var(--text-xs);
  }
</style>
