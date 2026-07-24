# Gamma Roadmap

## Source Of Truth

This is the only active roadmap for Gamma product direction, feature expansion, architecture planning, and "what to build next" decisions.

The previous phase-plan roadmap has been archived at [`docs/archive/roadmap_v1_phase_plan.md`](./docs/archive/roadmap_v1_phase_plan.md). Use that archive only for historical context about completed and paused first-roadmap scope. Do not treat archived phase details as current implementation instructions when they conflict with this file, the current repo state, or the README.

`roadmap_v2.md` has been removed as an active root document. Its current-state snapshot, workstreams, provider strategy, and beta-readiness direction have been merged here so agents and contributors have one planning source.

---

## Purpose

This roadmap defines the current expansion layer for **Gamma** after the first roadmap's completed and paused phase checkpoints.

The original roadmap moved Gamma from a portfolio/risk application into a first-pass multi-domain research environment. The current roadmap is about turning those first-pass surfaces into a deeper, more coherent research platform while adding only the new domains that are large enough to justify their own workspaces.

The core product boundary remains unchanged:

**Gamma is a read-only research environment, not an execution platform.**

Gamma can ingest market data, study portfolios, inspect strategies, analyze commodities, monitor vessels, compare companies, explore wallet behavior, and use AI to structure research. It should not place trades, rebalance portfolios, run execution bots, or provide arbitrary in-app code execution paths that could become execution surfaces.

This roadmap should therefore support four goals:

1. Harden and deepen the first-pass research tabs.
2. Add new research domains only when their data model and analytical surface justify the complexity.
3. Improve the shared platform layer so new tabs do not become isolated UI experiments.
4. Prepare Gamma for external testing through installer, tutorial, diagnostics, and friend/family beta readiness.

---

## Historical Roadmap 1 Checkpoint

The original roadmap is no longer active planning guidance, but its phase checkpoints explain how Gamma reached the current app shape.

| Original phase | Checkpoint status | Current interpretation |
| --- | --- | --- |
| Phase 1 - Prediction Markets | Complete first pass | Keep future work targeted and driven by Macro, Commodities, Sealanes, or Copilot needs. |
| Phase 2 - Macro | Paused around 84% | Continue as Macro hardening and global/provider depth inside this roadmap. |
| Phase 3 - Keyboard Navigation & Workspace Customization | Complete first pass | Preserve and extend as shared workspace infrastructure where useful. |
| Phase 4 - AI Copilot | Paused around 70% | Continue as grounded Copilot sessions, synthesis, memos, operator actions, and provider streaming work. |
| Phase 5 - Crypto | Paused around 73% | Continue as wallet/on-chain depth, narrative baskets, DEX context, and saved crypto research. |
| Phase 6 - Fundamentals | Paused around 83% | Continue as fundamentals hardening, raw/normalized inspection, reverse valuation, peers, and broader provider coverage. |

Anything previously marked deferred or paused is eligible current-roadmap scope, but should not be continued blindly. The priority rule is:

**Prioritize work that strengthens Gamma as a cross-domain research platform.**

Provider adapters, data models, reusable analytics, provenance, cross-tab handoffs, and Copilot grounding should usually outrank UI-only additions.

---

## Current App State Snapshot

_Updated: 2026-07-15_

Gamma is now a broad read-only research application with two primary workspaces:

- `Portfolio`: Portfolio, Risk, and Options.
- `Research`: SITREP, Equity Research, Strategy Lab, Macro, Prediction Markets, Crypto, Fundamentals, Commodities, Sealanes, Copilot, plus cross-listed Risk and Options.

The implemented app state is materially ahead of the original second-pass starting point:

- `Portfolio` is a working account and history surface with IBKR/mock data paths, base-currency conversion, persisted local history, benchmark-aware performance, diagnostics, and account-subscribe helpers.
- `Risk` is a real read-only analytics surface for Portfolio and Research contexts, including contribution, concentration, drawdown/cumulative/rolling analytics, beta/correlation style views, Monte Carlo-style terminal return modeling, and coverage warnings.
- `Options` now has a registered multi-mode IV workspace with Overview, Chain, Surface, Realized vs IV, Implied Probabilities, and Strategies views. It has live/mock IV surface collection, session start/stop/status routes, market-data mode controls, selectable display-grid surface models, option-chain quality metadata, derived skew/term/realized analytics, a local implied-probability surface, a strategy-builder payoff matrix, Gamma-owned chain/strategy Greeks, and Copilot tools.
- `SITREP` is the locked Research home and cross-domain triage surface. It reuses Research, Macro, Commodities, Prediction Markets, and News payloads, plus media/provider/status context, rather than acting as a standalone provider.
- `Equity Research` owns equity market overview, scope analysis, comparables, scenario context, and saved equity research. `Strategy Lab` owns imported return streams, weighted Gamma object compositions, backtest/analyze views, regime/stress lenses, and saved runs.
- `Macro` is now a six-mode workspace with Snapshot, Cross-Asset, Rates & Policy, Events / Regimes, Trade Partners, and Country Compare. It has FRED, Treasury, DB.nomics, Census trade-partner, IBKR FX proxy, US event, prediction-market linkage, coherence/lead-lag, policy path, event-study, bilateral trade-context, and country-comparison logic.
- `Prediction Markets` remains first-pass complete with Polymarket/Kalshi adapters, screener/detail/history/wallet/related/calibration routes, venue status, filtering, canonicalization, freshness, and research ranking.
- `Crypto` is a substantial first-pass workspace with CoinGecko and GeckoTerminal adapters, token overview/deep-dive/flows-liquidity modes, narratives, synthetic portfolios, DEX liquidity, flow proxies, comparison analytics, and Copilot grounding.
- `Fundamentals` is a deep current-roadmap workspace with Overview, Financials, Peers, DCF, Reverse Valuation, and Reference / Filings modes. It uses SEC/EdgarTools ingestion, IBKR market context, local peer/DCF persistence, raw-versus-normalized inspection, DCF snapshots, reverse solves, and Copilot tools.
- `Commodities` is a first-pass current-roadmap domain tab with six modes, sample/EIA/FRED/IBKR provider paths, curve/spread/inventory/event/cross-domain models, Energy and Metals analytics, and Copilot grounding.
- `Sealanes` is a paused maritime prototype with normalized maritime models, sample/static context, AISstream server-side websocket proxying, viewport live subscriptions, map overlays, route/chokepoint/port/vessel/event concepts, and clear data-provider limits.
- `Copilot` now exists both as the shell shelf and as a dedicated workspace rebuilt as a standard chat interface: conversation sidebar with search/archive/new-chat, chat transcript, pinned composer, multi-select context-scope dropdown, and Agent/Operator role controls. It supports grounded research cards, read-only domain tools, OpenAI/mock/disabled provider boundaries, local sessions/turns/context snapshots, synthesis/active-tab focus, provider-native Responses streaming through a Gamma run-event contract, cancellation/timeout/idempotent terminal persistence, and typed finalized-result transcript blocks with full current ResearchCard/source/tool/warning rendering in the dedicated tab. Memos were removed from the tab; backend memo/report endpoints remain, but the app does not yet expose a complete artifact editing/export workflow.
- `System` now exposes health, status, provider capabilities, provider usage diagnostics with activation-aware health labels, read-only boundary metadata, diagnostics, connection toggles, market-data mode, base-currency mutation, and account-subscribe helpers.
- `News` has a first-pass sample/RSS provider boundary and `/news/latest` feed route for lightweight event context.

The main remaining roadmap gaps are no longer "make the tabs exist." They are live/provider-backed reliability, provider depth, provenance adoption consistency, real cross-tab handoff actions, saved workflow depth, live-provider smoke coverage, installer/first-run readiness, tutorial flows, and richer beta-facing diagnostics/error states built on the new provider usage visibility.

### Current Tab Progress Snapshot

This table tracks the visible app tabs as of 2026-07-15. Percentages are pragmatic implementation snapshots, not release promises.

| Workspace | Tab | Current completion | What is left |
| --- | --- | ---: | --- |
| Portfolio | `Portfolio` | ~74% | Harden account/history persistence, improve first-run provider setup, broaden diagnostics around IBKR subscriptions, and add beta-facing empty/error states. Base-currency snapshot handling and OHLCV caching were fixed in July. |
| Portfolio / Research | `Risk` | ~78% | Separate research-book context from the live account in one screen (audit P1), expand per-leg contribution decomposition for research books, validate optimization/scenario assumptions more deeply, add richer stress/regime slices, and expand interactive test coverage. Strategy Lab book handoff and idempotent auto-compute now work. |
| Portfolio / Research | `Options` | ~75% | Harden live-provider smoke coverage, add historical IV/skew persistence, improve expiry/strike and moneyness controls, make source/Greeks assumptions more inspectable, make underlying-history sourcing more durable, and deepen Research/Fundamentals/Copilot handoffs. View-scoped adaptive polling, visible-symbol loading, scoped IV errors, and honest empty-surface reasons landed on July 12; SSVI visuals now separate observed option-pair IV points from fitted surface/smile/term geometry. A July 24 live XLE API retest passed with 21 points across six expiries; the active-view polling and navigation-away behavior still needs a permitted UI retest. |
| Research | `SITREP` | 100% / Complete for this pass | Closed with backend-persisted triage notes/states and migration, grounded Copilot context, enriched/deduped multi-source news, lens-preserving handoffs, shared provenance/quality badges, per-section age/oldest-section reporting, and verified Bloomberg fallback behavior at the external-embed ceiling. |
| Research | `Equity Research` | ~80% | Add fuller index/reference universes, broader non-US coverage, richer Fundamentals/Risk/IV/Copilot handoffs, comparables depth, scenario context, explicit provider selection, and a visible warning when synthetic-scope short legs are dropped. Now a self-contained view with latest-day KPIs and price provenance. |
| Research | `Strategy Lab` | ~78% | Deepen Gamma object composition, saved-run workflows, and read-only sandbox architecture decisions; fix composer state-loss traps (legs reset on tab switch, silent compose no-op before validation). Signed long/short books, all-mode UI polish, the Risk handoff, and Copilot grounding landed in June/July. |
| Research | `Macro` | ~86% | Deepen Trade Partners and Country Compare beyond first-pass US/curated coverage, expand EU/global official data, improve source citations, and wire real handoffs to Commodities, Sealanes, Prediction Markets, and Copilot memos. |
| Research | `Prediction Markets` | First-pass complete / targeted hardening | Keep enhancements opportunistic: better event taxonomy, commodity/maritime links, saved market clusters, calibration depth, and Copilot summaries where other tabs need them. Intent search is now semantically honest and verified as a live corroboration path. |
| Research | `Crypto` | ~74% | Add real wallet/transfer adapters, persistent narrative baskets, deeper pool monitoring, transaction-level DEX context, derivatives overlays, and saved crypto research sessions. |
| Research | `Fundamentals` | Complete (100% current pass) | Complete-for-now US SEC company research workspace. July 13 completion added exact-match focus continuity with explicit unsupported-instrument states, keyboard/browser-drivable search, Fundamentals-to-Strategy-Lab/Copilot/Equity Research/Risk/Options handoffs, YoY/QoQ statement trends, amendment/restatement context, terminal-value multiple framing, section-level degradation warnings, and targeted browser/reliability coverage. Broader non-US providers and consensus-estimate depth remain optional future expansion, not current-pass blockers. |
| Research | `Commodities` | ~75% | Retain freshly fetched quotes across drill interactions (audit P1), add vendor-grade futures-chain history, continuous/roll-adjusted mapping, historical curve snapshots, real metals warehouse data, seasonal inventory surprise models, unit-normalized basis checks, and live cross-domain handoff flows. The `% CHG` prior-close fix and dated daily references are verified live. |
| Research | `Sealanes` | Paused ~45% | Evaluate AIS/historical data providers, add durable AIS caching, keep static chokepoint context rendering when the live sample is empty, improve chokepoint baselines, build real event replay, enrich vessel metadata, and avoid risk labels until methodology is validated. |
| Research | `Copilot` | 76% | Extend typed transcript blocks to plans/Operator/reports/confirmations, add in-tab memo/report editing and export, finish session lifecycle and retention controls, productionize inline Operator confirmations and Agents SDK live events, validate claim/source resolution, expand Sealanes/news and priority domain drilldowns, add shelf-to-workspace continuity, and pass the Copilot release gate. |

