# Fundamentals Phase 6 Spec

> **Implementation status (2026-07-13):** This document remains the V1 architecture and product-shape specification. The active [`roadmap.md`](../roadmap.md) now marks Fundamentals V2 complete for the current pass. The shipped workspace extends this foundation with Peers, Reverse Valuation, and Reference / Filings modes; raw-versus-normalized inspection; YoY/QoQ and amendment context; DCF snapshots and terminal-value framing; cross-tab handoffs; explicit degraded states; and browser/reliability coverage. Non-US providers, estimates, and segment depth remain future expansion.

## Goal

Implement Phase 6 as a first-pass `Fundamentals` research workspace that lets the user:

- orient quickly to a public US company,
- inspect clean historical financials,
- compare the company against a stable peer basket,
- build and iterate a scenario-based DCF model,
- preserve source and transformation provenance throughout.

This phase should extend Gamma's existing research architecture rather than bolt on a generic fundamentals dashboard. The tab should remain read-only with respect to markets and execution, while allowing rich local editing of valuation assumptions and scenario definitions.

## V1 Product Shape

Phase 6 V1 should be a `US-only` pass for SEC filers and should launch with three modes:

1. `Overview`
2. `Financials`
3. `DCF`

These three modes are sufficient for a serious first pass:

- `Overview` answers: what is this company, how is it valued now, and how does it compare to peers?
- `Financials` answers: how has the business actually evolved?
- `DCF` answers: what assumptions would justify or challenge the current valuation?

## Scope

### In Scope

- US-listed / SEC-filing companies only
- SEC-native statement and filing ingestion
- price-aware headline valuation context using existing IBKR integration
- company overview with profile, headline financials, small price chart, and peer heatmap
- normalized annual and quarterly financial statements
- common derived ratio and trend analytics
- stable peer basket support
- spreadsheet-style DCF workbench with `Bear`, `Base`, and `Bull` scenarios
- sensitivity outputs and compact DCF summary outputs
- provenance on raw and derived entities

### Out of Scope for V1

- non-US or non-SEC-first coverage
- analyst estimate integrations
- full global taxonomy coverage
- automatic true peer-modeling beyond a first-pass rule system
- fully flexible multi-tab workbook behavior
- collaborative sharing
- broker execution or portfolio integration beyond price context

## Provider Strategy

### Recommended Split

- `SEC / EDGAR layer`: filing metadata, statements, XBRL facts, shares-related facts, report periods, restatement-aware history
- `IBKR layer`: price chart, current price, and price-dependent valuation fields
- `Gamma analytics layer`: ratios, trend calculations, peer basket logic, DCF engine, sensitivity analysis, reverse-valuation later

### Why

This split matches Gamma's existing architecture:

- provider adapters remain separate,
- provenance can stay explicit,
- price-sensitive metrics do not get conflated with filing-derived metrics,
- the important research logic remains owned by Gamma.

## Data Principles

### Filing Truth vs Market Truth

The tab must distinguish between:

- `filing-derived values`
- `market-derived values`
- `Gamma-derived values`

Examples:

- revenue, EBIT, cash flow, debt, and report period come from SEC filings
- price and chart history come from IBKR
- EV, EV/EBIT, FCF margin, ROIC, CAGR, and DCF outputs are Gamma-derived

This distinction should be visible in provenance and explainable in Copilot.

### Annual and Quarterly Integrity

V1 should support both:

- `annual`
- `quarterly`

But the analytics layer must not blur them carelessly. Gamma should keep explicit period semantics so it can avoid bad comparisons such as mixing annual margins with quarterly per-share fields without labeling.

### Amendment and Restatement Awareness

The SEC layer should preserve:

- filing date,
- acceptance timestamp when available,
- form type,
- accession number,
- fiscal period end,
- amendment flag when applicable.

Gamma should prefer a clear policy over silent replacement. If an amended filing is used or a prior period was restated, the normalized record should expose that fact.

