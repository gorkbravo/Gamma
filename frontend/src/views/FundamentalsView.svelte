<script lang="ts">
  import { onMount } from "svelte";
  import SearchDropdown from "../components/SearchDropdown.svelte";
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
  const lowerBetterMetricIds = new Set(["ev_to_sales", "ev_to_ebit", "price_to_earnings", "net_debt_to_ebit"]);
  const positiveOnlyLowerBetterMetricIds = new Set(["ev_to_sales", "ev_to_ebit", "price_to_earnings"]);
  const marketContextMetricIds = ["current_price", "market_cap", "enterprise_value", "ev_to_sales", "ev_to_ebit", "net_debt", "diluted_shares"];

  export let mode: FundamentalsMode = "overview";
  let searchQuery = "";
  let statementBasis: FundamentalsStatementBasis = "annual";
  let statementKind: FundamentalsStatementKind = "income";
  let peerDraftTickers: string[] = [];
  let peerDirty = false;
  let dcfDraft: FundamentalsDcfDraft = createDcfDraft(null);
  let dcfDirty = false;
  let peerFingerprint = "";
  let dcfFingerprint = "";
  let searchHydratedTicker = "";

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

  function companySummary(company: FundamentalsOverview["company"] | FundamentalsFinancials["company"] | null) {
    if (!company) {
      return "Select a company to load the SEC profile, filings, statements, and DCF context.";
    }
    const description = String(company.description ?? "").trim();
    const syntheticDescription = [
      description.startsWith(company.name),
      description.includes("listed on"),
      description.includes("files as a"),
      description.includes(" in ")
    ].filter(Boolean).length >= 2;
    if (description && !syntheticDescription) {
      return description;
    }
    return "A proper business summary is not available in the current SEC-native company payload yet.";
  }

  function heatmapScore(metricId: string, value: number | null | undefined, rowValues: Array<number | null | undefined>) {
    if (value == null || !Number.isFinite(value)) {
      return null;
    }
    if (positiveOnlyLowerBetterMetricIds.has(metricId) && value <= 0) {
      return null;
    }
    const comparableValues = rowValues.filter((candidate): candidate is number => {
      if (candidate == null || !Number.isFinite(candidate)) {
        return false;
      }
      if (positiveOnlyLowerBetterMetricIds.has(metricId)) {
        return candidate > 0;
      }
      return true;
    });
    if (comparableValues.length < 2) {
      return 0.5;
    }
    const minimum = Math.min(...comparableValues);
    const maximum = Math.max(...comparableValues);
    if (minimum === maximum) {
      return 0.5;
    }
    const scaled = (value - minimum) / (maximum - minimum);
    return lowerBetterMetricIds.has(metricId) ? 1 - scaled : scaled;
  }

  function heatmapCellClass(metricId: string, value: number | null | undefined, rowValues: Array<number | null | undefined>) {
    const score = heatmapScore(metricId, value, rowValues);
    if (score == null) return "heat-neutral";
    if (score >= 0.88) return "heat-positive-strong";
    if (score >= 0.72) return "heat-positive";
    if (score >= 0.58) return "heat-positive-soft";
    if (score >= 0.42) return "heat-warning";
    if (score >= 0.28) return "heat-negative-soft";
    if (score >= 0.14) return "heat-negative";
    return "heat-negative-strong";
  }

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

  function sensitivityHeatClass(value: number | null | undefined, range: { min: number; max: number }) {
    if (value == null || !Number.isFinite(value)) return "";
    if (range.max === range.min) return "sens-heat-mid";
    const t = (value - range.min) / (range.max - range.min);
    if (t >= 0.85) return "sens-heat-pos-strong";
    if (t >= 0.6) return "sens-heat-pos";
    if (t >= 0.4) return "sens-heat-mid";
    if (t >= 0.15) return "sens-heat-neg";
    return "sens-heat-neg-strong";
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
    searchQuery = ticker.trim().toUpperCase();
    await onSelectCompany(ticker, options);
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

  $: {
    const nextTicker = overview?.company?.ticker ?? financials?.company?.ticker ?? "";
    if (nextTicker && nextTicker !== searchHydratedTicker && searchQuery.trim().length === 0) {
      searchQuery = nextTicker;
      searchHydratedTicker = nextTicker;
    } else if (!nextTicker) {
      searchHydratedTicker = "";
    }
  }

  $: currentCompany = overview?.company ?? financials?.company ?? null;
  $: headlineMetrics = overview?.headline_metrics ?? [];
  $: headlineStripMetrics = headlineMetrics.slice(0, 5);
  $: searchResults = search?.results ?? [];
  $: searchDropdownResults = searchResults.map((result) => ({
    id: result.ticker,
    primary: `${result.ticker}${result.exchange ? ` | ${result.exchange}` : ""}`,
    secondary: result.name,
    state: result.ticker === selectedTicker ? "Active" : null,
    selected: result.ticker === selectedTicker
  }));
  $: overviewWarnings = overview?.warnings ?? [];
  $: financialWarnings = financials?.warnings ?? [];
  $: dcfWarnings = dcfModel?.warnings ?? [];
  $: combinedWarnings = [...overviewWarnings, ...financialWarnings, ...dcfWarnings].reduce<string[]>((rows, warning) => {
    const text = warning.trim();
    if (!text || rows.includes(text)) {
      return rows;
    }
    return [...rows, text];
  }, []);
  $: currentStatement = statementViewForSelection(financials, statementBasis, statementKind);
  $: currentRatioView = statementViewForSelection(financials, statementBasis, "ratios");
  $: activeScenario = findDcfScenario(dcfModel, dcfDraft.activeScenarioId);
  $: activeScenarioSummary = activeScenario?.summary ?? null;
  $: sensitivityRange = (() => {
    const rows = dcfModel?.sensitivity_matrix?.rows ?? [];
    const values: number[] = [];
    for (const row of rows) {
      for (const cell of row) {
        const value = cell?.implied_value_per_share;
        if (typeof value === "number" && Number.isFinite(value)) values.push(value);
      }
    }
    if (!values.length) return { min: 0, max: 0 };
    return { min: Math.min(...values), max: Math.max(...values) };
  })();
  $: dcfSummaryRows = dcfModel?.scenarios.filter((scenario) => scenario.summary != null) ?? [];
  $: dcfScenarioValueScale = (() => {
    const values: number[] = [];
    for (const scenario of dcfSummaryRows) {
      const low = scenario.summary?.implied_value_low;
      const high = scenario.summary?.implied_value_high;
      const point = scenario.summary?.implied_value_per_share;
      if (typeof low === "number" && Number.isFinite(low)) values.push(low);
      if (typeof high === "number" && Number.isFinite(high)) values.push(high);
      if (typeof point === "number" && Number.isFinite(point)) values.push(point);
    }
    const currentPrice = dcfSummaryRows[0]?.summary?.current_price;
    if (typeof currentPrice === "number" && Number.isFinite(currentPrice)) values.push(currentPrice);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return null;
    return { min, max };
  })();
  function scenarioRangePercent(value: number | null | undefined) {
    if (!dcfScenarioValueScale || value == null || !Number.isFinite(value)) return null;
    const { min, max } = dcfScenarioValueScale;
    return ((value - min) / (max - min)) * 100;
  }
  $: filingCount = overview?.filings?.length ?? financials?.filings?.length ?? 0;
  $: dilutedSharesMetric = headlineMetrics.find((metric) => metric.metric_id === "diluted_shares") ?? null;
  $: companyAbout = companySummary(currentCompany);
  $: companyInfoRows = [
    { label: "Exchange", value: currentCompany?.exchange ?? "N/A" },
    { label: "SIC", value: currentCompany?.sic_description ?? currentCompany?.sic ?? "N/A" },
    { label: "Latest Reported", value: shortDate(currentCompany?.latest_report_period) },
    { label: "Latest Filed", value: shortDate(currentCompany?.latest_filing_date) },
    { label: "Diluted Shares", value: dilutedSharesMetric?.display_value ?? "N/A" },
    { label: "Filings Loaded", value: filingCount ? `${filingCount}` : "N/A" }
  ];
  $: headerNote = combinedWarnings[0] ?? "";
  $: marketContextMetrics = marketContextMetricIds
    .map((metricId) => headlineMetrics.find((metric) => metric.metric_id === metricId))
    .filter((metric): metric is NonNullable<typeof headlineMetrics[number]> => Boolean(metric));
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
          </div>
        {/each}
      </div>
    </div>

    <div class="search-strip">
      <div class="search-actions">
        <div class="search-control filter-wide">
          <span class="search-label">Company Search</span>
          <SearchDropdown
            bind:value={searchQuery}
            placeholder="AAPL, Microsoft, NVDA..."
            ariaLabel="Company search"
            emptyLabel="No SEC matches"
            results={searchDropdownResults}
            enterBehavior="submit"
            on:submit={() => runSearch(false)}
            on:select={(event) => chooseCompany(String(event.detail.id))}
          />
        </div>
        <button type="button" on:click={() => runSearch(false)} disabled={loading}>{loading ? "Loading..." : "Run Search"}</button>
        <button type="button" class="secondary" on:click={() => runSearch(true)} disabled={loading}>Refresh Search</button>
        {#if currentCompany}
          <button type="button" class="secondary" on:click={() => chooseCompany(currentCompany.ticker, { forceRefresh: true, resetThread: false })} disabled={loading}>
            Refresh {currentCompany.ticker}
          </button>
        {/if}
      </div>

      {#if headerNote}
        <div class="header-note" title={combinedWarnings.join(" | ")}>
          <span class="focus-label">Note</span>
          <p>{headerNote}</p>
          {#if combinedWarnings.length > 1}
            <small>+{combinedWarnings.length - 1}</small>
          {/if}
        </div>
      {/if}
    </div>
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
              <p>{companyAbout}</p>
            </div>
            <div class="meta-flat">
              {#each companyInfoRows as row}
                <div class="meta-row">
                  <span>{row.label}</span>
                  <strong>{row.value}</strong>
                </div>
              {/each}
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

          <div class="kpi-grid valuation-kpi-grid">
            {#each (marketContextMetrics.length ? marketContextMetrics : headlineMetrics.slice(0, 7)) as metric}
              <div class="metric">
                <span>{metric.label}</span>
                <strong class={metricTone(metric.metric_id, metric.value)}>{metric.display_value ?? "N/A"}</strong>
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
                            <div class={`heat-cell ${heatmapCellClass(row.metric_id, cell.value, row.cells.map((candidate) => candidate.value))}`}>
                              <strong>{cell.display_value ?? "N/A"}</strong>
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
                {@const lowPct = scenarioRangePercent(scenario.summary?.implied_value_low)}
                {@const highPct = scenarioRangePercent(scenario.summary?.implied_value_high)}
                {@const pointPct = scenarioRangePercent(scenario.summary?.implied_value_per_share)}
                {@const pricePct = scenarioRangePercent(scenario.summary?.current_price)}
                <div class="focus-row compact-focus scenario-row">
                  <span class="focus-label">{scenario.label}</span>
                  <strong class={toneClass(scenario.summary?.upside_downside_pct)}>{currency(scenario.summary?.implied_value_per_share, 2)}</strong>
                  <p>
                    EV {compactCurrency(scenario.summary?.enterprise_value)}
                    | Equity {compactCurrency(scenario.summary?.equity_value)}
                    | {pct(scenario.summary?.upside_downside_pct)}
                  </p>
                  {#if lowPct != null && highPct != null && highPct > lowPct}
                    <div class="scenario-range" title={`WACC × terminal growth sensitivity range: ${currency(scenario.summary?.implied_value_low, 2)} – ${currency(scenario.summary?.implied_value_high, 2)}`}>
                      <div class="range-track">
                        <div class="range-fill {toneClass(scenario.summary?.upside_downside_pct)}" style={`left:${lowPct}%; right:${100 - highPct}%`}></div>
                        {#if pointPct != null}
                          <div class="range-point" style={`left:${pointPct}%`}></div>
                        {/if}
                        {#if pricePct != null}
                          <div class="range-price-tick" style={`left:${pricePct}%`} title={`Current price ${currency(scenario.summary?.current_price, 2)}`}></div>
                        {/if}
                      </div>
                      <div class="range-bounds">
                        <small>{currency(scenario.summary?.implied_value_low, 0)}</small>
                        <small>{currency(scenario.summary?.implied_value_high, 0)}</small>
                      </div>
                    </div>
                  {/if}
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
    <div class="financials-shell">
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
                  <th>{period.label}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#if currentStatement?.lines?.length}
                {#each currentStatement.lines as line}
                  <tr>
                    <td class="statement-label-cell"><strong>{line.label}</strong></td>
                    {#each line.cells as cell}
                      <td><strong>{cell.display_value ?? "N/A"}</strong></td>
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

      <div class="financials-support-grid">
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
      </div>
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

        <div class="kpi-grid scenario-kpi-grid">
          <article class="metric">
            <span>Current Price</span>
            <strong>{currency(activeScenarioSummary?.current_price, 2)}</strong>
          </article>
          <article class="metric">
            <span>Enterprise Value</span>
            <strong>{compactCurrency(activeScenarioSummary?.enterprise_value)}</strong>
          </article>
          <article class="metric">
            <span>Equity Value</span>
            <strong>{compactCurrency(activeScenarioSummary?.equity_value)}</strong>
          </article>
          <article class="metric">
            <span>Implied / Share</span>
            <strong>{currency(activeScenarioSummary?.implied_value_per_share, 2)}</strong>
          </article>
          <article class="metric">
            <span>Upside / Downside</span>
            <strong class={toneClass(activeScenarioSummary?.upside_downside_pct)}>{pct(activeScenarioSummary?.upside_downside_pct)}</strong>
          </article>
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

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
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
                    <td class="sheet-label">{row.label}</td>
                    {#each row.display_values as value}
                      <td class="sheet-cell sheet-cell-fixed"><span class="sheet-fixed">{value ?? "N/A"}</span></td>
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

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
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
                    <td class="sheet-label">{row.label}</td>
                    {#each dcfModel?.projection_years ?? [] as _year, index}
                      <td class="sheet-cell sheet-cell-edit">
                        <input class="sheet-input" value={editableValue(assumptionSeriesValue(dcfDraft.activeScenarioId, row.line_key, index), row.unit)} on:change={(event) => handleAssumptionChange(row.line_key, row.unit, index, event)} />
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

        <div class="table-wrap sheet-wrap">
          <table class="sheet-table">
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
                    <td class="sheet-label">{row.label}</td>
                    {#each dcfModel?.projection_years ?? [] as _year, index}
                      <td class="sheet-cell" class:sheet-cell-edit={row.editable} class:sheet-cell-fixed={!row.editable} class:overridden-cell={row.overridden[index]}>
                        {#if row.editable}
                          <input class="sheet-input" value={projectionEditableValue(activeScenario, row.line_key, index)} on:change={(event) => handleProjectionOverrideChange(row.line_key, index, event)} />
                        {:else}
                          <span class="sheet-fixed">{row.display_values[index] ?? "N/A"}</span>
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

        <div class="table-wrap compact-wrap sheet-wrap">
          <table class="sheet-table sensitivity-table">
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
                    <td class="sheet-label">{pct(dcfModel.sensitivity_matrix.terminal_growth_values[rowIndex])}</td>
                    {#each row as cell}
                      <td class={`sheet-cell sens-cell ${sensitivityHeatClass(cell.implied_value_per_share, sensitivityRange)}`}>{currency(cell.implied_value_per_share, 2)}</td>
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

  .financials-shell {
    display: grid;
    gap: 0.5rem;
  }

  .financials-support-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 0.5rem;
    align-items: start;
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
  .search-actions,
  .search-strip,
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
  .search-actions,
  .headline-strip,
  .search-strip,
  .scenario-strip {
    flex-wrap: wrap;
  }

  .headline-block {
    display: grid;
    gap: 0.12rem;
  }

  .subtitle,
  .muted,
  .focus-row p,
  .meta-row span {
    color: var(--text-2);
  }

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
  .scenario-card.selected-scenario {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
  }

  .mode-bar button:hover,
  button:hover,
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

  .scenario-card {
    display: grid;
    gap: 0.12rem;
    text-align: left;
  }

  .scenario-card strong {
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
  .search-control {
    display: grid;
    gap: 0.2rem;
  }

  .filter-wide {
    flex: 0 1 16rem;
  }

  .search-control {
    min-width: min(16rem, 100%);
    max-width: 18rem;
  }

  .search-label {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .header-note {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 0.6rem;
    align-items: baseline;
    min-width: 0;
    max-width: 34rem;
    padding-left: 0.75rem;
    border-left: 1px solid var(--divider);
  }

  .header-note p,
  .header-note small {
    color: var(--text-2);
    margin: 0;
  }

  .header-note p {
    font-size: 0.76rem;
    line-height: 1.35;
  }

  .header-note small {
    font-size: 0.7rem;
    white-space: nowrap;
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

  .search-strip {
    justify-content: space-between;
    align-items: end;
  }

  .search-actions {
    align-items: end;
    min-width: 0;
  }

  .search-strip button {
    min-height: 1.9rem;
    padding: 0.28rem 0.56rem;
    font-size: 0.74rem;
  }

  .grid-input {
    min-width: 6rem;
    text-align: right;
    padding-inline: 0.4rem;
  }

  .sheet-table {
    table-layout: fixed;
  }

  .table-wrap.sheet-wrap {
    overflow-x: hidden;
  }

  .sheet-table thead th {
    text-align: right;
    padding: 0.35rem 0.5rem;
  }

  .sheet-table thead th:first-child {
    text-align: left;
  }

  .sheet-table tbody td {
    padding: 0;
    border-top: 1px solid var(--divider);
    border-left: 1px solid var(--divider);
    vertical-align: middle;
    height: 1.85rem;
  }

  .sheet-table tbody td:first-child {
    border-left: 0;
  }

  .sheet-table .sheet-label {
    padding: 0 0.55rem;
    color: var(--text-1);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sheet-table .sheet-cell {
    text-align: right;
  }

  .sheet-table .sheet-fixed {
    display: block;
    padding: 0 0.5rem;
    color: var(--accent);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .sheet-table .sheet-input {
    display: block;
    width: 100%;
    min-width: 0;
    min-height: 0;
    border: 0;
    background: transparent;
    color: var(--text-0);
    text-align: right;
    padding: 0 0.5rem;
    height: 1.83rem;
    font: inherit;
    font-size: 0.82rem;
    font-variant-numeric: tabular-nums;
  }

  .sheet-table .sheet-input:focus {
    outline: 1px solid var(--accent);
    outline-offset: -1px;
    background: var(--bg-1);
  }

  .sheet-table .sheet-cell-edit {
    background: var(--bg-1);
  }

  .sheet-table .sheet-cell-fixed {
    background: var(--bg-0);
  }

  .sensitivity-table .sens-cell {
    padding: 0 0.55rem;
    text-align: right;
    color: var(--text-0);
    font-variant-numeric: tabular-nums;
  }

  .sens-heat-pos-strong {
    background: color-mix(in srgb, var(--positive) 32%, transparent);
  }

  .sens-heat-pos {
    background: color-mix(in srgb, var(--positive) 18%, transparent);
  }

  .sens-heat-mid {
    background: color-mix(in srgb, var(--warning) 16%, transparent);
  }

  .sens-heat-neg {
    background: color-mix(in srgb, var(--negative) 18%, transparent);
  }

  .sens-heat-neg-strong {
    background: color-mix(in srgb, var(--negative) 32%, transparent);
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

  .scenario-range {
    margin-top: 0.35rem;
    display: grid;
    gap: 0.18rem;
  }

  .scenario-range .range-track {
    position: relative;
    height: 0.45rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--text-2) 22%, transparent);
  }

  .scenario-range .range-fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: 999px;
    background: color-mix(in srgb, var(--text-1) 55%, transparent);
  }

  .scenario-range .range-fill.positive {
    background: color-mix(in srgb, var(--positive) 55%, transparent);
  }

  .scenario-range .range-fill.negative {
    background: color-mix(in srgb, var(--negative) 55%, transparent);
  }

  .scenario-range .range-point {
    position: absolute;
    top: 50%;
    width: 0.55rem;
    height: 0.55rem;
    margin-left: -0.275rem;
    border-radius: 50%;
    background: var(--text-0);
    box-shadow: 0 0 0 2px var(--bg-0);
    transform: translateY(-50%);
  }

  .scenario-range .range-price-tick {
    position: absolute;
    top: -0.15rem;
    bottom: -0.15rem;
    width: 2px;
    margin-left: -1px;
    background: var(--warning);
    border-radius: 1px;
  }

  .scenario-range .range-bounds {
    display: flex;
    justify-content: space-between;
    font-size: 0.7rem;
    color: var(--text-2);
  }

  .profile-about p {
    color: var(--text-1);
    line-height: 1.45;
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

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(8.8rem, 1fr));
    gap: 0;
    padding-block: 0.15rem;
  }

  .valuation-kpi-grid {
    grid-template-columns: repeat(7, minmax(0, 1fr));
  }

  .scenario-kpi-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }

  .metric {
    border: 0;
    border-left: 1px solid var(--divider);
    background: none;
    padding: 0.2rem 1rem;
    display: grid;
    gap: 0.12rem;
    min-width: 0;
  }

  .metric:first-child {
    padding-left: 0;
    border-left: 0;
  }

  .metric span {
    color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.62rem;
  }

  .metric strong {
    display: block;
    margin: 0.22rem 0;
    font-size: 1rem;
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

  .period-head {
    display: grid;
    gap: 0.12rem;
  }

  .statement-label-cell {
    min-width: 14rem;
  }

  .statement-label-cell strong,
  .statement-wrap tbody td strong {
    display: block;
    color: var(--text-0);
    font-weight: 600;
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

  .selected-cell .heat-cell {
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 32%, transparent);
  }

  .heat-cell {
    display: grid;
    gap: 0.1rem;
    padding: 0.38rem 0.42rem;
    margin: -0.18rem -0.12rem;
    min-height: 2rem;
    align-content: center;
  }

  .heat-cell strong {
    font-size: 0.82rem;
  }

  .heat-positive-strong {
    background: color-mix(in srgb, var(--positive) 28%, transparent);
  }

  .heat-positive {
    background: color-mix(in srgb, var(--positive) 22%, transparent);
  }

  .heat-positive-soft {
    background: color-mix(in srgb, var(--positive) 12%, transparent);
  }

  .heat-warning {
    background: color-mix(in srgb, var(--warning) 18%, transparent);
  }

  .heat-negative-soft {
    background: color-mix(in srgb, color-mix(in srgb, var(--negative) 58%, var(--warning)) 16%, transparent);
  }

  .heat-negative-strong {
    background: color-mix(in srgb, var(--negative) 28%, transparent);
  }

  .heat-negative {
    background: color-mix(in srgb, var(--negative) 20%, transparent);
  }

  .heat-neutral {
    background: transparent;
    color: var(--text-2);
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
    .profile-grid,
    .financials-support-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .header-top,
    .mode-kpi-row,
    .panel-header,
    .search-actions,
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

    .scalar-grid {
      grid-template-columns: 1fr;
    }

    .valuation-kpi-grid,
    .scenario-kpi-grid {
      grid-template-columns: 1fr;
    }

    .header-note {
      grid-template-columns: 1fr;
      gap: 0.2rem;
      padding-left: 0;
      border-left: 0;
      border-top: 1px solid var(--divider);
      padding-top: 0.45rem;
      max-width: none;
    }
  }
</style>