### Completion Boundary For The Current Pass

Gamma should not keep adding major tabs or broad new domains just to fill the roadmap. For the current pass, "complete for now" means the app is ready to be treated as a stable first-pass personal research environment and a candidate for controlled external testing. The bar is provider-backed/live behavior where Gamma has configured credentials or public provider access; mock/sample data is fallback, demo, and test support, not the definition of completeness.

The current pass should be considered complete when:

- active docs agree on the current app shape, tab list, mode registry, and product boundary;
- the existing Portfolio, Risk, Options, SITREP, Equity Research, Strategy Lab, Macro, Prediction Markets, Crypto, Fundamentals, Commodities, Sealanes, and Copilot surfaces keep their current first-pass workflows working against live or provider-backed data wherever the required credentials, public endpoints, entitlements, or TWS session are available;
- provider-backed paths have smoke coverage or explicit unavailable/degraded labels, rather than silently falling back to sample data or blank states;
- cross-tab handoffs that already exist preserve the selected entity/lens well enough for normal research use;
- provider usage, provenance, freshness, and read-only boundary warnings are visible enough that a user can tell what is live/provider-backed, delayed, cached, sample, stale, derived, or unsupported;
- README run commands, validation commands, and provider setup notes are accurate;
- beta-facing diagnostics, empty states, and first-run guidance are good enough for a trusted tester who has not read the code.

Everything beyond that line should be treated as targeted future deepening, not as required to call the current app "complete for now." In particular, deeper wallet analytics, vendor-grade futures history, full global macro coverage, exhaustive options modeling, broader non-US fundamentals, richer maritime AIS history, Copilot voice, and optional external deep research are valuable future work, but they are not blockers for this completion boundary. Copilot V2's own 100% gate below is intentionally stricter than the app-wide first-pass completion boundary. A feature that only works through sample data when a real provider path is available should be treated as incomplete or degraded, not as done.

---

## Progress Tracking

This roadmap is intentionally not written as a strict linear phase plan. Most workstreams can move in parallel as long as their data dependencies are respected.

Status markers:

- `Not started (0%)`
- `Planned`
- `In progress (~X%)`
- `Blocked`
- `Complete (100%)`

Dependency markers:

- `Foundation`: should happen early because many workstreams depend on it.
- `Parallelizable`: can be worked on alongside other roadmap surfaces.
- `Independent`: can be implemented with little dependency on other roadmap work.
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

_Status: In progress (~77%)_
_Dependency marker: Foundation_
_Parallelization note: Some pieces are independent, but this workstream should start early because it shapes most V2 tabs._
_Recent progress: Workstream 1 now has shared provenance/freshness primitives, provider-agnostic cache freshness policies, a generic cross-tab handoff envelope, a compact Copilot context contract, explicit read-only boundary metadata at `/system/read-only-boundary`, hardened provider capability metadata for active/optional/sample/planned providers, an in-memory provider usage ledger exposed through `/system/provider-usage`, activation-condition metadata that distinguishes `idle_by_design`, `not_requested`, `needs_config`, `healthy`, `degraded`, and `unavailable` provider states, a compact provider-usage diagnostics surface in Settings, a reusable frontend mode-registry helper, local saved-research / fundamentals / Copilot persistence stores, first-pass diagnostics routes, a news provider boundary, and broad mode registration across Research, Macro, Crypto, Fundamentals, Commodities, Sealanes, and Options. Since June it also gained a shared provenance-badge contract adopted across views, cross-tab handoff session expiry with an earlier-sessions queue, a frontend request coordinator and adaptive poller for market-data loading, design type/space/radius token scales migrated across all views, and split runtime/system/portfolio frontend stores._

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
- Research Overview and SITREP now use explicit listed-market provider policies instead of assuming TWS. The default live Research Overview policy is `yfinance,ibkr`, while SITREP defaults to `yfinance`; both use a short 5-minute overview cache and keep source providers visible in returned payloads and warnings. `AKShare` is recognized as a planned China/Asia hook but does not have an active adapter yet.

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
- Workstream 1 is now close to its practical standalone ceiling before more provider and beta work begins. The remaining foundation work is mostly adoption work: wiring `CrossTabHandoffEnvelope` into actual UI actions, applying provenance/freshness consistently across all legacy and V2 payloads, making provider selection user-facing where needed, expanding domain-specific saved workflow models, broadening activation-condition coverage as more conditional providers are identified, and turning diagnostics/setup metadata into a beta-ready first-run experience.

### Deliverable

At the end of this workstream, Gamma should have a clearer platform layer for provider selection, source transparency, read-only enforcement, mode navigation, cross-tab handoffs, Copilot grounding, and cache/freshness display.

---

## Workstream 1A - SITREP

_Status: Complete for this pass (100%)_
_Dependency marker: Cross-domain aggregator; improves with provider foundation_
_Recent progress: A first-pass locked `SITREP` tab is now the Research workspace home. It aggregates Research Overview, Macro Snapshot, Commodities Overview, Prediction Markets screener, and News payloads into a dense situation-report surface with a Bloomberg Television embed, cross-domain change triage, equities, FX, yields, commodities tables, provider caveats, system/provider mode context, and row handoffs into Research, Macro, Commodities, and Prediction Markets. The July 12-13 completion passes added the backend-owned concurrent workspace contract, backend-persisted follow-ups with notes/resolved states and localStorage migration, a grounded SITREP Copilot context, RSS breadth plus high-confidence entity/ticker tagging and cross-feed deduplication, source reliability labels, shared provenance badges, per-section age and oldest-section reporting, and target-consumed entity/lens/timeframe handoffs. A live mock/provider-backed browser audit verified one aggregate bootstrap request, all panels populated with honest live/delayed/historical/sample labels, follow-up persistence through reload, SITREP Copilot selection, SPY news handoff, WTI Energy-lens handoff, Bloomberg fallback messaging/links, and no console errors._

### Why this workstream matters

SITREP is the operating picture for Gamma. It should not replace the domain tabs. Its job is to answer:

- What changed?
- What matters right now?
- Which deeper workspace should I open next?

This makes it different from `Research`, `Macro`, `Commodities`, or `Prediction Markets`. Those tabs remain analytical domains. SITREP is the entry point and triage layer that compresses signals from them.

### Current composition

The composition reuses existing domain payloads, but since 2026-07-13 the backend owns the aggregate contract (`SitrepService` / `GET /sitrep/workspace`) instead of the frontend firing six separate requests:

- `Research Overview` supplies equity market-map nodes, leaders, laggards, coverage, and freshness labels (plus the global-indices board).
- `Macro Snapshot` supplies focus items, FX/rates metrics, divergences, event windows, and warnings.
- `Commodities Overview` supplies commodity price, curve, inventory, event, and provider coverage context.
- `Prediction Markets` supplies open market/event context and freshness warnings.
- `News` supplies the market-news feed.
- Bloomberg Television is embedded through the public YouTube channel live-stream endpoint when YouTube/Bloomberg allow embedding.

Sections load concurrently server-side; a failing section degrades into an explicit `section_warnings` entry and a null section rather than failing the report, and the frontend keeps per-panel refresh buttons on the targeted per-domain loaders.

### Provider and data needs

Required for the next meaningful step:

- `News hardening`: complete for this pass. Normalized source, URL, publication time, detected tickers/entities, tags, summary snippets, cross-feed item deduplication, reliability/freshness labels, provenance, expanded curated RSS configuration, and explicit RSS/sample fallback behavior are implemented. Broader institutional-news coverage remains targeted future depth, not a current-pass blocker.
- `SITREP response model`: complete for this pass. `SitrepService` owns the cross-domain contract behind `GET /sitrep/workspace` with section subsets, force-refresh, concurrent composition, per-section degradation, API coverage, backend follow-up persistence, and grounded Copilot synthesis; embedded section timestamps/freshness drive section-specific age reporting.
- `Provider-neutral listed-market data`: broader and fresher equity/index/ETF coverage beyond the current narrow Research Overview seeds.
- `FX and rates freshness policy`: clearer distinction between delayed IBKR, FRED/public daily series, and unavailable intraday context.
- `Media embed fallback`: complete at the external ceiling. Gamma cannot control Bloomberg/YouTube/HLS availability; the player keeps honest loading/unavailable status plus Bloomberg and YouTube fallback links.
- `Cross-tab handoff wiring`: complete for this pass. Listed-market/news handoffs carry the selected symbol and research timeframe, FX/rates carry region/timeframe/theme, commodities carry mode plus selected instrument, prediction markets carry market ID, and persisted follow-ups preserve the same request for reload/reopen.
- `Copilot context`: complete for this pass. SITREP is a selectable grounded scope backed by a compact server-built context bundle containing workspace sections, section warnings, and persisted follow-ups.

### Completion snapshot