## Mode 1 - Overview

### Purpose

Provide first-pass orientation and current valuation context without forcing the user into the full statement view.

### Core Layout

The mode should follow the standard Gamma two-column workspace pattern.

### Primary Column

- company header
- `About` block
- headline KPI strip
- small price chart
- peer heatmap

### Support Column

- provenance and filing summary
- capital structure / shares summary
- DCF summary card when a saved model exists

### Core Content

### Company Header

Should show:

- company name
- ticker
- exchange
- primary classification labels
- latest reported fiscal period

### About Block

Should show a concise company description and key metadata such as:

- sector
- industry
- headquarters
- fiscal year end

### KPI Strip

Should include a mix of filing and market context, such as:

- revenue
- EBITDA or EBIT if available
- FCF
- market cap
- enterprise value
- EV / sales
- EV / EBIT or P/E when valid
- net debt
- diluted shares outstanding

### Price Chart

Should reuse the compact time-series treatment already present elsewhere in Gamma.

The purpose is not technical analysis. It is quick valuation context:

- recent price direction
- price level relative to current market-cap context
- direct visual anchor before opening DCF

### Peer Heatmap

This is one of the signature features of the mode.

The heatmap should:

- use a single stable peer basket across all ratio sections,
- keep company order fixed while the selected company remains in context,
- group metrics by family,
- use Gamma's token-based data colors only in data context.

Suggested metric groups:

- valuation: `EV/Sales`, `EV/EBIT`, `EV/EBITDA`, `P/E`, `FCF yield`
- profitability: `gross margin`, `EBIT margin`, `FCF margin`
- growth: `revenue growth`, `EBIT growth`, `FCF growth`
- efficiency: `ROIC`, `ROE`, `asset turnover`
- balance sheet: `net debt / EBIT`, `current ratio`, `cash conversion`

The important design rule is consistency:

- same peers,
- same ordering,
- same metric families,
- visible missing-data treatment rather than silent dropping.

## Mode 2 - Financials

### Purpose

Provide the actual operating history needed before serious modeling.

This mode is essential because it separates statement inspection from valuation construction.

### Core Layout

### Primary Column

- statement viewer
- trend and ratio overlays

### Support Column

- filing history panel
- statement notes / caveats
- peer snapshot or quick ratio summary

### Core Content

### Statement Viewer

Should support:

- income statement
- balance sheet
- cash flow statement
- annual / quarterly toggle
- normalized view and raw-label view where feasible

The table should prioritize:

- clean line-item continuity across periods,
- explicit handling of missing values,
- period labels with report dates,
- easy scanning across years and quarters.

### Trend Layer

Should provide:

- YoY change
- QoQ change where valid
- multi-year CAGR where valid
- margin progression
- dilution trend
- capex and working-capital behavior

### Ratio Layer

Common ratios should be Gamma-owned and transparently defined.

Initial V1 ratio families:

- margins
- returns on capital
- liquidity
- leverage
- cash conversion
- capital intensity

These should be computed from normalized statement data plus, where required, price-dependent market fields from IBKR.

### Filing History Panel

Should display:

- filing type
- filing date
- report period
- amendment status
- accession reference

This panel gives the user a direct path back to source chronology and helps preserve Gamma's research-first trust model.

## Mode 3 - DCF

### Purpose

Provide a spreadsheet-like valuation workbench rather than a form-based toy calculator.

This mode should feel closer to an editable model sheet than to a KPI dashboard.

### Core DCF Model Concept

The DCF should be built around three parallel scenarios:

- `Bear`
- `Base`
- `Bull`

For each modeled line item, Gamma should store:

- historical actuals
- scenario-specific projected values
- one currently selected active scenario for displayed outputs

The key rule is:

- the visible working projection row is a view of the selected scenario,
- the scenario rows are the source of truth,
- switching scenarios changes the displayed working line and downstream outputs.

