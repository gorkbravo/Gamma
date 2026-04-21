<script lang="ts">
  import type { IvSessionStatus, IvSurface, SystemStatus, TimeSeriesPoint } from "../lib/api/types";
  import type { IvLoadOptions } from "../lib/stores/app";
  import {
    daysToExpiry,
    deriveDistributionBuckets,
    deriveRealizedVolatility,
    deriveSkewRows,
    deriveSurfacePaths,
    deriveSurfaceStats,
    deriveTermStructure,
    nearestStrikeIndex,
    optionsModes,
    type OptionsMode,
  } from "../lib/view-models/iv";

  export let mode: OptionsMode = "surface";
  export let status: SystemStatus | null = null;
  export let requestedSymbol = "SPY";
  export let result: IvSurface | null = null;
  export let session: IvSessionStatus | null = null;
  export let underlyingPricePoints: TimeSeriesPoint[] = [];
  export let loading = false;
  export let sessionLoading = false;
  export let onLoad: (options: IvLoadOptions) => void;
  export let onStartSession: (options: IvLoadOptions) => void;
  export let onStopSession: () => void;
  export let onRefreshSession: () => void;

  let symbol = "SPY";
  let marketDataMode = "delayed";
  let waitSeconds = 2.5;
  let selectedExpiry = 0;

  const fmt = (value: number | null | undefined, digits = 2) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : value.toLocaleString(undefined, { maximumFractionDigits: digits });
  const pct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const signedPct = (value: number | null | undefined, digits = 1) =>
    value == null || !Number.isFinite(value)
      ? "N/A"
      : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
  const shortTime = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "N/A";

  function submit() {
    onLoad({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode,
      waitSeconds
    });
  }

  function startSession() {
    onStartSession({
      symbol: symbol.trim().toUpperCase() || "SPY",
      marketDataMode
    });
  }

  function heatIntensity(value: number | null | undefined) {
    if (value == null || surfaceStats.minIv == null || surfaceStats.maxIv == null) {
      return 0;
    }
    const range = Math.max(surfaceStats.maxIv - surfaceStats.minIv, 0.01);
    return Math.max(0.12, Math.min(0.86, (value - surfaceStats.minIv) / range));
  }

  function toneClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function chooseMode(nextMode: OptionsMode) {
    mode = nextMode;
  }

  $: if (result && selectedExpiry >= result.expiries.length) {
    selectedExpiry = 0;
  }

  $: if (requestedSymbol && requestedSymbol !== symbol) {
    symbol = requestedSymbol;
  }

  let expiryRows: Array<{ expiry: string; values: number[] }> = [];
  let slice: { expiry: string; values: number[] } | undefined;
  let termStructure = deriveTermStructure(result);
  let atmStrikeIndex = nearestStrikeIndex(result);
  let surfaceStats = deriveSurfaceStats(result);
  let skewRows = deriveSkewRows(result);
  let surfacePaths = deriveSurfacePaths(result);
  let realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  let distributionBuckets = deriveDistributionBuckets(result);
  let maxDistributionProbability = 0;

  $: expiryRows = result?.expiries.map((expiry, index) => ({
    expiry,
    values: result.iv_grid[index] ?? []
  })) ?? [];
  $: slice = expiryRows[selectedExpiry];
  $: termStructure = deriveTermStructure(result);
  $: atmStrikeIndex = nearestStrikeIndex(result);
  $: surfaceStats = deriveSurfaceStats(result);
  $: skewRows = deriveSkewRows(result);
  $: surfacePaths = deriveSurfacePaths(result);
  $: realizedRows = deriveRealizedVolatility(underlyingPricePoints, surfaceStats.frontAtmIv);
  $: distributionBuckets = deriveDistributionBuckets(result);
  $: maxDistributionProbability = Math.max(...distributionBuckets.map((bucket) => bucket.probability), 0.01);
</script>

