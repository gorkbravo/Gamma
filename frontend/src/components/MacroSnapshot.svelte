<script lang="ts">
  import MacroDivergenceCard from "./MacroDivergenceCard.svelte";
  import TimeSeriesChart, { type ChartSeries } from "./TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroEvent,
    MacroEventsResponse,
    MacroMode,
    MacroSnapshot,
    MacroSnapshotFocusItem,
    MacroTheme,
  } from "../lib/api/types";

  export let snapshot: MacroSnapshot | null = null;
  export let events: MacroEventsResponse | null = null;
  export let loading = false;
  export let fxChart1: ChartSeries[] = [];
  export let fxChart2: ChartSeries[] = [];
  export let fxChart3: ChartSeries[] = [];
  export let fxLast0: string | null = null;
  export let fxLast1: string | null = null;
  export let fxLast2: string | null = null;
  export let fxPairOptions: Array<{ id: string; label: string; seriesId: string }> = [];
  export let fxPair0 = "eurusd";
  export let fxPair1 = "gbpusd";
  export let fxPair2 = "usdjpy";
  export let maxSnapshotMetrics = 0;
  export let onDrillTo: (mode: MacroMode, theme?: string | null) => void;

  const themeLabels: Record<string, string> = {
    all: "All", growth: "Growth", inflation: "Inflation",
    policy: "Policy", recession_risk: "Recession Risk",
  };

  function deltaClass(display: string | null | undefined): string {
    if (!display) return "";
    const trimmed = display.trim();
    if (trimmed.startsWith("+") || trimmed.startsWith("▲")) return "positive";
    if (trimmed.startsWith("-") || trimmed.startsWith("−") || trimmed.startsWith("▼")) return "negative";
    return "";
  }

  function linkedMarketTone(label: string | null | undefined): string {
    if (label === "aligned") return "positive";
    if (label === "diverging") return "negative";
    return "";
  }

  function signalBadgeTone(label: string | null | undefined): string {
    if (label === "aligned" || label === "coherent") return "positive";
    if (label === "diverging" || label === "fractured") return "negative";
    if (label === "mixed" || label === "narrow") return "warning";
    return "";
  }

  function modeLabel(mode: string | null | undefined): string {
    if (!mode) return "Macro";
    return mode.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function focusTargetText(modeTarget: string, targetTheme: string | null | undefined): string {
    const tLabel = targetTheme ? themeLabels[targetTheme as MacroTheme] ?? targetTheme.replace(/_/g, " ") : null;
    return tLabel ? `${modeLabel(modeTarget)} · ${tLabel}` : modeLabel(modeTarget);
  }

  function shortDate(value: string | null | undefined) {
    return value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "N/A";
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

  $: snapshotFocusItems = snapshot?.focus_items ?? [];
  $: eventRows = events?.events ?? snapshot?.upcoming_events ?? [];
  $: groupedEvents = groupEventsByMonth(eventRows);
</script>

<!-- What Matters Now -->
{#if snapshotFocusItems.length}
  <article class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">What Matters Now</p>
        <h3>Actionable macro questions</h3>
      </div>
    </div>
    <div class="focus-grid">
      {#each snapshotFocusItems as item}
        <button class="focus-card" type="button" on:click={() => onDrillTo(item.mode_target as MacroMode, item.target_theme)}>
          <div class="focus-card-head">
            <strong>{item.title}</strong>
            {#if item.signal_label}
              <span class="tag {signalBadgeTone(item.signal_label)}">{item.signal_label}</span>
            {/if}
          </div>
          <p class="focus-summary">{item.summary}</p>
          <span class="focus-target">{focusTargetText(item.mode_target, item.target_theme)}</span>
        </button>
      {/each}
    </div>
  </article>
{/if}

<!-- Snapshot Theme Table -->
{#if (snapshot?.snapshot_cards ?? []).length}
  <article class="panel snapshot-table-panel">
    <div class="table-wrap">
      <table class="snapshot-table">
        <thead>
          <tr>
            <th class="col-theme">Theme</th>
            <th class="col-drill"></th>
            {#each Array.from({ length: maxSnapshotMetrics }) as _}
              <th class="col-metric"></th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each snapshot?.snapshot_cards ?? [] as card}
            <tr class="snapshot-row" tabindex="0" role="button" on:click={() => onDrillTo(card.mode_target as MacroMode, card.target_theme)} on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDrillTo(card.mode_target as MacroMode, card.target_theme); } }}>
              <td class="col-theme">
                <span class="row-theme">
                  {card.title}
                  {#if card.signal_label}
                    <span class="tag inline-tag {signalBadgeTone(card.signal_label)}">{card.signal_label}</span>
                  {/if}
                </span>
                <span class="row-summary">{card.summary}</span>
                {#if card.linked_markets?.length}
                  <span class="linked-hint">
                    <span class="linked-dot {linkedMarketTone(card.linked_markets[0].macro_alignment)}"></span>
                    {card.linked_markets.length} linked {card.linked_markets.length === 1 ? "market" : "markets"}
                    {#if card.linked_markets[0].macro_alignment}
                      · <span class={linkedMarketTone(card.linked_markets[0].macro_alignment)}>{card.linked_markets[0].macro_alignment}</span>
                    {/if}
                  </span>
                {/if}
              </td>
              <td class="col-drill">
                <span class="tag">{card.drilldown_label ?? modeLabel(card.mode_target)}</span>
              </td>
              {#each card.metrics as metric}
                <td class="col-metric">
                  <span class="metric-label" title={metric.label}>{metric.label}</span>
                  <strong class="metric-value" class:absent={metric.display_value == null}>{metric.display_value ?? "N/A"}</strong>
                  {#if metric.delta_display}
                    <small class="metric-delta {deltaClass(metric.delta_display)}">{metric.delta_display}</small>
                  {/if}
                </td>
              {/each}
              {#each Array.from({ length: maxSnapshotMetrics - card.metrics.length }) as _}
                <td class="col-metric"></td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </article>
{:else if !loading}
  <div class="panel empty-state">
    <p>No snapshot cards available for this configuration.</p>
  </div>
{/if}

<!-- FX Strip -->
<div class="fx-strip">
  <article class="panel fx-panel">
    <div class="fx-header">
      <small class="eyebrow">FX</small>
      <select class="fx-select" bind:value={fxPair0}>
        {#each fxPairOptions as pair}<option value={pair.id}>{pair.label}</option>{/each}
      </select>
      {#if fxLast0}<strong class="fx-last-price">{fxLast0}</strong>{/if}
    </div>
    <TimeSeriesChart series={fxChart1} height={160} emptyMessage="Loading FX data" />
  </article>
  <article class="panel fx-panel">
    <div class="fx-header">
      <small class="eyebrow">FX</small>
      <select class="fx-select" bind:value={fxPair1}>
        {#each fxPairOptions as pair}<option value={pair.id}>{pair.label}</option>{/each}
      </select>
      {#if fxLast1}<strong class="fx-last-price">{fxLast1}</strong>{/if}
    </div>
    <TimeSeriesChart series={fxChart2} height={160} emptyMessage="Loading FX data" />
  </article>
  <article class="panel fx-panel">
    <div class="fx-header">
      <small class="eyebrow">FX</small>
      <select class="fx-select" bind:value={fxPair2}>
        {#each fxPairOptions as pair}<option value={pair.id}>{pair.label}</option>{/each}
      </select>
      {#if fxLast2}<strong class="fx-last-price">{fxLast2}</strong>{/if}
    </div>
    <TimeSeriesChart series={fxChart3} height={160} emptyMessage="Loading FX data" />
  </article>
</div>

<!-- Bottom Row: Divergences + Events -->
<div class="detail-grid">
  <article class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Divergences</p>
        <h3>Top ranked disagreements</h3>
      </div>
    </div>
    {#if (snapshot?.top_divergences ?? []).length}
      <div class="list">
        {#each snapshot?.top_divergences ?? [] as row}
          <button class="list-row interactive" type="button" on:click={() => onDrillTo("cross_asset", row.theme)}>
            <MacroDivergenceCard
              headline={row.headline}
              summary={row.summary}
              score={row.score}
              label={row.label}
              theme={row.theme}
              coherence={row.coherence}
              compact
            />
          </button>
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No divergences detected for current context.</p>
    {/if}
  </article>

  <article class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">Events</p>
        <h3>Upcoming macro calendar</h3>
      </div>
    </div>
    {#if eventRows.length}
      <div class="list events-scroll">
        {#each groupedEvents as group}
          <div class="date-group-header">{group.label}</div>
          {#each group.events as event}
            <div class="list-row">
              <strong>{event.title}</strong>
              <span class="list-detail">
                <span class="event-date" class:absent={shortDate(event.scheduled_at) === "N/A"}>{shortDate(event.scheduled_at)}</span>
                <span class="event-category">{event.category}</span>
                <span class="event-category">{event.importance}</span>
              </span>
            </div>
          {/each}
        {/each}
      </div>
    {:else}
      <p class="empty-hint">No upcoming events for this region.</p>
    {/if}
  </article>
</div>

<style>
  /* ── Panels ── */

  .panel-header > div { min-width: 0; }

  /* ── Focus cards (What Matters Now) ── */
  .focus-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .focus-card {
    border: 1px solid rgba(46, 60, 74, 0.35);
    background: var(--surface-soft);
    color: inherit;
    font: inherit;
    padding: var(--space-5);
    display: grid;
    gap: var(--space-2);
    text-align: left;
    cursor: pointer;
    transition: background 120ms ease, border-color 120ms ease;
  }

  .focus-card:hover {
    background: rgba(122, 166, 200, 0.05);
    border-color: rgba(122, 166, 200, 0.28);
  }

  .focus-card:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .focus-card-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    align-items: center;
  }

  .focus-card-head strong {
    font-size: var(--text-base);
    line-height: 1.3;
  }

  .focus-summary {
    margin: 0;
    color: var(--text-1);
    font-size: var(--text-sm);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .focus-target {
    margin: 0;
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* ── Snapshot table ── */
  .snapshot-table-panel {
    padding: 0;
    overflow: hidden;
  }

  .table-wrap { overflow: auto; }

  .snapshot-table {
    width: 100%;
    border-collapse: collapse;
    /* Auto layout, not fixed: themes carry different numbers of metrics, and
       fixed layout padded every row out to the widest one and then split the
       width equally — so columns that were empty in most rows took the same
       89px as the ones carrying labels. */
    table-layout: auto;
  }

  .snapshot-table thead th {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid rgba(46, 60, 74, 0.4);
    color: var(--text-2);
    font-size: var(--text-2xs);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    background: var(--surface-0);
    position: sticky;
    top: 0;
    z-index: 1;
    text-align: left;
    font-weight: 500;
  }

  .snapshot-table .col-theme { width: 20%; min-width: 15rem; }
  .snapshot-table .col-drill { width: 11%; }
  .snapshot-table .col-metric {
    width: auto;
    min-width: 6.5rem;
  }

  .snapshot-row {
    cursor: pointer;
    transition: background 120ms ease;
  }

  .snapshot-row:hover { background: rgba(122, 166, 200, 0.05); }

  .snapshot-row:focus-visible {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .snapshot-row td {
    padding: var(--space-4) var(--space-4);
    border-bottom: 1px solid rgba(46, 60, 74, 0.25);
    vertical-align: top;
  }

  .snapshot-row:last-child td { border-bottom: 0; }

  .row-theme {
    display: block;
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--text-0);
    line-height: 1.3;
  }

  .inline-tag {
    margin-left: var(--space-3);
    vertical-align: middle;
  }

  .row-summary {
    display: block;
    color: var(--text-2);
    font-size: var(--text-xs);
    line-height: 1.3;
    margin-top: var(--space-1);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .col-drill { vertical-align: middle !important; }

  /* ── Linked market hint (compact) ── */
  .linked-hint {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
    color: var(--text-2);
    font-size: var(--text-2xs);
  }

  .linked-dot {
    display: inline-block;
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 50%;
    background: var(--text-2);
    flex-shrink: 0;
  }

  .linked-dot.positive { background: var(--positive); }
  .linked-dot.negative { background: var(--negative); }

  /* ── Metrics in snapshot table ── */
  .metric-label {
    /* A label cut to "US UNEMPL…" costs more than the row it saves. Two lines
       at --text-2xs, with the height reserved either way so values across the
       row stay on one baseline. */
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: var(--text-2xs);
    line-height: var(--leading-tight);
    min-height: calc(2em * 1.2);
    overflow: hidden;
  }

  .metric-value {
    display: block;
    font-size: var(--text-base);
    line-height: 1.2;
    margin-top: 0.08rem;
  }

  .metric-delta {
    display: inline-block;
    font-size: var(--text-xs);
    margin-top: 0.04rem;
    color: var(--text-2);
  }

  .metric-delta.positive { color: var(--positive); }
  .metric-delta.negative { color: var(--negative); }

  /* ── FX strip ── */
  .fx-strip {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .fx-panel {
    gap: 0;
    padding: 0;
    overflow: hidden;
  }

  .fx-header {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--divider);
    min-height: 28px;
    box-sizing: border-box;
  }

  .fx-panel :global(.chart-shell) {
    border: none;
  }

  .fx-last-price {
    margin-left: auto;
    font-size: var(--text-base);
    color: var(--text-0);
    letter-spacing: 0.02em;
  }

  .fx-select {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: var(--space-2) var(--space-3);
    font: inherit;
    font-size: var(--text-base);
    cursor: pointer;
    transition: border-color 120ms ease;
  }

  .fx-select:hover { border-color: rgba(122, 166, 200, 0.32); }
  .fx-select:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }

  /* ── Bottom grid ── */
  .detail-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  /* ── Lists ── */
  .list { display: grid; gap: 0; }

  .events-scroll {
    max-height: 24rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: rgba(122, 166, 200, 0.18) transparent;
  }

  .list-row {
    display: grid;
    gap: var(--space-1);
    text-align: left;
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    cursor: default;
  }

  .list-row:first-child { padding-top: 0; }
  .list-row:last-child { border-bottom: 0; }

  .list-row.interactive {
    cursor: pointer;
    border: 0;
    border-bottom: 1px solid rgba(46, 60, 74, 0.3);
    background: transparent;
    color: inherit;
    font: inherit;
    width: 100%;
    padding: var(--space-3) 0;
  }

  .list-row.interactive:hover { background: rgba(122, 166, 200, 0.04); }
  .list-row.interactive:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .list-row.interactive:last-child { border-bottom: 0; }

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
    border-color: rgba(196, 154, 90, 0.3);
    background: rgba(196, 154, 90, 0.08);
    color: var(--accent-2);
  }

  /* ── Empty states ── */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-7);
    color: var(--text-2);
  }

  .empty-state p { margin: 0; }

  .empty-hint {
    color: var(--text-2);
    font-size: var(--text-sm);
    margin: 0;
    padding: var(--space-3) 0;
  }

  /* ── Typography ── */

  h3, p, small { margin: 0; }

  .positive { color: var(--positive); }
  .negative { color: var(--negative); }

  /* ── Responsive ── */
  @media (max-width: 1080px) {
    .detail-grid { grid-template-columns: 1fr; }
    .focus-grid { grid-template-columns: 1fr; }
    .fx-strip { grid-template-columns: 1fr; }
  }
</style>