- `Locked navigation home`: 100% complete for this pass. SITREP is pinned as the first Research workspace tab and remains the locked Research home.
- `Dense visual shell`: 100% complete for this pass. The tokenized terminal-density shell includes market tables, Events & Markets, saved Follow-Ups, provenance, stable empty/degraded states, and responsive one-column fallback.
- `Cross-domain aggregation`: 100% complete for this pass. `SitrepService` concurrently composes all six domains behind the single workspace request with section subsets, force refresh, explicit degradation, section-specific clocks, saved triage, and Copilot synthesis on the same contract.
- `News`: 100% complete for this pass. The RSS/sample boundary now includes expanded curated feeds, headline/snippet entity detection, clickable listed-market chips, item-level cross-feed deduplication, and per-source reliability/freshness labels. Further paid/institutional breadth is future depth.
- `Bloomberg TV`: 100% at the external ceiling. HLS is best-effort because Gamma cannot control remote embed policy; loading/unavailable messaging and external Bloomberg/YouTube links are verified.
- `Provider transparency`: 100% complete for this pass. The four market tables and news use the shared provenance badge, source-quality labels are shown where supplied, Provider Status exposes per-section source/freshness/as-of/age, and the header explicitly labels the oldest loaded section.
- `Cross-tab handoffs`: 100% complete for this pass. Market/news/follow-up handoffs preserve and consume the selected entity, target mode, and available region/timeframe/theme/instrument/market lens.
- `Saved triage / follow-ups`: 100% complete for this pass. Follow-ups are capped and schema-validated in the backend JSON store with CRUD routes, notes, open/resolved state, persisted handoffs, reload durability, and one-time migration of existing `gamma.sitrep.follow_ups.v1` localStorage data.
- `Copilot context`: 100% complete for this pass. SITREP is selectable in the dock and grounds synthesis in loaded workspace summaries, section warnings, provenance sources, and saved follow-ups.

### Deliverable

At the end of SITREP V2, Gamma should open into a credible cross-asset situation report that shows market movement, news/events, live media, freshness/caveats, and direct drilldowns into the deeper research tabs without becoming a generic quote dashboard or execution surface.

---

## Workstream 2 - Research V2

_Status: In progress (~79%)_
_Dependency marker: Parallelizable, but improved by provider foundation_
_Parallelization note: The multi-mode UI can begin before all market-data providers are selected, but Strategy Lab and Overview need reliable data contracts._

### Why this workstream matters

The current Research tab is useful but narrow. It builds and analyzes single-name or synthetic scopes. This roadmap should turn Research into a more general research hub without violating Gamma's read-only boundary.

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
- The former combined Research tab has been split into two mode-bearing tabs. `Equity Research` owns `Overview`, `Scope Analysis`, `Comparables`, `Scenario / Context`, and `Saved Equity Research`; `Strategy Lab` owns `Composer`, `Backtest / Analyze`, `Regime / Stress`, `Imports`, and `Saved Runs`. Legacy `/Research/*` navigation still maps into the split tabs, and the existing single-ticker and synthetic-portfolio analyzer remains available under `Scope Analysis`. As of July 2026 the split is physical, not just navigational: the shared 4,825-line `ResearchView.svelte` was deleted and each tab is a self-contained view building as an independent lazy chunk. Strategy Lab additionally supports signed long/short book composition with per-leg validation, an inbound handoff queue with session expiry, a working `Open In Risk` handoff, and verified Copilot grounding.

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

Implementation note:
- Scope Analysis now emits clearer missing-history diagnostics that include the requested lookback and explicitly state that unavailable symbols are excluded from the aligned return stream. Saved scope payloads include compact builder metadata so safe saved scopes can be reloaded into the Scope Analysis builder without persisting raw uploads or introducing execution behavior.

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
- A first-pass `/research/overview` data contract now returns provider-neutral overview nodes, group nodes, rankings, coverage, freshness/source labels, warnings, and transformation notes. The frontend consumes that payload in the default `Overview` mode with a local treemap-style view and leader/laggard/risk panels. Current coverage is intentionally narrow: `Sample equities` is an offline-friendly sample/watchlist, `Major ETFs` depends on provider history, and `Broad US Market` uses static S&P 500-derived proxy metadata for first-pass sector/industry and market-cap sizing. It is not live index membership or complete market coverage, and nodes fall back to limited/equal sizing when market-cap data is unavailable.
- A follow-up pass made the static/proxy boundary more explicit in both payloads and UI: overview coverage now carries priced ratios, missing/thin-history counts, observation ranges, history-source labels, reference-metadata labels, and universe coverage labels. `Broad US Market` remains a static large-cap seed, not a complete or live S&P 500 membership model.

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

Implementation note:
- A first-pass `POST /research/strategy-lab/analyze` flow accepts JSON rows parsed from pasted CSV, maps date/value/optional benchmark columns, supports return or NAV/level interpretation, validates duplicate dates, missing values, minimum observations, frequency, outliers, and benchmark alignment, and returns cumulative/annualized return, annualized volatility, Sharpe-style and Sortino-style metrics, max drawdown and duration, rolling statistics, monthly/annual tables, capture ratios when benchmark data is present, warnings, and uploaded-CSV provenance. The frontend exposes this as a dense data-only Strategy Lab mode; no strategy code execution or broker actions are introduced.
- Validation now also warns on likely whole-percent versus decimal mistakes, keeps benchmark overlap failures non-fatal when the strategy stream is otherwise valid, and supports restoring a saved normalized Strategy Lab result into the Strategy Lab result state. Raw uploaded CSV rows are still not persisted by default.

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

Implementation note:
- A first-pass `POST /research/compare-scenario/analyze` flow compares normalized return streams from the latest Scope Analysis result, latest Strategy Lab result, or saved return-stream objects. It aligns observations, normalizes starting NAV, reports relative return, volatility gap, max-drawdown gap, rolling correlation and beta where available, warnings, and per-leg metrics. The frontend renders comparison selection, normalized charting, and side-by-side metrics without portfolio modification or rebalance behavior.
- Compare now returns explicit left/right observation counts plus overlap start/end diagnostics, warns on thin or short common windows, and surfaces relative drawdown as a dedicated read-only visualization. Scenario remains historical analytics only.

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

Implementation note:
- A first-pass local JSON saved-research layer now supports list, create, load, and delete routes under `/research/saved`. It stores typed items with schema version, object type, normalized payload, notes, warnings, source/provenance fields, and timestamps. The frontend can save current Scope Analysis and Strategy Lab results, list saved items in a dense table, delete them, and reuse saved return streams in Compare / Scenario. Raw uploaded CSV files are not persisted by default.
- Saved Research now supports safer reuse: saved Scope Analysis objects can reload compatible builder inputs, saved Strategy Lab objects can restore normalized result state, saved return streams remain available to Compare / Scenario, and future/unknown schema versions are loaded best-effort with explicit warnings. It is still a compact structured store, not a full notebook.

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

Implementation note:
- Items 1-6 now have first-pass implementations plus a second hardening pass for coverage diagnostics, saved-object reload/reuse, Strategy Lab validation, Compare alignment/relative-drawdown diagnostics, and a split Equity Research / Strategy Lab mode shell. Remaining Research workstream scope is mainly provider-backed depth and cross-domain breadth: full index/reference data, broader non-US coverage, richer Fundamentals/Risk/IV/Copilot handoffs, deeper macro-aware regime slicing, and a true provider-selection layer beyond the current IBKR/mock/static-reference setup.

### Deliverable

At the end of Research V2, Gamma should have a genuine research hub that can inspect market scopes, imported strategies, market overview maps, and comparisons without becoming an execution or arbitrary-code platform.

---

## Workstream 3 - Macro V2

_Status: In progress (~86%)_
_Dependency marker: Parallelizable_
_Parallelization note: Most Macro workstream scope can proceed independently, but provider foundation helps EU/global expansion and cross-tab handoffs._
_Recent progress: Macro is now a six-mode workspace with Snapshot, Cross-Asset, Rates & Policy, Events / Regimes, Trade Partners, and Country Compare; FRED, Treasury, DB.nomics, Census trade-partner, IBKR FX proxy, and US event adapters; ranked divergence/coherence and lead-lag interpretation; linked prediction-market context; policy-path and meeting-ladder proxies; event-study framing; bilateral trade-partner context; country-comparison context; deep-link style mode navigation; and Copilot drilldown tools._

#### Completion snapshot

- `Snapshot mode`: ~84% complete. The mode has region/timeframe/theme context, focus items, metric cards, why-now framing, linked prediction markets, comparison histories, FX context, and deep links into other Macro modes. Remaining work: broader non-US coverage, stronger freshness labels per card, and cleaner cross-tab links into Commodities and Sealanes.
- `Cross-Asset mode`: ~80% complete. Ranked divergences, driver/counter-signal framing, comparison overlays, linked contracts, coherence profiles, and lead/lag caveats are implemented. Remaining work: broader theme taxonomy, credit/stress proxies, provider-backed commodity links, and more explicit score component displays.
- `Rates & Policy mode`: ~88% complete. Curve nodes, front-end/path proxies, real-yield/breakeven style interpretation where series exist, linked policy contracts, meeting-ladder proxies, and event-aware context are live. Remaining work: deeper EU/ECB coverage, better official policy calendar breadth, and clearer methodology for path proxies.
- `Events / Regimes mode`: ~82% complete. Public event coverage, event windows, event-study summaries, pre/post-event coherence, and regime framing are implemented. Remaining work: richer official calendars, EU/global breadth, saved event studies, and real cross-tab event handoffs.
- `Trade Partners mode`: ~58% complete. The mode has registered navigation, a dedicated view, normalized trade-partner summary rows, first-pass radial/table visualization, Census-backed US goods-trade rows where configured, and curated fallback rows. Remaining work: services trade, revisions, commodity drilldowns, non-US official adapters, country-group treatment, and direct links into Commodities and Sealanes.
- `Country Compare mode`: ~45% complete. The mode has registered navigation, a dedicated comparison view, curated first-pass rows, and comparison-region context. Remaining work: live IMF/OECD/Eurostat-backed country series, broader indicator coverage, vintage/unit normalization, and clearer methodology/caveat panels.
- `Macro coherence engine`: ~80% complete. The engine is service-owned and produces transparent heuristic divergence, agreement/disagreement, lead/lag, and source warning context. Remaining work: reusable cross-domain extraction, stronger validation, and avoiding over-interpretation as causal inference.
- `Copilot integration`: ~78% complete. Macro context and read-only drilldown tools are exposed to Copilot. Remaining work: richer source-citation paths and saved memo/context linkage.

