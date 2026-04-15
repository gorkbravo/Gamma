# Gamma Roadmap V2

## Purpose

Roadmap V2 defines the next expansion layer for **Gamma** after the first roadmap's completed and paused phase checkpoints.

The original roadmap moved Gamma from a portfolio/risk application into a first-pass multi-domain research environment. Roadmap V2 is about turning those first-pass surfaces into a deeper, more coherent research platform while adding a small number of new domains that are large enough to justify their own workspaces.

The core product boundary remains unchanged:

**Gamma is a read-only research environment, not an execution platform.**

Gamma can ingest market data, study portfolios, inspect strategies, analyze commodities, monitor vessels, compare companies, explore wallet behavior, and use AI to structure research. It should not place trades, rebalance portfolios, run execution bots, or provide arbitrary in-app code execution paths that could become execution surfaces.

Roadmap V2 should therefore support four goals:

1. Harden and deepen the first-pass research tabs.
2. Add new research domains only when their data model and analytical surface justify the complexity.
3. Improve the shared platform layer so new tabs do not become isolated UI experiments.
4. Prepare Gamma for external testing through installer, tutorial, diagnostics, and friend/family beta readiness.

---

## Relationship To The Original Roadmap

[`roadmap.md`](./roadmap.md) remains the source of truth for the first roadmap's product principles, completed phases, paused checkpoints, and deferred V2 scope.

Roadmap V2 does not replace that document. It starts from its end state:

- Prediction Markets is complete at a first-pass level.
- Macro is paused with a live multi-mode workspace.
- Keyboard navigation and workspace customization are complete at a first-pass level.
- Copilot is paused with a shell-level, read-only, context-aware foundation.
- Crypto is paused with a live multi-mode research workspace.
- Fundamentals is paused with a live first-pass company-analysis workspace.

Anything marked as deferred or paused in the first roadmap is eligible V2 scope, but V2 should not blindly continue every old item. The new rule is:

**Prioritize work that strengthens Gamma as a cross-domain research platform.**

That means provider adapters, data models, reusable analytics, provenance, cross-tab handoffs, and Copilot grounding should usually outrank UI-only additions.

---

## Progress Tracking

Roadmap V2 is intentionally not written as a strict linear phase plan. Most workstreams can move in parallel as long as their data dependencies are respected.

Status markers:

- `Not started (0%)`
- `Planned`
- `In progress (~X%)`
- `Blocked`
- `Complete (100%)`

Dependency markers:

- `Foundation`: should happen early because many workstreams depend on it.
- `Parallelizable`: can be worked on alongside other V2 surfaces.
- `Independent`: can be implemented with little dependency on other V2 work.
- `Blocked by X`: should not be started deeply until a specific prerequisite is resolved.
- `Opportunistic`: should be done only when adjacent work creates a clear need.

Progression notes in this roadmap should be read as **implementation gravity**, not as mandatory sequencing. For example, mode-level keybindings can be built while Maritime Intelligence is still unstarted. A futures-curve analytics layer, however, should not be built before Gamma has a reliable futures-chain provider shape.

---

## Guiding Product Principles

### 1. Read-only by design

Gamma should continue to aggregate, transform, visualize, compare, and explain data without becoming an execution venue.

This matters most for:

- IBKR / TWS integration,
- strategy analysis,
- Copilot tooling,
- crypto wallet analytics,
- future commodities and futures workflows.

The practical rule is:

- market-data access is allowed,
- portfolio inspection is allowed,
- strategy-return analysis is allowed,
- simulation and scenario analysis are allowed,
- order placement and automated execution are not allowed.

### 2. Provider adapters before feature sprawl

Every new provider should sit behind a clear adapter boundary. Tabs should consume normalized records, not provider-native payloads.

Provider-specific behavior should be explicit:

- entitlement requirements,
- rate limits,
- freshness and delay,
- symbol conventions,
- asset coverage,
- historical depth,
- source timestamp,
- transformation notes.

### 3. Modes over tab sprawl

New top-level tabs should be rare. A tab deserves to exist when it has:

- a distinct data model,
- a distinct research workflow,
- enough internal modes to avoid being a single-page dashboard,
- cross-tab relationships that add value to the rest of Gamma.

This is why `Commodities` and `Maritime Intelligence` can justify top-level surfaces, while smaller additions should usually become modes inside existing tabs.

### 4. Research, not just monitoring

Every major surface should help answer:

- What changed?
- Why might it matter?
- What is inconsistent?
- What should be compared?
- What would disconfirm the current interpretation?

Raw charts are useful, but V2 should focus on research workflows, not quote screens.

### 5. Imported strategy data before arbitrary code

Gamma can support strategy research without becoming an execution or notebook platform.

The V2 bias should be:

- allow imported return streams,
- validate and normalize external CSVs,
- compare imported strategies to benchmarks and factors,
- support scenario analysis and risk diagnostics,
- avoid arbitrary code execution inside the app.

If code execution is ever reconsidered, it should be a separate sandboxed architecture decision, not a hidden feature inside Research.

### 6. Cross-tab handoffs should become first-class

Gamma's value increases when tabs talk to each other.

Important V2 handoffs include:

- Research to Risk,
- Research to IV,
- Research to Fundamentals,
- Macro to Commodities,
- Commodities to Maritime Intelligence,
- Commodities to Prediction Markets,
- Fundamentals to Copilot,
- IV to Copilot,
- Maritime Intelligence to Macro and Commodities.

### 7. Copilot must remain grounded

Copilot should be powerful because it understands Gamma's internal state, not because it acts as a generic chatbot.

V2 Copilot should:

- cite loaded Gamma context,
- distinguish source-backed facts from inference,
- expose scope and warnings,
- use read-only internal tools,
- persist research sessions,
- draft memos from actual app state.

### 8. Beta readiness is product work

Installer, tutorial, setup flow, mock mode, diagnostics, and clear error states are not polish-only tasks. They determine whether Gamma can be tested by people who are not already familiar with the codebase.

---

## Workstream 1 - Cross-Cutting Platform Foundation

_Status: In progress (~65%)_
_Dependency marker: Foundation_
_Parallelization note: Some pieces are independent, but this workstream should start early because it shapes most V2 tabs._
_Recent progress: Workstream 1 now has shared provenance/freshness primitives, provider-agnostic cache freshness policies, a generic cross-tab handoff envelope, a compact Copilot context contract, explicit read-only boundary metadata at `/system/read-only-boundary`, hardened provider capability metadata for active/optional/sample/planned providers, and a reusable frontend mode-registry helper._

### Why this workstream matters

V2 adds deeper surfaces and new domains. Without stronger platform foundations, each tab will end up solving the same problems separately:

- provider selection,
- cache behavior,
- provenance,
- symbol mapping,
- mode navigation,
- Copilot context,
- cross-tab handoffs.

This workstream prevents V2 from becoming a collection of unrelated dashboards.

### Goal of the workstream

Build shared infrastructure that makes V2 tabs easier to implement, easier to trust, and easier to connect.

It should help answer engineering questions such as:

- Which provider supplied this value?
- Is this value live, delayed, stale, mocked, or derived?
- Which instruments are supported by which source?
- Can this tab safely hand context to another tab?
- Can Copilot explain exactly what context it is grounded in?

### Functionality

#### 1. Provider capability registry

Gamma should maintain a normalized registry of provider capabilities.

For each provider, the app should know:

- supported asset classes,
- supported regions,
- live vs delayed coverage,
- historical depth,
- rate or pacing limits where known,
- entitlement requirements,
- whether the source is official, broker-sourced, public-market, on-chain, filing-based, or model-generated,
- whether the source supports batch fetching,
- whether the source is safe for background refresh.

This should help decide when Research uses TWS, when Commodities needs a dedicated futures provider, when a field should be marked unavailable, and what warnings Copilot should see.

Implementation note:
- `/system/provider-capabilities` now exposes a static read-only capability registry with active, optional, sample, and planned provider records. Existing providers remain separated from planned candidates such as Polygon, Twelve Data, Financial Modeling Prep, EODHD, ALFRED, Nasdaq Data Link, AISHub, and paid AIS vendors. Planned records document expected domains, freshness, entitlements/API-key needs, limitations, provenance notes, and read-only safety notes without making live calls or implying adapters are implemented.

#### 2. Read-only IBKR / TWS market-data boundary

IBKR / TWS can be a strong paid data source for live equities, ETFs, options, futures, FX, IV surfaces, and portfolio snapshots.

