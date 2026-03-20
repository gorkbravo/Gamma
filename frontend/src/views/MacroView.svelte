<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    MacroContextState,
    MacroDivergenceListResponse,
    MacroEventsResponse,
    MacroMode,
    MacroSeriesHistory,
    MacroSnapshot,
    MacroTheme,
  } from "../lib/api/types";
  import { macroContext, setMacroContext } from "../lib/stores/app";

  export let snapshot: MacroSnapshot | null = null;
  export let divergences: MacroDivergenceListResponse | null = null;
  export let events: MacroEventsResponse | null = null;
  export let histories: Record<string, MacroSeriesHistory> = {};
  export let loading = false;
  export let onLoadWorkspace: (options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;
  export let onLoadSeries: (seriesId: string, options?: Partial<MacroContextState> & { forceRefresh?: boolean }) => Promise<unknown> | void;

  const modes: Array<{ id: MacroMode; label: string }> = [
    { id: "snapshot", label: "Snapshot" },
    { id: "cross_asset", label: "Cross-Asset" },
    { id: "rates_policy", label: "Rates & Policy" },
  ];
  const themeLabels: Record<MacroTheme, string> = {
    all: "All",
    growth: "Growth",
    inflation: "Inflation",
    policy: "Policy",
    recession_risk: "Recession Risk",
  };
  const modeSeries: Record<MacroMode, string[]> = {
    snapshot: [],
    cross_asset: ["us-cpi-yoy", "us-5y-breakeven", "us-dollar-broad", "us-hy-oas"],
    rates_policy: ["us-fed-funds", "us-2y-yield", "us-10y-yield", "us-real-10y-yield", "us-5y-breakeven"],
  };

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null ? "N/A" : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "N/A";

  function historyKey(seriesId: string) {
    return `${$macroContext.region}:${$macroContext.timeframe}:${seriesId}`;
  }

  async function refreshContext(next: Partial<MacroContextState>) {
    setMacroContext(next);
    await onLoadWorkspace(next);
  }

  async function drillTo(mode: MacroMode, theme?: string | null) {
    await refreshContext({
      mode,
      ...(theme ? { theme: theme as MacroTheme } : {})
    });
  }

  async function ensureSeries(seriesIds: string[]) {
    for (const seriesId of seriesIds) {
      if (!histories[historyKey(seriesId)]) {
        await onLoadSeries(seriesId);
      }
    }
  }

  onMount(async () => {
    if (!snapshot) {
      await onLoadWorkspace();
    }
  });

  $: if ($macroContext.mode === "rates_policy") {
    void ensureSeries(modeSeries.rates_policy);
  }

  $: if ($macroContext.mode === "cross_asset") {
    void ensureSeries(modeSeries.cross_asset);
  }

  function chartFromSeries(seriesId: string, color: string): ChartSeries[] {
    const history = histories[historyKey(seriesId)];
    if (!history?.points?.length) {
      return [];
    }
    return [
      {
        id: seriesId,
        label: history.title,
        color,
        type: "line",
        data: history.points.map((point) => ({
          time: Math.floor(new Date(point.timestamp).getTime() / 1000),
          value: point.value
        }))
      }
    ];
  }

  $: ratesChart = [
    ...chartFromSeries("us-2y-yield", "#7aa6c8"),
    ...chartFromSeries("us-10y-yield", "#c49a5a"),
  ];
  $: inflationChart = [
    ...chartFromSeries("us-real-10y-yield", "#7aa6c8"),
    ...chartFromSeries("us-5y-breakeven", "#c49a5a"),
  ];
  $: crossAssetCards =
    $macroContext.theme === "all"
      ? snapshot?.cross_asset ?? []
      : (snapshot?.cross_asset ?? []).filter((row) => row.theme === $macroContext.theme);
  $: eventRows = events?.events ?? snapshot?.upcoming_events ?? [];
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="headline-block">
      <p class="eyebrow">Macro</p>
      <h2>Mode-driven research workspace</h2>
      <p class="muted">Shared context stays live while you move between Snapshot, Cross-Asset, and Rates & Policy.</p>
      {#if loading}
        <p class="eyebrow">Refreshing context</p>
      {/if}
    </div>

    <div class="mode-bar" role="tablist" aria-label="Macro modes">
      {#each modes as mode}
        <button
          class:selected={mode.id === $macroContext.mode}
          type="button"
          on:click={() => refreshContext({ mode: mode.id })}
        >
          {mode.label}
        </button>
      {/each}
    </div>

    <div class="context-bar">
      <label>
        <span>Region</span>
        <select value={$macroContext.region} on:change={(event) => refreshContext({ region: (event.currentTarget as HTMLSelectElement).value as MacroContextState["region"] })}>
          <option value="US">US</option>
          <option value="Global">Global</option>
        </select>
      </label>
      <label>
        <span>Timeframe</span>
        <select value={$macroContext.timeframe} on:change={(event) => refreshContext({ timeframe: (event.currentTarget as HTMLSelectElement).value as MacroContextState["timeframe"] })}>
          <option value="1M">1M</option>
          <option value="3M">3M</option>
          <option value="6M">6M</option>
          <option value="1Y">1Y</option>
        </select>
      </label>
      <label>
        <span>Theme</span>
        <select value={$macroContext.theme} on:change={(event) => refreshContext({ theme: (event.currentTarget as HTMLSelectElement).value as MacroTheme })}>
          {#each Object.entries(themeLabels) as [value, label]}
            <option value={value}>{label}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Compare</span>
        <select value={$macroContext.comparisonRegion ?? ""} on:change={(event) => refreshContext({ comparisonRegion: ((event.currentTarget as HTMLSelectElement).value || null) as MacroContextState["comparisonRegion"] })}>
          <option value="">None</option>
          <option value="Global">Global</option>
        </select>
      </label>
    </div>
  </article>

  {#if $macroContext.mode === "snapshot"}
    <div class="workspace-grid">
      {#each snapshot?.snapshot_cards ?? [] as card}
        <button class="panel card-panel clickable" type="button" on:click={() => drillTo(card.mode_target as MacroMode, card.target_theme)}>
          <div class="panel-header">
            <div>
              <small class="eyebrow">{themeLabels[(card.target_theme as MacroTheme) ?? "all"] ?? "Macro"}</small>
              <h3>{card.title}</h3>
            </div>
            <span class="tag">{card.mode_target.replace("_", " ")}</span>
          </div>
          <p class="muted">{card.subtitle}</p>
          <p>{card.summary}</p>
          <div class="metric-grid">
            {#each card.metrics as metric}
              <article class="metric">
                <span>{metric.label}</span>
                <strong>{metric.display_value ?? "N/A"}</strong>
                <small>{metric.delta_display ?? ""}</small>
              </article>
            {/each}
          </div>
        </button>
      {/each}
    </div>

    <div class="detail-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Divergences</p>
            <h3>Top ranked disagreements</h3>
          </div>
        </div>
        <div class="list">
          {#each snapshot?.top_divergences ?? [] as row}
            <button class="list-row" type="button" on:click={() => drillTo("cross_asset", row.theme)}>
              <strong>{row.headline}</strong>
              <span>{row.summary}</span>
            </button>
          {/each}
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Events</p>
            <h3>Upcoming macro calendar</h3>
          </div>
        </div>
        <div class="list">
          {#each eventRows as event}
            <div class="list-row static">
              <strong>{event.title}</strong>
              <span>{shortDate(event.scheduled_at)} | {event.category}</span>
            </div>
          {/each}
        </div>
      </article>
    </div>
  {:else if $macroContext.mode === "rates_policy"}
    <div class="detail-grid">
      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Rates & Policy</p>
            <h3>{snapshot?.rates_policy?.headline ?? "Rates context loading"}</h3>
          </div>
          <span class="tag">US-first</span>
        </div>
        <p class="muted">{snapshot?.rates_policy?.summary}</p>
        <div class="metric-grid">
          {#each snapshot?.rates_policy?.policy_metrics ?? [] as metric}
            <article class="metric">
              <span>{metric.label}</span>
              <strong>{metric.display_value}</strong>
              <small>{metric.delta_display}</small>
            </article>
          {/each}
        </div>
        <TimeSeriesChart series={ratesChart} height={320} emptyMessage="Loading rates history." />
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Curve</p>
            <h3>Current vs prior</h3>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Tenor</th>
              <th>Current</th>
              <th>Prior</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            {#each snapshot?.rates_policy?.curve_nodes ?? [] as node}
              <tr>
                <td>{node.tenor}</td>
                <td>{fmt(node.current_value)}</td>
                <td>{fmt(node.prior_value)}</td>
                <td>{node.change_bps == null ? "N/A" : `${node.change_bps.toFixed(0)} bps`}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Real Rates</p>
            <h3>Breakeven split</h3>
          </div>
        </div>
        <div class="metric-grid compact">
          {#each snapshot?.rates_policy?.real_yield_metrics ?? [] as metric}
            <article class="metric">
              <span>{metric.label}</span>
              <strong>{metric.display_value}</strong>
              <small>{metric.delta_display}</small>
            </article>
          {/each}
        </div>
        <TimeSeriesChart series={inflationChart} height={280} emptyMessage="Loading real-yield history." />
      </article>

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Calendar</p>
            <h3>Meeting and release context</h3>
          </div>
        </div>
        <div class="list">
          {#each snapshot?.rates_policy?.events ?? [] as event}
            <div class="list-row static">
              <strong>{event.title}</strong>
              <span>{shortDate(event.scheduled_at)} | {event.category}</span>
            </div>
          {/each}
        </div>
      </article>
    </div>
  {:else}
    <div class="detail-grid">
      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Cross-Asset</p>
            <h3>Do these markets agree?</h3>
          </div>
        </div>
        <div class="workspace-grid">
          {#each crossAssetCards as card}
            <article class="card-panel secondary">
              <div class="panel-header">
                <div>
                  <small class="eyebrow">{themeLabels[card.theme as MacroTheme] ?? card.theme}</small>
                  <h3>{card.headline}</h3>
                </div>
                <span class="tag">{card.agreement_label}</span>
              </div>
              <p class="muted">{card.summary}</p>
              <div class="metric-grid compact">
                {#each card.metrics as metric}
                  <article class="metric">
                    <span>{metric.label}</span>
                    <strong>{metric.display_value}</strong>
                    <small>{metric.delta_display}</small>
                  </article>
                {/each}
              </div>
            </article>
          {/each}
        </div>
      </article>

      <article class="panel span-2">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Ranked Divergences</p>
            <h3>Best research candidates</h3>
          </div>
        </div>
        <div class="list">
          {#each divergences?.divergences ?? [] as row}
            <div class="list-row static">
              <strong>{row.headline}</strong>
              <span>{row.summary}</span>
              <small>Score {row.score.toFixed(2)} | {row.label}</small>
            </div>
          {/each}
        </div>
      </article>
    </div>
  {/if}
</section>

<style>
  .view,
  .workspace-grid,
  .detail-grid,
  .metric-grid,
  .context-bar,
  .mode-bar,
  .list {
    display: grid;
    gap: 0.9rem;
  }

  .workspace-grid {
    grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
  }

  .detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .header-panel,
  .panel,
  .card-panel {
    border: 1px solid var(--panel-border);
    background: linear-gradient(180deg, rgba(12, 14, 16, 0.97), rgba(9, 10, 12, 0.95));
    padding: 1rem;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    gap: 0.8rem;
    align-items: start;
  }

  .context-bar {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .mode-bar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .mode-bar button,
  .context-bar select,
  .list-row,
  .clickable {
    cursor: pointer;
  }

  button,
  select {
    border: 1px solid var(--panel-strong);
    background: #0d0f12;
    color: var(--text-0);
    padding: 0.65rem 0.8rem;
    font: inherit;
    width: 100%;
  }

  .clickable {
    text-align: left;
  }

  .mode-bar button.selected,
  .tag {
    border-color: rgba(122, 166, 200, 0.36);
    background: rgba(122, 166, 200, 0.08);
  }

  .metric-grid {
    grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  }

  .metric {
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.62);
    padding: 0.8rem;
    min-width: 0;
  }

  .metric span,
  .eyebrow,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.66rem;
  }

  .list-row {
    display: grid;
    gap: 0.2rem;
    text-align: left;
    border: 1px solid rgba(46, 60, 74, 0.52);
    background: rgba(8, 13, 18, 0.62);
    padding: 0.8rem;
  }

  .list-row.static {
    cursor: default;
  }

  .span-2 {
    grid-column: span 2;
  }

  .tag,
  h2,
  h3,
  p,
  small {
    margin: 0;
  }

  .muted {
    color: var(--text-2);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.7rem 0.5rem;
    border-bottom: 1px solid rgba(46, 60, 74, 0.52);
    text-align: left;
  }

  @media (max-width: 1080px) {
    .detail-grid,
    .context-bar {
      grid-template-columns: 1fr;
    }

    .span-2 {
      grid-column: auto;
    }
  }
</style>
