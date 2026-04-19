<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import type {
    CommodityCurveSnapshot,
    CommodityInventorySeries,
    CommodityMarketSummary,
    CommodityMode,
    CommodityPriceHistory,
    CommoditySpreadSnapshot,
    CommodityWorkspaceResponse
  } from "../lib/api/types";
  import type { CommodityWorkspaceLoadOptions } from "../lib/stores/app";

  export let workspace: CommodityWorkspaceResponse | null = null;
  export let loading = false;
  export let mode: CommodityMode = "overview";
  export let onLoadWorkspace: (options?: CommodityWorkspaceLoadOptions) => Promise<unknown> | void;

  const modes: Array<{ id: CommodityMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "energy", label: "Energy" },
    { id: "metals", label: "Metals" },
    { id: "curves_spreads", label: "Curves & Spreads" },
    { id: "inventories_fundamentals", label: "Inventories & Fundamentals" },
    { id: "events_cross_domain", label: "Events / Cross-Domain" }
  ];

  let selectedInstrumentId = "wti";

  $: if (workspace?.selected_instrument_id && workspace.selected_instrument_id !== selectedInstrumentId) {
    selectedInstrumentId = workspace.selected_instrument_id;
  }
  $: if (workspace?.mode && modes.some((item) => item.id === workspace?.mode)) {
    mode = workspace.mode as CommodityMode;
  }

  $: selectedSummary = findSelectedSummary(workspace, selectedInstrumentId);
  $: selectedHistory = findSelectedHistory(workspace, selectedInstrumentId);
  $: selectedCurve = findSelectedCurve(workspace, selectedInstrumentId);
  $: selectedInventory = findSelectedInventory(workspace, selectedInstrumentId);
  $: energySummaries = (workspace?.market_summaries ?? []).filter((summary) => summary.instrument.family === "energy");
  $: metalsSummaries = (workspace?.market_summaries ?? []).filter((summary) => summary.instrument.family === "metals");
  $: visibleSummaries = mode === "metals" ? metalsSummaries : mode === "energy" ? energySummaries : workspace?.market_summaries ?? [];
  $: priceSeries = buildPriceSeries(selectedHistory);
  $: curveSeries = buildCurveSeries(selectedCurve);
  $: visibleInventories = mode === "metals"
    ? []
    : mode === "overview" || mode === "energy" || mode === "inventories_fundamentals"
      ? workspace?.inventories ?? []
      : [];
  $: selectedEvents = (workspace?.events ?? []).filter(
    (event) => !selectedInstrumentId || event.linked_instrument_ids.includes(selectedInstrumentId)
  );

  onMount(() => {
    if (!workspace) {
      void onLoadWorkspace({ mode, selectedInstrumentId });
    }
  });

  async function refresh(nextMode = mode, forceRefresh = false) {
    await onLoadWorkspace({ mode: nextMode, selectedInstrumentId, forceRefresh });
  }

  async function selectMode(nextMode: CommodityMode) {
    mode = nextMode;
    await refresh(nextMode, false);
  }

  async function handleInstrumentChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    selectedInstrumentId = target.value;
    await refresh(mode, false);
  }

  function findSelectedSummary(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.market_summaries ?? []).find((summary) => summary.instrument.instrument_id === instrumentId) ?? null;
  }

  function findSelectedHistory(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.price_histories ?? []).find((history) => history.instrument_id === instrumentId) ?? null;
  }

  function findSelectedCurve(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.curves ?? []).find((curve) => curve.instrument_id === instrumentId) ?? null;
  }

  function findSelectedInventory(data: CommodityWorkspaceResponse | null, instrumentId: string) {
    return (data?.inventories ?? []).find((series) => series.metadata.instrument_id === instrumentId) ?? null;
  }

  function buildPriceSeries(history: CommodityPriceHistory | null): ChartSeries[] {
    if (!history?.points.length) {
      return [];
    }
    return [
      {
        id: history.instrument_id,
        label: history.label,
        color: "var(--chart-primary)",
        type: "area",
        data: history.points
          .map((point) => ({
            time: Math.floor(new Date(point.timestamp).getTime() / 1000),
            value: point.value
          }))
          .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      }
    ];
  }

  function buildCurveSeries(curve: CommodityCurveSnapshot | null): ChartSeries[] {
    if (!curve?.nodes.length) {
      return [];
    }
    const data = curve.nodes
      .map((node, index) => {
        const timestamp = node.contract.expiry_date
          ? Math.floor(new Date(node.contract.expiry_date).getTime() / 1000)
          : Math.floor(new Date(curve.as_of).getTime() / 1000) + (index + 1) * 30 * 24 * 60 * 60;
        return {
          time: timestamp,
          value: node.price ?? 0
        };
      })
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
    return [
      {
        id: `${curve.instrument_id}-curve`,
        label: `${curve.instrument_id.replace("_", " ").toUpperCase()} curve`,
        color: "var(--chart-secondary)",
        type: "line",
        data
      }
    ];
  }

  function formatNumber(value: number | null | undefined, digits = 2) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    return value.toLocaleString(undefined, {
      maximumFractionDigits: digits,
      minimumFractionDigits: Math.abs(value) < 10 && value !== 0 ? Math.min(digits, 2) : 0
    });
  }

  function formatPct(value: number | null | undefined, fromDecimal = true) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    const pct = fromDecimal ? value * 100 : value;
    return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
  }

  function formatPercentile(value: number | null | undefined) {
    if (value == null || Number.isNaN(value)) {
      return "N/A";
    }
    return `${value.toFixed(1)}%`;
  }

  function formatDate(value: string | null | undefined) {
    if (!value) {
      return "N/A";
    }
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  }

  function valueClass(value: number | null | undefined) {
    if (value == null) {
      return "";
    }
    if (value > 0) {
      return "positive";
    }
    if (value < 0) {
      return "negative";
    }
    return "";
  }

  function spreadUnit(spread: CommoditySpreadSnapshot) {
    return spread.definition.unit === "ratio" ? "x" : spread.definition.unit;
  }

  function inventoryValue(series: CommodityInventorySeries) {
    return `${formatNumber(series.latest_value, 2)} ${series.metadata.unit}`;
  }
