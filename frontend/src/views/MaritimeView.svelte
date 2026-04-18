<script lang="ts">
  import { onMount } from "svelte";
  import type {
    MaritimeAisPosition,
    MaritimeChokepointSummary,
    MaritimeFlowSummary,
    MaritimeMode,
    MaritimeTrackSnippet,
    MaritimeVesselStatic,
    MaritimeWorkspaceResponse
  } from "../lib/api/types";
  import type { MaritimeLoadOptions } from "../lib/stores/app";

  export let workspace: MaritimeWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: MaritimeMode = "live_map";
  export let onLoadWorkspace: (options?: MaritimeLoadOptions) => Promise<unknown> | void;

  const modes: Array<{ id: MaritimeMode; label: string }> = [
    { id: "live_map", label: "Live Map" },
    { id: "chokepoints", label: "Chokepoints" },
    { id: "trade_flows", label: "Trade Flows" },
    { id: "fleet_monitoring", label: "Fleet / Vessel" },
    { id: "event_replay", label: "Event Replay" }
  ];

  const modeDescriptions: Record<MaritimeMode, string> = {
    live_map: "Latest sample positions, tracks, and coverage status.",
    chokepoints: "Strategic bottleneck density, commodity links, and method caveats.",
    trade_flows: "Class-based flow proxies with explicit cargo-inference limits.",
    fleet_monitoring: "Sample vessels and watchlists without risk or sanctions labels.",
    event_replay: "Historical/sample event windows and track snippets for replay work."
  };

  function coverageLabel(value: string | null | undefined) {
    const text = String(value ?? "unknown").replace(/_/g, " ");
    return text.toUpperCase();
  }

  function shortDate(value: string | null | undefined) {
    return value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";
  }

  function pct(value: number | null | undefined, digits = 0) {
    return value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  }

  function number(value: number | null | undefined, digits = 1) {
    return value == null ? "N/A" : value.toFixed(digits);
  }

  function vesselTypeLabel(value: string | null | undefined) {
    const labels: Record<string, string> = {
      dry_bulk: "Dry Bulk",
      lng_carrier: "LNG",
      product_tanker: "Products",
      tanker: "Tanker",
      container: "Container"
    };
    return labels[String(value ?? "")] ?? String(value ?? "Unknown").replace(/_/g, " ");
  }

  function byVesselId(vessels: MaritimeVesselStatic[]) {
    return Object.fromEntries(vessels.map((vessel) => [vessel.vessel_id, vessel]));
  }

  function vesselFor(position: MaritimeAisPosition) {
    return vesselIndex[position.vessel_id] ?? null;
  }

  function trackVessel(track: MaritimeTrackSnippet) {
    return vesselIndex[track.vessel_id] ?? null;
  }

  function typeCounts(positions: MaritimeAisPosition[]) {
    const counts = new Map<string, number>();
    for (const position of positions) {
      const vessel = vesselIndex[position.vessel_id];
      const key = vesselTypeLabel(vessel?.vessel_type);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((left, right) => right[1] - left[1]);
  }

  function summaryTone(summary: MaritimeChokepointSummary) {
    if ((summary.congestion_score ?? 0) >= 1.35) return "warning";
    if (summary.total_vessel_count <= 0) return "muted";
    return "";
  }

  function flowTone(flow: MaritimeFlowSummary) {
    const confidence = flow.inference_confidence ?? 0;
    if (confidence >= 0.6) return "positive";
    if (confidence < 0.5) return "warning";
    return "";
  }

  function modeFromWorkspace(value: string | null | undefined): MaritimeMode {
    return modes.some((item) => item.id === value) ? (value as MaritimeMode) : "live_map";
  }

  async function setMode(nextMode: MaritimeMode) {
    mode = nextMode;
    await onLoadWorkspace({ mode: nextMode });
  }

  async function refresh(forceRefresh = false) {
    await onLoadWorkspace({ mode, forceRefresh });
  }

  onMount(() => {
    if (!workspace) void refresh(false);
  });

  $: if (workspace?.mode) {
    mode = modeFromWorkspace(workspace.mode);
  }
  $: vesselIndex = byVesselId(workspace?.vessels ?? []);
  $: positions = workspace?.positions ?? [];
  $: chokepointSummaries = workspace?.chokepoint_summaries ?? [];
  $: flows = workspace?.flow_summaries ?? [];
  $: tracks = workspace?.tracks ?? [];
  $: watchlists = workspace?.watchlists ?? [];
  $: events = workspace?.event_windows ?? [];
  $: coverage = workspace?.coverage ?? null;
  $: activeChokepoints = chokepointSummaries.filter((summary) => summary.total_vessel_count > 0).length;
  $: typeLeaderboard = typeCounts(positions);
  $: headlineMetrics = [
    { label: "Coverage", value: coverageLabel(coverage?.coverage_status), meta: coverage?.provider_label ?? "No provider" },
    { label: "Positions", value: String(positions.length), meta: coverage?.freshness_label ? coverageLabel(coverage.freshness_label) : null },
    { label: "Chokepoints", value: `${activeChokepoints}/${chokepointSummaries.length}`, meta: "sample density" },
    { label: "Flows", value: String(flows.length), meta: "cargo inferred" }
  ];
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Maritime Intelligence</p>
        <div class="headline-title-row">
          <h2>Shipping Flow Research</h2>
          {#if loading}<span class="loading-pill">Refreshing</span>{/if}
          {#if coverage}<span class="coverage-badge">{coverageLabel(coverage.coverage_status)}</span>{/if}
        </div>
      </div>
      <div class="panel-actions">
        <button type="button" on:click={() => refresh(false)} disabled={loading}>{loading ? "Loading..." : "Reload"}</button>
        <button type="button" class="secondary" on:click={() => refresh(true)} disabled={loading}>Refresh</button>
      </div>
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Maritime modes">
        {#each modes as modeOption}
          <button class:selected={modeOption.id === mode} role="tab" aria-selected={modeOption.id === mode} type="button" on:click={() => setMode(modeOption.id)}>
            {modeOption.label}
          </button>
        {/each}
      </div>
      <div class="headline-strip">
        {#each headlineMetrics as metric}
          <div class="headline-kpi">
            <span class="headline-kpi-label">{metric.label}</span>
            <strong class="headline-kpi-value">{metric.value}</strong>
            {#if metric.meta}<small class="headline-kpi-meta">{metric.meta}</small>{/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="coverage-row">
      <p>{modeDescriptions[mode]}</p>
      <p>{coverage?.caveats?.[0] ?? "AIS provider evaluation is still unresolved; live global coverage is unavailable."}</p>
    </div>
  </article>

  {#if workspace?.warnings?.length}
    <article class="panel warning-panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow">Coverage</p>
          <h3>Interpretation Caveats</h3>
        </div>
        <small>{shortDate(workspace.retrieved_at)}</small>
      </div>
      <div class="notes-list">
        {#each workspace.warnings as warning}
          <div class="note-row">
            <span class="focus-label">Note</span>
            <p>{warning}</p>
          </div>
        {/each}
      </div>
    </article>
  {/if}

  {#if mode === "live_map"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Live Map</p>
              <h3>Latest Vessel Positions</h3>
            </div>
            <small>{coverage?.supports_live ? "Live provider" : "Sample / not live"}</small>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Vessel</th><th>Class</th><th>Status</th><th>Speed</th><th>Lat</th><th>Lon</th><th>Time</th></tr>
              </thead>
              <tbody>
                {#if positions.length}
                  {#each positions as position}
                    {@const vessel = vesselFor(position)}
                    <tr>
                      <td><div class="market-title"><strong>{vessel?.name ?? position.vessel_id}</strong><small>MMSI {position.mmsi}</small></div></td>
                      <td>{vessel?.vessel_class ?? "Unknown"}</td>
                      <td>{position.navigation_status ?? "N/A"}</td>
                      <td>{number(position.speed_knots)} kn</td>
                      <td>{number(position.latitude, 2)}</td>
                      <td>{number(position.longitude, 2)}</td>
                      <td>{shortDate(position.timestamp)}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="7">No vessel positions are available for the current coverage path.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Tracks</p>
              <h3>Route Snippets</h3>
            </div>
            <small>{tracks.length} snippets</small>
          </div>
          <div class="track-grid">
            {#each tracks as track}
              {@const vessel = trackVessel(track)}
              <div class="flat-row">
                <span class="focus-label">{vessel?.name ?? track.vessel_id}</span>
                <strong>{track.label}</strong>
                <p>{track.chokepoint_ids.length ? track.chokepoint_ids.join(", ") : "No named chokepoint"} | {track.points.length} points</p>
              </div>
            {/each}
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Fleet Mix</p>
              <h3>Sample Clustering</h3>
            </div>
          </div>
          <div class="focus-list">
            {#each typeLeaderboard as [label, count]}
              <div class="focus-row">
                <span class="focus-label">{label}</span>
                <strong>{count} vessels</strong>
                <p>Latest sample positions only.</p>
              </div>
            {/each}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Ports</p>
              <h3>Reference Nodes</h3>
            </div>
            <small>{workspace?.ports.length ?? 0} ports</small>
          </div>
          <div class="focus-list">
            {#each workspace?.ports ?? [] as port}
              <div class="focus-row">
                <span class="focus-label">{port.country}</span>
                <strong>{port.name}</strong>
                <p>{port.terminal_type ?? "Terminal"} | {port.commodity_links.join(", ") || "No commodity links"}</p>
              </div>
            {/each}
          </div>
        </article>
      </aside>
    </div>
  {:else if mode === "chokepoints"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Chokepoints</p>
              <h3>Bottleneck Density</h3>
            </div>
            <small>{coverageLabel(coverage?.coverage_status)}</small>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Chokepoint</th><th>Region</th><th>Vessels</th><th>Score</th><th>Label</th><th>Commodities</th></tr>
              </thead>
              <tbody>
                {#each chokepointSummaries as summary}
                  <tr>
                    <td><strong>{summary.name}</strong></td>
                    <td>{summary.region}</td>
                    <td>{summary.total_vessel_count}</td>
                    <td class={summaryTone(summary)}>{number(summary.congestion_score, 2)}</td>
                    <td>{summary.congestion_label}</td>
                    <td>{summary.commodity_links.join(", ")}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </div>
      <aside class="support-column">
        {#each chokepointSummaries.slice(0, 4) as summary}
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">{summary.region}</p>
                <h3>{summary.name}</h3>
              </div>
              <small>{summary.total_vessel_count} vessels</small>
            </div>
            <div class="focus-list">
              <div class="focus-row">
                <span class="focus-label">Method</span>
                <p>{summary.methodology}</p>
              </div>
              <div class="focus-row">
                <span class="focus-label">Mix</span>
                <p>{Object.entries(summary.vessel_count_by_type).map(([type, count]) => `${vesselTypeLabel(type)} ${count}`).join(" | ") || "No sample vessels"}</p>
              </div>
            </div>
          </article>
        {/each}
      </aside>
    </div>
  {:else if mode === "trade_flows"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Trade Flows</p>
              <h3>Commodity-Linked Movement</h3>
            </div>
            <small>Cargo inferred</small>
          </div>
          <div class="flow-grid">
            {#each flows as flow}
              <div class="flow-row">
                <div>
                  <span class="focus-label">{vesselTypeLabel(flow.vessel_type)}</span>
                  <strong>{flow.label}</strong>
                  <p>{flow.summary}</p>
                </div>
                <div class="flow-stats">
                  <strong>{flow.vessel_count}</strong>
                  <small>vessels</small>
                  <strong class={flowTone(flow)}>{pct(flow.inference_confidence)}</strong>
                  <small>confidence</small>
                </div>
              </div>
            {/each}
          </div>
        </article>
      </div>
      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Method</p>
              <h3>Cargo Inference</h3>
            </div>
          </div>
          <div class="focus-list">
            {#each flows.slice(0, 5) as flow}
              <div class="focus-row">
                <span class="focus-label">{flow.inferred_commodity ?? "Unknown"}</span>
                <p>{flow.inference_caveat}</p>
              </div>
            {/each}
          </div>
        </article>
      </aside>
    </div>
  {:else if mode === "fleet_monitoring"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Fleet / Vessel</p>
              <h3>Sample Vessel Registry</h3>
            </div>
            <small>No risk labels</small>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Vessel</th><th>Identifiers</th><th>Class</th><th>Flag</th><th>Inferred Cargo</th><th>Confidence</th></tr>
              </thead>
              <tbody>
                {#each workspace?.vessels ?? [] as vessel}
                  <tr>
                    <td><div class="market-title"><strong>{vessel.name}</strong><small>{vessel.vessel_type}</small></div></td>
                    <td><div class="market-title"><strong>MMSI {vessel.identity.mmsi}</strong><small>IMO {vessel.identity.imo ?? "N/A"}</small></div></td>
                    <td>{vessel.vessel_class}</td>
                    <td>{vessel.flag ?? "N/A"}</td>
                    <td>{vessel.cargo_inference ?? "N/A"}</td>
                    <td>{pct(vessel.cargo_inference_confidence)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </div>
      <aside class="support-column">
        {#each watchlists as watchlist}
          <article class="panel">
            <div class="panel-header">
              <div>
                <p class="eyebrow">Watchlist</p>
                <h3>{watchlist.label}</h3>
              </div>
              <small>{watchlist.vessel_ids.length} vessels</small>
            </div>
            <p class="muted">{watchlist.description}</p>
            <div class="focus-list">
              {#each watchlist.caveats as caveat}
                <div class="focus-row">
                  <span class="focus-label">Caveat</span>
                  <p>{caveat}</p>
                </div>
              {/each}
            </div>
          </article>
        {/each}
      </aside>
    </div>
  {:else}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Event Replay</p>
              <h3>Event Windows</h3>
            </div>
            <small>{events.length} windows</small>
          </div>
          <div class="event-grid">
            {#each events as event}
              <div class="event-row">
                <span class="focus-label">{event.region}</span>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
                <small>{shortDate(event.start_at)} to {shortDate(event.end_at)} | {event.linked_chokepoint_ids.join(", ")}</small>
              </div>
            {/each}
          </div>
        </article>
      </div>
      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Replay Inputs</p>
              <h3>Track Snippets</h3>
            </div>
          </div>
          <div class="focus-list">
            {#each tracks as track}
              <div class="focus-row">
                <span class="focus-label">{track.points.length} points</span>
                <strong>{track.label}</strong>
                <p>{track.chokepoint_ids.join(", ") || "No named chokepoint"}</p>
              </div>
            {/each}
          </div>
        </article>
      </aside>
    </div>
  {/if}
</section>

<style>
  .view,
  .primary-column,
  .support-column,
  .notes-list,
  .focus-list,
  .track-grid,
  .flow-grid,
  .event-grid {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(22rem, 0.8fr);
    gap: 0.5rem;
    align-items: start;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.9rem;
    display: grid;
    gap: 0.5rem;
  }

  .header-panel {
    gap: 0.35rem;
  }

  .header-top,
  .panel-header,
  .mode-kpi-row,
  .headline-title-row,
  .headline-strip,
  .panel-actions,
  .coverage-row,
  .flow-row {
    display: flex;
    gap: 0.5rem;
  }

  .header-top,
  .panel-header,
  .mode-kpi-row,
  .flow-row {
    justify-content: space-between;
    align-items: flex-start;
  }

  .headline-title-row,
  .headline-strip,
  .panel-actions,
  .coverage-row {
    flex-wrap: wrap;
    align-items: baseline;
  }

  .headline-block,
  .market-title,
  .flow-row > div,
  .event-row {
    min-width: 0;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(5, auto);
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.4rem 0.78rem;
    font: inherit;
    font-size: 0.78rem;
    white-space: nowrap;
    cursor: pointer;
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button:hover,
  button:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
  }

  .mode-bar button.selected {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  button {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-0);
    padding: 0.42rem 0.72rem;
    font: inherit;
    font-size: 0.78rem;
    cursor: pointer;
  }

  button.secondary {
    color: var(--text-1);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
    border-color: var(--panel-border);
  }

  .loading-pill,
  .coverage-badge {
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: 0.2rem 0.5rem;
    white-space: nowrap;
  }

  .coverage-badge {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 32%, transparent);
    background: color-mix(in srgb, var(--warning) 6%, transparent);
  }

  .headline-kpi {
    padding: 0.12rem 0.65rem 0.2rem 0.65rem;
    border-left: 1px solid var(--divider);
    text-align: right;
  }

  .headline-kpi:first-child {
    border-left: 0;
  }

  .headline-kpi-label,
  .eyebrow,
  .focus-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .headline-kpi-value {
    display: block;
    font-size: 0.9rem;
    line-height: 1.2;
  }

  .headline-kpi-meta,
  .muted,
  .focus-row p,
  .note-row p,
  .flat-row p,
  .flow-row p,
  .event-row p,
  small,
  .market-title small {
    color: var(--text-2);
    line-height: 1.35;
  }

  .coverage-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
  }

  .coverage-row p {
    margin: 0;
    color: var(--text-2);
  }

  .warning-panel {
    border-color: color-mix(in srgb, var(--warning) 28%, var(--panel-border));
  }

  .focus-row,
  .note-row,
  .flat-row,
  .event-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
    display: grid;
    gap: 0.12rem;
  }

  .focus-row:first-child,
  .note-row:first-child,
  .flat-row:first-child,
  .event-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .flow-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.55rem;
  }

  .flow-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .flow-stats {
    min-width: 7rem;
    text-align: right;
    display: grid;
    gap: 0.08rem;
  }

  .table-wrap {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: auto;
    max-height: 31rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  thead th {
    text-align: left;
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.6rem;
    padding: 0.45rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    position: sticky;
    top: 0;
    background: var(--bg-0);
    z-index: 1;
  }

  tbody td {
    padding: 0.5rem 0.55rem;
    border-top: 1px solid var(--divider);
    vertical-align: top;
  }

  h2,
  h3,
  p,
  small,
  strong {
    margin: 0;
  }

  h2 {
    font-size: 1rem;
  }

  h3 {
    font-size: 0.94rem;
  }

  .positive {
    color: var(--positive);
  }

  .warning {
    color: var(--warning);
  }

  .muted {
    color: var(--text-2);
  }

  @media (max-width: 1180px) {
    .workspace-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .mode-kpi-row,
    .header-top,
    .flow-row {
      flex-direction: column;
      align-items: stretch;
    }

    .mode-bar {
      width: 100%;
      grid-template-columns: 1fr;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }

    .mode-bar button:last-child {
      border-bottom: 0;
    }

    .headline-kpi {
      border-left: 0;
      border-top: 1px solid var(--divider);
      text-align: left;
      padding-left: 0;
    }

    .headline-kpi:first-child {
      border-top: 0;
    }
  }
</style>
