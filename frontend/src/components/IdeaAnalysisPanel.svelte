<script lang="ts">
  // Test and risk snapshots of an idea (Workstream 12, I3c). Each run is a
  // frozen snapshot of the idea's legs through Strategy Lab (a backtest) or
  // Risk (VaR, expected shortfall, stress replay), kept with its date, window
  // and provenance and recomputed only when the user asks. A backtest is
  // in-sample and carries no costs; both are labelled where its figures are.
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import ProvenanceBadge from "./ProvenanceBadge.svelte";
  import type { Idea, IdeaTestSnapshot } from "../lib/api/types";
  import { formatTrackingReturn, returnTone, sessionTime } from "../lib/idea-tracking";
  import { formatIdeaInstant } from "../lib/ideas";
  import { asLoss, episodeCoverageText, formatRatio, snapshotLegsText, snapshotWindowText, worstEpisode } from "../lib/idea-analysis";
  import { toProvenanceBadge } from "../lib/provenance";
  import { trialsTag, trialsText } from "../lib/idea-signals";

  export let idea: Idea;
  export let busy: "" | "test" | "risk" = "";
  export let error = "";
  export let onRunTest: (ideaId: string) => Promise<unknown> | void = () => {};
  export let onRunRisk: (ideaId: string) => Promise<unknown> | void = () => {};

  $: test = (idea.tests ?? []).at(-1) ?? null;
  $: risk = (idea.risks ?? []).at(-1) ?? null;
  $: canRun = idea.legs.length > 0 && (idea.status === "draft" || idea.status === "active");
  $: testSeries = test ? curveSeries(test) : [];
  $: worst = risk ? worstEpisode(risk) : null;
  $: shownEpisodes = (risk?.episodes ?? []).filter((item) => item.status !== "unavailable");

  function curveSeries(snapshot: IdeaTestSnapshot): ChartSeries[] {
    const base = snapshot.equity_curve[0]?.[1] ?? 1;
    const benchBase = snapshot.benchmark_curve[0]?.[1] ?? 1;
    const series: ChartSeries[] = [
      {
        id: "test",
        label: "Backtest, no costs",
        color: "var(--chart-primary)",
        type: "area",
        valueFormat: "percent",
        data: snapshot.equity_curve.map(([day, value]) => ({ time: sessionTime(day), value: (value / base - 1) * 100 })),
      },
    ];
    if (snapshot.benchmark_curve.length) {
      series.push({
        id: "benchmark",
        label: snapshot.benchmark,
        color: "var(--chart-secondary)",
        type: "line",
        valueFormat: "percent",
        data: snapshot.benchmark_curve.map(([day, value]) => ({ time: sessionTime(day), value: (value / benchBase - 1) * 100 })),
      });
    }
    return series;
  }

</script>