<section class="view">
  <div class="workspace-header">
    <div>
      <span class="eyebrow">OPTIONS</span>
      <h2>{result?.symbol ?? symbol}</h2>
    </div>
    <div class="action-row">
      <button on:click={submit} disabled={loading}>{loading ? "Loading..." : "Load Snapshot"}</button>
      <button on:click={startSession} disabled={sessionLoading}>{sessionLoading ? "Starting..." : "Start Session"}</button>
      <button on:click={onRefreshSession} disabled={sessionLoading}>Refresh Session</button>
      <button on:click={onStopSession} disabled={sessionLoading || !session?.running}>Stop Session</button>
    </div>
  </div>

  <div class="mode-kpi-row">
    <div class="mode-bar" role="tablist" aria-label="Options modes">
      {#each optionsModes as optionMode}
        <button
          class:selected={optionMode.id === mode}
          role="tab"
          aria-selected={optionMode.id === mode}
          type="button"
          on:click={() => chooseMode(optionMode.id)}
        >
          {optionMode.label}
        </button>
      {/each}
    </div>

    <div class="kpi-strip">
      <div><span>Spot</span><strong>{fmt(result?.spot, 2)}</strong></div>
      <div><span>Front ATM</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
      <div><span>Term Slope</span><strong class={toneClass(surfaceStats.termSlope)}>{signedPct(surfaceStats.termSlope)}</strong></div>
      <div><span>Points</span><strong>{surfaceStats.populatedPoints}</strong></div>
      <div><span>Freshness</span><strong>{result?.freshness_label ?? (result?.delayed ? "delayed" : "unknown")}</strong></div>
    </div>
  </div>

  <article class="panel controls-panel">
    <div class="field-grid">
      <label>
        <span>Symbol</span>
        <input bind:value={symbol} placeholder="SPY" />
      </label>
      <label>
        <span>Requested Mode</span>
        <select bind:value={marketDataMode}>
          <option value="delayed">Delayed</option>
          <option value="live">Live</option>
          <option value="auto">Auto</option>
        </select>
      </label>
      <label>
        <span>Wait</span>
        <select bind:value={waitSeconds}>
          <option value={1.5}>1.5s</option>
          <option value={2.5}>2.5s</option>
          <option value={4}>4.0s</option>
        </select>
      </label>
    </div>
    <div class="source-strip">
      <div><span>Backend</span><strong>{status?.market_data_mode ?? "unknown"}</strong></div>
      <div><span>Session</span><strong>{session?.running ? "running" : "idle"}</strong></div>
      <div><span>Provider</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
      <div><span>Updated</span><strong>{shortTime(result?.timestamp)}</strong></div>
    </div>
  </article>

  {#if mode === "surface"}
    <div class="workspace-grid surface-grid">
      <article class="panel surface-panel">
        <div class="panel-header">
          <div>
            <h3>Surface</h3>
            <p>{result?.expiries.length ?? 0} expiries x {result?.strikes.length ?? 0} strikes</p>
          </div>
          <strong>{surfaceStats.frontExpiry ?? "N/A"}</strong>
        </div>
        {#if surfacePaths.length}
          <svg class="surface-svg" viewBox="0 0 520 240" role="img" aria-label="Projected volatility surface">
            <line x1="32" y1="198" x2="472" y2="198" />
            <line x1="32" y1="198" x2="86" y2="106" />
            <line x1="472" y1="198" x2="526" y2="106" />
            {#each surfacePaths as path}
              <polyline
                points={path.points}
                style={`--path-alpha:${Math.round(Math.max(0.26, Math.min(0.92, (path.value ?? surfaceStats.averageIv ?? 0.1) / Math.max(surfaceStats.maxIv ?? 0.5, 0.01))) * 100)}%;`}
              />
            {/each}
          </svg>
        {:else}
          <p class="muted">No options surface loaded.</p>
        {/if}
      </article>

      <article class="panel heatmap-panel">
        <div class="panel-header">
          <div>
            <h3>Expiry / Strike Grid</h3>
            <p>Spot-relative strike column is marked at {fmt(surfaceStats.atmStrike, 2)}</p>
          </div>
        </div>
        {#if expiryRows.length}
          <div class="heatmap" style={`--strike-count:${result?.strikes.length ?? 1};`}>
            <div class="cell header">Expiry</div>
            {#each result?.strikes ?? [] as strike, strikeIndex}
              <div class="cell header" class:spot={strikeIndex === atmStrikeIndex}>{fmt(strike, 2)}</div>
            {/each}
            {#each expiryRows as row, rowIndex}
              <button class:active={selectedExpiry === rowIndex} class="cell expiry" on:click={() => (selectedExpiry = rowIndex)}>
                {row.expiry}
              </button>
              {#each row.values as value}
                <div class="cell data" style={`--heat:${Math.round(heatIntensity(value) * 72)}%;`}>
                  {pct(value)}
                </div>
              {/each}
            {/each}
          </div>
        {:else}
          <p class="muted">No options surface loaded.</p>
        {/if}
      </article>
    </div>

    <div class="detail-grid">
      <article class="panel">
        <h3>Selected Expiry Slice</h3>
        {#if slice}
          <div class="bar-list">
            {#each slice.values as value, index}
              <div class="bar-row">
                <span>{fmt(result?.strikes[index], 2)}</span>
                <div class="bar"><div class="fill" style={`width:${Math.min(value / Math.max(surfaceStats.maxIv ?? 1, 0.01), 1) * 100}%`}></div></div>
                <strong>{pct(value)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">Select an expiry after loading a surface.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>ATM Term Structure</h3>
        {#if termStructure.length}
          <div class="bar-list">
            {#each termStructure as point}
              <div class="bar-row">
                <span>{point.expiry}</span>
                <div class="bar"><div class="fill" style={`width:${Math.min((point.iv ?? 0) / Math.max(surfaceStats.maxIv ?? 1, 0.01), 1) * 100}%`}></div></div>
                <strong>{pct(point.iv)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">Load a surface to inspect ATM term structure.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Surface Context</h3>
        <div class="metric-list">
          <div><span>Selected Expiry</span><strong>{slice?.expiry ?? "N/A"}</strong></div>
          <div><span>ATM Strike</span><strong>{fmt(surfaceStats.atmStrike, 2)}</strong></div>
          <div><span>IV Range</span><strong>{pct(surfaceStats.minIv)} - {pct(surfaceStats.maxIv)}</strong></div>
          <div><span>Average IV</span><strong>{pct(surfaceStats.averageIv)}</strong></div>
        </div>
      </article>
    </div>
  {:else if mode === "skew_term"}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Skew By Expiry</h3>
        {#if skewRows.length}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Expiry</th>
                  <th>ATM</th>
                  <th>Put Wing</th>
                  <th>Call Wing</th>
                  <th>Put Skew</th>
                  <th>Call Skew</th>
                  <th>Wing Spread</th>
                </tr>
              </thead>
              <tbody>
                {#each skewRows as row}
                  <tr>
                    <td>{row.expiry}</td>
                    <td>{pct(row.atmIv)}</td>
                    <td>{fmt(row.putWingStrike, 2)} / {pct(row.putWingIv)}</td>
                    <td>{fmt(row.callWingStrike, 2)} / {pct(row.callWingIv)}</td>
                    <td class={toneClass(row.putSkew)}>{signedPct(row.putSkew)}</td>
                    <td class={toneClass(row.callSkew)}>{signedPct(row.callSkew)}</td>
                    <td class={toneClass(row.wingSpread)}>{signedPct(row.wingSpread)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">Load a surface to inspect skew.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Term Diagnostics</h3>
        <div class="metric-list">
          <div><span>Front Expiry</span><strong>{surfaceStats.frontExpiry ?? "N/A"}</strong></div>
          <div><span>Front DTE</span><strong>{surfaceStats.frontExpiry ? daysToExpiry(surfaceStats.frontExpiry) : 0}</strong></div>
          <div><span>Front ATM IV</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
          <div><span>Back ATM IV</span><strong>{pct(surfaceStats.backAtmIv)}</strong></div>
          <div><span>Back - Front</span><strong class={toneClass(surfaceStats.termSlope)}>{signedPct(surfaceStats.termSlope)}</strong></div>
        </div>
      </article>
    </div>
  {:else if mode === "realized_implied"}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Realized vs Implied</h3>
        {#if realizedRows.some((row) => row.realizedVol != null)}
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Window</th>
                  <th>Realized Vol</th>
                  <th>Front ATM IV</th>
                  <th>IV - RV</th>
                  <th>Obs</th>
                </tr>
              </thead>
              <tbody>
                {#each realizedRows as row}
                  <tr>
                    <td>{row.window}D</td>
                    <td>{pct(row.realizedVol)}</td>
                    <td>{pct(surfaceStats.frontAtmIv)}</td>
                    <td class={toneClass(row.spreadToFrontIv)}>{signedPct(row.spreadToFrontIv)}</td>
                    <td>{row.observationCount}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="muted">Run or open a single-ticker Research context to compare realized history against the loaded options surface.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Data Boundary</h3>
        <div class="metric-list">
          <div><span>Implied Source</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
          <div><span>Realized Source</span><strong>{underlyingPricePoints.length ? "Research price history" : "N/A"}</strong></div>
          <div><span>Price Points</span><strong>{underlyingPricePoints.length}</strong></div>
          <div><span>Surface Freshness</span><strong>{result?.freshness_label ?? "unknown"}</strong></div>
        </div>
      </article>
    </div>
  {:else if mode === "distribution"}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Front Expiry Distribution Proxy</h3>
        {#if distributionBuckets.length}
          <div class="distribution">
            {#each distributionBuckets as bucket}
              <div class="dist-row">
                <span>{bucket.label}</span>
                <div class="bar"><div class="fill" style={`width:${(bucket.probability / maxDistributionProbability) * 100}%`}></div></div>
                <strong>{pct(bucket.probability, 1)}</strong>
              </div>
            {/each}
          </div>
        {:else}
          <p class="muted">Load a surface with spot and front ATM IV to inspect the first-pass distribution proxy.</p>
        {/if}
      </article>

      <article class="panel">
        <h3>Assumptions</h3>
        <div class="metric-list">
          <div><span>Method</span><strong>Lognormal proxy</strong></div>
          <div><span>Expiry</span><strong>{surfaceStats.frontExpiry ?? "N/A"}</strong></div>
          <div><span>Vol Input</span><strong>{pct(surfaceStats.frontAtmIv)}</strong></div>
          <div><span>Caveat</span><strong>Not Breeden-Litzenberger RND</strong></div>
        </div>
      </article>
    </div>
  {:else}
    <div class="workspace-grid">
      <article class="panel">
        <h3>Provider Path</h3>
        <div class="metric-list">
          <div><span>Provider</span><strong>{result?.source_provider ?? "N/A"}</strong></div>
          <div><span>Origin</span><strong>{result?.origin ?? "N/A"}</strong></div>
          <div><span>Freshness</span><strong>{result?.freshness_label ?? "unknown"}</strong></div>
          <div><span>Delayed</span><strong>{result?.delayed == null ? "unknown" : result.delayed ? "yes" : "no"}</strong></div>
          <div><span>Retrieved</span><strong>{shortTime(result?.retrieved_at)}</strong></div>
        </div>
      </article>

      <article class="panel">
        <h3>Transformation</h3>
        <p class="note">{result?.transformation_note ?? "No surface transformation note available."}</p>
        <div class="warning-list">
          {#each result?.warnings ?? [] as warning}
            <div>{warning}</div>
          {/each}
          {#each result?.messages ?? [] as message}
            <div>{message}</div>
          {/each}
          {#if !(result?.warnings.length || result?.messages.length)}
            <div>No provider warnings for the active surface.</div>
          {/if}
        </div>
      </article>
    </div>
  {/if}
</section>

<style>
  .view,
  .workspace-grid,
  .detail-grid,
  .bar-list,
  .metric-list,
  .distribution,
  .warning-list {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-header,
  .mode-kpi-row,
  .panel-header,
  .action-row,
  .source-strip,
  .bar-row,
  .dist-row,
  .metric-list > div {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .workspace-header {
    align-items: end;
  }

  .workspace-grid {
    grid-template-columns: minmax(0, 1.45fr) minmax(18rem, 0.75fr);
    align-items: start;
  }

  .surface-grid {
    grid-template-columns: minmax(22rem, 0.9fr) minmax(0, 1.1fr);
  }

  .detail-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .panel {
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    padding: 0.75rem;
    min-width: 0;
  }

  .eyebrow,
  .panel p,
  span,
  .muted,
  th {
    color: var(--text-2);
  }

  .eyebrow,
  th {
    font-size: 0.68rem;
    text-transform: uppercase;
  }

  h2,
  h3,
  p {
    margin: 0;
  }

  h2 {
    font-size: 1.25rem;
  }

  h3 {
    font-size: 0.9rem;
  }

  strong {
    color: var(--text-0);
    font-weight: 650;
  }

  .mode-kpi-row {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .mode-bar {
    display: inline-grid;
    grid-template-columns: repeat(5, auto);
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
    background: transparent;
    color: var(--text-1);
    padding: 0.42rem 0.82rem;
    cursor: pointer;
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button:hover {
    background: rgba(122, 166, 200, 0.06);
    color: var(--text-0);
  }

  .mode-bar button.selected {
    background: rgba(122, 166, 200, 0.12);
    color: var(--accent);
  }

  .kpi-strip {
    display: grid;
    grid-template-columns: repeat(5, minmax(6rem, 1fr));
    border: 1px solid var(--panel-border);
    flex: 1;
  }

  .kpi-strip > div {
    padding: 0.38rem 0.58rem;
    border-right: 1px solid var(--divider);
    display: grid;
    gap: 0.12rem;
  }

  .kpi-strip > div:last-child {
    border-right: 0;
  }

  .controls-panel {
    display: grid;
    grid-template-columns: minmax(20rem, 0.9fr) minmax(0, 1.1fr);
    gap: 0.75rem;
    align-items: end;
  }

  .field-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 0.7fr;
    gap: 0.5rem;
  }

  label {
    display: grid;
    gap: 0.28rem;
  }

  input,
  select,
  button {
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
    color: var(--text-0);
    padding: 0.48rem 0.58rem;
    font: inherit;
    border-radius: 2px;
  }

  button {
    cursor: pointer;
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
  }

  .action-row {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .source-strip {
    flex-wrap: wrap;
    align-items: center;
  }

  .source-strip > div {
    min-width: 7rem;
    display: grid;
    gap: 0.12rem;
    text-align: right;
  }

  .surface-svg {
    width: 100%;
    min-height: 15rem;
    background: var(--bg-0);
    border: 1px solid var(--divider);
  }

  .surface-svg line {
    stroke: var(--divider);
    stroke-width: 1;
  }

  .surface-svg polyline {
    fill: none;
    stroke: color-mix(in srgb, var(--chart-primary) var(--path-alpha), var(--text-2));
    stroke-width: 1.1;
    vector-effect: non-scaling-stroke;
  }

  .heatmap {
    display: grid;
    grid-template-columns: 7rem repeat(var(--strike-count, 1), minmax(3.6rem, 1fr));
    gap: 0;
    overflow: auto;
    border: 1px solid var(--divider);
  }

  .cell {
    border-right: 1px solid var(--divider);
    border-bottom: 1px solid var(--divider);
    padding: 0.45rem 0.36rem;
    min-height: 2.35rem;
    text-align: center;
    white-space: nowrap;
  }

  .header {
    background: var(--surface-0);
    color: var(--text-2);
  }

  .spot {
    color: var(--warning);
  }

  .expiry {
    color: var(--text-1);
    border-radius: 0;
  }

  .expiry.active {
    color: var(--accent);
    background: rgba(122, 166, 200, 0.08);
  }

  .data {
    background: color-mix(in srgb, var(--chart-primary) var(--heat), var(--bg-0));
    color: var(--text-0);
    font-weight: 650;
  }

  .bar-row,
  .dist-row,
  .metric-list > div,
  .warning-list > div {
    align-items: center;
    border-top: 1px solid var(--divider);
    padding-top: 0.42rem;
  }

  .bar,
  .fill {
    height: 0.5rem;
  }

  .bar {
    flex: 1;
    min-width: 5rem;
    background: var(--surface-2);
  }

  .fill {
    background: var(--chart-primary);
  }

  .table-wrap {
    border: 1px solid var(--divider);
    overflow: auto;
    background: var(--bg-0);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th,
  td {
    padding: 0.48rem 0.55rem;
    border-bottom: 1px solid var(--divider);
    text-align: left;
    white-space: nowrap;
  }

  td {
    color: var(--text-1);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  .note {
    color: var(--text-1);
    line-height: 1.5;
  }

  @media (max-width: 1140px) {
    .workspace-header,
    .workspace-grid,
    .surface-grid,
    .detail-grid,
    .controls-panel,
    .field-grid,
    .mode-kpi-row {
      grid-template-columns: 1fr;
    }

    .workspace-header,
    .action-row,
    .source-strip {
      align-items: stretch;
      flex-direction: column;
    }

    .source-strip > div {
      text-align: left;
    }

    .kpi-strip,
    .mode-bar {
      grid-template-columns: 1fr;
    }

    .mode-bar button {
      border-right: 0;
      border-bottom: 1px solid var(--panel-strong);
    }

    .mode-bar button:last-child {
      border-bottom: 0;
    }
  }
</style>