</script>

<section class="view">
  <header class="workspace-header panel">
    <div>
      <p class="eyebrow">Commodities Research</p>
      <h1>Energy, metals, curves, inventories, and cross-domain context</h1>
      <p class="subtle">
        {workspace?.coverage.provider_label ?? "Sample Commodities Dataset"} | {workspace?.coverage.freshness_label ?? "loading"}
      </p>
    </div>
    <div class="header-actions">
      <label>
        Market
        <select bind:value={selectedInstrumentId} on:change={handleInstrumentChange} disabled={loading || !workspace}>
          {#each workspace?.instruments ?? [] as instrument}
            <option value={instrument.instrument_id}>{instrument.name}</option>
          {/each}
        </select>
      </label>
      <button type="button" on:click={() => refresh(mode, true)} disabled={loading}>
        {loading ? "Loading" : "Refresh"}
      </button>
    </div>
  </header>

  <nav class="mode-bar panel" aria-label="Commodities modes">
    {#each modes as item}
      <button
        type="button"
        class:active={mode === item.id}
        on:click={() => selectMode(item.id)}
        disabled={loading}
      >
        {item.label}
      </button>
    {/each}
  </nav>

  {#if workspace}
    <section class="kpi-strip">
      <article class="metric panel">
        <span>Selected</span>
        <strong>{selectedSummary?.instrument.symbol ?? selectedInstrumentId.toUpperCase()}</strong>
        <small>{selectedSummary?.instrument.quote_unit ?? "unit unavailable"}</small>
      </article>
      <article class="metric panel">
        <span>Last</span>
        <strong>{formatNumber(selectedSummary?.latest_price, 2)}</strong>
        <small class={valueClass(selectedSummary?.latest_change)}>
          {formatNumber(selectedSummary?.latest_change, 2)} | {formatPct(selectedSummary?.latest_change_pct)}
        </small>
      </article>
      <article class="metric panel">
        <span>Curve</span>
        <strong>{selectedCurve?.shape_label ?? selectedSummary?.curve_state ?? "unavailable"}</strong>
        <small>Front {formatNumber(selectedCurve?.front_spread, 3)}</small>
      </article>
      <article class="metric panel">
        <span>Roll Proxy</span>
        <strong>{formatPct(selectedCurve?.roll_yield_proxy_pct, false)}</strong>
        <small>Front spread annualized</small>
      </article>
      <article class="metric panel">
        <span>Inventory</span>
        <strong>{selectedInventory?.interpretation ?? "no linked series"}</strong>
        <small>{selectedInventory ? inventoryValue(selectedInventory) : "N/A"}</small>
      </article>
      <article class="metric panel">
        <span>Coverage</span>
        <strong>{workspace.coverage.coverage_status.replace("_", " ")}</strong>
        <small>{formatDate(workspace.coverage.source_timestamp ?? workspace.retrieved_at)}</small>
      </article>
    </section>

    {#if mode === "overview" || mode === "energy" || mode === "metals"}
      <section class="split">
        <article class="panel chart-panel">
          <div class="section-head">
            <div>
              <h2>{selectedSummary?.instrument.name ?? "Selected Market"} Price</h2>
              <p>{selectedHistory?.source_provider ?? "source unavailable"} | {selectedHistory?.transformation_note ?? "No transformation note."}</p>
            </div>
          </div>
          <TimeSeriesChart series={priceSeries} height={270} emptyMessage="No commodity price history" />
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Market Snapshot</h2>
              <p>Latest normalized price, curve state, and first linked fundamental signal.</p>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Last</th>
                  <th>Chg</th>
                  <th>Curve</th>
                  <th>Inventory</th>
                </tr>
              </thead>
              <tbody>
                {#each visibleSummaries as summary}
                  <tr class:selected={summary.instrument.instrument_id === selectedInstrumentId}>
                    <td>{summary.instrument.name}</td>
                    <td>{formatNumber(summary.latest_price, 2)}</td>
                    <td class={valueClass(summary.latest_change)}>{formatPct(summary.latest_change_pct)}</td>
                    <td>{summary.curve_state}</td>
                    <td>{summary.inventory_signal ?? "N/A"}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "overview" || mode === "energy" || mode === "curves_spreads"}
      <section class="split">
        <article class="panel chart-panel">
          <div class="section-head">
            <div>
              <h2>Curve</h2>
              <p>{selectedCurve?.summary ?? "Select a market with curve nodes."}</p>
            </div>
          </div>
          <TimeSeriesChart series={curveSeries} height={260} emptyMessage="No curve nodes" />
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Curve Nodes</h2>
              <p>Front contracts and changes from the normalized provider snapshot.</p>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Contract</th>
                  <th>Month</th>
                  <th>Price</th>
                  <th>Chg</th>
                </tr>
              </thead>
              <tbody>
                {#each selectedCurve?.nodes ?? [] as node}
                  <tr>
                    <td>{node.contract.symbol}</td>
                    <td>{node.contract.contract_month}</td>
                    <td>{formatNumber(node.price, 3)}</td>
                    <td class={valueClass(node.change)}>{formatNumber(node.change, 3)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    {/if}

    {#if mode === "overview" || mode === "curves_spreads" || mode === "metals" || mode === "energy"}
      <section class="panel">
        <div class="section-head">
          <div>
            <h2>Spreads</h2>
            <p>Calendar spreads, metal ratios, and product-crack proxies with z-score context where enough history exists.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Spread</th>
                <th>Value</th>
                <th>Change</th>
                <th>Z</th>
                <th>Percentile</th>
                <th>Interpretation</th>
              </tr>
            </thead>
            <tbody>
              {#each workspace.spreads as spread}
                <tr>
                  <td>
                    <strong>{spread.definition.label}</strong>
                    <span>{spread.definition.formula}</span>
                  </td>
                  <td>{formatNumber(spread.value, 3)} {spreadUnit(spread)}</td>
                  <td class={valueClass(spread.change)}>{formatNumber(spread.change, 3)}</td>
                  <td>{formatNumber(spread.z_score, 2)}</td>
                  <td>{formatPercentile(spread.percentile)}</td>
                  <td>{spread.interpretation ?? "N/A"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    {/if}

    {#if mode === "overview" || mode === "energy" || mode === "inventories_fundamentals"}
      <section class="inventory-grid">
        {#each visibleInventories as series}
          <article class="panel inventory-panel">
            <div>
              <h2>{series.metadata.label}</h2>
              <p>{series.metadata.source_provider} | {series.metadata.frequency}</p>
            </div>
            <dl>
              <div>
                <dt>Latest</dt>
                <dd>{inventoryValue(series)}</dd>
              </div>
              <div>
                <dt>Change</dt>
                <dd class={valueClass(series.latest_change)}>{formatNumber(series.latest_change, 2)}</dd>
              </div>
              <div>
                <dt>Percentile</dt>
                <dd>{formatPercentile(series.seasonal_percentile)}</dd>
              </div>
              <div>
                <dt>Signal</dt>
                <dd>{series.interpretation ?? "N/A"}</dd>
              </div>
            </dl>
          </article>
        {/each}
      </section>
    {/if}

    {#if mode === "overview" || mode === "events_cross_domain"}
      <section class="split">
        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Events</h2>
              <p>Official releases and sample watch items linked to the selected commodity universe.</p>
            </div>
          </div>
          <div class="note-list">
            {#each (selectedEvents.length ? selectedEvents : workspace.events) as event}
              <div class="note-row">
                <strong>{event.title}</strong>
                <span>{event.relative_label ?? event.category} | {formatDate(event.scheduled_at)}</span>
                <p>{event.summary}</p>
              </div>
            {/each}
          </div>
        </article>

        <article class="panel">
          <div class="section-head">
            <div>
              <h2>Cross-Domain</h2>
              <p>Heuristic handoffs into Macro, Prediction Markets, and Sealanes contexts.</p>
            </div>
          </div>
          <div class="note-list">
            {#each workspace.cross_domain_links as link}
              <div class="note-row">
                <strong>{link.target_label}</strong>
                <span>{link.target_domain} | confidence {formatNumber(link.confidence, 2)}</span>
                <p>{link.summary}</p>
              </div>
            {/each}
          </div>
        </article>
      </section>
    {/if}

    <footer class="panel provenance">
      <strong>Provenance</strong>
      <span>{workspace.source_provider} | {workspace.origin}</span>
      <span>{workspace.transformation_note}</span>
      {#if workspace.coverage.caveats.length}
        <ul>
          {#each workspace.coverage.caveats.slice(0, 4) as caveat}
            <li>{caveat}</li>
          {/each}
        </ul>
      {/if}
    </footer>
  {:else}
    <article class="panel empty-state">
      <h2>Loading Commodities</h2>
      <p>Gamma is preparing sample commodities research data.</p>
    </article>
  {/if}
</section>

<style>
  .view {
    display: grid;
    gap: 0.6rem;
    padding-bottom: 1rem;
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.85rem;
    min-width: 0;
  }

  .workspace-header {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
  }

  .workspace-header h1,
  .section-head h2,
  .inventory-panel h2,
  .empty-state h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 650;
    letter-spacing: 0;
    color: var(--text-0);
  }

  .eyebrow,
  .subtle,
  .section-head p,
  .inventory-panel p,
  .note-row span,
  .provenance span,
  td span,
  small {
    color: var(--text-2);
  }

  .eyebrow,
  .subtle,
  .section-head p,
  .inventory-panel p {
    margin: 0.25rem 0 0;
  }

  .header-actions {
    display: flex;
    align-items: end;
    gap: 0.5rem;
  }

  label {
    display: grid;
    gap: 0.25rem;
    color: var(--text-2);
  }

  select,
  button {
    min-height: 2rem;
    border: 1px solid var(--panel-strong);
    border-radius: 4px;
    background: transparent;
    color: var(--text-0);
    padding: 0.35rem 0.55rem;
  }

  button {
    cursor: pointer;
  }

  button:disabled,
  select:disabled {
    cursor: default;
    color: var(--text-2);
  }

  .mode-bar {
    display: flex;
    gap: 0.35rem;
    overflow-x: auto;
    padding: 0.45rem;
  }

  .mode-bar button {
    white-space: nowrap;
    color: var(--text-1);
  }

  .mode-bar button.active {
    border-color: var(--accent);
    color: var(--text-0);
    background: var(--surface-1);
  }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0.5rem;
  }

  .metric {
    display: grid;
    gap: 0.25rem;
    min-height: 6rem;
  }

  .metric span,
  dt {
    color: var(--text-2);
  }

  .metric strong {
    font-size: 1rem;
    font-weight: 650;
    letter-spacing: 0;
    word-break: break-word;
  }

  .split {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(21rem, 0.8fr);
    gap: 0.6rem;
  }

  .chart-panel {
    min-height: 22rem;
  }

  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .table-wrap {
    overflow: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.45rem 0.35rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    vertical-align: top;
  }

  th {
    color: var(--text-2);
    font-weight: 500;
  }

  td strong,
  td span {
    display: block;
  }

  tr.selected {
    background: var(--surface-1);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .inventory-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.6rem;
  }

  .inventory-panel {
    display: grid;
    gap: 0.7rem;
  }

  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.6rem;
    margin: 0;
  }

  dt,
  dd {
    margin: 0;
  }

  dd {
    margin-top: 0.2rem;
    color: var(--text-0);
  }

  .note-list {
    display: grid;
    gap: 0.55rem;
  }

  .note-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.55rem;
  }

  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .note-row strong,
  .note-row span {
    display: block;
  }

  .note-row p {
    margin: 0.3rem 0 0;
    color: var(--text-1);
  }

  .provenance {
    display: grid;
    gap: 0.35rem;
  }

  .provenance ul {
    margin: 0.25rem 0 0;
    padding-left: 1.1rem;
    color: var(--text-2);
  }

  .empty-state {
    min-height: 12rem;
  }

  @media (max-width: 1100px) {
    .kpi-strip,
    .inventory-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .split {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  @media (max-width: 720px) {
    .workspace-header,
    .header-actions {
      align-items: stretch;
      flex-direction: column;
    }

    .kpi-strip,
    .inventory-grid,
    dl {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
