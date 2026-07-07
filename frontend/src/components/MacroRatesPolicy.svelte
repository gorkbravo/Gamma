<script lang="ts">
  import MacroLinkedMarketRow from "./MacroLinkedMarketRow.svelte";
  import MacroMetricRow from "./MacroMetricRow.svelte";
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroEvent,
    MacroSnapshot,
  } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;
  export let ratesChart: ChartSeries[] = [];
  export let inflationChart: ChartSeries[] = [];
  export let region: MacroContextState["region"] = "US";

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });

  function shortDate(value: string | null | undefined) {
    return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "N/A";
  }

  function deltaClass(display: string | null | undefined): string {
    if (!display) return "";
    const trimmed = display.trim();
    if (trimmed.startsWith("+") || trimmed.startsWith("▲")) return "positive";
    if (trimmed.startsWith("-") || trimmed.startsWith("−") || trimmed.startsWith("▼")) return "negative";
    return "";
  }

  function signalBadgeTone(label: string | null | undefined): string {
    if (label === "aligned" || label === "coherent") return "positive";
    if (label === "diverging" || label === "fractured") return "negative";
    if (label === "mixed" || label === "narrow") return "warning";
    return "";
  }

  function groupEventsByMonth<T extends { scheduled_at: string }>(evts: T[]): Array<{ label: string; events: T[] }> {
    const groups: Array<{ label: string; events: T[] }> = [];
    let current = "";
    for (const event of evts) {
      if (!event.scheduled_at) continue;
      const d = new Date(event.scheduled_at);
      const key = d.toLocaleString("en-US", { month: "long", year: "numeric" });
      if (key !== current) { current = key; groups.push({ label: key, events: [] }); }
      groups.at(-1)!.events.push(event);
    }
    return groups;
  }

  $: ratesPolicyTag = region === "EU" ? "EU-light" : "US-first";
  $: inflationPanelEyebrow = region === "EU" ? "Inflation / FX" : "Real Rates";
  $: inflationPanelTitle = region === "EU" ? "Inflation and currency proxy split" : "Breakeven split";
  $: inflationChartEmptyMessage = region === "EU" ? "Loading inflation and FX history." : "Loading real-yield history.";
  $: ratesPolicyGroupedEvents = groupEventsByMonth(snapshot?.rates_policy?.events ?? []);
</script>