<article class="panel is-flush analysis-panel" aria-label="Test and risk">
  <div class="panel-title">
    <h3>Test and risk</h3>
    <div class="title-actions">
      <span class="header-meta">Recomputed only when you ask</span>
      <button
        type="button"
        class="btn is-small is-ghost"
        disabled={!canRun || Boolean(busy)}
        title={canRun ? "Backtest the legs in Strategy Lab" : "Add legs to a draft or active idea first"}
        on:click={() => onRunTest(idea.idea_id)}>{busy === "test" ? "Testing…" : test ? "Rerun test" : "Run test"}</button
      >
      <button
        type="button"
        class="btn is-small is-ghost"
        disabled={!canRun || Boolean(busy)}
        title={canRun ? "Run Risk on the legs' research book" : "Add legs to a draft or active idea first"}
        on:click={() => onRunRisk(idea.idea_id)}>{busy === "risk" ? "Running…" : risk ? "Rerun risk" : "Run risk"}</button
      >
    </div>
  </div>

  {#if error}<p class="analysis-error" role="alert">{error}</p>{/if}

  <section class="snapshot" aria-label="Backtest snapshot">
    <div class="snapshot-head">
      <strong>Backtest</strong>
      {#if test}
        <span class="tag warning">No costs</span>
        <span class="tag">In-sample only</span>
        {#if test.source !== "idea_legs"}<span class="tag accent" title={test.source_ids.attached_label ?? ""}>From {test.source === "risk_tab" ? "Risk" : "Strategy Lab"}</span>{/if}
        <span
          class="tag accent"
          title={test.trial_count != null ? `${trialsText(test.trial_count, test.trial_count_lower_bound)} recorded for this idea when this backtest ran` : "Run before trial counting (I4)"}
          >{trialsTag(test.trial_count, test.trial_count_lower_bound)}</span
        >
        {#if test.stale_reason}<span class="tag warning" title={test.stale_reason}>Stale</span>{/if}
        <span class="header-meta">{formatIdeaInstant(test.created_at)} · {snapshotWindowText(test)} · {snapshotLegsText(test)}</span>
        <ProvenanceBadge data={test.provenance ? toProvenanceBadge({ ...test.provenance, warnings: test.warnings }) : null} variant="dot" />
      {/if}
    </div>
    {#if test}
      <div class="snapshot-stats">
        <div class="stat"><span>Total return</span><strong class={returnTone(test.metrics.total_return)}>{formatTrackingReturn(test.metrics.total_return)}</strong></div>
        <div class="stat"><span>Annual return</span><strong class={returnTone(test.metrics.annual_return)}>{formatTrackingReturn(test.metrics.annual_return)}</strong></div>
        <div class="stat"><span>Volatility</span><strong class:absent={test.metrics.annual_volatility == null}>{formatTrackingReturn(test.metrics.annual_volatility).replace("+", "")}</strong></div>
        <div class="stat"><span>Sharpe</span><strong class:absent={test.metrics.sharpe_ratio == null}>{formatRatio(test.metrics.sharpe_ratio)}</strong></div>
        <div class="stat"><span>Max drawdown</span><strong class:negative={(test.metrics.max_drawdown ?? 0) < 0}>{formatTrackingReturn(test.metrics.max_drawdown)}</strong></div>
        <div class="stat">
          <span>{test.benchmark}</span>
          <strong class={returnTone(test.metrics.benchmark_total_return)}>{formatTrackingReturn(test.metrics.benchmark_total_return)}</strong>
          <small>excess {formatTrackingReturn(test.metrics.excess_total_return)}</small>
        </div>
      </div>
      <TimeSeriesChart series={testSeries} height={160} showLegend emptyMessage="No curve" />
    {:else}
      <p class="snapshot-empty">{canRun ? "No backtest yet. Run one to freeze it here with its date and window." : "Add legs to backtest the idea."}</p>
    {/if}
  </section>

  <section class="snapshot" aria-label="Risk snapshot">
    <div class="snapshot-head">
      <strong>Risk</strong>
      {#if risk}
        {#if risk.source !== "idea_legs"}<span class="tag accent" title={risk.source_ids.attached_label ?? ""}>From {risk.source === "risk_tab" ? "Risk" : "Strategy Lab"}</span>{/if}
        {#if risk.stale_reason}<span class="tag warning" title={risk.stale_reason}>Stale</span>{/if}
        <span class="header-meta">{formatIdeaInstant(risk.created_at)} · {snapshotWindowText(risk)} · {Math.round(risk.alpha * 100)}%, 1 day</span>
        <ProvenanceBadge data={risk.provenance ? toProvenanceBadge({ ...risk.provenance, warnings: risk.warnings }) : null} variant="dot" />
      {/if}
    </div>
    {#if risk}
      <div class="snapshot-stats">
        <div class="stat"><span>VaR, historical</span><strong class:negative={risk.metrics.historical_var != null} class:absent={risk.metrics.historical_var == null}>{formatTrackingReturn(asLoss(risk.metrics.historical_var))}</strong></div>
        <div class="stat"><span>Expected shortfall</span><strong class:negative={risk.metrics.historical_es != null} class:absent={risk.metrics.historical_es == null}>{formatTrackingReturn(asLoss(risk.metrics.historical_es))}</strong></div>
        <div class="stat"><span>VaR, parametric</span><strong class:negative={risk.metrics.parametric_var != null} class:absent={risk.metrics.parametric_var == null}>{formatTrackingReturn(asLoss(risk.metrics.parametric_var))}</strong></div>
        <div class="stat"><span>Volatility</span><strong class:absent={risk.metrics.annual_volatility == null}>{formatTrackingReturn(risk.metrics.annual_volatility).replace("+", "")}</strong></div>
        <div class="stat"><span>Beta</span><strong class:absent={risk.metrics.beta == null}>{formatRatio(risk.metrics.beta)}</strong></div>
        <div class="stat">
          <span>Worst replayed episode</span>
          <strong class={returnTone(worst?.book_return)} class:absent={!worst}>{worst ? formatTrackingReturn(worst.book_return) : "N/A"}</strong>
          <small>{worst ? (worst.status === "full" ? worst.label : `${worst.label} · ${episodeCoverageText(worst).toLowerCase()}`) : "No episode in the available history"}</small>
        </div>
      </div>
      {#if shownEpisodes.length}
        <div class="table-scroll">
          <table class="data-table is-compact episodes-table">
            <thead><tr><th>Episode</th><th class="num">Window</th><th class="num">Book</th><th class="num">{risk.benchmark}</th><th>Coverage</th></tr></thead>
            <tbody>
              {#each shownEpisodes as episode (episode.episode_id)}
                <tr>
                  <td>{episode.label}</td>
                  <td class="num">{episode.start} → {episode.end}</td>
                  <td class="num {returnTone(episode.book_return)}">{formatTrackingReturn(episode.book_return)}</td>
                  <td class="num {returnTone(episode.benchmark_return)}">{formatTrackingReturn(episode.benchmark_return)}</td>
                  <td>{episodeCoverageText(episode)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    {:else}
      <p class="snapshot-empty">{canRun ? "No risk snapshot yet. Run one to freeze VaR, expected shortfall and the stress replay here." : "Add legs to check the idea's risk."}</p>
    {/if}
  </section>
</article>

<style>
  .title-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    min-width: 0;
  }

  .analysis-error {
    margin: 0;
    padding: 0 var(--space-5) var(--space-2);
    color: var(--negative);
    font-size: var(--text-xs);
  }

  .snapshot {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-2) 0 var(--space-4);
  }

  .snapshot + .snapshot {
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

  .header-meta {
    color: var(--text-2);
    font-size: var(--text-xs);
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

  .snapshot-empty {
    margin: 0;
    padding: 0 var(--space-5);
    color: var(--text-2);
    font-size: var(--text-sm);
  }

  .table-scroll {
    position: relative;
    overflow-x: auto;
  }

  .episodes-table {
    min-width: 30rem;
  }
</style>
