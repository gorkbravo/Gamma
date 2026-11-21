<script lang="ts">
  // Tracking section of the Idea view (Workstream 12, I3a): the hypothetical
  // forward record of an idea with legs. The backend rebuilds the canonical
  // daily series from provider closes on every read; this panel shows it, its
  // segments and the cost assumptions, always labelled "Hypothetical, not
  // executed". Gaps stay gaps (the chart line breaks), and the gross record is
  // shown next to the net one so a cost edit can never hide what prices did.
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import WhatIsThis from "./WhatIsThis.svelte";
  import type {
    Idea,
    IdeaTrackingCostClass,
    IdeaTrackingResponse,
    IdeaTrackingSettingsPayload,
  } from "../lib/api/types";
  import {
    COST_CLASS_SHORT_LABELS,
    LEG_COST_CLASSES,
    SEGMENT_START_LABELS,
    SEGMENT_STATUS_LABELS,
    TRACKING_LABEL,
    TRACKING_STATUS_LABELS,
    changedCosts,
    costDraftError,
    formatBp,
    formatCostDrag,
    formatTrackingReturn,
    returnTone,
    segmentLegsText,
    segmentPeriodText,
    trackingChartData,
    trackingMetaText,
  } from "../lib/idea-tracking";
  import { formatIdeaInstant } from "../lib/ideas";
  import type { ProvenanceBadgeData } from "../lib/provenance";

  export let idea: Idea;
  export let tracking: IdeaTrackingResponse | null = null;
  export let loading = false;
  export let error = "";
  export let onLoad: (ideaId: string) => Promise<unknown> | void = () => {};
  export let onUpdate: (ideaId: string, payload: IdeaTrackingSettingsPayload) => Promise<IdeaTrackingResponse | null> = async () => null;

  const WARNINGS_SHOWN = 4;

  $: record = idea.tracking ?? null;
  $: hasRecord = Boolean(record?.segments.length);
  // Se reconstruye al abrir la idea y cuando cambian sus segmentos o su estado, no en cada edición.
  $: lastSegment = record?.segments.at(-1) ?? null;
  $: loadKey = hasRecord ? `${idea.idea_id}|${idea.status}|${record?.segments.length}|${lastSegment?.ended_at ?? ""}` : "";
  let loadedKey = "";
  $: if (loadKey && loadKey !== loadedKey) {
    loadedKey = loadKey;
    void onLoad(idea.idea_id);
  }
  $: current = tracking && tracking.idea_id === idea.idea_id ? tracking : null;
  $: summary = current?.summary ?? null;
  $: benchmarkSymbol = current?.benchmark.symbol ?? record?.benchmark ?? "SPY";
  $: chartData = trackingChartData(current);
  let chartSeries: ChartSeries[] = [];
  $: chartSeries = buildChartSeries(chartData, benchmarkSymbol);

  function buildChartSeries(data: ReturnType<typeof trackingChartData>, symbol: string): ChartSeries[] {
    const net: ChartSeries = {
      id: "net",
      label: "Net, hypothetical",
      color: "var(--chart-primary)",
      type: "area",
      breakOnGaps: true,
      valueFormat: "percent",
      markers: data.markers,
      data: data.net,
    };
    if (!data.benchmark.length) return [net];
    // La comparación es una línea gris continua (salvo huecos reales): nunca discontinua.
    const benchmark: ChartSeries = {
      id: "benchmark",
      label: symbol,
      color: "var(--chart-secondary)",
      type: "line",
      breakOnGaps: true,
      valueFormat: "percent",
      data: data.benchmark,
    };
    return [net, benchmark];
  }
  $: chartMessage = !hasRecord
    ? "Not started"
    : loading && !current
      ? "Loading…"
      : error && !current
        ? "Tracking unavailable"
        : current?.status_reason && !current.points.length
          ? current.status_reason
          : "No sessions yet";
  $: costRange = legCostRange(current);
  $: meta = current ? [current.status !== "tracking" ? TRACKING_STATUS_LABELS[current.status] : "", trackingMetaText(current)].filter(Boolean).filter((item, index, all) => all.indexOf(item) === index).join(" · ") : "";
  $: badge = badgeData(current);

  function legCostRange(response: IdeaTrackingResponse | null): string {
    const values = (response?.segments ?? [])
      .flatMap((segment) => segment.legs.map((leg) => leg.cost_bp))
      .filter((value): value is number => value != null && Number.isFinite(value));
    if (!values.length) return "";
    const low = Math.min(...values);
    const high = Math.max(...values);
    return low === high ? `${formatBp(low)} per side` : `${Number(low.toFixed(2))}–${formatBp(high)} per side`;
  }

  function badgeData(response: IdeaTrackingResponse | null): ProvenanceBadgeData | null {
    if (!response || !response.provenance.length) return null;
    const providers = [...new Set(response.provenance.map((row) => row.source_provider).filter(Boolean))];
    const demo = response.warnings.some((item) => item.includes("demo sample history"));
    const unavailable = response.provenance.some((row) => !row.available);
    const retrieved = response.provenance
      .map((row) => row.retrieved_at)
      .filter((value): value is string => Boolean(value))
      .sort()
      .at(-1);
    return {
      provider: providers.join(", ") || null,
      // Serie reconstruida (derivada) de cierres históricos; la demo usa datos de muestra.
      state: demo ? "sample" : unavailable ? "unavailable" : "derived",
      rawLabel: null,
      qualityLabel: TRACKING_LABEL,
      retrievedAt: retrieved ?? response.computed_at,
      sourceTimestamp: response.summary.as_of,
      transformationNote: response.methodology,
      warnings: response.warnings,
    };
  }

  // ── Cost assumptions ────────────────────────────────────────────────────
  let costsOpen = false;
  let showAllWarnings = false;
  let saving = false;
  let costError = "";
  let draft: Record<string, string> = {};
  let legDraft: Record<string, IdeaTrackingCostClass> = {};

  $: legRows = uniqueLegs(current);

  function uniqueLegs(response: IdeaTrackingResponse | null) {
    const seen = new Map<string, { key: string; label: string; detected: IdeaTrackingCostClass; current: IdeaTrackingCostClass }>();
    for (const segment of response?.segments ?? []) {
      for (const leg of segment.legs) {
        if (!LEG_COST_CLASSES.includes(leg.detected_class) && !LEG_COST_CLASSES.includes(leg.asset_class)) continue;
        seen.set(leg.key, { key: leg.key, label: leg.label, detected: leg.detected_class, current: leg.asset_class });
      }
    }
    return [...seen.values()];
  }

  function openCosts() {
    if (costsOpen) {
      costsOpen = false;
      return;
    }
    draft = Object.fromEntries(
      (current?.cost_model.classes ?? []).filter((item) => item.editable).map((item) => [item.asset_class, String(item.per_side_bp ?? "")])
    );
    legDraft = Object.fromEntries(legRows.map((row) => [row.key, row.current]));
    costError = "";
    costsOpen = true;
  }

  $: draftError = costsOpen ? costDraftError(draft) : "";

  async function saveCosts() {
    if (!current || saving) return;
    if (draftError) {
      costError = draftError;
      return;
    }
    const payload: IdeaTrackingSettingsPayload = {};
    const costs = changedCosts(current.cost_model.classes, draft);
    if (costs) payload.per_side_bp = costs;
    const classes: Record<string, string | null> = {};
    for (const row of legRows) {
      const chosen = legDraft[row.key];
      if (chosen && chosen !== row.current) classes[row.key] = chosen === row.detected ? null : chosen;
    }
    if (Object.keys(classes).length) payload.leg_classes = classes;
    if (!payload.per_side_bp && !payload.leg_classes) {
      costsOpen = false;
      return;
    }
    saving = true;
    try {
      const result = await onUpdate(idea.idea_id, payload);
      if (result) costsOpen = false;
      else costError = error || "The costs were not saved.";
    } finally {
      saving = false;
    }
  }

  $: warnings = current?.warnings ?? [];
  $: shownWarnings = showAllWarnings ? warnings : warnings.slice(0, WARNINGS_SHOWN);