### Why this workstream matters

Macro already exists as a strong first-pass workspace. V2 should make it more complete, more global, and more connected to other tabs.

The current Macro workspace has:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`
- `Trade Partners`
- `Country Compare`

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

Macro should retain a compact mode structure:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`
- `Trade Partners`
- `Country Compare`

The main V2 expansion should be better US depth, meaningfully improved EU coverage, clearer Global comparisons, stronger event coverage, trade-partner and country-comparison depth, better coherence/lead-lag interpretation, and richer cross-tab links into Commodities, Sealanes, and Prediction Markets.

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

#### 5. Trade Partners V2

Trade Partners should explain how external demand, supply chains, imports, exports, FX, and commodity exposure shape a region's macro sensitivity.

V2 improvements:

- official partner-trade adapters beyond the first US Census goods slice,
- clearer country-group handling,
- services-trade and revisions context where available,
- commodity-linked trade drilldowns,
- partner concentration and trade-balance interpretation,
- links into Commodities, Sealanes, and country comparison context.

This mode should answer:

**Which bilateral trade links could explain or pressure the current macro view?**

#### 6. Country Compare V2

Country Compare should make cross-country macro context explicit instead of hiding it inside regional labels.

V2 improvements:

- IMF/OECD/Eurostat-backed indicator rows,
- harmonized units and frequencies,
- vintage/revision caveats where providers expose them,
- clearer comparison-region controls,
- external-balance, growth, inflation, labor, policy, and reserves context,
- links back into Cross-Asset and Events / Regimes.

This mode should answer:

**Is the current region-specific signal actually local, or part of a broader country divergence?**

#### 7. Macro coherence engine V2

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

Macro V2 needs macro time series, yield-curve histories, real-yield and breakeven histories, FX and dollar proxies, credit/stress proxies where available, official event calendars, trade-partner and country-comparison datasets, linked prediction-market metadata, linked commodity-market context, region and concept mappings, and provenance for every transformed series.

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

At the end of Macro V2, Gamma should have a more globally useful macro workspace with stronger event interpretation, better rates/policy depth, richer cross-asset coherence, explicit trade/country comparison context, and cleaner links to commodities, sealanes, and prediction markets.

---

## Workstream 4 - IV V2

_Status: In progress (~74%)_
_Dependency marker: Parallelizable, but dependent on IBKR / options data quality_
_Parallelization note: UI and analytics can progress incrementally, but live coverage depends on options entitlements and provider behavior._
_Recent progress: The June 5 options pass moved IV V2 from a surface viewer toward a usable volatility lab. Options now has registered modes for Overview, Chain, Surface, Realized vs IV, Implied Probabilities, and Strategies; `/iv/surface`, `/iv/session`, start/stop session routes; live/mock surface collection; market-data mode/depth controls; selectable line/spline/SSVI display-grid fitting with fit/fallback metadata; option-contract, pair, quality, expiry-analytics, model-metadata, and pricing-assumption models; frontend derived surface paths, skew rows, term-structure rows, realized-volatility comparisons, local implied-probability density slices with selectable probability mass, a chain-driven strategy builder with mark-to-model payoff matrix, Gamma-owned Black-Scholes chain and strategy Greeks, and Copilot IV surface/session tools. A July 12 reliability pass restricted adaptive polling to the active Options view with failure backoff, stopped idle session checks from repeatedly fetching underlying history without a real surface, persisted the visible input symbol at the app boundary, scoped IV errors so polling cannot erase them, and added explicit disconnected/collecting/entitlement/no-snapshot states. A follow-up visual pass made applied/partial parametric fits analytically honest: SSVI renders the fitted grid as the 3D surface and the actual blended option-pair IV cells as discrete observations, while smile and term visuals use fitted lines with observed markers; linear and spline interpolation views retain their simpler presentation._

#### Completion snapshot

- `Overview and Chain modes`: ~72% complete. The workspace can orient around a selected underlying, expose the front expiry chain, summarize ATM/skew/term context, show front-expiry smile/payoff context, and send priced chain rows into the strategy builder. Remaining work: better expiry/strike filtering, moneyness controls, more explicit source quality, and richer chain diagnostics.
- `Surface mode`: ~82% complete. The mode can request live/mock surfaces, display surface statistics, render heatmap/3D-style paths, expose provider/session/source warnings, and let the user choose line interpolation, spline interpolation, or SSVI for the display grid while preserving observed chain rows. Remaining work: richer 3D interaction, historical surface comparison, and better moneyness normalization.
- `Skew and term-structure modules`: ~67% complete. Derived term structure, front smile, and wing-skew rows are live from the current surface, but they are currently modules inside the registered workspace rather than standalone history-aware views. Remaining work: persistent skew history, richer smile diagnostics, event annotations, and cross-symbol comparison.
- `Realized vs IV mode`: ~55% complete. Realized-volatility windows and front-IV spreads can be derived when price history is available. Remaining work: more durable underlying history sourcing, configurable windows, IV percentile/rank history, and regime/event overlays.
- `Implied Probabilities mode`: ~64% complete. A local lognormal probability-density surface is derived across expiries and strikes from the fitted IV grid, with selectable probability mass on the expiry slice. Remaining work: clearer methodology labeling, skew-aware/risk-neutral density methods beyond the local proxy, snapshot comparison, and stronger sparse-data warnings.
- `Strategies mode`: ~62% complete. Selected chain rows can build multi-leg long/short call/put structures, show net premium, max profit/loss, breakevens, net Greeks, and a mark-to-model payoff matrix by underlying price and remaining DTE. Remaining work: reusable templates, editable quantities/leg parameters, scenario/event context, saved strategies, and clearer read-only/non-execution labeling.
- `Greeks / source quality`: ~72% complete. Backend models carry provider and Gamma-derived Greeks, pricing assumptions, quality metrics, contract selection metadata, and market-data line pressure; the frontend now shows Gamma-owned chain Greeks and strategy Greek summaries. Remaining work: fuller source-vs-derived inspection, assumptions drilldown, possible Greeks-specific mode only if useful, and broader entitlement/session diagnostics.
- `Copilot integration`: ~72% complete. Copilot can inspect IV surface context and session status. Remaining work: deeper skew/term/realized/probability/strategy drilldowns and cross-tab handoffs from Research/Fundamentals.

### Why this workstream matters

The current IV tab is now a first-pass volatility research workspace, but it still needs reliability, history, source transparency, and handoff hardening before IV V2 can be called complete for now.

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

Current registered modes:

- `Overview`
- `Chain`
- `Surface`
- `Realized vs IV`
- `Implied Probabilities`
- `Strategies`

Earlier second-pass planning treated `Skew & Term`, `Source`, `Greeks`, and `Events / Cross-Tab` as possible standalone modes. The current implementation keeps skew, term, Greeks, and source quality inside the registered workspace modules for now, and leaves event/cross-tab behavior as future handoff work rather than a separate mode. `Implied Probabilities` is the shipped label for the distribution work because the current implementation is a local density/probability-mass inspection surface, not a fully vendor-grade risk-neutral-distribution engine.

#### 1. Surface mode

This mode has evolved the original heatmap into a richer volatility-surface explorer.

Implemented first-pass behavior:

- 3D surface visualization,
- expiry/strike heatmap,
- selected expiry slices,
- selected strike slices,
- spot-relative annotations,
- surface freshness and entitlement warnings,
- mock-surface parity for development.
- selectable display-grid model: line interpolation, spline interpolation, or SSVI,
- fit status and fallback notes carried in the surface payload.

Remaining work should prioritize historical comparison, moneyness normalization, and interaction quality over more complex model fitting.

#### 2. Skew and term-structure modules

These modules should focus on structure.

It should show ATM term structure, put skew by expiry, call skew by expiry, selected delta/moneyness slices, skew change versus prior snapshot where available, term-structure slope, and event-related kinks.

This mode should help answer:

**Where is the market paying for asymmetry or event risk?**

#### 3. Greeks and source-quality inspection

This inspection layer adds basic options sensitivity context without requiring a standalone mode yet.

Current outputs:

- delta by strike/expiry,
- gamma by strike/expiry,
- vega by strike/expiry,
- theta by strike/expiry,
- rho by strike/expiry,
- aggregate strategy Greeks for selected multi-leg structures,
- provider/derived Greek counts in quality metadata,
- pricing assumptions and methodology notes in the backend payload.

This layer remains research context, not a position-management or execution surface.

Remaining work is to make provider-returned fields, Gamma-derived estimates, and their assumptions more directly inspectable in the UI.

#### 4. Realized vs IV mode

This mode should compare market-implied volatility against realized behavior.

It can include realized volatility windows, implied volatility at selected tenor, IV percentile/rank where history exists, volatility spread, rolling realized/IV comparison, and event-window realized move versus implied move.

Data limitations should be explicit because IV history may be provider-constrained.

#### 5. Implied Probabilities mode

This mode explores implied probability and risk-neutral-distribution ideas at a first-pass level.

Current behavior:

- local lognormal density surface derived from the fitted IV grid,
- implied probability mass by price bucket,
- comparison across expiries,
- selected expiry slice,
- selectable strike range with probability mass readout,
- visible methodology assumptions.

Remaining work is to add skew-aware density methods, distribution shifts across snapshots, stronger sparse-data caveats, and clearer separation between local proxy and full RND methodology.

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

1. Run and document live/mock smoke coverage for the June 5 Options flows: surface model switching, implied probabilities, strategy payoff matrix, and Gamma-owned Greeks.
2. Improve expiry/strike and moneyness controls without expanding the mode list.
3. Make source, quality, provider-vs-derived Greeks, and pricing assumptions easier to inspect from the UI.
4. Make underlying history sourcing durable enough for Realized vs IV to be reliable across normal research symbols.
5. Add historical IV/skew/surface snapshot persistence so Surface, Skew/Term, Realized vs IV, and Implied Probabilities can compare against prior states.
6. Add saved strategy templates/quantities only as read-only research artifacts, with explicit non-execution framing.
7. Deepen handoffs to Research, Fundamentals, and Copilot after the current Options state is stable.

#### Complete-for-now blockers

IV V2 can be called complete for now once the current shipped workspace is stable and honest rather than exhaustive. The remaining blockers are:

- live-provider smoke coverage for `/iv/surface`, `/iv/session`, model switching, probability slices, payoff matrices, and Greeks on at least one liquid underlying with TWS connected and one mock-mode path;
- a clearer source/quality inspection path that shows observed cells, interpolated cells, provider Greeks, Gamma-derived Greeks, fit status, pricing assumptions, market-data mode, and entitlement/session warnings in one place;
- durable underlying price-history sourcing for Realized vs IV, with explicit unavailable/degraded labels when history cannot be loaded;
- enough expiry/strike/moneyness controls to make max-depth snapshots usable without asking the user to infer which contracts were selected;
- historical IV/skew/surface snapshot persistence sufficient for basic before/after comparison, even if not vendor-grade history;
- explicit read-only/non-execution language in the Strategies flow and docs, since Gamma now calculates payoff and Greeks but still does not place or route orders;
- Copilot/Research/Fundamentals handoffs that preserve selected symbol, expiry, surface model, and warnings well enough for normal research use.

### Deliverable

At the end of IV V2, Gamma should have a volatility lab that can inspect chains, surfaces, skew, term structure, realized-versus-IV context, strategy payoffs, Greeks/source quality, and implied probabilities while remaining read-only. The current implementation has crossed the feature-shape line for that lab; the remaining work is reliability, history, source transparency, and handoff polish.

---

## Workstream 5 - Crypto V2

_Status: In progress (~74%)_
_Dependency marker: Parallelizable_
_Parallelization note: Wallet/on-chain work can progress independently, but provider selection affects depth and reliability._
_Recent progress: Crypto operates as a multi-mode workspace with Overview, Deep Dive, and Flows & Liquidity; CoinGecko and GeckoTerminal adapters; token detail/history/liquidity/flow/comparison routes; layer treemaps; narrative baskets; synthetic portfolio analysis; DEX liquidity tables; first-pass flow proxies; market-cap/liquidity/turnover/momentum screening; and Copilot crypto context/tools._

#### Completion snapshot

- `Overview mode`: ~82% complete. Cross-sectional screening, sorting, layer treemaps, narrative buckets, market-cap/liquidity/turnover/momentum diagnostics, and fallback basket classification are live. Remaining work: saved filters, stronger on-chain factors, and curated Gamma narrative definitions.
- `Token Deep Dive`: ~78% complete. Token detail, price history, supply/FDV context, liquidity context, comparison views, and warnings are implemented. Remaining work: unlock/supply schedule context, richer contract mapping, and more durable peer selection.
- `Narratives & Baskets`: ~74% complete. Provider category baskets, fallback layer baskets, synthetic portfolios, token-versus-basket comparison, and basket exposure summaries are live. Remaining work: persistent curated baskets, basket-versus-basket depth, and saved narrative research sets.
- `Wallets & Flows`: ~30% complete. Flow interpretation exists through DEX-derived proxies, concentration labels, and liquidity/turnover style summaries. Remaining work: actual wallet balances, transfers, counterparty/exchange labels, holder changes, and provider confidence metadata.
- `DEX Liquidity`: ~72% complete. GeckoTerminal-backed liquidity, pool matching, pool tables, concentration and flow summaries are live. Remaining work: pool monitoring over time, transaction-level drilldowns, suspicious liquidity changes, and stronger slippage models.
- `Derivatives`: ~0% complete. Funding, basis, open interest, and exchange derivatives overlays remain later work.
- `Copilot integration`: ~78% complete. Crypto context, price/liquidity/comparison tools, and provenance-aware summaries are available. Remaining work: wallet-aware tools and saved crypto research sessions.

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

Current registered modes:

- `Overview`
- `Deep Dive`
- `Flows & Liquidity`

The current UI consolidates narratives, baskets, synthetic portfolios, DEX liquidity, and flow proxies inside these three modes rather than exposing a longer mode bar. Future wallet/on-chain depth may justify a dedicated `Wallets & Flows` mode, and derivatives remain a later extension.

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

_Status: Complete (100% current pass)_
_Dependency marker: Parallelizable_
_Parallelization note: US SEC improvements can progress independently; European/international expansion depends on provider and normalization choices._
_Completion note: Fundamentals V2 now has first-class Overview, Financials, Peers, DCF, Reverse Valuation, and Reference / Filings modes; raw-versus-normalized SEC inspection; service-owned implied-expectation solves; peer diagnostics; DCF snapshots; sector-aware sanity checks; exact-ticker focus continuity; explicit unsupported ETF/fund/non-US states; keyboard-, automation-, and browser-drivable search; reusable company/scenario/peer context handoffs into Strategy Lab and Copilot; selected-company continuation into Equity Research, Risk, and Options; YoY/QoQ statement changes; amendment chronology; terminal-value multiple framing; section-level degraded-state warnings; and browser/reliability coverage. Broader regional/provider expansion is future depth outside the current completion boundary._

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

_Status: In progress (76%; checkpoint 1 verified)_
_Dependency marker: Parallelizable, but quality depends on tab-owned context builders_
_Parallelization note: Streaming and session persistence can be built early. Deep domain reasoning improves as each tab exposes better context and tools._
_Recent progress: The dedicated Copilot tab was rebuilt in June 2026 as a standard chat interface with session search/archive/new-chat, a pinned composer, Agent/Operator controls, and multi-select context scope. On July 14, the Agent path gained provider-native Responses streaming behind one Gamma NDJSON run-event contract. On July 15, finalized Agent results gained a discriminated transcript-block model and the dedicated tab reached parity with the shelf for all current ResearchCard fields and evidence. On July 17, checkpoint 1 replaced raw `urllib` transport with the supported OpenAI SDK, made runs server-owned with bounded cursor replay across disconnects, added completed function-argument and provider-error events, moved shelf Agent and custom-loop Operator work onto the shared run/reducer contract, added safe-boundary Operator cancellation, and verified idempotent single-terminal persistence across cancellation, timeout, refusal, incomplete output, provider failure, duplicate/stale/post-terminal events, and reconnect. The detailed engineering spec remains [`docs/copilot_v2_tab_plan.md`](./docs/copilot_v2_tab_plan.md); the milestone sequence and percentage gates below are the authoritative roadmap path to 100%._

### Why this workstream matters

Copilot already spans a quick shell shelf and a dedicated workspace. The remaining work is to turn those implemented surfaces into one reliable, replayable, source-resolved research system rather than two partially overlapping interfaces.

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

Current and target dedicated workspace structure:

- no global mode bar,
- a compact focus selector for `Synthesis` versus `Active Tab`,
- a role selector for `Research Agent` versus `Research Operator`,
- a composer grounded in Gamma context,
- an Operator Plan / Run Operator path for ordered app-native tests and confirmed local research-state workflows,
- session/thread history,
- artifact creation from persisted turns, with complete in-tab memo/report editing still required,
- scope controls for cross-domain synthesis.

Earlier drafts considered `Ask`, `Synthesize`, `Plan`, `Memo`, `Sessions`, and later `Voice` as separate modes. The implemented direction intentionally keeps Copilot closer to the SITREP pattern: a dedicated workspace with internal focus controls rather than a durable tab-level mode bar. This keeps Copilot from becoming another multi-mode analytical domain while still giving it persistent sessions and memo output.

#### Completion snapshot

- `Shell shelf`: ~88% complete. The contextual card remains live across supported tabs with read-only grounding, multi-select scope, full ResearchCard detail, provider warnings, and the same streaming loader/reducer used by the workspace. Remaining work: `Open in Copilot` continuity, source navigation, and reliable promotion of the exact thread/context.
- `Dedicated workspace`: ~80% complete. The standard chat interface now has sessions/search/archive/new-chat, a pinned composer, Agent/Operator controls, multi-select context scope, real provisional provider deltas, Stop/Retry, typed non-success states, full finalized ResearchCard/evidence parity, and native single-context domain resolution. Remaining work: typed plan/Operator/report/confirmation blocks, support inspector behavior, artifacts, richer session lifecycle, and source navigation.
- `Streaming and run lifecycle`: checkpoint 1 complete. The supported OpenAI SDK consumes typed Responses events; Agent and custom-loop Operator runs use one server-owned Gamma event contract with monotonic ids, completed function arguments, tools, warnings, confirmations, refusal/incomplete/provider-error/usage states, cancellation, timeout, bounded replay, disconnect survival, and exactly one persisted terminal. UI deltas remain provisional memory state rather than durable truth. Restart replay and richer retained run/session state remain checkpoint 3 work.
- `Session persistence`: ~80% complete. Local JSON persistence stores sessions, turns, context snapshots, and model/card results, and the chat sidebar now supports session search, archive/unarchive, and new-session flows. Remaining work: richer session titles, deletion, and migration/version handling.
- `Artifacts, memos, and reports`: ~50% complete. Backend memo/report schemas, persistence, generation, and Markdown export foundations exist, but the app does not yet expose a complete in-tab artifact workflow. Remaining work: source-turn selection, templates, editing, autosave, duplicate/delete, explicit overwrite, preview/export, and exact source/trace linkage.
- `Read-only tools and grounding`: ~80% complete. Copilot has domain context builders and read-only tools for Portfolio, Research, Strategy Lab, Risk, IV, Macro, Commodities, Prediction Markets, Crypto, Fundamentals, and synthesis, and the June grounding overhaul plus handoff-context coverage improved context fidelity. Remaining work: Sealanes/news drilldowns, stronger provenance citations, and tool coverage parity across V2 tabs.
- `Research Operator`: ~68% complete. Backend action registry metadata, operator plan models, shared live custom-loop events, safe-step cancellation, persisted progress/traces, typed read-only analyses, DCF confirmation checkpoints, reports, an eval harness, and Agents SDK orchestration behind a feature flag are live. Remaining work: provider-native Agents SDK progress parity, inline confirmations/diffs/rollback context, failure/resume evals, broader read-only drilldowns, and an evidence-backed default-orchestrator decision.
- `Diagnostics, routing, and release evidence`: ~45% complete. Provider configuration and usage foundations exist, and Agent/Operator test/eval paths are present. Remaining work: versioned model policy, resolved routing/usage/latency visibility, retention controls, structured diagnostic ids, accessibility/responsive coverage, restart replay, and representative live smoke gates.
- `Voice and optional external deep research`: excluded from Copilot V2 100%. They remain later opt-in extensions after the text workspace passes its release gate.

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

### Path from ~72% to 100%

Copilot percentage should advance only when a checkpoint's exit criteria are implemented and verified. The target percentage is a completion gate, not an estimate based on code volume. Work inside adjacent checkpoints may overlap, but a later percentage should not be claimed while an earlier blocker remains open.