However, Gamma should keep the adapter explicitly data-only.

The V2 IBKR boundary should:

- expose market-data and portfolio-inspection methods,
- expose entitlement and session state,
- expose pacing and market-data-line pressure where possible,
- avoid order-placement methods,
- avoid account-modification methods,
- avoid any feature path where Copilot can call execution-related functions.

This lets Gamma benefit from IBKR data without turning into an execution platform.

First-pass boundary note: Gamma relies on TWS API read-only configuration for the hard execution lock. Gamma's app-side responsibility is to keep its own adapter, UI, and Copilot paths data-only by exposing no order-placement or account-modification capabilities.

Implementation note:
- `/system/read-only-boundary` exposes Gamma's platform-level read-only contract. It records allowed research/data actions, prohibited execution/account/wallet actions, the TWS API read-only operator lock, and app-side notes that Gamma exposes no order placement, account modification, rebalancing, wallet signing, or transaction submission path.
- Copilot context bundles now carry default read-only safety metadata, and the OpenAI provider payload includes that metadata alongside workspace context and warnings.

#### 3. Research market-data abstraction

The Research workspace should not assume TWS is the only source of listed-market data.

The abstraction should support:

- provider priority by asset class,
- fallback providers,
- explicit source labels,
- source-specific warnings,
- base-currency conversion,
- corporate-action awareness where available,
- benchmark and sector metadata.

Potential sources include:

- `IBKR / TWS` for live entitled data,
- `Polygon`, `Twelve Data`, `Financial Modeling Prep`, or `EODHD` as optional market-data providers,
- `FRED`, `US Treasury`, `BLS`, `BEA`, `EIA`, `ECB`, and `Eurostat` for official macro and economic context,
- `SEC EDGAR` for filings and company data.

The first implementation does not need every provider. It needs the boundary to avoid hard-coding the research product around one source.

Implementation note:
- The provider registry now documents planned research market-data candidates and their expected provenance/freshness constraints. The actual Research V2 abstraction, provider priority engine, fallback selection, corporate-action policy, and broad adoption into Research endpoints remain future Workstream 2/Workstream 1 overlap.

#### 4. Normalized V2 entity schemas

V2 should extend Gamma's internal schemas to include:

- research scopes,
- imported strategy return streams,
- market overview nodes,
- futures contracts,
- futures curves,
- commodity spreads,
- commodity inventory series,
- maritime vessels,
- ports,
- chokepoints,
- shipping routes,
- AIS position points,
- Copilot sessions,
- saved memos,
- saved research workflows.

The schema design should preserve provider ID, normalized ID, source timestamp, retrieval timestamp, transformation note, and quality warnings where relevant.

Implementation note:
- Shared `ProvenanceRecord`, `FreshnessLabel`, `FreshnessRecord`, and `ProvenanceSummary` primitives now exist for future providers and context builders. They cover live, delayed, stale, historical, mocked, derived, model-generated, unavailable, and unknown labels without forcing a big-bang retrofit of every legacy response.

#### 5. Cache and freshness policy

Gamma should make cache behavior more explicit.

V2 cache records should distinguish:

- live values,
- delayed values,
- stale values,
- historical values,
- mocked values,
- derived values,
- model-generated values.

The UI should not need to know every provider rule, but it should be able to display a compact freshness/provenance label.

Implementation note:
- A provider-agnostic `CacheFreshnessPolicy` and `CacheFreshnessAssessment` skeleton now tracks retrieval timestamps, source timestamps, TTLs, stale behavior, refresh needs, usability, warnings, and compact freshness labels. Default internal policies cover short-lived snapshots, daily research series, historical references, and generated/mocked context.

#### 6. Mode-level keybindings

The first roadmap completed workspace and tab-level keyboard navigation. V2 should extend this to mode-level navigation inside tabs.

The intended model:

- `Ctrl+1` through `Ctrl+N` still switch tabs in the current workspace order.
- A separate shortcut family should move between modes inside the active tab.
- Mode keybindings should be discoverable in the keybindings viewer.
- The active mode should be visible and stable across refreshes when reasonable.

This should apply to Research, Macro, IV, Crypto, Fundamentals, Commodities, Maritime Intelligence, and the dedicated Copilot workspace.

First-pass implementation note: `Shift+1` through `Shift+N` now switch registered modes in the active tab for Macro, Crypto, and Fundamentals. The keybindings viewer exposes the derived mode map, and future tabs should register their modes through shared navigation metadata.

Implementation note:
- The frontend mode registry now has a small `defineTabModes` helper, duplicate validation, `hasRegisteredModes`, and `getModeRegistrySnapshot` so future mode-bearing tabs can join the existing shortcut/keybindings surface without inventing a separate metadata path.

#### 7. Cross-tab context handoff layer

Gamma already has some handoffs, such as Research to Risk and Research to IV. V2 should make this pattern explicit.

A handoff should carry:

- source tab,
- source mode,
- selected entity,
- selected timeframe,
- selected provider/source,
- relevant warnings,
- normalized IDs,
- timestamp,
- intended target tab/mode.

Examples:

- a Research scope opens Risk with its weights and history coverage,
- a single equity opens IV with its selected symbol,
- a Fundamentals company opens IV or Research with the same ticker,
- a Macro inflation divergence opens Commodities with energy and metals lenses,
- a Commodities oil curve opens Maritime Intelligence with tanker/chokepoint context,
- a Maritime chokepoint event opens Macro with geopolitical/risk context.

Implementation note:
- A shared `CrossTabHandoffEnvelope` now defines source tab/mode, selected entity, selected timeframe, provider/source, warnings, normalized IDs, timestamp, and intended target tab/mode. This is a generic serialization/validation contract only; no domain-specific Commodities, Maritime, Macro V2, or Research V2 handoff behavior has been implemented.

#### 8. Copilot context contract

Every V2 tab should expose a compact context builder for Copilot.

The context builder should include:

- active mode,
- selected entity,
- selected timeframe,
- visible headline metrics,
- source/provenance summaries,
- warnings,
- available drilldown tools,
- saved notes or session context when applicable.

Copilot should not scrape UI state loosely. It should consume intentional, tab-owned context payloads.

Implementation note:
- A compact `CopilotContextContract` skeleton now defines active mode, selected entity, selected timeframe, headline metrics, provenance summaries, warnings, available read-only drilldown tools, generated timestamp, and read-only safety metadata. Existing Copilot V1 behavior is preserved; this is the contract future tab-owned builders can adopt before Copilot V2 UI/session work begins.

### Data requirements

This workstream needs mostly internal metadata:

- provider definitions,
- capability records,
- entitlement/session records,
- cache entries,
- normalized IDs,
- cross-tab handoff payloads,
- mode definitions,
- keybinding definitions,
- Copilot context schemas.

### Data sources / APIs

Potential sources include:

- `IBKR / TWS` for broker and listed-market data,
- official macro and filing APIs,
- existing Gamma provider adapters,
- optional market-data providers selected later,
- local app state and cache records.

### Progression notes

This workstream should start with the smallest foundation that unblocks V2:

1. Define provider capability metadata.
2. Harden the IBKR read-only market-data boundary.
3. Add mode-level keybinding primitives.
4. Add a generic cross-tab handoff shape.
5. Add Copilot context-builder expectations for new tabs.

It does not need to build every provider before tab work starts. It only needs enough structure that tabs do not hard-code around a single source.

Current standalone ceiling note:
- Workstream 1 is now close to its practical standalone ceiling before other workstreams begin. The remaining foundation work is mostly adoption work: wiring the contracts into future domain builders, implementing the Research market-data abstraction with real provider selection, defining domain-specific V2 entity schemas, and retrofitting selected high-value existing endpoints as adjacent tabs are touched.

### Deliverable

At the end of this workstream, Gamma should have a clearer platform layer for provider selection, source transparency, read-only enforcement, mode navigation, cross-tab handoffs, Copilot grounding, and cache/freshness display.

---

## Workstream 2 - Research V2

_Status: In progress (~24%)_
_Dependency marker: Parallelizable, but improved by provider foundation_
_Parallelization note: The multi-mode UI can begin before all market-data providers are selected, but Strategy Lab and Overview need reliable data contracts._

### Why this workstream matters

The current Research tab is useful but narrow. It builds and analyzes single-name or synthetic scopes. Roadmap V2 should turn Research into a more general research hub without violating Gamma's read-only boundary.