</script>

<article class="panel is-flush tracking-panel" aria-label="Hypothetical tracking">
  <div class="panel-title tracking-title">
    <h3>Tracking <WhatIsThis key="stat.forward_return" stance={idea.stance} /></h3>
    <div class="title-actions">
      <span class="tag is-tinted context">{TRACKING_LABEL}</span>
      {#if meta}<span class="header-meta">{meta}</span>{/if}
      {#if badge}<ProvenanceBadge data={badge} variant="dot" />{/if}
      <button type="button" class="btn is-small is-ghost" aria-expanded={costsOpen} disabled={!current} on:click={openCosts}>Costs</button>
      <button
        type="button"
        class="btn is-small is-ghost"
        disabled={!hasRecord || loading}
        title="Rebuild the series from provider closes"
        on:click={() => onLoad(idea.idea_id)}>{loading ? "Rebuilding…" : "Rebuild"}</button
      >
    </div>
  </div>

  {#if !hasRecord}
    <p class="tracking-empty">
      {#if idea.status === "draft"}
        Tracking starts at the first close after the idea is activated with legs.
      {:else if !idea.legs.length}
        Add legs with signed weights to track a hypothetical book.
      {:else}
        Not started.
      {/if}
    </p>
  {:else}
    <div class="tracking-stats">
      <div class="stat">
        <span>Net since activation</span>
        <strong class={returnTone(summary?.net_return)} class:absent={summary?.net_return == null}>{formatTrackingReturn(summary?.net_return)}</strong>
        {#if summary?.first_session}<small>from {summary.first_session}</small>{/if}
      </div>
      <div class="stat">
        <span>Gross</span>
        <strong class={returnTone(summary?.gross_return)} class:absent={summary?.gross_return == null}>{formatTrackingReturn(summary?.gross_return)}</strong>
      </div>
      <div class="stat">
        <span>Costs <WhatIsThis key="stat.tracking_costs" stance={idea.stance} /></span>
        <strong class:negative={(summary?.cost_drag ?? 0) > 0} class:absent={summary?.cost_drag == null}>{formatCostDrag(summary?.cost_drag)}</strong>
        {#if costRange}<small>{costRange}</small>{/if}
      </div>
      <div class="stat">
        <span>{benchmarkSymbol}</span>
        <strong class={returnTone(summary?.benchmark_return)} class:absent={summary?.benchmark_return == null}>{formatTrackingReturn(summary?.benchmark_return)}</strong>
        {#if current && !current.benchmark.available}<small>Unavailable</small>{/if}
      </div>
      <div class="stat">
        <span>Excess</span>
        <strong class={returnTone(summary?.excess_return)} class:absent={summary?.excess_return == null}>{formatTrackingReturn(summary?.excess_return)}</strong>
      </div>
      <div class="stat">
        <span>Max drawdown</span>
        <strong class:negative={(summary?.max_drawdown ?? 0) < 0} class:absent={summary?.max_drawdown == null}>{formatTrackingReturn(summary?.max_drawdown)}</strong>
      </div>
    </div>

    {#if error && current}<p class="tracking-error" role="alert">{error}</p>{/if}

    <div class="tracking-chart">
      <TimeSeriesChart series={current?.points.length ? chartSeries : []} height={220} showLegend emptyMessage={chartMessage} />
    </div>

    <div class="table-scroll">
      <table class="data-table is-top segments-table">
        <thead>
          <tr>
            <th class="num">Segment</th>
            <th>Closes</th>
            <th>Legs (share of gross)</th>
            <th class="num">Gross</th>
            <th class="num">Costs</th>
            <th class="num">Net</th>
            <th class="num">{benchmarkSymbol}</th>
          </tr>
        </thead>
        <tbody>
          {#each current?.segments ?? [] as segment (segment.segment_id)}
            <tr>
              <td class="num">S{segment.number}</td>
              <td class="period-cell">
                <strong>{segmentPeriodText(segment)}</strong>
                <span class="meta">
                  {SEGMENT_START_LABELS[segment.start_reason] ?? segment.start_reason} {formatIdeaInstant(segment.started_at)}{#if segment.ended_at}
                    · ended {formatIdeaInstant(segment.ended_at)}{/if}{#if segment.gaps}
                    · {segment.gaps} {segment.gaps === 1 ? "gap" : "gaps"}{/if}
                </span>
                {#if segment.status !== "tracking" && segment.status !== "closed"}
                  <span class="tag" class:warning={segment.status === "unavailable" || segment.status === "untracked"}>{SEGMENT_STATUS_LABELS[segment.status]}</span>
                {/if}
              </td>
              <td class="legs-cell">
                {segmentLegsText(segment)}
                {#if segment.reason}<span class="meta">{segment.reason}</span>{/if}
              </td>
              <td class="num {returnTone(segment.gross_return)}" class:absent={segment.gross_return == null}>{formatTrackingReturn(segment.gross_return)}</td>
              <td class="num" class:negative={(segment.cost ?? 0) > 0} class:absent={segment.cost == null}>{formatCostDrag(segment.cost)}</td>
              <td class="num {returnTone(segment.net_return)}" class:absent={segment.net_return == null}>{formatTrackingReturn(segment.net_return)}</td>
              <td class="num {returnTone(segment.benchmark_return)}" class:absent={segment.benchmark_return == null}>{formatTrackingReturn(segment.benchmark_return)}</td>
            </tr>
          {:else}
            <tr class="empty-row"><td colspan="7">{loading ? "Loading…" : error ? "Tracking unavailable" : "No segments."}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>

    {#if costsOpen && current}
      <form class="costs-form" on:submit|preventDefault={saveCosts} aria-label="Cost assumptions">
        <div class="table-scroll">
          <table class="data-table is-compact is-top costs-table">
            <thead><tr><th>Asset class</th><th class="num">Per side</th><th>Basis</th></tr></thead>
            <tbody>
              {#each current.cost_model.classes as item (item.asset_class)}
                <tr>
                  <td>
                    {item.label}
                    {#if item.edited && item.default_bp != null}<span class="meta">default {formatBp(item.default_bp)}</span>{/if}
                  </td>
                  <td class="num">
                    {#if item.editable}
                      <input
                        class="form-control is-small bp-input"
                        inputmode="decimal"
                        bind:value={draft[item.asset_class]}
                        aria-label={`${item.label}, basis points per side`}
                      />
                    {:else}
                      <span class="absent">{item.source === "quote" ? "From quote" : "None"}</span>
                    {/if}
                  </td>
                  <td class="basis-cell">{item.basis}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if legRows.length}
          <div class="table-scroll">
            <table class="data-table is-compact leg-class-table">
              <thead><tr><th>Leg</th><th>Cost class</th></tr></thead>
              <tbody>
                {#each legRows as row (row.key)}
                  <tr>
                    <td>{row.label}<span class="meta">detected: {COST_CLASS_SHORT_LABELS[row.detected]}</span></td>
                    <td>
                      <select class="form-control is-small" bind:value={legDraft[row.key]} aria-label={`Cost class for ${row.label}`}>
                        {#each LEG_COST_CLASSES as option}
                          <option value={option}>{COST_CLASS_SHORT_LABELS[option]}</option>
                        {/each}
                      </select>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
        <div class="form-actions">
          {#if costError || draftError}<span class="tracking-error" role="alert">{costError || draftError}</span>{/if}
          <button type="button" class="btn is-small is-ghost" on:click={() => (costsOpen = false)}>Cancel</button>
          <button type="submit" class="btn is-small is-primary" disabled={saving || Boolean(draftError)}>{saving ? "Saving…" : "Save costs"}</button>
        </div>
      </form>
    {/if}

    {#if warnings.length}
      <ul class="tracking-warnings" aria-label="Tracking warnings">
        {#each shownWarnings as warning}
          <li>{warning}</li>
        {/each}
        {#if warnings.length > WARNINGS_SHOWN}
          <li>
            <button type="button" class="more-link" aria-expanded={showAllWarnings} on:click={() => (showAllWarnings = !showAllWarnings)}
              >{showAllWarnings ? "Show fewer" : `+${warnings.length - WARNINGS_SHOWN} more`}</button
            >
          </li>
        {/if}
      </ul>
    {/if}
  {/if}
</article>

<style>
  .tracking-title {
    flex-wrap: wrap;
  }

  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    min-width: 0;
  }

  .tracking-empty {
    margin: 0;
    padding: var(--space-2) var(--space-5) var(--space-5);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .tracking-stats {
    display: flex;
    flex-wrap: wrap;
    padding: 0 var(--space-5) var(--space-2);
  }

  .tracking-stats .stat {
    padding-inline: 0 var(--space-6);
  }

  .tracking-stats small {
    white-space: nowrap;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .tracking-chart {
    padding: 0 var(--space-2) var(--space-3) 0;
  }

  /* The scroll box keeps an .sr-only header inside it on a narrow window. */
  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .segments-table {
    min-width: 40rem;
  }

  .period-cell strong {
    font-weight: 500;
    white-space: nowrap;
  }

  .period-cell .tag {
    margin-top: var(--space-1);
  }

  .legs-cell {
    min-width: 12rem;
  }

  .meta {
    display: block;
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .costs-form {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4) 0 var(--space-3);
  }

  .costs-table {
    min-width: 36rem;
  }

  .basis-cell {
    color: var(--text-1);
    font-family: var(--font-ui);
    min-width: 18rem;
  }

  .bp-input {
    width: 5.5rem;
    text-align: right;
  }

  .form-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    padding: 0 var(--space-5);
  }

  .tracking-error {
    margin: 0;
    padding: 0 var(--space-5);
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .form-actions .tracking-error {
    padding: 0;
    margin-right: auto;
  }

  .tracking-warnings {
    margin: 0;
    padding: var(--space-3) var(--space-5) var(--space-4) calc(var(--space-5) + var(--space-5));
    display: grid;
    gap: var(--space-1);
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .more-link {
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    font-family: var(--font-ui);
    font-size: var(--text-xs);
    cursor: pointer;
  }

  .more-link:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
</style>