### Table Semantics

Historical values must be locked.

Projected values must support:

- editable scenario inputs,
- formula-derived defaults,
- per-cell manual overrides.

This is the preferred behavior:

1. Gamma provides a default projection rule for a line item.
2. The user can edit the scenario assumption driving that line.
3. The user can manually override any projected scenario cell if needed.

This produces a model that is both fast to start and flexible under scrutiny.

### Initial DCF Sections

### Historical Block

- revenue
- EBIT or operating income
- taxes
- D&A
- capex
- working capital change
- FCF

### Projection Drivers

- revenue growth
- EBIT margin
- tax rate
- D&A as percent of revenue or explicit values
- capex as percent of revenue or explicit values
- NWC investment as percent of incremental revenue or explicit values

### Valuation Assumptions

- WACC
- terminal growth rate
- optional share-count assumption
- optional net debt adjustment inputs if not already populated from current data

### Output Section

- projected FCF by year
- discount factors
- PV of interim cash flows
- terminal value
- enterprise value
- equity value
- implied value per share
- upside / downside vs current price

### Editing Rules

The DCF grid should clearly distinguish:

- `actual locked cells`
- `editable scenario cells`
- `formula output cells`
- `manual override cells`

Color and border semantics should follow Gamma's design principles and remain compact and spreadsheet-like.

### Scenario Behavior

V1 should support:

- switching active scenario
- preserving all three scenarios simultaneously
- independent editing of each scenario
- compact summary comparison across scenarios

The DCF summary card shown in `Overview` should reflect the currently selected active scenario while still exposing the `Bear/Base/Bull` range.

## Peer Basket Model

### Why Peer Basket Matters

A raw sector label is not enough for serious comps.

Phase 6 should therefore separate:

- `classification`
- `peer discovery`
- `peer basket`

### V1 Approach

### Classification Seed

Use one or more external labels to seed the initial comparable universe, such as:

- sector
- industry
- sub-industry where available

V1 does not need a perfect universal taxonomy. It needs a consistent first-pass seed.

### Gamma Peer Basket

Gamma should create a persistent peer basket entity with:

- focal company
- peer tickers
- display order
- basket label
- basket provenance
- user edits

The user must be able to:

- remove peers
- add peers
- keep the same peer set across overview heatmaps and financial comparisons

This basket should be treated as a research object, not just a temporary screen result.

### Selection Heuristics

Initial peer discovery can consider:

- classification overlap
- market-cap band
- revenue scale band
- profitability profile where available

But the final peer set should remain user-adjustable.

## Data Model

The exact implementation can vary, but Phase 6 should add normalized entities close to the following shapes.

### Core Company Context

- `CompanyRecord`
- `CompanyClassificationRecord`
- `CompanyPriceSnapshot`
- `CompanyOverviewSummary`

### Statements

- `FinancialPeriod`
- `FinancialStatementLine`
- `FinancialStatementView`
- `CompanyFinancialHistory`

### Peer Layer

- `PeerCandidateRecord`
- `PeerBasketRecord`
- `PeerHeatmapMetric`
- `PeerHeatmapView`

### DCF Layer

- `DcfModelRecord`
- `DcfScenarioRecord`
- `DcfProjectionLine`
- `DcfProjectionCell`
- `DcfValuationSummary`
- `DcfSensitivityMatrix`

## Provenance Requirements

Phase 6 should follow [`provenance_expectations.md`](./provenance_expectations.md).

At minimum:

- filing-derived records must carry provider and filing origin
- market-derived records must carry IBKR origin
- ratio and valuation outputs must carry a non-null `transformation_note`

Examples:

- `revenue` line item:
  - `source_provider = "sec"`
  - `origin = "fundamentals.sec.company_facts.revenue"`
- `EV / EBIT`:
  - dominant provider may be `ibkr` or `sec` depending on entity design
  - `transformation_note` must explain the price-plus-fundamental combination