Research V2 should become the place where the user can define a market or strategy scope, understand current market structure, import external strategy returns, compare scopes and benchmarks, and hand off selected context to Risk, IV, Fundamentals, and Copilot.

### Goal of the workspace

Research V2 should provide a multi-mode environment for broad listed-market research and strategy-return inspection.

It should help answer:

- What is this scope exposed to?
- How did this basket behave versus benchmarks?
- Which sectors or market groups are leading?
- Is an imported strategy actually differentiated after drawdown and risk analysis?
- How does a strategy perform across regimes?
- What should be sent to Risk, IV, Fundamentals, or Copilot next?

### Product structure

Research should evolve from a single page into a multi-mode workspace.

Suggested modes:

- `Overview`
- `Scope Analysis`
- `Strategy Lab`
- `Compare / Scenario`
- `Saved Research`

The current Research tab should become `Scope Analysis`, not be discarded.

Implementation note:
- Research now has a first-pass mode shell: `Overview` is registered first/default with `Shift+1`, and `Scope Analysis` is registered second with `Shift+2`. The existing single-ticker and synthetic-portfolio analyzer remains available under `Scope Analysis`.

#### 1. Scope Analysis mode

This mode preserves and improves the current Research workflow.

It should support:

- single-ticker research scopes,
- synthetic portfolio scopes,
- benchmark selection,
- base-currency conversion,
- scope preview before execution,
- historical return analysis,
- concentration diagnostics,
- constituent-level performance,
- handoff into Risk,
- handoff into IV for eligible single-name scopes,
- handoff into Fundamentals for eligible equities,
- Copilot grounding from the active scope.

V2 improvements should focus on clearer data-source labels, better missing-data diagnostics, saved/reloadable scopes, improved benchmark and sector metadata, better non-US support where provider coverage allows, and clearer separation between broker-derived and research-provider-derived histories.

The mode should remain explicit that research scopes are synthetic analysis contexts, not broker portfolios.

#### 2. Overview mode

This mode should provide a market-map view instead of a single-scope view.

It can include:

- equity index overview,
- sector and industry maps,
- country or region maps where data exists,
- ETF group views,
- breadth metrics,
- leadership/laggard tables,
- relative strength by sector or basket,
- volatility and drawdown heatmaps,
- market-cap weighted tree maps,
- watchlist mosaics,
- handoff from a map node into Scope Analysis or Fundamentals.

This mode should answer:

**What parts of the market are moving, leading, lagging, or breaking down?**

The first pass can be narrow:

- US large-cap sectors,
- selected major ETFs,
- user-defined watchlists,
- provider-backed price history,
- simple breadth and return metrics.

Later passes can expand to European equities, global ETFs, factor baskets, style buckets, and thematic groups.

Implementation note:
- A first-pass `/research/overview` data contract now returns provider-neutral overview nodes, group nodes, rankings, coverage, freshness/source labels, warnings, and transformation notes. The frontend consumes that payload in the default `Overview` mode with a local treemap-style view and leader/laggard/risk panels. Current coverage is intentionally narrow: the default `Sample equities` universe is an offline-friendly sample/watchlist and the optional `Major ETFs` universe depends on provider history; tile size is equal-weight until market-cap or index-weight data is available.

#### 3. Strategy Lab mode

This mode should allow the user to analyze strategy return streams without running code inside Gamma.

The first V2 implementation should support imported CSV files containing:

- date,
- strategy return,
- optional strategy NAV/equity curve,
- optional benchmark return,
- optional exposure fields,
- optional metadata columns.

Gamma should validate date parsing, duplicate dates, missing values, return versus level interpretation, frequency, outliers, benchmark alignment, and base currency if relevant.

Strategy Lab should compute:

- cumulative return,
- annualized return,
- annualized volatility,
- Sharpe-style and Sortino-style metrics where assumptions are clear,
- max drawdown,
- drawdown duration,
- rolling return,
- rolling volatility,
- rolling beta/correlation to benchmark,
- monthly/annual return tables,
- regime slices if Macro context is available,
- downside capture/upside capture where benchmarks exist.

This mode should not run arbitrary Python, call broker execution APIs, send orders, or treat uploaded returns as a live strategy.

#### 4. Compare / Scenario mode

This mode should compare multiple research objects.

Potential comparisons:

- scope versus scope,
- imported strategy versus benchmark,
- imported strategy versus synthetic basket,
- single equity versus peer basket,
- current portfolio versus research scope,
- period A versus period B,
- pre-event versus post-event windows.

The mode should support aligned return windows, normalized starting NAV, rolling correlation, rolling beta, relative drawdown, contribution analysis where weights exist, scenario-style weight edits without execution, and handoff to Risk for deeper risk analysis.

The word "scenario" should remain research-oriented. It means "what would the historical analytics look like under this hypothetical scope," not "rebalance the portfolio."

#### 5. Saved Research mode

This mode should make research reusable.

It can store:

- saved scopes,
- saved imported strategy runs,
- selected benchmarks,
- notes,
- provider warnings,
- run timestamps,
- Copilot-generated research cards,
- follow-up tasks.

This is not a full notebook initially. It is a structured saved-research layer that later Copilot and beta workflows can use.

### Data requirements

Research V2 needs instrument metadata, price history, FX history, benchmark metadata, sector/industry/classification metadata, watchlists, imported return streams, normalized research scopes, saved runs, provenance, and warning records.

### Data sources / APIs

Potential sources include:

- `IBKR / TWS` for entitled live and historical listed-market data,
- optional market-data providers such as `Polygon`, `Twelve Data`, `Financial Modeling Prep`, or `EODHD`,
- `FRED` and official macro sources for regime context,
- `SEC EDGAR` and Fundamentals adapters for company links,
- local CSV imports for strategy returns.

### Progression notes

Suggested progression:

1. Harden the current Research tab into `Scope Analysis`.
2. Add the multi-mode shell and mode keybindings.
3. Add saved scopes and clearer provider diagnostics.
4. Add CSV-based Strategy Lab.
5. Add first-pass Overview with a narrow universe.
6. Add Compare / Scenario workflows.
7. Add richer handoffs to Fundamentals, Risk, IV, and Copilot.

### Deliverable

At the end of Research V2, Gamma should have a genuine research hub that can inspect market scopes, imported strategies, market overview maps, and comparisons without becoming an execution or arbitrary-code platform.

---

## Workstream 3 - Macro V2

_Status: Planned_
_Dependency marker: Parallelizable_
_Parallelization note: Most Macro V2 work can proceed independently, but provider foundation helps EU/global expansion and cross-tab handoffs._

### Why this workstream matters

Macro already exists as a strong first-pass workspace. V2 should make it more complete, more global, and more connected to other tabs.

The current Macro workspace has:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`

V2 should deepen these modes rather than add a large number of new pages. If Commodities becomes a top-level tab, Macro should link into it instead of trying to duplicate a full commodity research desk internally.

### Goal of the workspace

Macro V2 should improve Gamma's ability to interpret cross-asset expectations, policy pricing, event windows, and regime shifts.

It should help answer:

- What changed across the macro landscape?
- Which markets are agreeing or disagreeing?
- Is the divergence driven by rates, growth, inflation, commodities, credit, FX, or prediction markets?
- Which region is leading the move?
- What upcoming event could confirm or invalidate the current regime framing?

### Product structure

Macro should retain its four-mode structure:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`

The main V2 expansion should be better US depth, meaningfully improved EU coverage, clearer Global comparisons, stronger event coverage, better coherence/lead-lag interpretation, and richer cross-tab links into Commodities and Prediction Markets.

#### 1. Snapshot V2

Snapshot should remain the fast situational-awareness mode.

V2 improvements:

- richer regional summary cards,
- clearer "what changed" grouping,
- stronger stale/missing-data handling,
- better comparison between US and EU lenses,
- linked commodities signals where relevant,
- linked prediction-market signals where relevant,
- more explicit provider and freshness labels,
- compact Copilot-ready context summary.

The mode should answer:

**What matters right now, and which deeper mode should I open next?**

#### 2. Cross-Asset V2

Cross-Asset should remain Macro's signature analytical mode.

V2 improvements:

- deeper divergence ranking,
- clearer driver/counter-signal attribution,
- cross-region comparison,
- richer theme taxonomy,
- more explicit lead/lag caveats,
- linked Prediction Markets context,
- linked Commodities context,
- eventual credit/stress proxies where reliable data exists.

The mode should continue to avoid pretending to be a causal factor model. It should present structured interpretation and transparent heuristics.