| Checkpoint | Target | Required delivery | Exit criteria |
| --- | ---: | --- | --- |
| Current verified baseline | ~72% | Native Agent streaming first slice, cancellable Gamma run-event contract, finalized-result transcript blocks, dedicated/shelf ResearchCard evidence parity, existing sessions/tools/operator foundations. | Current Copilot backend suites, frontend suites, typecheck, and production build remain green; live-provider failures stay typed rather than becoming neutral empty cards. |
| 1. Finish transport and run lifecycle | **76% verified 2026-07-17** | Supported OpenAI SDK typed streaming; completed function-call arguments, tool start/result, refusal, incomplete, provider error, usage, and final events; bounded cursor replay; shelf Agent and custom-loop Operator on the shared event/reducer contract. | Agent and Operator each produce one run id and one persisted terminal; pre-first-event and safe-boundary cancellation, timeout, reconnect, disconnect, duplicate/stale/post-terminal, refusal, incomplete, and provider-error tests pass. Focused gate: 85 backend tests; frontend: 259 tests plus typecheck/build/desktop check; desktop and 720px mock Agent/Operator UI inspected with zero console errors. |
| 2. Complete transcript and evidence contract | 80% | Extend discriminated transcript blocks to plans, Operator steps/results, reports, confirmations, diffs, and typed non-success states; resolve claim evidence to known source ids; add source/context navigation; visibly separate source-backed claims, inference, assumptions, missing data, and warnings. | Every persisted source-backed claim resolves to the turn's context/tool source registry or is reclassified before persistence. Shelf and workspace render equivalent evidence, and supported source refs open the correct Gamma tab/mode/entity without losing lens context. |
| 3. Finish sessions and in-tab artifacts | 86% | Add session rename, restore, delete, schema versioning/migrations, corrupted-record recovery, and faithful persistence of role/depth/scope/model/run/usage/artifact state. Add memo/report source-turn selection, templates, edit/autosave, preview, duplicate/delete, explicit overwrite, and Markdown export inside the workspace. | Restarting Gamma faithfully reopens transcript, context snapshots, runs, plans, traces, confirmations, memos, and reports. Artifact exports preserve claim labels, inline evidence refs, source metadata, warnings, provider/model metadata, and source-turn links. |
| 4. Productionize Research Operator | 91% | Stream Operator progress live; cancel only between safe steps; render inline confirmation checkpoints with before/after diff and rollback/snapshot context; retain one authoritative action registry and permission path; expand failure, stale-context, partial-tool, repeated-confirmation, cancellation, and resume evals. | Bounded read-only analyses run automatically, while every durable/non-trivial local research-state mutation stops on the exact active confirmation token. No trade, order, account, rebalance, wallet, or arbitrary-code capability exists. The default-orchestrator decision is backed by permission and quality evals rather than feature-flag availability alone. |
| 5. Close context and tool-coverage gaps | 94% | Add Sealanes context/read-only drilldowns without invented risk labels; make news item-level context first class; add priority IV, Commodities, and Equity Research drilldowns; implement context-size budgets, deterministic compaction, stale-context invalidation, and navigation mappings/fingerprints for every selectable scope. | Representative NVDA, CPI/Fed, oil-disruption, and portfolio-rate-shock requests select the appropriate domains, explain omissions, preserve freshness/provenance, and degrade explicitly when a provider or context is unavailable. |
| 6. Finish continuity, model policy, retention, and diagnostics | 97% | Add `Open in Copilot` from the shelf with exact thread/context/entity/lens continuity; add a versioned capability-aware model policy and eval-backed routing; record resolved model, routing reason, effort, latency, usage/cache/provider/tool counts, cancellation outcome, and orchestrator; explain local versus provider retention and support a tested `store: false` path. | Settings and the run inspector expose actionable configuration/provider/model/storage state and copyable safe diagnostic ids without credentials or sensitive payloads. Shelf promotion loses no context. Routing and any Agents SDK default are justified by recorded eval results against the retained baseline. |
| 7. Pass the Copilot V2 release gate | 100% | Complete accessibility, keyboard, desktop/narrow responsive, first-run, disabled/unconfigured/rate-limit/quota guidance, mock/offline, migration, restart-replay, and live-provider validation. Reconcile roadmap, detailed spec, README, provider setup, and validation commands. | Backend, frontend, build, eval, persistence-replay, and permission-invariant suites pass. Live Agent and Operator smoke passes for the representative research prompts when providers are intentionally configured. Happy, degraded, unavailable, refused, incomplete, cancelled, timeout, and provider-error states are all visible and tested. No execution-capable tool or hidden sample fallback crosses the read-only boundary. |

### Sequencing and dependency rules

1. Checkpoints 1 and 2 are the immediate blockers and may proceed together because the shared run-event and transcript-block contracts constrain all later UI.
2. Checkpoint 3 should land before broadening durable mutations so sessions and artifacts can replay confirmations and rollback context faithfully.
3. Checkpoint 4 may deepen read-only Operator coverage while checkpoint 3 is underway, but no new durable mutation family should ship before inline confirmation, persistence, and replay are reliable.
4. Checkpoint 5 should add backend context/tool contracts before large UI additions; source ids, freshness, fingerprints, and navigation mappings are part of each tool's definition of done.
5. Checkpoint 6 model routing must remain eval-backed. Do not advance completion by changing model strings alone.
6. Checkpoint 7 is a hard release gate. Passing unit tests without representative live-provider, restart-replay, accessibility, and permission-boundary evidence is not 100%.

Current model candidates and OpenAI-specific implementation details remain documented in [`docs/copilot_v2_tab_plan.md`](./docs/copilot_v2_tab_plan.md). The roadmap requirement is stable: routing must be capability-aware, versioned, observable, and supported by comparative eval evidence.

### Explicit non-goals for Copilot V2 100%

The following do not block 100%:

- voice input or spoken output,
- unrestricted web browsing,
- default long-running external deep research,
- arbitrary code execution,
- trading, order routing, account mutation, portfolio rebalancing, wallet connection/signing, or wallet transactions,
- adding every conceivable domain tool after the representative cross-domain research workflows pass.

Optional external deep research may be added later only as an explicit background job with provider/data-retention disclosure, citations, cancellation, and hard spend/tool limits. Voice remains a later extension after the text workspace is complete.

### Deliverable

At 100%, Gamma should have one coherent Copilot research system across the shelf and dedicated workspace. It should stream and replay grounded Agent and Operator work; resolve claims to known evidence; run bounded read-only Gamma analyses; stop for visible confirmation before durable local research-state changes; create, edit, save, reopen, and export memos/reports; preserve session, context, trace, artifact, provider, model, usage, and warning state across restart; and expose understandable diagnostics and non-success states while preserving Gamma's read-only market/account/wallet boundary.

---

## Workstream 8 - Commodities Tab

_Status: In progress (~75%)_
_Dependency marker: First-pass sample/EIA/IBKR vertical slice is live; vendor-grade futures-chain history, continuous front-month mapping, real metals warehouse feeds, physical-flow data, and full cross-domain handoffs remain data-provider dependent._
_Parallelization note: The current tab can be hardened independently across UI, analytics, Copilot grounding, and sample/EIA coverage, but deeper curve history, provider-validated crack spreads, true seasonal inventory models, real warehouse stocks, and maritime links need stronger futures and physical-flow data._
_Recent progress: Commodities now exists as a first-pass research tab with `Overview`, `Energy`, `Metals`, `Curves & Spreads`, `Inventories & Fundamentals`, and `Events / Cross-Domain` modes; normalized commodity/futures/inventory/event models; `/commodities/*` API routes; a sample provider; optional EIA official energy inventories, storage, production, crude trade, refinery, and product-demand fundamentals with FRED spot/proxy history enrichment; optional IBKR/TWS read-only futures-curve construction from discovered `FUT` contracts; Gamma-owned curve/spread/inventory/overview analytics; expanded sample metals coverage for platinum, aluminum, and zinc; sample COMEX/LME warehouse-stock proxies; Energy crack-spread matrix, term-structure heatmap, inventory seasonality cloud, vessel/flow proxy modules, EIA fundamental stack chart, and fundamental tape with sparklines; Metals macro-driver correlation, precious-ratio gauges, warehouse-stock, and copper/aluminum substitution-spread modules; frontend matrix/chart/ranking/detail panels; mode shortcuts/navigation registration; provider capability metadata; read-only warnings; tests; and Commodities Copilot context._

#### Completion snapshot