<div class="rates-layout">
  <!-- Main Rates & Policy panel -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Rates & Policy</p>
        <h3>{snapshot?.rates_policy?.headline ?? "Rates context loading"}</h3>
      </div>
      <span class="tag region-tag">{ratesPolicyTag}</span>
    </div>
    <p class="section-summary">{snapshot?.rates_policy?.summary}</p>

    {#if snapshot?.rates_policy?.linked_markets?.length}
      <div class="linked-section">
        {#each snapshot.rates_policy.linked_markets as market}
          <MacroLinkedMarketRow {market} />
        {/each}
      </div>
    {/if}

    <MacroMetricRow metrics={snapshot?.rates_policy?.policy_metrics ?? []} />
    <TimeSeriesChart series={ratesChart} height={320} emptyMessage="Loading rates history." />
  </article>

  <!-- Path proxy -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Path Proxy</p>
        <h3>{snapshot?.rates_policy?.path_headline ?? "Front-end path proxy loading"}</h3>
      </div>
      {#if snapshot?.rates_policy?.market_alignment_label}
        <span class="tag info-tag">{snapshot.rates_policy.market_alignment_label}</span>
      {/if}
    </div>
    {#if snapshot?.rates_policy?.path_summary}
      <p class="section-summary">{snapshot.rates_policy.path_summary}</p>
    {/if}
    <MacroMetricRow metrics={snapshot?.rates_policy?.path_metrics ?? []} compact />
    {#if snapshot?.rates_policy?.path_research_focus}
      <p class="research-focus">{snapshot.rates_policy.path_research_focus}</p>
    {/if}

    {#if snapshot?.rates_policy?.expectation_summary || (snapshot?.rates_policy?.expectation_metrics ?? []).length}
      <div class="subsection">
        <div class="subsection-head">
          <span class="eyebrow">Expectation Overlay</span>
          {#if snapshot?.rates_policy?.market_alignment_label}
            <span class="tag {signalBadgeTone(snapshot.rates_policy.market_alignment_label)}">{snapshot.rates_policy.market_alignment_label}</span>
          {/if}
        </div>
        {#if snapshot?.rates_policy?.expectation_summary}
          <p class="section-summary">{snapshot.rates_policy.expectation_summary}</p>
        {/if}
        <MacroMetricRow metrics={snapshot?.rates_policy?.expectation_metrics ?? []} compact />
      </div>
    {/if}
  </article>

  <!-- Meeting Ladder -->
  {#if snapshot?.rates_policy?.meeting_path}
    <article class="panel span-2">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Meeting Ladder</p>
          <h3>{snapshot.rates_policy.meeting_path.headline}</h3>
        </div>
        <span class="tag info-tag">{snapshot.rates_policy.meeting_path.window_label}</span>
      </div>
      <p class="section-summary">{snapshot.rates_policy.meeting_path.summary}</p>
      <MacroMetricRow metrics={snapshot.rates_policy.meeting_path.metrics} compact />
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Meeting</th>
              <th>Date</th>
              <th>Implied policy</th>
              <th>Step</th>
              <th>Cumulative</th>
            </tr>
          </thead>
          <tbody>
            {#each snapshot.rates_policy.meeting_path.meetings as meeting}
              <tr>
                <td>{meeting.title}</td>
                <td>{shortDate(meeting.scheduled_at)}</td>
                <td>{meeting.implied_policy_rate_display ?? "N/A"}</td>
                <td class={deltaClass(meeting.incremental_change_display)}>{meeting.incremental_change_display ?? "N/A"}</td>
                <td class={deltaClass(meeting.cumulative_change_display)}>{meeting.cumulative_change_display ?? "N/A"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if snapshot.rates_policy.meeting_path.research_focus}
        <p class="research-focus">{snapshot.rates_policy.meeting_path.research_focus}</p>
      {/if}
    </article>
  {/if}

  <!-- Curve table -->
  <article class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Curve</p>
        <h3>Current vs prior</h3>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Tenor</th><th>Current</th><th>Prior</th><th>Delta</th></tr>
        </thead>
        <tbody>
          {#each snapshot?.rates_policy?.curve_nodes ?? [] as node}
            <tr>
              <td>{node.tenor}</td>
              <td>{fmt(node.current_value)}</td>
              <td>{fmt(node.prior_value)}</td>
              <td class="{node.change_bps != null && node.change_bps > 0 ? 'positive' : ''} {node.change_bps != null && node.change_bps < 0 ? 'negative' : ''}">{node.change_bps == null ? "N/A" : `${node.change_bps > 0 ? "+" : ""}${node.change_bps.toFixed(0)} bps`}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </article>

  <!-- Breakeven / Inflation split -->
  <article class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">{inflationPanelEyebrow}</p>
        <h3>{inflationPanelTitle}</h3>
      </div>
    </div>
    <MacroMetricRow metrics={snapshot?.rates_policy?.real_yield_metrics ?? []} compact />
    <TimeSeriesChart series={inflationChart} height={280} emptyMessage={inflationChartEmptyMessage} />
  </article>

  <!-- Calendar -->
  <article class="panel span-2">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Calendar</p>
        <h3>Meeting and release context</h3>
      </div>
    </div>
    {#if (snapshot?.rates_policy?.events ?? []).length}
      <div class="list events-scroll">
        {#each ratesPolicyGroupedEvents as group}
          <div class="date-group-header">{group.label}</div>
          {#each group.events as event}
            <div class="list-row">
              <strong>{event.title}</strong>
              <span class="list-detail">
                <span class="event-date">{shortDate(event.scheduled_at)}</span>
                <span class="event-category">{event.category}</span>
                <span class="event-category">{event.importance}</span>
              </span>
            </div>
          {/each}
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No upcoming rate events.</p>
    {/if}
  </article>
</div>

<style>
  .rates-layout {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* ── Panel ── */
  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: var(--space-5);
    display: grid;
    gap: var(--space-4);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: var(--space-5);
    align-items: start;
  }

  .panel-header > div { min-width: 0; }
  .span-2 { grid-column: span 2; }

  /* ── Text ── */
  .section-summary {
    color: var(--text-2);
    margin: 0;
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .research-focus {
    margin: 0;
    padding: var(--space-1) 0 var(--space-1) var(--space-4);
    border-left: 2px solid rgba(46, 60, 74, 0.35);
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  /* ── Subsections ── */
  .subsection {
    display: grid;
    gap: var(--space-3);
    padding-top: var(--space-3);
    border-top: 1px solid rgba(46, 60, 74, 0.26);
  }

  .subsection-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    align-items: center;
    flex-wrap: wrap;
  }

  /* ── Linked markets ── */
  .linked-section {
    display: grid;
    gap: 0;
  }

  /* ── Tags ── */
  .tag {
    display: inline-block;
    border: 1px solid rgba(122, 166, 200, 0.24);
    background: rgba(122, 166, 200, 0.06);
    color: var(--accent);
    padding: var(--space-1) var(--space-3);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .tag.positive {
    border-color: rgba(75, 180, 116, 0.25);
    background: rgba(75, 180, 116, 0.06);
    color: var(--positive);
  }

  .tag.negative {
    border-color: rgba(198, 107, 97, 0.32);
    background: rgba(198, 107, 97, 0.08);
    color: var(--negative);
  }

  .tag.warning {
    border-color: rgba(196, 154, 90, 0.32);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  .region-tag {
    border-color: rgba(196, 154, 90, 0.24);
    background: rgba(196, 154, 90, 0.06);
    color: var(--accent-2);
  }

  .info-tag {
    border-color: rgba(196, 154, 90, 0.24);
    background: rgba(196, 154, 90, 0.06);
    color: var(--accent-2);
  }

  /* ── Tables ── */
  .table-wrap { overflow: auto; }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th, td {
    padding: var(--space-4) var(--space-4);
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    text-align: left;
  }

  th {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--surface-0);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  tbody tr:nth-child(even) { background: rgba(122, 166, 200, 0.02); }

  .positive { color: var(--positive); }
  .negative { color: var(--negative); }

  /* ── Lists ── */
  .events-scroll {
    max-height: 24rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(122, 166, 200, 0.18) transparent;
  }

  .list-row {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
  }

  .list-row:first-child { padding-top: 0; }
  .list-row:last-child { border-bottom: 0; }

  .list-detail {
    color: var(--text-2);
    font-size: var(--text-sm);
    line-height: 1.35;
  }

  .event-date { color: var(--text-1); }

  .event-category {
    color: var(--text-2);
    margin-left: var(--space-3);
  }

  .event-category::before {
    content: "·";
    margin-right: var(--space-3);
    opacity: 0.5;
  }

  .date-group-header {
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: var(--space-4) var(--space-5) var(--space-2);
    background: var(--surface-soft);
    border-bottom: 1px solid rgba(46, 60, 74, 0.2);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .empty-hint {
    color: var(--text-2);
    font-size: var(--text-sm);
    margin: 0;
    padding: var(--space-3) 0;
  }

  /* ── Typography ── */
  .eyebrow {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: var(--text-2xs);
    margin: 0;
  }

  h3, p { margin: 0; }

  @media (max-width: 1080px) {
    .rates-layout { grid-template-columns: 1fr; }
    .span-2 { grid-column: auto; }
  }
</style>