Potential theme groups:

- growth,
- inflation,
- policy,
- recession risk,
- risk appetite,
- dollar/liquidity,
- geopolitics,
- commodity shock.

#### 3. Rates & Policy V2

Rates & Policy should deepen from a first-pass rates surface into a more mature policy-expectations workspace.

V2 improvements:

- clearer curve family selection,
- better US Treasury curve history,
- deeper EU rates and ECB context where data allows,
- meeting-ladder improvements,
- better policy-path proxy methodology,
- inflation breakeven and real-yield interpretation,
- more explicit central-bank event windows,
- prediction-market links where policy contracts exist.

The mode should support front-end changes, curve slope changes, real yield changes, breakeven changes, policy meeting context, pre/post event repricing summaries, and visual comparison of market-implied and official-policy context where data quality permits.

#### 4. Events / Regimes V2

Events / Regimes should become a stronger interpretation layer.

V2 improvements:

- broader official event calendars,
- better EU event coverage,
- richer pre-event setup windows,
- richer post-event reaction windows,
- event history by type,
- clearer regime labels,
- cross-tab links to commodities and prediction markets,
- saved event studies.

Event categories can include inflation releases, labor releases, growth releases, central-bank meetings, Treasury/refunding events where relevant, major geopolitical catalysts, and commodity inventory releases where linked to Commodities.

#### 5. Macro coherence engine V2

The coherence engine should become a reusable service rather than tab-local logic.

It should support:

- ranked divergences,
- signal agreement/disagreement,
- lead/lag annotations,
- timeframe coherence,
- source warnings,
- comparison overlays,
- explainable scoring components.

The engine should still be transparent and heuristic unless a later statistical model is explicitly designed and validated.

### Data requirements

Macro V2 needs macro time series, yield-curve histories, real-yield and breakeven histories, FX and dollar proxies, credit/stress proxies where available, official event calendars, linked prediction-market metadata, linked commodity-market context, region and concept mappings, and provenance for every transformed series.

### Data sources / APIs

Potential sources include:

- `FRED`,
- `ALFRED` where revision-aware history matters,
- `US Treasury`,
- `BLS`,
- `BEA`,
- `EIA`,
- `ECB`,
- `Eurostat`,
- `Fed` public releases,
- `IBKR / TWS` for entitled market proxies,
- Prediction Markets adapters,
- future Commodities adapters.

### Progression notes

Suggested progression:

1. Improve series registry and provenance.
2. Deepen US Snapshot and Rates & Policy quality.
3. Expand EU coverage where concept mappings are clean.
4. Improve official event coverage.
5. Refine coherence/lead-lag methodology.
6. Add explicit Macro to Commodities and Macro to Prediction Markets handoffs.

### Deliverable

At the end of Macro V2, Gamma should have a more globally useful macro workspace with stronger event interpretation, better rates/policy depth, richer cross-asset coherence, and cleaner links to commodities and prediction markets.

---

## Workstream 4 - IV V2

_Status: Planned_
_Dependency marker: Parallelizable, but dependent on IBKR / options data quality_
_Parallelization note: UI and analytics can progress incrementally, but live coverage depends on options entitlements and provider behavior._

### Why this workstream matters

The current IV tab is a useful surface-inspection tool, but it is not yet a full volatility research workspace.

V2 should make IV more analytical by adding richer surface views, skew and term-structure analysis, Greeks context, realized-versus-implied comparison, implied distribution work, and cross-tab handoffs.

### Goal of the workspace

IV V2 should help the user inspect options-implied expectations without turning Gamma into an options execution tool.

It should answer:

- What does the surface look like?
- Where is skew concentrated?
- How has implied volatility moved versus realized volatility?
- What does the market imply about the distribution of future prices?
- Are upcoming events visible in the term structure?
- How does the selected equity or research scope connect to volatility context?

### Product structure

Suggested modes:

- `Surface`
- `Skew & Term`
- `Greeks`
- `Realized vs Implied`
- `Implied Distribution`
- `Events / Cross-Tab`

#### 1. Surface mode

This mode should evolve the current heatmap into a richer volatility-surface explorer.

V2 improvements:

- 3D surface visualization,
- expiry/strike heatmap,
- moneyness normalization,
- selected expiry slices,
- selected strike slices,
- spot-relative annotations,
- surface freshness and entitlement warnings,
- mock-surface parity for development.

The first pass should prioritize clarity and stability over complex model fitting.

#### 2. Skew & Term mode

This mode should focus on structure.

It should show ATM term structure, put skew by expiry, call skew by expiry, selected delta/moneyness slices, skew change versus prior snapshot where available, term-structure slope, and event-related kinks.

This mode should help answer:

**Where is the market paying for asymmetry or event risk?**

#### 3. Greeks mode

This mode should add basic options sensitivity context.

Potential outputs:

- delta by strike/expiry,
- gamma by strike/expiry,
- vega by strike/expiry,
- theta by strike/expiry,
- aggregate Greek heatmaps for selected expiry,
- spot-relative exposure summaries.

This mode should be framed as research context, not a position-management or execution surface.

If Gamma lacks reliable option model inputs, the UI should clearly distinguish provider-returned fields from Gamma-derived estimates.

#### 4. Realized vs Implied mode

This mode should compare market-implied volatility against realized behavior.

It can include realized volatility windows, implied volatility at selected tenor, IV percentile/rank where history exists, volatility spread, rolling realized/IV comparison, and event-window realized move versus implied move.

Data limitations should be explicit because IV history may be provider-constrained.

#### 5. Implied Distribution mode

This mode should explore risk-neutral distribution ideas.

Possible features:

- first-pass RND visualization,
- implied probability mass by price bucket,
- comparison across expiries,
- distribution shifts across snapshots,
- caveats about model assumptions and data sparsity.

This should be added after the surface and skew data paths are stable.

#### 6. Events / Cross-Tab mode

This mode should connect IV to the rest of Gamma.

Potential handoffs:

- Research single ticker to IV,
- Fundamentals company to IV,
- IV event risk to Copilot,
- earnings or macro event windows to IV,
- IV selected underlying to Risk or Research.

This mode should help answer:

**What does options pricing add to the broader research context?**

### Data requirements

IV V2 needs option chains, implied volatility by strike/expiry, underlying spot, historical underlying prices, risk-free rate inputs, dividend/corporate-action context where available, option Greeks where provider-returned or Gamma-derived, IV history if available, and event dates for selected underlyings.

### Data sources / APIs

Potential sources include:

- `IBKR / TWS` as the main live options source,
- internal historical price adapters,
- `FRED` or Treasury series for rate assumptions where needed,
- Fundamentals adapters for company/event links,
- future optional options-data providers if IBKR history is insufficient.

### Progression notes

Suggested progression:

1. Stabilize the current surface data model and provenance.
2. Add 3D surface and better moneyness/expiry controls.
3. Add Skew & Term mode.
4. Add Realized vs Implied mode.
5. Add Greeks mode if provider/model inputs are reliable.
6. Add Implied Distribution mode.
7. Add deeper handoffs to Research, Fundamentals, and Copilot.

### Deliverable

At the end of IV V2, Gamma should have a volatility lab that can inspect surfaces, skew, term structure, realized-versus-implied context, Greeks, and implied distributions while remaining read-only.

---

## Workstream 5 - Crypto V2

_Status: Planned_
_Dependency marker: Parallelizable_
_Parallelization note: Wallet/on-chain work can progress independently, but provider selection affects depth and reliability._

### Why this workstream matters

Crypto V1 established a useful token, basket, liquidity, and comparison surface. V2 should make it more on-chain aware.

The main gap is flow. Crypto becomes much more valuable when Gamma can connect price, liquidity, wallet behavior, pool activity, and narrative movement.

### Goal of the workspace

Crypto V2 should support token, basket, wallet, and liquidity research in a read-only environment.

It should answer:

- Which tokens or narratives are attracting attention?
- Are price moves supported by liquidity and flow?
- Are large wallets accumulating or distributing?
- Which pools are changing meaningfully?
- How does on-chain behavior compare to market behavior?
- Are derivatives/funding signals confirming or contradicting spot/on-chain signals?

### Product structure

Suggested modes:

- `Overview`
- `Token Deep Dive`
- `Narratives & Baskets`
- `Wallets & Flows`
- `DEX Liquidity`
- `Derivatives` later

#### 1. Overview mode

Overview should continue to be the entry point.

V2 improvements:

- stronger cross-sectional screening,
- on-chain-aware factors,
- clearer narrative grouping,
- better layer/category taxonomy,
- stronger market-cap/liquidity/turnover diagnostics,
- saved filters,
- Copilot-ready overview context.

This mode should answer:

**Where should I look first?**

#### 2. Token Deep Dive mode

This mode should deepen token-level research.

V2 improvements:

- richer price and volume history,
- supply and unlock context where available,
- token contract mapping,
- chain-specific identifiers,
- narrative/basket membership,
- liquidity and pool context,
- wallet activity summary,
- peer comparison,
- warnings for thin or unreliable data.

#### 3. Narratives & Baskets mode

This mode should make narratives first-class research objects.

It should support provider category baskets, Gamma-curated baskets, synthetic baskets, basket-versus-basket comparisons, token-versus-basket comparisons, relative strength, turnover and liquidity comparison, basket breadth, and narrative concentration.

The goal is to study crypto themes as baskets, not only as single tokens.

#### 4. Wallets & Flows mode

This is the highest-value V2 expansion.

It should support:

- wallet balances,
- transfer history,
- large inflows/outflows,
- exchange interaction,
- whale or large-holder movement,
- counterparty patterns,
- token-specific flow summaries,
- flow versus price comparison,
- concentration and holder-change metrics.

This mode should be careful about interpretation. Wallet labels and inferred flows should carry confidence and source warnings.

#### 5. DEX Liquidity mode

This mode should deepen current GeckoTerminal-backed pool work.

V2 improvements:

- pool monitoring over time,
- liquidity changes,
- volume/liquidity ratios,
- pool concentration,
- transaction-level drilldowns where provider support exists,
- slippage-style proxies,
- suspicious liquidity changes,
- pool-to-token comparison.

#### 6. Derivatives mode

This should remain a later V2 extension.

Potential features:

- funding rates,
- open interest,
- basis,
- perpetual futures overlays,
- exchange-level comparison,
- spot versus derivatives divergence.

This should only be added after the token/on-chain/liquidity foundation is stronger.

### Data requirements

Crypto V2 needs token metadata, price and volume history, supply metrics, token contracts, chain IDs, DEX pool data, wallet balances, transfers, holder concentration, large transactions, narrative/category mappings, and derivatives metrics if added.

### Data sources / APIs

Potential sources include:

- `CoinGecko`,
- `GeckoTerminal`,
- `Alchemy`,
- `Dune`,
- `DefiLlama` as a possible supplemental source,
- chain-specific explorers where needed,
- optional derivatives data providers later.

### Progression notes

Suggested progression:

1. Improve token and basket provenance.
2. Add Gamma-curated basket definitions.
3. Add wallet/transfer provider adapter.
4. Add Wallets & Flows mode.
5. Deepen DEX Liquidity mode with monitoring and transaction context.
6. Improve comparative analytics.
7. Add derivatives overlays only after core on-chain work is stable.

### Deliverable

At the end of Crypto V2, Gamma should provide a flow-aware crypto research workspace that connects token behavior, narrative baskets, wallets, pools, and liquidity conditions.

---

## Workstream 6 - Fundamentals V2

_Status: Planned_
_Dependency marker: Parallelizable_
_Parallelization note: US SEC improvements can progress independently; European/international expansion depends on provider and normalization choices._

### Why this workstream matters

Fundamentals V1 established a real company-analysis workspace with SEC-native data, peer baskets, and persistent DCF scenarios. V2 should deepen the analytical layer and improve market-implied expectation work.

The highest-value additions are:

- reverse valuation,
- raw-versus-normalized inspection,
- peer/reference depth,
- better market-price context,
- broader regional support where data quality allows.

### Goal of the workspace

Fundamentals V2 should help the user understand businesses, financial statements, valuation assumptions, and market-implied expectations.

It should answer:

- What does this business look like financially?
- What changed across statements and ratios?
- How does the company compare to peers?
- What assumptions does the current price imply?
- What would need to be true for the stock to be undervalued or overvalued?
- How reliable are the underlying filing and market-data inputs?

### Product structure

Suggested modes:

- `Overview`
- `Financials`
- `Peers`
- `DCF`
- `Reverse Valuation`
- `Reference / Filings`

#### 1. Overview V2

Overview should become a stronger orientation surface.

V2 improvements:

- clearer source separation between filing-derived, market-derived, and Gamma-derived metrics,
- better headline KPI selection,
- improved market-price context,
- peer basket summary,
- valuation summary,
- warning cards for missing or stale market data,
- Copilot context summary.

#### 2. Financials V2

Financials should improve statement inspection.

V2 improvements:

- raw-versus-normalized toggles,
- richer statement row provenance,
- restatement/amendment indicators,
- trend overlays,
- YoY and QoQ change views,
- margin and ratio overlays,
- better handling of sparse or irregular company facts.

The mode should help the user understand both the normalized output and the original filing trail behind it.

#### 3. Peers mode

Peers should become a fuller comparison layer.

It should support persistent peer baskets, peer heatmaps, margin comparison, growth comparison, capital efficiency comparison, valuation multiple comparison, implied expectation comparison where available, and peer basket handoff to Research.

The peer layer should be explicit when peer data is incomplete or market-dependent.

#### 4. DCF V2

DCF should build on the existing Bear / Base / Bull workbench.

V2 improvements:

- better assumption ergonomics,
- clearer projection-driver views,
- scenario comparison,
- sensitivity matrix improvements,
- optional terminal multiple framing,
- better market-price context,
- saved model snapshots,
- Copilot memo generation from selected scenario.

The DCF should remain a research model, not a recommendation engine.

#### 5. Reverse Valuation mode

This should be the flagship V2 addition.

Reverse Valuation should estimate what assumptions are implied by the current market price.

Potential outputs:

- implied revenue CAGR,
- implied margin path,
- implied terminal assumptions,
- implied reinvestment needs,
- implied FCF trajectory,
- scenario gap versus user's Base case,
- sensitivity of implied assumptions to WACC or terminal growth.

This mode aligns especially well with Gamma because it turns market price into a research question:

**What would have to be true?**

#### 6. Reference / Filings mode

This mode should make provenance easier to inspect.

It can include filing history, filing links, amendment markers, statement source trace, company facts coverage, missing taxonomy warnings, and temporary identity/config warnings where relevant.

### Data requirements

Fundamentals V2 needs company metadata, filing chronology, annual and quarterly statements, company facts, normalized statement rows, ratio calculations, market prices, share counts, debt/cash context, peer definitions, DCF assumptions, reverse-valuation outputs, and provenance metadata.

### Data sources / APIs

Potential sources include:

- `SEC EDGAR / data.sec.gov via EdgarTools`,
- `IBKR / TWS` for market-price context where available,
- optional market/reference providers such as `Financial Modeling Prep`, `EODHD`, or similar if validated,
- later European filings/reference providers if international expansion becomes a V2 priority.

### Progression notes

Suggested progression:

1. Improve source/provenance separation in Overview.
2. Add raw-versus-normalized statement inspection.
3. Improve peer comparison depth.
4. Add Reverse Valuation mode.
5. Improve DCF scenario persistence and snapshots.
6. Add Fundamentals-specific Copilot grounding.
7. Explore European equities only after provider and normalization quality are clear.

### Deliverable

At the end of Fundamentals V2, Gamma should support deeper company research, peer comparison, DCF analysis, and reverse-valuation work with clear filing and market-data provenance.

---

## Workstream 7 - Copilot V2

_Status: Planned_
_Dependency marker: Parallelizable, but quality depends on tab-owned context builders_
_Parallelization note: Streaming and session persistence can be built early. Deep domain reasoning improves as each tab exposes better context and tools._

### Why this workstream matters

The current Copilot layer is useful, but it is still a shell-level drawer. Roadmap V2 should keep that quick-assist surface while adding a dedicated Copilot workspace.

The goal is not to create a generic chatbot. The goal is to create an AI-assisted research layer grounded in Gamma's internal state.

### Goal of the workspace

Copilot V2 should help the user move from data to structured research output.

It should answer:

- What does the current context suggest?
- What hypothesis should be tested?
- Which tabs should be compared?
- What data is missing?
- What memo can be drafted from this session?
- What are the caveats and source limitations?

### Product structure

Copilot should have two surfaces:

- shell-level Copilot shelf for quick contextual research cards,
- dedicated Copilot workspace for persistent sessions, synthesis, workflow planning, and memos.

Suggested dedicated workspace modes:

- `Ask`
- `Synthesize`
- `Plan`
- `Memo`
- `Sessions`
- `Voice` later

#### 1. Ask mode

Ask mode is the focused assistant interface.

It should support:

- streaming responses,
- active context display,
- selected domain grounding,
- follow-up turns,
- source and warning panels,
- clear reset behavior when grounding changes.

This mode should remain read-only and grounded in Gamma context.

#### 2. Synthesize mode

Synthesize mode should compare loaded contexts across tabs.

Examples:

- Macro inflation divergence plus Commodities energy curve,
- Prediction Markets geopolitical contract plus oil and Maritime chokepoint context,
- Fundamentals company valuation plus IV event risk,
- Research strategy returns plus Macro regime context,
- Crypto wallet flows plus token price and liquidity context.

The output should separate agreements, contradictions, missing data, possible hypotheses, and next research steps.

#### 3. Plan mode

Plan mode should convert ideas into research workflows.

It should produce:

- testable hypothesis,
- required data,
- proposed metrics,
- confounders,
- tabs to inspect,
- invalidation conditions,
- next steps.

This is especially useful when a market observation needs to become a structured research process.

#### 4. Memo mode

Memo mode should generate saved research outputs.

Potential memo types:

- short research note,
- cross-tab synthesis brief,
- company memo,
- macro event note,
- strategy review,
- commodity curve note,
- maritime disruption note.

Memos should carry source contexts, timestamp, warnings, assumptions, and inferred versus source-backed claims.

#### 5. Sessions mode

Sessions mode should manage continuity.

It can include:

- saved threads,
- saved memos,
- linked tabs,
- saved research cards,
- follow-up tasks,
- reopened context bundles.

This turns Copilot from a one-off drawer into a research memory layer.

#### 6. Voice mode

Voice should be a later V2 or V3-style extension.

Possible features:

- speech-to-text prompts,
- spoken summaries,
- hands-free navigation prompts,
- session dictation.

Voice should not be added before the text/session/memo workflows are reliable.

### Data requirements

Copilot V2 needs tab context payloads, tool schemas, source refs, warning records, session storage, memo storage, selected contexts, model/provider metadata, and response provenance.

### APIs / model layer

Potential infrastructure includes:

- OpenAI model/provider boundary,
- streaming response support,
- structured output schemas,
- read-only internal tools,
- local session persistence,
- optional later provider abstraction.

### Progression notes

Suggested progression:

1. Add streaming.
2. Improve session persistence.
3. Define tab context-builder requirements.
4. Add dedicated Copilot workspace shell.
5. Add Synthesize and Plan modes.
6. Add Memo mode and saved outputs.
7. Add richer domain tools as each V2 tab matures.
8. Consider voice only after the core workspace is stable.

### Deliverable

At the end of Copilot V2, Gamma should have a dedicated AI research workspace that can ask, synthesize, plan, and draft memos from grounded Gamma context while preserving the read-only boundary.

---

## Workstream 8 - Commodities Tab

_Status: Planned_
_Dependency marker: Blocked by futures/commodity provider shape for deeper curve work_
_Parallelization note: Official energy/inventory data can start early; full futures-curve analytics need a reliable futures-chain and historical data path._

### Why this tab deserves to exist

Commodities can be more than a Macro sub-mode. A deep Commodities surface has its own data model, curves, spreads, inventories, seasonality, and supply-demand context.

It deserves a top-level tab if Gamma treats it as a commodity research desk rather than a quote board.

The tab should cover:

- energy,
- precious metals,
- industrial metals,
- selected agricultural markets later,
- futures curves,
- calendar spreads,
- inter-commodity spreads,
- inventories,
- macro and geopolitical links,
- maritime/trade-flow links.

### Goal of the tab

The Commodities tab should help the user understand commodity price behavior through curves, spreads, supply-demand indicators, and cross-domain context.

It should answer:

- What is the curve shape?
- Is the market in contango or backwardation?
- Which calendar spreads are moving?
- Are inventories confirming the price move?
- Which commodities are pricing inflation, scarcity, growth, or geopolitical risk?
- Are shipping disruptions relevant?
- How does this connect to Macro and Prediction Markets?

### Product structure

Suggested modes:

- `Overview`
- `Energy`
- `Metals`
- `Curves & Spreads`
- `Inventories & Fundamentals`
- `Events / Cross-Domain`

Agriculture can be a later extension if provider coverage and product focus justify it.

#### 1. Overview mode

Overview should provide a commodity market snapshot.

It can include:

- energy price cards,
- metals price cards,
- curve-state summaries,
- largest movers,
- spread movers,
- inventory surprises,
- macro-linked signals,
- maritime-linked signals,
- event and release calendar highlights.

This mode should answer:

**Which commodity markets deserve attention right now?**

#### 2. Energy mode

Energy should likely be the first deep commodity vertical.

Initial markets can include:

- WTI crude,
- Brent crude if provider support exists,
- Henry Hub natural gas,
- gasoline,
- heating oil / diesel,
- selected electricity or LNG proxies later.

Core features:

- spot/front-month history,
- futures curve,
- curve change over time,
- calendar spreads,
- crack spreads where data allows,
- inventories,
- production,
- imports/exports,
- refinery utilization,
- seasonal context,
- EIA release/event overlays.

Energy should link naturally to Macro inflation mode, Maritime tanker/chokepoint context, geopolitical prediction markets, and Copilot synthesis.

#### 3. Metals mode

Metals should cover both macro-sensitive and industrial commodities.

Initial markets can include:

- gold,
- silver,
- copper,
- platinum/palladium if useful,
- iron ore or aluminum later if provider coverage is strong.

Core features:

- futures or proxy price history,
- curve shape where available,
- gold versus real yields,
- copper versus growth proxies,
- gold/silver ratio,
- copper/gold ratio,
- inventory/warehouse data where available,
- China/global growth links where data exists.

The mode should avoid pretending all metals have equal data quality. COMEX data and LME-style data may have different provider constraints.

#### 4. Curves & Spreads mode

This should be the analytical center of the tab.

It should support:

- futures-curve table,
- curve chart by contract month,
- curve change by date,
- contango/backwardation labeling,
- front spread,
- selected calendar spreads,
- roll yield proxy,
- inter-commodity spreads,
- spread z-scores or percentile where history exists,
- saved spread watchlist.

Examples include crude M1-M2, crude M1-M6, natural gas summer/winter spreads, gold/silver ratio, copper/gold ratio, gasoline/crude crack, and heating oil/crude crack.

This mode should answer:

**What is the market saying through term structure rather than headline price?**

#### 5. Inventories & Fundamentals mode

This mode should connect prices to physical/fundamental context.

Potential modules:

- EIA crude inventories,
- product inventories,
- natural gas storage,
- production,
- refinery runs,
- imports/exports,
- demand proxies,
- seasonal ranges,
- inventory surprise overlays,
- inventory versus spread comparison.

For metals, this mode can later include exchange warehouse stocks, production/consumption indicators, China/import proxies, and industrial activity overlays.

#### 6. Events / Cross-Domain mode

This mode should connect Commodities to the rest of Gamma.

Potential links:

- Macro inflation and growth themes,
- Maritime chokepoint disruptions,
- geopolitical prediction markets,
- policy events,
- weather or seasonal events where data exists,
- Copilot-generated commodity notes.

This mode should help answer:

**Is this commodity move isolated, or is it part of a broader macro/geopolitical flow?**

### Data requirements

Commodities needs commodity instrument metadata, futures contract metadata, futures price history, front-month mapping, curve snapshots, settlement history, spread definitions, inventory series, production/demand series, event calendars, cross-tab links to Macro, Maritime Intelligence, and Prediction Markets, plus provenance and freshness metadata.

### Data sources / APIs

Potential sources include:

- `IBKR / TWS` for entitled futures market data,
- `EIA` for energy inventory, production, storage, and demand data,
- `FRED` for selected commodity and macro-sensitive series,
- `Nasdaq Data Link` for selected public or premium commodity datasets,
- `Databento` for deeper futures history if needed,
- direct exchange/vendor sources later if the tab becomes data-intensive,
- future Maritime Intelligence adapters for shipping context.

### Progression notes

Suggested progression:

1. Define commodity instrument and futures-curve schemas.
2. Establish whether IBKR/TWS can provide enough futures-chain and history coverage for the first pass.
3. Build Energy mode with EIA fundamentals and a narrow futures set.
4. Add Curves & Spreads mode for the initial energy contracts.
5. Add Metals mode with gold, silver, and copper.
6. Add cross-tab links to Macro and Prediction Markets.
7. Add Maritime Intelligence links once that tab has route/chokepoint context.
8. Consider deeper paid futures data only if IBKR/TWS proves insufficient for curve history and analytics.

### Deliverable

At the end of Commodities V2, Gamma should have a full commodity research workspace with curves, spreads, inventories, energy/metals context, and cross-domain links into Macro, Maritime Intelligence, Prediction Markets, and Copilot.

---

## Workstream 9 - Maritime Intelligence Tab

_Status: Planned_
_Dependency marker: Blocked by AIS/provider evaluation for live global coverage_
_Parallelization note: Historical/prototype work can start with free or sample datasets, but a serious live product requires a reliable AIS/provider decision._

### Why this tab deserves to exist

The initial idea was an AIS map. The stronger product framing is **Maritime Intelligence**.

The tab should not simply plot vessels. It should help interpret shipping flows, chokepoints, disruptions, route changes, and commodity-linked trade movement.

This is a distinct research domain because it has vessel entities, AIS positions, routes, ports, chokepoints, fleet classifications, event replay, commodity-flow links, and potential risk/shadow-fleet analytics.

### Goal of the tab

Maritime Intelligence should help the user understand what shipping behavior implies for markets and geopolitics.

It should answer:

- Where are vessels clustering?
- Are chokepoints congested or disrupted?
- Are routes changing?
- Which commodity flows are affected?
- Are tankers, LNG carriers, bulkers, or container ships behaving differently?
- Is there a market or geopolitical event connected to this movement?
- Which signals should be handed to Commodities, Macro, or Copilot?

### Product structure

Suggested modes:

- `Live Map`
- `Chokepoints`
- `Trade Flows`
- `Fleet / Vessel Monitoring`
- `Event Replay`
- `Risk Signals` later

#### 1. Live Map mode

Live Map should be the orientation surface.

It should show:

- vessel positions where provider coverage allows,
- vessel type filters,
- route or track snippets,
- selected vessel detail,
- map clustering,
- port/chokepoint labels,
- freshness and provider status,
- warnings for incomplete coverage.

The map should not imply full global truth if the provider only supplies partial coverage.

#### 2. Chokepoints mode

This mode should focus on strategic maritime bottlenecks.

Potential chokepoints:

- Strait of Hormuz,
- Suez Canal,
- Bab el-Mandeb,
- Turkish Straits,
- Panama Canal,
- Strait of Malacca,
- Danish Straits,
- Cape of Good Hope rerouting context.

Metrics can include vessel count by type, congestion proxy, transit changes, dwell time where data permits, route deviation, recent versus historical comparison, and linked commodity relevance.

This mode should answer:

**Is a maritime bottleneck showing stress that matters for markets?**

#### 3. Trade Flows mode

Trade Flows should connect vessel movement to market interpretation.

Initial flow categories:

- crude tankers,
- product tankers,
- LNG carriers,
- dry bulk,
- container ships later.

Potential modules:

- flow by route,
- flow by region,
- flow by vessel class,
- port call summaries,
- inferred route changes,
- commodity-linked movement,
- export/import proxies where reliable.

This mode should be built carefully. AIS does not automatically identify cargo. Cargo inference should be labeled as inferred and confidence-scored where used.

#### 4. Fleet / Vessel Monitoring mode

This mode should allow research on vessel groups.

It can support selected vessels, fleet watchlists, vessel metadata, flag, owner/operator where available, vessel class, last known position, recent route history, and suspicious behavior flags where data supports them.

The mode should be useful before shadow-fleet ML exists, but designed so that later ML probabilities can slot in cleanly.

#### 5. Event Replay mode

Event Replay should allow historical study.

Potential workflows:

- replay vessel traffic around a chokepoint disruption,
- compare route patterns before and after an event,
- study port congestion during a supply shock,
- inspect maritime reaction to geopolitical events,
- save event windows for Copilot memos.

This mode can start from historical datasets before live global AIS is solved.

#### 6. Risk Signals mode

This should be a later extension.

Potential risk signals:

- AIS gaps,
- unusual loitering,
- flag changes,
- route anomalies,
- sanctioned vessel proximity,
- dark activity proxies,
- shadow-fleet probability from an external ML project.

This should not be rushed. Risk labeling has higher false-positive and reputational risk, so the tab should carry confidence and methodology caveats.

### Data requirements

Maritime Intelligence needs AIS position records, vessel static metadata, vessel type/class, MMSI/IMO identifiers, port and terminal metadata, chokepoint polygons, route definitions, historical track points, event windows, fleet/watchlist definitions, optional sanctions/risk metadata, optional ML probability outputs later, and provider/freshness coverage metadata.

### Data sources / APIs

Potential sources include:

- `AISstream` for prototype live AIS streaming,
- `NOAA / MarineCadastre` for US historical AIS data,
- `Global Fishing Watch` for non-commercial vessel/event-style analysis where terms fit,
- `AISHub` if membership/participation requirements are practical,
- paid providers such as `MarineTraffic`, `Spire`, or `VesselFinder` if reliable global coverage becomes necessary,
- user-owned shadow-fleet ML outputs in a later roadmap.

### Progression notes

Suggested progression:

1. Define vessel, position, route, port, and chokepoint schemas.
2. Build a mock/historical map using a limited dataset.
3. Prototype AISstream or another low-cost live feed.
4. Add Chokepoints mode using normalized regions.
5. Add Event Replay using historical AIS.
6. Add basic commodity-flow links to Commodities.
7. Evaluate paid AIS providers only after the product shape proves useful.
8. Add shadow-fleet/risk analytics later, likely V3, once the base maritime data model is stable.

### Deliverable

At the end of Maritime Intelligence V2, Gamma should provide a credible maritime research surface that can inspect vessel movement, chokepoints, route changes, event windows, and commodity-flow links with clear source and coverage caveats.

---

## Workstream 10 - Prediction Markets Targeted V2

_Status: Opportunistic_
_Dependency marker: Opportunistic_
_Parallelization note: Prediction Markets is not a core V2 rebuild unless other tabs create specific cross-domain needs._

### Why this workstream is limited

Prediction Markets is already complete at a first-pass level. V2 should not deepen it in isolation unless there is a clear research payoff.

The most useful V2 work is likely cross-domain:

- prediction markets linked to Macro,
- prediction markets linked to Commodities,
- prediction markets linked to Maritime Intelligence,
- better event consistency across related markets and traditional data.

### Potential V2 additions

Targeted additions can include:

- better geopolitical market taxonomy,
- improved related-market matching for commodity and maritime events,
- event-window linking to Macro and Commodities,
- calibration improvements where resolved-market history exists,
- richer market-to-market consistency checks,
- saved prediction-market research sets,
- Copilot summaries of linked contract clusters.

### Progression notes

This workstream should be triggered by needs from Macro Events / Regimes, Commodities Events / Cross-Domain, Maritime Intelligence chokepoint/event work, or Copilot synthesis.

### Deliverable

Prediction Markets V2 should remain a targeted enhancement layer, not a major standalone rebuild.

---

## Workstream 11 - Beta Readiness

_Status: Planned_
_Dependency marker: Parallelizable, but final release polish depends on product stability_
_Parallelization note: Installer and tutorial planning can begin early; final beta packaging should wait until core workflows are stable._

### Why this workstream matters

Gamma cannot be tested by friends and family until setup, onboarding, diagnostics, and error states are understandable without developer intervention.

This workstream turns Gamma from a personal research app into something that can be installed, explored, and tested by external users.

### Goal of the workstream

Prepare Gamma for a controlled beta with non-developer users.

It should answer:

- Can someone install the app?
- Can someone run it in mock/demo mode?
- Can someone understand which providers are optional or required?
- Can someone recover from missing IBKR/TWS, API keys, or provider entitlements?
- Can someone learn the main workflows without reading the code?
- Can beta feedback be collected in a structured way?

### Functionality

#### 1. Installer

The installer should provide:

- packaged desktop app,
- backend runtime packaging,
- clear environment/config expectations,
- mock/demo mode support,
- user-facing setup path,
- upgrade/uninstall expectations.

The installer should not require the user to understand the repo layout.

#### 2. First-run setup

First-run setup should guide the user through:

- mock/demo mode,
- IBKR/TWS connection status,
- optional provider keys,
- base currency,
- SEC identity/config where relevant,
- Copilot provider configuration if used,
- diagnostics page.