- `Tab shell and mode navigation`: ~78% complete. Commodities is a top-level Research workspace tab with the intended six-mode structure, shared selected-instrument state, refresh behavior, mode shortcut registration, and Copilot shelf integration. Remaining work: durable deep links, richer state persistence, real cross-tab handoff actions, and saved commodity watchlists.
- `Domain models and API surface`: ~76% complete. Gamma now has normalized instruments, price histories, futures contracts, curve nodes, spreads, inventories/fundamentals, overview analytics, events, cross-domain links, coverage metadata, Pydantic schemas, and `/commodities/*` routes. Recent work added composite crack-spread and substitution-spread definitions without changing the read-only API boundary. Remaining work: durable spread/watchlist entities, a first-class historical curve-snapshot contract, explicit front-month/continuous-futures mapping, richer event-source models, and stronger provider-quality metadata.
- `Provider layer`: ~68% complete. The tab has an offline sample provider, optional EIA official US energy inventory/storage/production/import/export/refinery/demand enrichment, optional FRED spot/proxy price histories, optional IBKR/TWS futures curves built from read-only contract discovery, market-data snapshots, front-contract history, and local daily curve observations, plus expanded sample platinum/aluminum/zinc and COMEX/LME warehouse-stock proxy rows. Remaining work: vendor-grade futures-chain history, exchange calendar handling, continuous/roll-adjusted histories, regional/PADD-level energy depth, real metals warehouse feeds, and provider quality scoring.
- `Overview mode`: ~73% complete. The workspace has market breadth, a commodity matrix with dated prior-close `% CHG` (the stale-cached-curve P0 was fixed and verified live), per-row daily price references, price-basis reconciliation, selected term-structure stack, momentum/roll scatter, ranked backwardation/contango/inventory/spread/mover panels, event highlights, and cross-domain notes. Remaining work: retaining freshly fetched quotes across drill interactions (drilling currently reverts to the cached view), richer "what changed" windows, stored historical curve-stack comparisons, true inventory-surprise context, unit-normalized basis checks, alert/watchlist behavior, and cleaner click-through handoffs.
- `Energy mode`: ~82% complete. WTI, Brent, Henry Hub, gasoline, and heating oil have first-pass summaries, curves, adjacent calendar-spread heatmap, 1-1/2-1-1/3-2-1 crack-spread matrix, selected EIA inventory/storage/production/trade/refinery/demand fundamentals, indexed fundamental-stack charting, fundamental tape sparklines, inventory seasonality-cloud rendering, sample event context, vessel/flow handoff proxy, and optional IBKR roots. Remaining work: provider-validated crack-spread methodology, true seasonal surprise models, better Brent/global handling, regional/PADD-level energy detail, real tanker/floating-storage feeds, and optional LNG/electricity proxies.
- `Metals mode`: ~60% complete. Gold, silver, platinum, copper, aluminum, and zinc now have first-pass sample/FRED/IBKR-compatible coverage where configured, price histories, curves, gold/silver and gold/platinum ratios, copper/gold and copper/aluminum relative-value spreads, Macro USD/real-yield correlation rendering, and sample COMEX/LME warehouse-stock proxy rows. Remaining work: real exchange/warehouse inventory coverage, stronger China/global demand context, richer industrial-metals breadth, and provider-backed macro/warehouse data-quality labels.
- `Curves & Spreads mode`: ~68% complete. Current curve charts/tables, contango/backwardation labels, front/M1-M6 spreads, inter-commodity ratios, composite crack proxies, substitution spreads, z-scores, and percentiles exist where history is available. Remaining work: historical futures-curve stacks, provider-backed spread history, curve-change-by-date views, roll calendar handling, seasonality-aware spreads, and saved spread watchlists.
- `Inventories & Fundamentals mode`: ~64% complete. Sample inventory/fundamental series, selected official EIA weekly energy inventories/storage/production/trade/refinery/demand series, inventory cloud rendering, indexed fundamental-stack charting, compact fundamental tape sparklines, panel-level history sparklines, and sample COMEX/LME warehouse rows feed latest value, change, percentile, and interpretation panels. Remaining work: real surprise models, true 5-year seasonal ranges, real metals inventories, regional coverage, and tighter price-versus-inventory comparison modules.
- `Events / Cross-Domain mode`: ~40% complete. Sample EIA release events, Red Sea/Suez watch items, and heuristic Macro, Maritime, Prediction Markets, and Copilot links are live. Remaining work: real event calendar ingestion, actual `CrossTabHandoffEnvelope` flows, prediction-market retrieval, Sealanes route/chokepoint context, weather/geopolitical event sources, and saved commodity notes.
- `Copilot and test coverage`: ~71% complete. Commodities has a compact Copilot context helper, mock Copilot tool/card support, backend tests for sample/EIA/IBKR/API/Copilot behavior including broader EIA fundamentals, and frontend render coverage for the workspace shell, degraded provider notices, Energy deep-flow/fundamental modules, and Metals macro modules. Remaining work: richer drilldown tools, source-citation drill paths, live-provider smoke coverage, and broader interactive UI tests.

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

Current progression:

1. First-pass commodity instrument, futures-curve, inventory, event, spread, and overview schemas are live; next schema work should focus on historical curve snapshots, continuous/front-month mapping, saved spread/watchlist entities, and provider-quality metadata.
2. IBKR/TWS can provide a usable read-only first pass for discovered futures curves and front-contract history when TWS is connected and entitled; next work should validate pacing, entitlement behavior, root mappings, exchange calendars, and whether IBKR is enough for stored historical curve analytics.
3. Energy mode is the strongest vertical and should be hardened next with deeper EIA fundamentals, true 5-year seasonal ranges, provider-validated crack-spread framing, real flow data, and clearer global/Brent caveats.
4. Curves & Spreads should move from current-snapshot analytics toward stored historical curve stacks, curve-change views, spread watchlists, and provider-backed spread histories.
5. Metals mode has a stronger sample/proxy research surface after the macro-correlation, precious-ratio, warehouse-stock, and substitution-spread pass, but should remain careful until provider coverage for real futures, warehouse stocks, and macro overlays is stronger.
6. Cross-domain links to Macro, Prediction Markets, and Copilot are currently heuristic notes; they should become real handoff flows once the shared handoff layer has domain-specific target behavior.
7. Maritime Intelligence links should wait for stronger route/chokepoint and commodity-flow context from the Sealanes workstream.
8. Deeper paid futures data should be evaluated only if IBKR/TWS proves insufficient for historical curve storage, spread analytics, and reliable multi-contract coverage.

### Deliverable

At the end of Commodities V2, Gamma should have a full commodity research workspace with curves, spreads, inventories, energy/metals context, and cross-domain links into Macro, Maritime Intelligence, Prediction Markets, and Copilot.

---

## Workstream 9 - Maritime Intelligence Tab

_Status: Paused (~45%)_
_Pause note: Workstream 9 is paused at the current Sealanes prototype because the next meaningful step is data-dependent, not UI-dependent. Gamma now has the internal models, provider boundaries, sample/static context, AISstream viewport prototype, and map-overlay workspace needed to evaluate maritime research workflows, but richer chokepoint analytics, trade-flow interpretation, event replay, and fleet monitoring require better historical AIS, port-call/cargo context, or a stronger validated AIS provider._
_Dependency marker: Further progress is blocked by AIS/provider evaluation for live global coverage and by historical AIS/port-call data for replay, baselines, route-change detection, and commodity-flow inference._
_Parallelization note: Useful follow-on work should focus on provider evaluation, historical dataset ingestion, durable AIS caching, and data-quality measurement. Additional UI polish is lower leverage until Gamma has more complete vessel metadata, route history, and coverage confidence._
_Recent progress: The Research workspace now exposes the maritime surface as `Sealanes`, with normalized maritime domain models, sample provider coverage, provenance-rich payloads, AISstream backend websocket proxying that keeps the API key server-side, live viewport subscriptions at zoom 4+, contextual major sealanes, static major port references, heading-aware vessel chevrons where AIS fields support them, map-native overlay controls for chokepoints / trade flows / fleet / event replay, a right-side detail drawer pattern, event replay degradation when historical tracks are unavailable, and display settings for ports and vessel-type filtering._

#### Completion snapshot

- `Domain models and provider boundary`: ~64% complete. MMSI/IMO identity, AIS positions, vessel static records, ports, chokepoints, tracks, event windows, fleet watchlists, coverage metadata, and provenance fields now exist, with sample and AISstream provider paths separated. Remaining work: richer historical track storage, fuller vessel metadata enrichment, provider quality scoring, and durable cache/persistence beyond the current in-memory/live sample layer.
- `Live Map mode`: ~62% complete. A real Sealanes live map now exists with MapLibre, dark maritime styling, static major shipping lanes, major port reference points, zoom-gated AISstream live streaming, debounced viewport subscriptions, heading-aware chevrons, coverage status, map-native overlay controls, display settings, port visibility, and vessel-type filtering. Remaining work: stronger clustering, longer track tails, viewport health diagnostics, and better handling of sparse AISstream coverage.
- `AISstream prototype`: ~47% complete. The app can proxy AISstream over the backend, keep credentials out of the browser, subscribe by viewport, and ingest dynamic plus static AIS message types for heading and high-level AIS ship-type codes. Remaining work: provider quality evaluation, reconnection/backoff hardening, message-volume controls, static/dynamic message joining quality, durable buffering, and explicit limits around AIS type codes versus actual cargo class.
- `Chokepoints mode`: ~37% complete. Sample chokepoint definitions, map overlay boxes, hover context, click-through details, and first-pass density summaries exist, but the counts are still sample/partial and not operational congestion measurements. Historical baselines, dwell/transit time, and validated chokepoint polygons remain open.
- `Trade Flows mode`: ~25% complete. Gamma can show explicit sample flow proxies by vessel class and route context with cargo-inference caveats. Real cargo-flow interpretation remains blocked on stronger vessel metadata, route/port-call history, and commodity data links.
- `Fleet / Vessel Monitoring mode`: ~32% complete. Sample vessel registry and watchlist structures exist, vessel chevrons can open detail drawers, and vessel-type display filters are live, with no risk/sanctions labels. Live watchlists, owner/operator enrichment, and durable vessel histories remain open.
- `Event Replay mode`: ~22% complete. Sample event windows and track snippets exist to exercise the workflow where sample tracks are present, and the UI now degrades explicitly when live AISstream coverage has no historical tracks. Historical AIS replay is not implemented. NOAA/MarineCadastre or another historical dataset remains the likely next dependency.
- `Risk Signals mode`: 0% complete by design. Suspicious-behavior, sanctions, dark-activity, and shadow-fleet labels remain intentionally out of scope until the base data model, historical context, and methodology are validated.

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

_Status: Opportunistic / first-pass complete_
_Dependency marker: Opportunistic_
_Parallelization note: Prediction Markets is not a core V2 rebuild unless other tabs create specific cross-domain needs._
_Current implementation snapshot: Prediction Markets has Polymarket and Kalshi adapters, screener, detail, probability history, wallet summary, related-market matching, calibration summary, venue status, canonicalization, freshness labels, research ranking, and Copilot history/flow tools. V2 should remain targeted around Macro, Commodities, Sealanes, and Copilot needs rather than become a broad rebuild._

### Why this workstream is limited

Prediction Markets is already complete at a first-pass level. V2 should not deepen it in isolation unless there is a clear research payoff.

The most useful targeted hardening is likely cross-domain:

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

_Status: In progress (~25%)_
_Dependency marker: Parallelizable, but final release polish depends on product stability_
_Parallelization note: Installer and tutorial planning can begin early; final beta packaging should wait until core workflows are stable._
_Recent progress: Gamma has mock/demo defaults, system health/status routes, `/diagnostics` and `/diagnostics/run`, `/system/provider-usage`, provider capability metadata, provider usage summaries and activation-aware health labels in Settings, read-only boundary metadata, market-data mode and base-currency controls, account-subscribe diagnostics helpers, local persistence stores for portfolio history/research/fundamentals/Copilot, and clearer provider warnings across several V2 tabs. A recurring live-IBKR usability audit loop (June/July 2026 runs under `docs/audits/usability/`) is now feeding structured findings into hardening passes, and several beta-facing empty/error states and honest cached-vs-fresh labels came out of it. Gamma is still not packaged as an installer and does not yet have a real first-run setup or guided tutorial._

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

This roadmap should use multiple provider classes rather than search for one universal provider.

### Broker/listed-market provider

`IBKR / TWS` should remain first-class for:

- Portfolio,
- IV,
- high-fidelity listed-market context when explicitly requested or needed as fallback,
- options,
- futures where subscriptions make sense,
- global equities and ETFs where entitled.

The adapter should remain read-only.

IBKR/TWS capacity should be treated as scarce. The working budget model is: `critical_live` for IV/active portfolio/selected commodity curves, `broker_state` for account/positions/FX, `public_refresh` for SITREP and Research Overview through yfinance/AKShare-like providers, `official_slow` for FRED/Treasury/EIA/SEC/DB.nomics, and `manual_heavy` for broad IBKR history loads, full curve refreshes, or deep options scans.

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