- `DCF implied value per share`:
  - `source_provider = "manual"` or dominant provider strategy
  - `origin = "fundamentals.dcf.compute"`
  - `transformation_note` must explain that the value is Gamma-derived from scenario inputs plus current market and statement context

## Adapter Strategy

Phase 6 should introduce dedicated fundamentals adapters rather than accessing SEC or IBKR data directly from the application layer.

Suggested split:

- `SecFundamentalsAdapter`
- `IbkrValuationAdapter`
- optional later `ClassificationAdapter`

Then add an application service such as:

- `FundamentalsService`

Responsibilities:

- resolve company and ticker context
- fetch and normalize statement history
- attach price-aware valuation context
- build peer basket candidates
- return overview and financial-mode payloads
- persist and load DCF model state

## Cache Strategy

The fundamentals layer should reuse Gamma's existing cache pattern.

Suggested cache tiers:

- company metadata and classification seed: medium TTL
- statement history: long TTL with manual refresh option
- filing chronology: long TTL
- price snapshot and mini-chart: shorter TTL
- user DCF state and peer basket state: local persisted research objects

Cached SEC-derived records must preserve original `retrieved_at`.

## API Shape

Exact route names may vary, but V1 likely needs endpoints comparable to:

- `/fundamentals/search`
- `/fundamentals/overview`
- `/fundamentals/financials`
- `/fundamentals/peers`
- `/fundamentals/dcf`
- `/fundamentals/dcf/save`
- `/fundamentals/dcf/sensitivity`

The route layer should stay thin and delegate to application services, consistent with the current Gamma backend pattern.

## UI Principles

The tab should follow [`design_principles.md`](./design_principles.md).

Important implications for this tab:

- the DCF grid should feel like one flat analytical plane, not like stacked cards
- the heatmap should use compact borders and dense typography
- the tab should prefer column layouts and dividers over decorative containers
- the mode bar should match Macro and Crypto patterns

The `DCF` mode is the one place where spreadsheet density is desirable and should not be over-softened.

## V1 Non-Goals

The following should explicitly remain out of the first pass:

- automatic perfect comps
- sell-side style estimate consensus
- multi-currency multinational normalization
- advanced segment valuation
- full reverse-DCF engine
- broad governance and ownership workflows

These can follow once the core statement and DCF architecture is stable.

## Suggested Delivery Order

1. `Company context and SEC ingestion`
2. `Overview mode with headline valuation context`
3. `Financials mode with annual / quarterly statements and common ratios`
4. `Peer basket and heatmap`
5. `DCF engine and scenario storage`
6. `DCF UI grid and overview summary card`
7. `Sensitivity matrices`

This order keeps the data model and statement trust layer ahead of the valuation UI.

## Testing

### Backend

- company resolution works for supported US tickers
- annual and quarterly financial history serialize correctly
- provenance is attached to statement, peer, and valuation outputs
- peer basket persistence works
- DCF scenarios recalculate deterministically
- manual override cells survive save/load

### Frontend

- mode switching preserves company context
- peer order remains stable across metric groups
- annual / quarterly toggles update statement view cleanly
- DCF grid visually distinguishes locked, editable, derived, and overridden cells
- switching `Bear/Base/Bull` updates displayed working lines and summary outputs

## Follow-On Work

Likely post-V1 expansions:

1. richer classification sources and taxonomy switching
2. reverse-valuation mode
3. deeper segment and geographic revenue analysis
4. ownership and proxy overlays
5. estimate overlays
6. broader peer and basket tooling

## Summary

Phase 6 V1 should not try to be a full equity terminal.

It should be a disciplined first-pass fundamentals workspace built around:

- `Overview`
- `Financials`
- `DCF`

with SEC-native data, IBKR market context, Gamma-owned ratios, Gamma-owned peer baskets, and a serious spreadsheet-style scenario model as the centerpiece.