The app should be usable in a limited mode even without every provider configured.

#### 3. Tutorial

The tutorial should introduce:

- Portfolio workspace,
- Research workspace,
- navigation and keybindings,
- Research scopes,
- Macro modes,
- Prediction Markets workflow,
- Crypto workflow,
- Fundamentals workflow,
- IV workflow,
- Copilot usage,
- provenance/warnings.

The tutorial should be workflow-based, not feature-list based.

Example tutorials:

- analyze a single stock,
- build a synthetic research scope,
- inspect macro divergences,
- compare a prediction market to macro context,
- inspect a crypto token and its liquidity,
- build a basic DCF scenario,
- ask Copilot for a structured research plan.

#### 4. Mock/demo data

Mock mode should become more intentional.

It should include:

- realistic portfolio sample,
- research sample,
- macro sample,
- prediction-market sample,
- crypto sample,
- fundamentals sample,
- IV sample,
- later commodities/maritime samples.

The goal is for a tester to understand the app before connecting real providers.

#### 5. Diagnostics and error states

Beta users need understandable diagnostics.

Gamma should surface:

- backend status,
- frontend/API connection,
- IBKR/TWS status,
- provider key status,
- entitlement warnings,
- cache status,
- stale data warnings,
- mock/live mode labels,
- recent error logs where safe.

Provider failures should produce actionable messages, not silent blank panels.

#### 6. Feedback loop

Beta testing should produce structured feedback.

Potential feedback categories:

- install friction,
- provider setup friction,
- confusing UI states,
- unclear warnings,
- slow workflows,
- broken data paths,
- missing tutorial context,
- high-value feature requests.

### Progression notes

Suggested progression:

1. Keep README run commands accurate.
2. Define first-run setup requirements.
3. Improve mock/demo data coverage.
4. Build or document installer path.
5. Add tutorial flows.
6. Add diagnostics and error-state polish.
7. Run controlled friend/family testing.
8. Feed findings into a beta hardening pass.

### Deliverable

At the end of Beta Readiness, Gamma should be installable and testable by trusted external users with clear setup, tutorial, mock mode, diagnostics, and feedback loops.

---

## Data Provider Strategy

Roadmap V2 should use multiple provider classes rather than search for one universal provider.

### Broker/listed-market provider

`IBKR / TWS` should remain first-class for:

- Portfolio,
- IV,
- live listed-market context,
- options,
- futures where subscriptions make sense,
- global equities and ETFs where entitled.

The adapter should remain read-only.

### Official and public data providers

Official/free providers should remain the preferred backbone for macro, energy, economic, and filing-backed data.

Important providers:

- `FRED`,
- `ALFRED` where revision history matters,
- `BLS`,
- `BEA`,
- `EIA`,
- `US Treasury`,
- `ECB`,
- `Eurostat`,
- `SEC EDGAR / data.sec.gov`.

These providers are especially useful because they are stable, source-transparent, and provenance-friendly.

### Research market-data providers

Research should support a provider-neutral market-data layer.

Potential providers:

- `IBKR / TWS`,
- `Polygon`,
- `Twelve Data`,
- `Financial Modeling Prep`,
- `EODHD`,
- other validated sources later.

The choice should depend on coverage, cost, quality, historical depth, and terms.

### Commodities providers

Commodities may use:

- `IBKR / TWS` for entitled live futures data,
- `EIA` for energy fundamentals,
- `FRED` for selected commodity/macroeconomic series,
- `Nasdaq Data Link` for public or paid commodity datasets,
- `Databento` or exchange/vendor data if full futures-curve history becomes necessary.

### Maritime providers

Maritime Intelligence may use:

- `AISstream` for prototype live AIS,
- `NOAA / MarineCadastre` for historical US AIS,
- `Global Fishing Watch` for non-commercial vessel/event-style research where terms fit,
- `AISHub` if participation is practical,
- paid AIS vendors if the tab needs reliable global coverage.

### Crypto providers

Crypto should continue to build from:

- `CoinGecko`,
- `GeckoTerminal`,
- `Alchemy`,
- `Dune`,
- optional chain/explorer/derivatives providers later.

### AI provider

Copilot should continue to use a provider boundary.

The model provider should be swappable in architecture, but the product behavior should remain:

- read-only,
- context-grounded,
- provenance-aware,
- structured where possible.

---

## Suggested V2 Implementation Gravity

This is not a strict sequence, but it describes the most sensible order of pressure.

### Early foundation

Highest-leverage early work:

- provider capability registry,
- IBKR read-only market-data boundary,
- mode-level keybindings,
- cross-tab handoff payloads,
- Copilot context-builder contract,
- README/docs alignment.

### First existing-tab hardening pass

Likely early wins:

- Research multi-mode shell,
- Research saved scopes,
- Macro EU/global/event refinements,
- Fundamentals raw-versus-normalized inspection,
- Copilot streaming/session persistence,
- IV surface model cleanup.

### First new-domain prototypes

New tabs should begin as data prototypes before full UI builds:

- Commodities futures-chain and EIA prototype,
- Commodities curve/spread schema,
- Maritime vessel/position/chokepoint schema,
- Maritime historical/mock map,
- AIS provider feasibility.

### Deep V2 buildout

After data shapes are proven:

- Strategy Lab,
- Market Overview,
- Commodities Energy and Curves & Spreads,
- IV Skew & Term and Realized vs Implied,
- Crypto Wallets & Flows,
- Fundamentals Reverse Valuation,
- Copilot dedicated workspace,
- Maritime Chokepoints and Event Replay.

### Beta readiness

As soon as the app has stable representative workflows:

- installer,
- first-run setup,
- tutorial,
- mock/demo data,
- diagnostics,
- friend/family beta loop.

---

## Summary Of Workstreams

### Workstream 1 - Cross-Cutting Platform Foundation

Build provider, provenance, cache, mode-navigation, cross-tab handoff, and Copilot-context infrastructure.

### Workstream 2 - Research V2

Turn Research into a multi-mode hub for scope analysis, market overview, imported strategy returns, comparison, and saved research.

### Workstream 3 - Macro V2

Deepen Snapshot, Cross-Asset, Rates & Policy, and Events / Regimes with better EU/global coverage, event interpretation, and cross-domain links.

### Workstream 4 - IV V2

Expand IV into a volatility lab with 3D surfaces, skew/term structure, Greeks, realized-versus-implied analysis, and implied-distribution work.

### Workstream 5 - Crypto V2

Add wallet/on-chain analytics, richer pool monitoring, better narrative/basket comparisons, and later derivatives overlays.

### Workstream 6 - Fundamentals V2

Add raw-versus-normalized inspection, better peer/reference depth, DCF improvements, reverse valuation, and eventual broader regional support.

### Workstream 7 - Copilot V2

Keep the shell shelf, add a dedicated Copilot workspace, and support streaming, sessions, synthesis, planning, memos, and later voice.

### Workstream 8 - Commodities

Build a full commodity research tab with energy, metals, futures curves, spreads, inventories, events, and cross-domain links.

### Workstream 9 - Maritime Intelligence

Build a maritime research tab around AIS, vessels, chokepoints, routes, event replay, trade-flow interpretation, and later shadow-fleet/risk analytics.

### Workstream 10 - Prediction Markets Targeted V2

Add only targeted prediction-market improvements driven by Macro, Commodities, Maritime Intelligence, or Copilot needs.

### Workstream 11 - Beta Readiness

Prepare Gamma for external testing with installer, tutorial, first-run setup, mock/demo flows, diagnostics, and feedback loops.

---

## End State Vision

If Roadmap V2 is executed well, Gamma becomes a deeper read-only research platform where the user can:

- inspect portfolios and risk,
- build and compare research scopes,
- import strategy returns without running arbitrary code,
- study market overview maps,
- interpret macro regimes,
- compare prediction markets to traditional market context,
- inspect company fundamentals and reverse valuation,
- analyze crypto tokens, wallets, baskets, and liquidity,
- study volatility surfaces and implied distributions,
- analyze commodity curves, spreads, and inventories,
- monitor maritime flows and chokepoints,
- ask Copilot to synthesize grounded context across domains,
- save research sessions and memos,
- onboard trusted testers through a real installer and tutorial.

The desired end state is not a generic terminal clone. It is a focused, transparent, read-only research environment where every major feature is backed by data models, provider boundaries, reusable analytics, provenance, and cross-domain reasoning.
