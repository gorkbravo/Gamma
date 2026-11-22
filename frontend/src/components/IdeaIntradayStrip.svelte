<script lang="ts">
  // Intraday strip of the tracking panel (Workstream 12, I3d). While Trader
  // Workstation is connected, the backend records IBKR marks for the legs of
  // the open segment and values them against the canonical daily series; this
  // strip shows today's hypothetical P&L, the intraday drawdown, each mark's
  // quality (live, delayed, frozen) and the stretches with no marks. It never
  // changes the daily record above it, and it is labelled "Hypothetical, not
  // executed" like every other figure of the book.
  import { onDestroy } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import type { Idea, IdeaIntradayQuality, IdeaIntradayView } from "../lib/api/types";
  import { TRACKING_LABEL, formatTrackingReturn, returnTone } from "../lib/idea-tracking";
  import {
    INTRADAY_GAP_LABELS,
    INTRADAY_QUALITY_LABELS,
    cadenceText,
    formatMark,
    gapDurationText,
    gapPeriodText,
    gapReasonDetail,
    intradayChartData,
    intradayMetaText,
    intradayQualityTone,
    markFieldText,
    shouldPollIntraday,
  } from "../lib/idea-intraday";
  import type { ProvenanceBadgeData, ProvenanceState } from "../lib/provenance";

  export let idea: Idea;
  export let view: IdeaIntradayView | null | undefined = null;
  export let onLoadSession: (ideaId: string, session?: string | null) => Promise<unknown> | void = () => {};

  // Mientras graba la sesión de hoy se relee cada minuto; las marcas llegan cada cinco.
  const POLL_MS = 60_000;

  $: available = Boolean(view?.available);
  $: summary = view?.summary ?? null;
  $: quality = summary?.quality ?? null;
  $: chartPoints = intradayChartData(view);
  let series: ChartSeries[] = [];
  $: series = chartPoints.length
    ? [
        {
          id: "today",
          label: "Today, hypothetical",
          color: "var(--chart-primary)",
          type: "area",
          breakOnGaps: true,
          // Cada marca es una observación: se ve aunque quede sola entre dos huecos.
          showPointMarkers: true,
          pointMarkerRadius: 2,
          valueFormat: "percent",
          data: chartPoints,
        },
      ]
    : [];
  $: emptyMessage = view?.points.length ? "No priced marks yet" : "No marks";
  $: badge = badgeData(view);
  $: reasonText = view?.status_reason ?? "No IBKR marks yet. Gamma records them every 5 minutes while Trader Workstation is connected.";

  function stateFor(value: IdeaIntradayQuality | null): ProvenanceState {
    if (value === "live") return "live";
    if (value === "delayed" || value === "delayed_frozen") return "delayed";
    if (value === "frozen") return "historical";
    return "unavailable";
  }

  function badgeData(current: IdeaIntradayView | null | undefined): ProvenanceBadgeData | null {
    if (!current?.available) return null;
    return {
      provider: current.source_provider,
      state: stateFor(current.summary.quality),
      rawLabel: null,
      qualityLabel: TRACKING_LABEL,
      retrievedAt: current.summary.as_of,
      sourceTimestamp: current.summary.as_of,
      transformationNote: `${current.methodology} ${cadenceText(current)}.`,
      warnings: current.warnings,
    };
  }

  let timer: ReturnType<typeof setInterval> | null = null;
  let pollingFor = "";
  $: pollKey = shouldPollIntraday(view) ? `${idea.idea_id}|${view?.session ?? ""}` : "";
  $: if (pollKey !== pollingFor) {
    pollingFor = pollKey;
    if (timer) clearInterval(timer);
    timer = null;
    if (pollKey) {
      const session = view?.session ?? null;
      timer = setInterval(() => {
        if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
        void onLoadSession(idea.idea_id, session);
      }, POLL_MS);
    }
  }
  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  function chooseSession(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    void onLoadSession(idea.idea_id, value || null);
  }
</script>

