<script lang="ts">
  import { onMount } from "svelte";
  import TimeSeriesChart, { type ChartSeries } from "../components/TimeSeriesChart.svelte";
  import { parseApiTimestampToUtcSeconds } from "../lib/chart-data";
  import type {
    FundamentalsDcfModel,
    FundamentalsDcfScenario,
    FundamentalsFinancials,
    FundamentalsOverview,
    FundamentalsSearchResponse
  } from "../lib/api/types";
  import type {
    FundamentalsDcfSavePayload,
    FundamentalsSearchOptions,
    FundamentalsSelectOptions
  } from "../lib/stores/app";
  import {
    buildDcfSavePayload,
    createDcfDraft,
    findDcfScenario,
    normalizePeerTickers,
    parseEditableNumber,
    setDraftActiveScenario,
    statementViewForSelection,
    updateDraftAssumptionSeriesValue,
    updateDraftOverride,
    updateDraftScalarAssumption,
    type FundamentalsDcfDraft,
    type FundamentalsMode,
    type FundamentalsStatementBasis,
    type FundamentalsStatementKind
  } from "../lib/view-models/fundamentals";

  export let search: FundamentalsSearchResponse | null = null;
  export let selectedTicker: string | null = null;
  export let overview: FundamentalsOverview | null = null;
  export let financials: FundamentalsFinancials | null = null;
  export let dcfModel: FundamentalsDcfModel | null = null;
  export let loading = false;
  export let saving = false;
  export let onSearch: (options?: FundamentalsSearchOptions) => Promise<unknown> | void;
  export let onSelectCompany: (ticker: string, options?: FundamentalsSelectOptions) => Promise<unknown> | void;
  export let onSavePeerBasket: (ticker: string, peerTickers: string[]) => Promise<unknown> | void;
  export let onSaveDcfModel: (ticker: string, payload: FundamentalsDcfSavePayload) => Promise<unknown> | void;

  const modeOptions: Array<{ id: FundamentalsMode; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "financials", label: "Financials" },
    { id: "dcf", label: "DCF" }
  ];
  const statementOptions: Array<{ id: FundamentalsStatementKind; label: string }> = [
    { id: "income", label: "Income" },
    { id: "balance", label: "Balance Sheet" },
    { id: "cashflow", label: "Cash Flow" },
    { id: "ratios", label: "Ratios" }
  ];
  const basisOptions: Array<{ id: FundamentalsStatementBasis; label: string }> = [
    { id: "annual", label: "Annual" },
    { id: "quarterly", label: "Quarterly" }
  ];
  const familyLabels: Record<string, string> = {
    valuation: "Valuation",
    profitability: "Profitability",
    growth: "Growth",
    returns: "Returns",
    balance_sheet: "Balance Sheet"
  };

  let mode: FundamentalsMode = "overview";
  let searchQuery = "";
  let statementBasis: FundamentalsStatementBasis = "annual";
  let statementKind: FundamentalsStatementKind = "income";
  let peerDraftTickers: string[] = [];
  let peerDirty = false;
  let dcfDraft: FundamentalsDcfDraft = createDcfDraft(null);
  let dcfDirty = false;
  let peerFingerprint = "";
  let dcfFingerprint = "";

  const currency = (value: number | null | undefined, digits = 0) =>
    value == null
      ? "N/A"
      : new Intl.NumberFormat(undefined, {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: digits
        }).format(value);

  const compactCurrency = (value: number | null | undefined) => {
    if (value == null) return "N/A";
    const absolute = Math.abs(value);
    if (absolute >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`;
    if (absolute >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
    if (absolute >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    return currency(value, 0);
  };

  const pct = (value: number | null | undefined, digits = 1) =>
    value == null ? "N/A" : `${(value * 100).toFixed(digits)}%`;
  const shortDate = (value: string | null | undefined) =>
    value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "N/A";

  function toneClass(value: number | null | undefined) {
    if (value == null) return "";
    return value >= 0 ? "positive" : "negative";
  }

  function metricTone(metricId: string, value: number | null | undefined) {
    if (value == null) return "";
    if (metricId.includes("yield") || metricId.includes("margin") || metricId.includes("growth") || metricId === "roic" || metricId === "roe" || metricId === "cash_conversion") {
      return toneClass(value);
    }
    return "";
  }

  function editableValue(value: number | null | undefined, unit: string) {
    if (value == null) return "";
    if (unit === "percent") return (value * 100).toFixed(1);
    if (unit === "shares") return Math.round(value).toString();
    if (unit === "ratio") return value.toFixed(3);
    return value.toFixed(2);
  }

  function parseAssumptionInput(rawValue: string, unit: string) {
    const parsed = parseEditableNumber(rawValue);
    if (parsed == null) return null;
    return unit === "percent" ? parsed / 100 : parsed;
  }

  function projectionEditableValue(scenario: FundamentalsDcfScenario | null, lineKey: string, index: number) {
    const overrideValues = dcfDraft.scenarios[dcfDraft.activeScenarioId]?.overrides[lineKey] ?? [];
    const overrideValue = overrideValues[index];
    if (overrideValue != null) {
      return editableValue(overrideValue, "currency");
    }
    const row = scenario?.projection_rows.find((item) => item.line_key === lineKey);
    return editableValue(row?.values[index], row?.unit ?? "currency");
  }

  function assumptionSeriesValue(scenarioId: string, key: string, index: number) {
    const raw = dcfDraft.scenarios[scenarioId]?.assumptions[key];
    return Array.isArray(raw) ? (raw[index] as number | null | undefined) : null;
  }

  function scalarAssumptionValue(scenarioId: string, key: string) {
    const raw = dcfDraft.scenarios[scenarioId]?.assumptions[key];
    return typeof raw === "number" ? raw : null;
  }

  async function runSearch(forceRefresh = false) {
    await onSearch({
      query: searchQuery.trim() || undefined,
      limit: 12,
      forceRefresh
    });
  }

  async function chooseCompany(ticker: string, options: FundamentalsSelectOptions = {}) {
    await onSelectCompany(ticker, options);
  }

  function handleSearchKeydown(event: KeyboardEvent) {
    if (event.key === "Enter") {
      event.preventDefault();
      void runSearch(false);
    }
  }

  function togglePeer(ticker: string, checked: boolean) {
    const normalized = ticker.trim().toUpperCase();
    if (!normalized || normalized === overview?.company.ticker) return;
    peerDraftTickers = checked
      ? normalizePeerTickers(overview?.company.ticker ?? "", [...peerDraftTickers, normalized])
      : peerDraftTickers.filter((item) => item !== normalized);
    peerDirty = true;
  }

  async function savePeerBasket() {
    if (!overview) return;
    await onSavePeerBasket(overview.company.ticker, normalizePeerTickers(overview.company.ticker, peerDraftTickers));
    peerDirty = false;
  }

  function selectScenario(nextScenarioId: string) {
    dcfDraft = setDraftActiveScenario(dcfDraft, nextScenarioId);
    dcfDirty = true;
  }

  function handleAssumptionChange(key: string, unit: string, index: number, event: Event) {
    dcfDraft = updateDraftAssumptionSeriesValue(
      dcfDraft,
      dcfDraft.activeScenarioId,
      key,
      index,
      parseAssumptionInput((event.currentTarget as HTMLInputElement).value, unit)
    );
    dcfDirty = true;
  }

  function handleScalarChange(key: string, event: Event) {
    dcfDraft = updateDraftScalarAssumption(
      dcfDraft,
      dcfDraft.activeScenarioId,
      key,
      parseAssumptionInput((event.currentTarget as HTMLInputElement).value, "percent")
    );
    dcfDirty = true;
  }

  function handleProjectionOverrideChange(lineKey: string, index: number, event: Event) {
    dcfDraft = updateDraftOverride(
      dcfDraft,
      dcfDraft.activeScenarioId,
      lineKey,
      index,
      parseEditableNumber((event.currentTarget as HTMLInputElement).value)
    );
    dcfDirty = true;
  }

  async function saveDcfDraft() {
    if (!dcfModel) return;
    await onSaveDcfModel(dcfModel.ticker, buildDcfSavePayload(dcfDraft));
    dcfDirty = false;
  }

  onMount(() => {
    if (!search?.results?.length && !overview && !financials && !dcfModel) {
      void runSearch(false);
    }
  });

  $: if (overview?.company?.ticker && searchQuery.trim().length === 0) {
    searchQuery = overview.company.ticker;
  }

  $: {
    const nextPeerFingerprint = `${overview?.company.ticker ?? ""}:${overview?.peer_basket?.peer_tickers.join(",") ?? ""}`;
    if (nextPeerFingerprint !== peerFingerprint) {
      peerFingerprint = nextPeerFingerprint;
      peerDraftTickers = [...(overview?.peer_basket?.peer_tickers ?? [])];
      peerDirty = false;
    }
  }

  $: {
    const nextDcfFingerprint = JSON.stringify({
      ticker: dcfModel?.ticker ?? "",
      retrievedAt: dcfModel?.retrieved_at ?? "",
      activeScenarioId: dcfModel?.active_scenario_id ?? "",
      scenarioIds: dcfModel?.scenarios.map((scenario) => scenario.scenario_id) ?? []
    });
    if (nextDcfFingerprint !== dcfFingerprint) {
      dcfFingerprint = nextDcfFingerprint;
      dcfDraft = createDcfDraft(dcfModel);
      dcfDirty = false;
    }
  }

  $: currentCompany = overview?.company ?? financials?.company ?? null;
  $: headlineMetrics = overview?.headline_metrics ?? [];
  $: headlineStripMetrics = headlineMetrics.slice(0, 5);
  $: searchResults = search?.results ?? [];
  $: overviewWarnings = overview?.warnings ?? [];
  $: financialWarnings = financials?.warnings ?? [];
  $: dcfWarnings = dcfModel?.warnings ?? [];
  $: currentStatement = statementViewForSelection(financials, statementBasis, statementKind);
  $: currentRatioView = statementViewForSelection(financials, statementBasis, "ratios");
  $: activeScenario = findDcfScenario(dcfModel, dcfDraft.activeScenarioId);
  $: activeScenarioSummary = activeScenario?.summary ?? null;
  $: dcfSummaryRows = dcfModel?.scenarios.filter((scenario) => scenario.summary != null) ?? [];
  $: priceSeries = overview?.price_history?.length
    ? [
        {
          id: "price",
          label: `${overview.company.ticker} price`,
          color: "var(--chart-primary)",
          type: "area",
          data: overview.price_history
            .map((point) => ({ time: parseApiTimestampToUtcSeconds(point.timestamp), value: point.price }))
            .filter((point): point is { time: number; value: number } => point.time != null)
        }
      ] satisfies ChartSeries[]
    : [];
  $: groupedHeatmapRows = Object.entries(
    (overview?.peer_heatmap?.rows ?? []).reduce<Record<string, NonNullable<FundamentalsOverview["peer_heatmap"]>["rows"]>>((groups, row) => {
      const family = row.family ?? "other";
      groups[family] = [...(groups[family] ?? []), row];
      return groups;
    }, {})
  );
</script>

<section class="view">
  <article class="panel header-panel">
    <div class="header-top">
      <div class="headline-block">
        <p class="eyebrow">Fundamentals</p>
        <div class="headline-title-row">
          <h2>Fundamentals Research</h2>
          {#if loading}<span class="loading-pill">Refreshing</span>{/if}
          {#if saving}<span class="loading-pill secondary-pill">Saving</span>{/if}
        </div>
        <p class="subtitle">
          {#if currentCompany}
            {currentCompany.name} ({currentCompany.ticker}) {currentCompany.exchange ? `| ${currentCompany.exchange}` : ""}
          {:else}
            US SEC-filer research with filing-native statements, stable peer baskets, and Gamma-owned DCF logic.
          {/if}
        </p>
      </div>
      <div class="header-badges">
        {#each currentCompany?.classification_labels ?? [] as label}
          <span>{label}</span>
        {/each}
        {#if currentCompany?.latest_report_period}
          <span>Latest {shortDate(currentCompany.latest_report_period)}</span>
        {/if}
      </div>
    </div>

    <div class="mode-kpi-row">
      <div class="mode-bar" role="tablist" aria-label="Fundamentals modes">
        {#each modeOptions as option}
          <button class:selected={option.id === mode} role="tab" aria-selected={option.id === mode} type="button" on:click={() => (mode = option.id)}>
            {option.label}
          </button>
        {/each}
      </div>
      <div class="headline-strip">
        {#each headlineStripMetrics as metric}
          <div class="headline-kpi">
            <span class="headline-kpi-label">{metric.label}</span>
            <strong class="headline-kpi-value">{metric.display_value ?? "N/A"}</strong>
            {#if metric.value != null}
              <small class={`headline-kpi-meta ${metricTone(metric.metric_id, metric.value)}`}>{metric.source_provider}</small>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="search-strip">
      <label class="search-field filter-wide">
        <span>Company Search</span>
        <input bind:value={searchQuery} placeholder="AAPL, Microsoft, NVDA..." on:keydown={handleSearchKeydown} />
      </label>
      <button type="button" on:click={() => runSearch(false)} disabled={loading}>{loading ? "Loading..." : "Run Search"}</button>
      <button type="button" class="secondary" on:click={() => runSearch(true)} disabled={loading}>Refresh Search</button>
      {#if currentCompany}
        <button type="button" class="secondary" on:click={() => chooseCompany(currentCompany.ticker, { forceRefresh: true, resetThread: false })} disabled={loading}>
          Refresh {currentCompany.ticker}
        </button>
      {/if}
    </div>

    <div class="results-strip">
      {#if searchResults.length}
        {#each searchResults as result}
          <button type="button" class:result-chip={true} class:selected-chip={result.ticker === selectedTicker} on:click={() => chooseCompany(result.ticker)}>
            <strong>{result.ticker}</strong>
            <small>{result.name}</small>
          </button>
        {/each}
      {:else}
        <span class="muted">Search results will appear here once Gamma resolves a SEC-ticker match set.</span>
      {/if}
    </div>

    {#if overviewWarnings.length || financialWarnings.length || dcfWarnings.length}
      <div class="notes-list">
        {#each [...overviewWarnings, ...financialWarnings, ...dcfWarnings] as warning}
          <div class="note-row">
            <span class="focus-label">Note</span>
            <p>{warning}</p>
          </div>
        {/each}
      </div>
    {/if}
  </article>

  {#if mode === "overview"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Company</p>
              <h3>Profile</h3>
            </div>
            <small>{currentCompany?.cik ?? "No CIK"}</small>
          </div>

          <div class="profile-grid">
            <div class="profile-about">
              <span class="section-label">About</span>
              <p>{currentCompany?.description ?? "Select a company to load the SEC profile, filings, statements, and DCF context."}</p>
            </div>
            <div class="meta-flat">
              <div class="meta-row"><span>Exchange</span><strong>{currentCompany?.exchange ?? "N/A"}</strong></div>
              <div class="meta-row"><span>SIC</span><strong>{currentCompany?.sic_description ?? currentCompany?.sic ?? "N/A"}</strong></div>
              <div class="meta-row"><span>Filer Category</span><strong>{currentCompany?.filer_category ?? "N/A"}</strong></div>
              <div class="meta-row"><span>Fiscal Year End</span><strong>{currentCompany?.fiscal_year_end ?? "N/A"}</strong></div>
              <div class="meta-row"><span>Incorporation</span><strong>{currentCompany?.state_of_incorporation ?? "N/A"}</strong></div>
              <div class="meta-row"><span>Latest Reported</span><strong>{shortDate(currentCompany?.latest_report_period)}</strong></div>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Market Context</p>
              <h3>Price and Valuation</h3>
            </div>
            <small>{overview?.price_history?.length ?? 0} points</small>
          </div>

          {#if priceSeries.length}
            <div class="chart-panel">
              <TimeSeriesChart series={priceSeries} height={240} emptyMessage="No price history available." />
            </div>
          {:else}
            <div class="empty-panel">Price history appears once Gamma resolves the selected ticker through the IBKR-aware valuation path.</div>
          {/if}

          <div class="kpi-grid">
            {#each headlineMetrics.slice(0, 10) as metric}
              <div class="metric">
                <span>{metric.label}</span>
                <strong>{metric.display_value ?? "N/A"}</strong>
                <small>{metric.origin}</small>
              </div>
            {/each}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Comps</p>
              <h3>Peer Heatmap</h3>
            </div>
            <small>{overview?.peer_heatmap?.tickers.length ?? 0} companies</small>
          </div>

          <div class="table-wrap heatmap-wrap">
            <table>
              <thead>
                <tr>
                  <th>Family</th>
                  <th>Metric</th>
                  {#each overview?.peer_heatmap?.tickers ?? [] as ticker}
                    <th class:selected-col={ticker === currentCompany?.ticker}>{ticker}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if groupedHeatmapRows.length}
                  {#each groupedHeatmapRows as [family, rows]}
                    {#each rows as row, rowIndex}
                      <tr>
                        <td class="family-cell">{rowIndex === 0 ? (familyLabels[family] ?? family) : ""}</td>
                        <td>{row.label}</td>
                        {#each row.cells as cell}
                          <td class:selected-cell={cell.ticker === currentCompany?.ticker}>
                            <div class="heat-value">
                              <strong>{cell.display_value ?? "N/A"}</strong>
                              <small>{cell.source_provider}</small>
                            </div>
                          </td>
                        {/each}
                      </tr>
                    {/each}
                  {/each}
                {:else}
                  <tr><td colspan={(overview?.peer_heatmap?.tickers.length ?? 0) + 2}>Peer heatmap appears once Gamma can load the focal company and at least one comparable peer.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Research Object</p>
              <h3>Peer Basket</h3>
            </div>
            <small>{peerDraftTickers.length} peers selected</small>
          </div>

          <div class="builder-actions">
            <button type="button" class="secondary" on:click={savePeerBasket} disabled={!peerDirty || saving || !overview}>
              {saving ? "Saving..." : "Save Basket"}
            </button>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Use</th><th>Ticker</th><th>Reason</th><th>Exchange</th></tr>
              </thead>
              <tbody>
                {#if overview?.peer_candidates?.length}
                  {#each overview.peer_candidates as candidate}
                    <tr>
                      <td>
                        <input type="checkbox" checked={peerDraftTickers.includes(candidate.ticker)} on:change={(event) => togglePeer(candidate.ticker, (event.currentTarget as HTMLInputElement).checked)} />
                      </td>
                      <td><strong>{candidate.ticker}</strong><small>{candidate.name}</small></td>
                      <td>{candidate.reason ?? "N/A"}</td>
                      <td>{candidate.exchange ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">Peer candidates appear once Gamma loads a focal company.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">DCF</p>
              <h3>Scenario Summary</h3>
            </div>
            <small>{dcfSummaryRows.length} scenarios</small>
          </div>

          <div class="focus-list">
            {#if dcfSummaryRows.length}
              {#each dcfSummaryRows as scenario}
                <div class="focus-row compact-focus">
                  <span class="focus-label">{scenario.label}</span>
                  <strong class={toneClass(scenario.summary?.upside_downside_pct)}>{currency(scenario.summary?.implied_value_per_share, 2)}</strong>
                  <p>
                    EV {compactCurrency(scenario.summary?.enterprise_value)}
                    | Equity {compactCurrency(scenario.summary?.equity_value)}
                    | {pct(scenario.summary?.upside_downside_pct)}
                  </p>
                </div>
              {/each}
            {:else}
              <div class="focus-row compact-focus">
                <span class="focus-label">DCF</span>
                <strong>No model yet</strong>
                <p>The DCF workbench will populate once Gamma builds or restores a fundamentals model for the selected company.</p>
              </div>
            {/if}
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Source Trail</p>
              <h3>Filings and Provenance</h3>
            </div>
            <small>{overview?.filings?.length ?? 0} filings</small>
          </div>

          <div class="focus-list">
            <div class="focus-row compact-focus">
              <span class="focus-label">Company</span>
              <strong>{currentCompany?.source_provider ?? "N/A"}</strong>
              <p>{currentCompany?.origin ?? "No company context loaded."}</p>
            </div>
            <div class="focus-row compact-focus">
              <span class="focus-label">Price Context</span>
              <strong>{overview?.headline_metrics.find((metric) => metric.metric_id === "current_price")?.source_provider ?? "N/A"}</strong>
              <p>{overview?.headline_metrics.find((metric) => metric.metric_id === "current_price")?.origin ?? "No market context loaded."}</p>
            </div>
            <div class="focus-row compact-focus">
              <span class="focus-label">Derived Analytics</span>
              <strong>Gamma-owned</strong>
              <p>{overview?.peer_heatmap?.transformation_note ?? dcfModel?.transformation_note ?? "Derived values will describe their transformation note here."}</p>
            </div>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Form</th><th>Report</th><th>Filed</th><th>Amend</th></tr>
              </thead>
              <tbody>
                {#if overview?.filings?.length}
                  {#each overview.filings as filing}
                    <tr>
                      <td>{filing.form}</td>
                      <td>{shortDate(filing.report_period)}</td>
                      <td>{shortDate(filing.filing_date)}</td>
                      <td>{filing.is_amendment ? "Yes" : "No"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">Recent SEC filings appear here for the selected company.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </aside>
    </div>
  {:else if mode === "financials"}
    <div class="workspace-grid">
      <div class="primary-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Statement Viewer</p>
              <h3>{statementOptions.find((option) => option.id === statementKind)?.label ?? "Statement"}</h3>
            </div>
            <div class="panel-actions">
              <div class="mode-bar compact-bar">
                {#each basisOptions as option}
                  <button type="button" class:selected={option.id === statementBasis} on:click={() => (statementBasis = option.id)}>{option.label}</button>
                {/each}
              </div>
              <div class="mode-bar compact-bar statement-bar">
                {#each statementOptions as option}
                  <button type="button" class:selected={option.id === statementKind} on:click={() => (statementKind = option.id)}>{option.label}</button>
                {/each}
              </div>
            </div>
          </div>

          <div class="table-wrap statement-wrap">
            <table>
              <thead>
                <tr>
                  <th>Line Item</th>
                  {#each currentStatement?.periods ?? [] as period}
                    <th>
                      <div class="period-head">
                        <strong>{period.label}</strong>
                        <small>{period.form ?? "N/A"} | {shortDate(period.filing_date)}</small>
                      </div>
                    </th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if currentStatement?.lines?.length}
                  {#each currentStatement.lines as line}
                    <tr>
                      <td><div class="line-label"><strong>{line.label}</strong><small>{line.origin}</small></div></td>
                      {#each line.cells as cell}
                        <td><div class="cell-stack"><strong>{cell.display_value ?? "N/A"}</strong><small>{cell.concept_name ?? cell.form ?? "N/A"}</small></div></td>
                      {/each}
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan={(currentStatement?.periods.length ?? 0) + 1}>Statement data appears once Gamma loads a valid SEC-filer history for the selected ticker.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <aside class="support-column">
        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Ratios</p>
              <h3>{statementBasis === "annual" ? "Annual" : "Quarterly"} Trend Grid</h3>
            </div>
            <small>{currentRatioView?.lines.length ?? 0} rows</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ratio</th>
                  {#each currentRatioView?.periods ?? [] as period}
                    <th>{period.label}</th>
                  {/each}
                </tr>
              </thead>
              <tbody>
                {#if currentRatioView?.lines?.length}
                  {#each currentRatioView.lines as line}
                    <tr>
                      <td>{line.label}</td>
                      {#each line.cells as cell}
                        <td class={metricTone(line.line_key, cell.value)}>{cell.display_value ?? "N/A"}</td>
                      {/each}
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan={(currentRatioView?.periods.length ?? 0) + 1}>Ratio rows appear once Gamma derives the normalized statement history.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Chronology</p>
              <h3>Filing History</h3>
            </div>
            <small>{financials?.filings?.length ?? 0} filings</small>
          </div>

          <div class="table-wrap compact-wrap">
            <table>
              <thead>
                <tr><th>Form</th><th>Report</th><th>Filed</th><th>Accession</th></tr>
              </thead>
              <tbody>
                {#if financials?.filings?.length}
                  {#each financials.filings as filing}
                    <tr>
                      <td>{filing.form}</td>
                      <td>{shortDate(filing.report_period)}</td>
                      <td>{shortDate(filing.filing_date)}</td>
                      <td>{filing.accession_number ?? "N/A"}</td>
                    </tr>
                  {/each}
                {:else}
                  <tr><td colspan="4">Filing chronology appears once Gamma loads the SEC submission history.</td></tr>
                {/if}
              </tbody>
            </table>
          </div>
        </article>
      </aside>
    </div>
  {:else}
    <div class="dcf-shell">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Scenario Engine</p>
            <h3>Bear / Base / Bull</h3>
          </div>
          <div class="panel-actions">
            {#if dcfDirty}<span class="dirty-pill">Pending recalculation</span>{/if}
            <button type="button" on:click={saveDcfDraft} disabled={!dcfDirty || saving || !dcfModel}>{saving ? "Saving..." : "Recalculate + Save"}</button>
          </div>
        </div>

        <div class="scenario-strip">
          {#each dcfModel?.scenarios ?? [] as scenario}
            <button type="button" class:scenario-card={true} class:selected-scenario={scenario.scenario_id === dcfDraft.activeScenarioId} on:click={() => selectScenario(scenario.scenario_id)}>
              <span>{scenario.label}</span>
              <strong>{currency(scenario.summary?.implied_value_per_share, 2)}</strong>
              <small class={toneClass(scenario.summary?.upside_downside_pct)}>{pct(scenario.summary?.upside_downside_pct)}</small>
            </button>
          {/each}
        </div>

        <div class="summary-strip">
          <div class="summary-metric"><span>Current Price</span><strong>{currency(activeScenarioSummary?.current_price, 2)}</strong></div>
          <div class="summary-metric"><span>Enterprise Value</span><strong>{compactCurrency(activeScenarioSummary?.enterprise_value)}</strong></div>
          <div class="summary-metric"><span>Equity Value</span><strong>{compactCurrency(activeScenarioSummary?.equity_value)}</strong></div>
          <div class="summary-metric"><span>Implied / Share</span><strong>{currency(activeScenarioSummary?.implied_value_per_share, 2)}</strong></div>
          <div class="summary-metric"><span>Upside / Downside</span><strong class={toneClass(activeScenarioSummary?.upside_downside_pct)}>{pct(activeScenarioSummary?.upside_downside_pct)}</strong></div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Historical Block</p>
            <h3>Actuals</h3>
          </div>
          <small>{dcfModel?.historical_year_labels.length ?? 0} periods</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Line</th>
                {#each dcfModel?.historical_year_labels ?? [] as label}
                  <th>{label}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if dcfModel?.actual_rows?.length}
                {#each dcfModel.actual_rows as row}
                  <tr>
                    <td>{row.label}</td>
                    {#each row.display_values as value}
                      <td>{value ?? "N/A"}</td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.historical_year_labels.length ?? 0) + 1}>Historical actuals appear once Gamma can map enough annual SEC facts into the DCF history block.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Drivers</p>
            <h3>Scenario Assumptions</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"}</small>
        </div>

        <div class="scalar-grid">
          <label>
            <span>WACC %</span>
            <input value={editableValue(scalarAssumptionValue(dcfDraft.activeScenarioId, "wacc_pct"), "percent")} on:change={(event) => handleScalarChange("wacc_pct", event)} />
          </label>
          <label>
            <span>Terminal Growth %</span>
            <input value={editableValue(scalarAssumptionValue(dcfDraft.activeScenarioId, "terminal_growth_pct"), "percent")} on:change={(event) => handleScalarChange("terminal_growth_pct", event)} />
          </label>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Driver</th>
                {#each dcfModel?.projection_years ?? [] as year}
                  <th>{year}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if activeScenario?.assumption_rows?.length}
                {#each activeScenario.assumption_rows as row}
                  <tr>
                    <td><div class="line-label"><strong>{row.label}</strong><small>{row.origin}</small></div></td>
                    {#each dcfModel?.projection_years ?? [] as _year, index}
                      <td>
                        <input class="grid-input" value={editableValue(assumptionSeriesValue(dcfDraft.activeScenarioId, row.line_key, index), row.unit)} on:change={(event) => handleAssumptionChange(row.line_key, row.unit, index, event)} />
                      </td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.projection_years.length ?? 0) + 1}>Scenario assumption rows appear once Gamma builds the DCF model.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Projection Sheet</p>
            <h3>Working Scenario Line</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"} drives the visible projection sheet</small>
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Line</th>
                {#each dcfModel?.projection_years ?? [] as year}
                  <th>{year}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if activeScenario?.projection_rows?.length}
                {#each activeScenario.projection_rows as row}
                  <tr>
                    <td><div class="line-label"><strong>{row.label}</strong><small>{row.editable ? "Override-capable" : "Formula output"}</small></div></td>
                    {#each dcfModel?.projection_years ?? [] as _year, index}
                      <td class:overridden-cell={row.overridden[index]}>
                        {#if row.editable}
                          <input class="grid-input" value={projectionEditableValue(activeScenario, row.line_key, index)} on:change={(event) => handleProjectionOverrideChange(row.line_key, index, event)} />
                        {:else}
                          <div class="cell-stack"><strong>{row.display_values[index] ?? "N/A"}</strong><small>{row.origin}</small></div>
                        {/if}
                      </td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.projection_years.length ?? 0) + 1}>Projection rows appear once Gamma computes the active DCF scenario.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Sensitivity</p>
            <h3>WACC vs Terminal Growth</h3>
          </div>
          <small>{activeScenario?.label ?? "No scenario"}</small>
        </div>

        <div class="table-wrap compact-wrap">
          <table>
            <thead>
              <tr>
                <th>Terminal \\ WACC</th>
                {#each dcfModel?.sensitivity_matrix?.wacc_values ?? [] as wacc}
                  <th>{pct(wacc)}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if dcfModel?.sensitivity_matrix?.rows?.length}
                {#each dcfModel.sensitivity_matrix.rows as row, rowIndex}
                  <tr>
                    <td>{pct(dcfModel.sensitivity_matrix.terminal_growth_values[rowIndex])}</td>
                    {#each row as cell}
                      <td>{currency(cell.implied_value_per_share, 2)}</td>
                    {/each}
                  </tr>
                {/each}
              {:else}
                <tr><td colspan={(dcfModel?.sensitivity_matrix?.wacc_values.length ?? 0) + 1}>Sensitivity values appear once Gamma computes the active DCF scenario grid.</td></tr>
              {/if}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  {/if}
</section>

<style>
  .view,
  .primary-column,
  .support-column,
  .notes-list,
  .focus-list,
  .meta-flat {
    display: grid;
    gap: 0.5rem;
  }

  .view {
    gap: 0.5rem;
  }

  .dcf-shell {
    display: grid;
    gap: 0.5rem;
  }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.56fr) minmax(21rem, 0.94fr);
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
  .builder-actions,
  .panel-actions,
  .search-strip,
  .header-badges,
  .headline-strip,
  .scenario-strip {
    display: flex;
    gap: 0.5rem;
  }

  .header-top,
  .panel-header,
  .mode-kpi-row {
    justify-content: space-between;
    align-items: flex-start;
  }

  .headline-title-row,
  .header-badges,
  .headline-strip,
  .search-strip,
  .scenario-strip,
  .summary-strip,
  .results-strip {
    flex-wrap: wrap;
  }

  .headline-block {
    display: grid;
    gap: 0.12rem;
  }

  .subtitle,
  .muted,
  .metric small,
  .focus-row p,
  .meta-row span,
  .line-label small,
  .cell-stack small,
  .heat-value small {
    color: var(--text-2);
  }

  .header-badges span,
  .dirty-pill {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-1);
    padding: 0.18rem 0.45rem;
    font-size: 0.72rem;
    white-space: nowrap;
  }

  .dirty-pill {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 35%, var(--panel-strong));
  }

  .mode-bar {
    display: inline-grid;
    background: var(--surface-0);
    border: 1px solid var(--panel-strong);
    grid-template-columns: repeat(3, auto);
  }

  .compact-bar {
    grid-template-columns: repeat(2, auto);
  }

  .statement-bar {
    grid-template-columns: repeat(4, auto);
  }

  .mode-bar button,
  button,
  .result-chip,
  .scenario-card {
    border: 1px solid var(--panel-strong);
    background: var(--surface-0);
    color: var(--text-0);
    padding: 0.42rem 0.72rem;
    font: inherit;
    font-size: 0.78rem;
    cursor: pointer;
  }

  .mode-bar button {
    border: 0;
    border-right: 1px solid var(--panel-strong);
  }

  .mode-bar button:last-child {
    border-right: 0;
  }

  .mode-bar button.selected,
  .scenario-card.selected-scenario,
  .selected-chip {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .mode-bar button:hover,
  button:hover,
  .result-chip:hover,
  .scenario-card:hover {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--panel-strong));
  }

  button.secondary {
    color: var(--text-1);
  }

  button:disabled {
    cursor: not-allowed;
    color: var(--text-2);
    border-color: var(--panel-border);
  }

  .result-chip,
  .scenario-card {
    display: grid;
    gap: 0.12rem;
    text-align: left;
  }

  .scenario-card strong,
  .result-chip strong {
    font-size: 0.92rem;
  }

  .loading-pill {
    font-size: 0.64rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    padding: 0.2rem 0.5rem;
    white-space: nowrap;
  }

  .secondary-pill {
    color: var(--warning);
    border-color: color-mix(in srgb, var(--warning) 28%, transparent);
    background: color-mix(in srgb, var(--warning) 6%, transparent);
  }

  label,
  .search-field {
    display: grid;
    gap: 0.2rem;
  }

  .filter-wide {
    flex: 1 1 18rem;
  }

  input {
    border: 1px solid var(--panel-strong);
    background: var(--bg-1);
    color: var(--text-0);
    padding: 0.42rem 0.62rem;
    font: inherit;
    font-size: 0.82rem;
    min-height: 2rem;
  }

  .grid-input {
    min-width: 6rem;
    text-align: right;
    padding-inline: 0.4rem;
  }

  .scalar-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 12rem));
    gap: 0.5rem;
  }

  .eyebrow,
  .section-label,
  .focus-label,
  .headline-kpi-label,
  label > span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
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

  .headline-kpi {
    padding: 0.12rem 0.65rem 0.2rem 0.65rem;
    border-left: 1px solid var(--divider);
    text-align: right;
  }

  .headline-kpi:first-child {
    border-left: 0;
  }

  .headline-kpi-value {
    display: block;
    font-size: 0.9rem;
    line-height: 1.2;
  }

  .headline-kpi-meta {
    color: var(--text-2);
  }

  .profile-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
    gap: 0.75rem;
  }

  .profile-about,
  .meta-row,
  .focus-row,
  .note-row {
    display: grid;
    gap: 0.15rem;
  }

  .meta-row,
  .focus-row,
  .note-row {
    border-top: 1px solid var(--divider);
    padding-top: 0.45rem;
  }

  .meta-row:first-child,
  .focus-row:first-child,
  .note-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .chart-panel,
  .empty-panel {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    padding: 0.6rem;
  }

  .empty-panel {
    color: var(--text-2);
    min-height: 7rem;
    display: grid;
    place-items: center;
    text-align: center;
  }

  .kpi-grid,
  .summary-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
    gap: 0.4rem;
  }

  .metric,
  .summary-metric {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    padding: 0.55rem 0.65rem;
    display: grid;
    gap: 0.15rem;
  }

  .metric span,
  .summary-metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .metric strong,
  .summary-metric strong {
    font-size: 0.95rem;
  }

  .table-wrap {
    border: 1px solid var(--divider);
    background: var(--bg-0);
    overflow: auto;
    max-height: 30rem;
  }

  .compact-wrap {
    max-height: 18rem;
  }

  .heatmap-wrap {
    max-height: 34rem;
  }

  .statement-wrap {
    max-height: 42rem;
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

  .period-head,
  .line-label,
  .cell-stack,
  .heat-value {
    display: grid;
    gap: 0.12rem;
  }

  .family-cell {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .selected-col,
  .selected-cell {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
  }

  .overridden-cell {
    background: color-mix(in srgb, var(--warning) 7%, transparent);
  }

  .positive {
    color: var(--positive);
  }

  .negative {
    color: var(--negative);
  }

  @media (max-width: 1180px) {
    .workspace-grid,
    .profile-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .header-top,
    .mode-kpi-row,
    .panel-header,
    .search-strip {
      flex-direction: column;
      align-items: stretch;
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

    .mode-bar,
    .compact-bar,
    .statement-bar {
      width: 100%;
      grid-template-columns: 1fr;
    }

    .scalar-grid,
    .summary-strip {
      grid-template-columns: 1fr;
    }
  }
</style>