### Free-first provider backlog

Gamma should push as far as possible with free or public data before depending on paid vendor contracts. Paid providers remain valid later if a research surface proves valuable and public data cannot support the needed depth, but V2 provider expansion should first prefer sources that are official, public, no-key, or free-key.

The following backlog came from reviewing FinceptTerminal's provider surface and filtering out sources Gamma already uses directly or sources that are mostly redundant with current adapters.

| Provider | What it is for | Implementation notes / user requirements | Likely Gamma repo areas |
| --- | --- | --- | --- |
| `CFTC` | Commitment of Traders positioning for commodities, rates, FX, equity-index futures, and crowding/context overlays. | Usually no API key. Start with weekly COT reports, normalize report type, contract, commercial/non-commercial buckets, publication date, and futures root mapping. Treat as positioning context, not a signal. | `src/services/commodities_adapters.py`, `src/application/commodities_service.py`, `src/models/commodities.py`, `frontend/src/views/CommoditiesView.svelte`, later `src/application/macro_service.py` for rates/FX positioning context. |
| `OpenFIGI` | Instrument identity mapping across ticker, FIGI, ISIN, CUSIP, SEDOL, exchange, and asset class. Useful platform foundation before adding more global market data. | No key is required for low-volume use; optional free API key improves rate limits. Add a small adapter with request batching, cache mappings aggressively, and keep mapping confidence/warnings. | `src/application/instrument_identity.py`, `src/models/instruments.py`, `src/application/provider_capability_registry.py`, Research/Fundamentals handoffs. |
| `IMF` | Global macro, WEO/IFS/BOP-style country comparisons, external balances, inflation, GDP, rates, reserves, and macro regime context. | Usually no key. Main work is schema normalization: country codes, dataset codes, frequency, units, vintages where exposed, and uneven update cadence. Prefer curated series sets before a general browser. | `src/services/macro_adapters.py`, `src/application/macro_service.py`, `src/models/macro.py`, `frontend/src/views/MacroView.svelte`, Copilot macro context. |
| `OECD` | Cross-country leading indicators, labor, productivity, confidence, inflation, and country comparison data. | Usually no key. Normalize SDMX-style dimensions and cache by dataset/query. Start with a curated CLI/composite indicator set rather than full dataset discovery. | `src/services/macro_adapters.py`, `src/application/macro_service.py`, Macro Cross-Asset and Events / Regimes modes. |
| `BIS` | Credit, banking, debt, cross-border finance, liquidity and leverage regime context. | Usually no key. Requires careful unit/frequency metadata and country/instrument dimensions. Best as a Macro credit/liquidity layer, not a broad UI first. | `src/services/macro_adapters.py`, `src/application/macro_service.py`, Macro Cross-Asset, Copilot context. |
| `UN Comtrade` | Trade flows by commodity, reporting country, partner country, and period. Useful for commodity demand, sealanes, supply-chain, and geopolitical research. | Free registration/API key may be needed for practical limits. Normalize HS/SITC commodity codes, country codes, flow direction, quantity/value units, and revision timestamps. Start with selected commodities and route-relevant country pairs. | `src/services/commodities_adapters.py`, `src/application/commodities_service.py`, `src/application/maritime_service.py`, `src/models/handoff.py`, `frontend/src/views/CommoditiesView.svelte`, `frontend/src/views/MaritimeView.svelte`. |
| `WTO` | Trade policy, tariffs, goods/services trade statistics, and policy-friction context. | Public access varies by endpoint; may need API registration for some datasets. Useful after UN Comtrade schemas exist so WTO can be a policy/tariff overlay. | Macro Events / Regimes, Commodities Events, Maritime chokepoint/event context, Copilot synthesis. |
| `ILOSTAT` | International labor-market data beyond the US/EU first pass. | Usually no key. Normalize country, sex/age/sector dimensions and avoid overloading the first UI with too many cuts. | Macro growth/labor comparisons, Copilot country context. |
| `ONS` | UK official macro/statistics for a UK country lens. | Usually no key. Implement only if Gamma adds country-specific lenses beyond US/EU/Global; preserve dataset IDs and release/frequency metadata. | Macro country comparison, Rates & Policy, Events / Regimes. |
| `StatCan` | Canadian macro/statistics for a Canada country lens. | Usually no key. Same pattern as ONS: curated series first, provider-native IDs preserved, country lens later. | Macro country comparison, Rates & Policy, Events / Regimes. |
| `BCB` | Brazil central bank rates, FX, inflation, credit, and macro series. | Usually no key. Useful if LATAM macro becomes relevant; normalize series IDs, currency/rate units, and local calendar conventions. | Macro country comparison, FX/rates context. |
| `ADB` | Asia development and macro data, especially useful for regional context around China/Asia supply chains. | Usually no key. Treat as lower priority unless Asia macro or sealanes work needs regional context. | Macro country/regional comparison, Maritime/Commodities regional context. |
| `AkShare` | China/Asia equities, macro, rates, funds, and calendars. Useful for China-specific research where Western APIs have gaps. | Usually no API key, but it adds a Python dependency and relies on upstream web/API shapes that can change. Keep behind an optional adapter with strong error handling and provenance warnings. | New `src/services/akshare_adapters.py` or Macro/Research adapters, Macro country lens, Research market overview, possibly Commodities if China demand indicators are useful. |
| `Yahoo Finance / yfinance` | Free public live-ish historical prices across equities, ETFs, indices, FX, and crypto for low-impact overview surfaces and fallback coverage. | No key, but unofficial and subject to breakage/rate limits. It is now the default first provider for Research Overview and SITREP listed boards, cached around 5 minutes, and must not be treated as institutional quote truth. | `src/services/research_market_data.py`, `src/services/data_providers.py`, Research Overview/SITREP provider policy, mock/demo workflows. |
| `RSS news feeds` | Lightweight macro, company, commodity, and geopolitical news/event context for research surfaces and Copilot grounding. | Usually no key. Normalize feed source, URL, publication time, detected tickers/entities, tags, and summary snippets. Avoid pretending RSS is comprehensive or real-time institutional news. | New news adapter/service, Macro Events / Regimes, Fundamentals, Commodities Events, Copilot context, possibly `frontend/src/components/CopilotResearchCard.svelte`. |

Implementation rule:
- Each provider should start as a backend adapter plus normalized model/test coverage before any large UI build.
- Every response should carry `source_provider`, provider-native identifiers, `retrieved_at`, source timestamp where available, and a transformation note.
- Public/no-key providers should still be represented in `/system/provider-capabilities` so setup, diagnostics, and Copilot can distinguish active, optional free-key, planned, and unavailable sources.
- Paid alternatives should remain documented as later escalation paths only after a free-first implementation proves the workflow is worth deeper coverage.

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

- SITREP locked home and cross-domain triage hardening,
- Research multi-mode shell,
- Research saved scopes,
- Macro EU/global/event refinements,
- Fundamentals raw-versus-normalized inspection,
- Copilot run-lifecycle/session persistence hardening,
- IV source transparency, history, and handoff hardening.

### First new-domain prototypes

Commodities and Sealanes have both crossed the first-prototype line. New-domain work should now focus less on creating shells and more on validating provider quality, persistence, and handoffs:

- Commodities IBKR futures-chain and EIA/FRED provider hardening,
- Commodities historical curve/spread storage and provider-quality measurement,
- Sealanes AISstream provider evaluation,
- Sealanes historical track/cache feasibility,
- Sealanes vessel/route/chokepoint quality scoring.

### Deep V2 buildout

After data shapes are proven:

- SITREP news/feed hardening and cross-tab row handoffs,
- Strategy Lab saved/reuse hardening,
- Market Overview provider breadth,
- Commodities Energy/Curves hardening and Metals/Events deepening,
- IV skew/term modules and Realized vs IV,
- Crypto Wallets & Flows,
- Fundamentals Reverse Valuation,
- Copilot shared Agent/Operator streaming, typed evidence, complete session/artifact lifecycle, and release validation,
- Sealanes Chokepoints and Event Replay.

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

Build provider, provenance, cache, mode-navigation, cross-tab handoff, diagnostics, persistence, and Copilot-context infrastructure.

### Workstream 1A - SITREP

Keep the Research workspace home as a dense cross-asset situation report with news/events, live media, equities, FX, yields, commodities, provider caveats, and drilldowns into deeper tabs.

### Workstream 2 - Research V2

Turn Research into a multi-mode hub for scope analysis, market overview, imported strategy returns, comparison, and saved research.

### Workstream 3 - Macro V2

Deepen the live Snapshot, Cross-Asset, Rates & Policy, and Events / Regimes workspace with better EU/global coverage, event interpretation, and cross-domain links.

### Workstream 4 - IV V2

Harden the live Options workspace into a complete-for-now volatility lab with selectable surface models, skew/term, Greeks/source quality, realized-versus-implied, implied-probability, and strategy-payoff work.

### Workstream 5 - Crypto V2

Deepen the live Crypto workspace with wallet/on-chain analytics, richer pool monitoring, better narrative/basket comparisons, and later derivatives overlays.

### Workstream 6 - Fundamentals V2

Add raw-versus-normalized inspection, better peer/reference depth, DCF improvements, reverse valuation, and eventual broader regional support.

### Workstream 7 - Copilot V2

Finish the coherent shelf plus dedicated no-mode-bar Copilot system through shared Agent/Operator run lifecycle, typed evidence, source-resolved claims, complete sessions/artifacts, bounded confirmed Operator workflows, context/tool parity, diagnostics, and the release gate. Voice and optional external deep research remain later extensions.

### Workstream 8 - Commodities

Deepen the live first-pass commodity research tab into a fuller workspace with better historical curves, spreads, inventories, metals coverage, events, and cross-domain handoffs.

### Workstream 9 - Maritime Intelligence

Harden the paused Sealanes prototype around AIS, vessels, chokepoints, routes, event replay, trade-flow interpretation, and later shadow-fleet/risk analytics.

### Workstream 10 - Prediction Markets Targeted V2

Add only targeted prediction-market improvements driven by Macro, Commodities, Sealanes, or Copilot needs.

### Workstream 11 - Beta Readiness

Prepare Gamma for external testing by turning the existing mock/demo, diagnostics, provider metadata, and warning foundations into installer, tutorial, first-run setup, and feedback-loop workflows.

---

## End State Vision

If this roadmap is executed well, Gamma becomes a deeper read-only research platform where the user can:

- inspect portfolios and risk,
- start from a cross-asset situation report,
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