<section class="intraday" aria-label="Intraday, IBKR marks">
  <div class="intraday-head">
    <strong>Intraday</strong>
    <span class="tag is-tinted context">{TRACKING_LABEL}</span>
    {#if available && view}
      {#if quality}<span class="tag {intradayQualityTone(quality)}">{INTRADAY_QUALITY_LABELS[quality]}</span>{/if}
      {#if view.status === "recording"}
        <span class="tag accent">Recording</span>
      {:else if !view.tws_connected}
        <span class="tag">TWS disconnected</span>
      {/if}
      <span class="header-meta">{intradayMetaText(view)}</span>
    {/if}
    {#if view && view.sessions.length > 1}
      <select class="form-control is-small session-select" aria-label="Intraday session (UTC day)" value={view.session ?? ""} on:change={chooseSession}>
        {#each view.sessions as day}
          <option value={day}>{day}</option>
        {/each}
      </select>
    {/if}
    {#if badge}<ProvenanceBadge data={badge} variant="dot" />{/if}
  </div>

  {#if !available || !view || !summary}
    <p class="intraday-empty">{reasonText}</p>
  {:else}
    <div class="intraday-stats">
      <div class="stat">
        <span>Today</span>
        <strong class={returnTone(summary.today_return)} class:absent={summary.today_return == null}>{formatTrackingReturn(summary.today_return)}</strong>
        {#if view.reference}<small>vs close {view.reference.session}</small>{/if}
      </div>
      <div class="stat">
        <span>Since activation, live</span>
        <strong class={returnTone(summary.net_return)} class:absent={summary.net_return == null}>{formatTrackingReturn(summary.net_return)}</strong>
        <small>net of costs</small>
      </div>
      <div class="stat">
        <span>Intraday drawdown</span>
        <strong class:negative={(summary.intraday_drawdown ?? 0) < 0} class:absent={summary.intraday_drawdown == null}>{formatTrackingReturn(summary.intraday_drawdown)}</strong>
        <small>from the session peak</small>
      </div>
    </div>

    <div class="intraday-chart">
      <TimeSeriesChart {series} height={120} {emptyMessage} />
    </div>

    {#if view.gaps.length}
      <div class="table-scroll">
        <table class="data-table is-compact gaps-table" aria-label="Intraday gaps">
          <thead><tr><th>Gap, UTC</th><th class="num">Length</th><th>Why</th></tr></thead>
          <tbody>
            {#each view.gaps as gap (`${gap.start}|${gap.kind}`)}
              <tr>
                <td><strong>{gapPeriodText(gap)}</strong></td>
                <td class="num">{gapDurationText(gap)}</td>
                <td>{INTRADAY_GAP_LABELS[gap.kind]}{#if gapReasonDetail(gap)}<span class="meta">{gapReasonDetail(gap)}</span>{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    {#if view.legs.length}
      <div class="table-scroll">
        <table class="data-table is-compact legs-table" aria-label="Latest IBKR marks">
          <thead><tr><th>Leg</th><th class="num">Mark</th><th>Source</th><th class="num">Prior close</th><th class="num">Move</th></tr></thead>
          <tbody>
            {#each view.legs as leg (leg.key)}
              <tr>
                <td><strong>{leg.label}</strong></td>
                <td class="num" class:absent={leg.price == null}>{formatMark(leg.price)}</td>
                <td>
                  {#if leg.carried}
                    Last close<span class="meta">market closed</span>
                  {:else if leg.price == null}
                    <span class="absent">No mark</span>{#if leg.missing_reason}<span class="meta">{leg.missing_reason}</span>{/if}
                  {:else}
                    {markFieldText(leg.field)}{#if leg.quality}<span class="meta">{INTRADAY_QUALITY_LABELS[leg.quality]}</span>{/if}
                  {/if}
                </td>
                <td class="num" class:absent={leg.reference_close == null}>{formatMark(leg.reference_close)}</td>
                <td class="num {returnTone(leg.move)}" class:absent={leg.move == null}>{formatTrackingReturn(leg.move)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    {#if view.warnings.length}
      <ul class="intraday-warnings" aria-label="Intraday warnings">
        {#each view.warnings as warning}<li>{warning}</li>{/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .intraday {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-3) 0 var(--space-3);
    border-top: 1px solid var(--divider);
  }

  .intraday-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
    padding: 0 var(--space-5);
    font-size: var(--text-sm);
  }

  .intraday-head strong {
    font-weight: 600;
  }

  .header-meta {
    color: var(--text-2);
    font-size: var(--text-xs);
  }

  .session-select {
    width: auto;
    margin-left: auto;
  }

  .intraday-empty {
    margin: 0;
    padding: 0 var(--space-5);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .intraday-stats {
    display: flex;
    flex-wrap: wrap;
    padding: 0 var(--space-5);
  }

  .intraday-stats .stat {
    padding-inline: 0 var(--space-6);
  }

  .intraday-stats small {
    white-space: nowrap;
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .intraday-chart {
    padding: 0 var(--space-2) 0 0;
  }

  /* The scroll box keeps an .sr-only header inside it on a narrow window. */
  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .gaps-table {
    min-width: 30rem;
  }

  .legs-table {
    min-width: 32rem;
  }

  .meta {
    display: block;
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .intraday-warnings {
    margin: 0;
    padding: 0 var(--space-5) 0 calc(var(--space-5) + var(--space-5));
    display: grid;
    gap: var(--space-1);
    color: var(--text-2);
    font-size: var(--text-xs);
  }
</style>
