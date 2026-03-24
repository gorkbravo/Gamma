# Gamma Roadmap

## Purpose

This roadmap defines the planned expansion of **Gamma** from a portfolio/risk-oriented research app into a broader **read-only research environment** for prediction markets, macro and cross-asset expectations, valuation, on-chain analytics, and AI-assisted idea generation.

The core principle behind this roadmap is simple:

**Gamma is not a trading bot and not an execution platform.**  
It is a place to **aggregate data, structure research, test hypotheses, explore market behavior, and generate ideas**.

Because of that, every new tab should satisfy at least one of these goals:

1. Improve the ability to **discover research opportunities**
2. Improve the ability to **analyze a market, asset, or company**
3. Improve the ability to **generate, structure, and refine hypotheses**
4. Improve the ability to **compare scenarios without execution risk**

The roadmap is organized into phases so that development follows the highest **research value / implementation complexity** path first. The order is designed to avoid turning Gamma into a bloated dashboard with weak data foundations. The idea is to first build tabs where the data is relatively accessible and the research surface is rich, then later move into heavier normalization problems such as company fundamentals and valuation.

## Progress Tracking

Status markers in this roadmap are lightweight implementation estimates:
- `Not started (0%)`
- `In progress (~X%)`
- `Complete (100%)`

Per-task completion is tracked only for the currently active phase.

---

## Guiding Product Principles

### 1. Read-only by design
Gamma should remain focused on research, data aggregation, analytics, and experimentation. Even when the app studies strategies, wallet behavior, or arbitrage structures, it should not become an execution layer.

### 2. Data-first architecture
Tabs should not be built as isolated UI experiments. Each tab should be backed by a clear data model, a reliable ingestion path, a cache/storage layer, and reusable analytics functions.

### 3. Research, not just display
Each tab should go beyond showing raw data. The goal is not just to visualize information, but to help answer questions like:
- What is interesting here?
- What changed?
- What hypothesis is worth testing?
- What would invalidate this interpretation?

### 4. Reusable analytics layer
Whenever possible, the heavy logic should live outside the UI. Tabs should consume normalized datasets and computed analytics, rather than each widget doing its own independent calculations.

### 5. Provenance and transparency
As Gamma expands, especially into fundamentals and AI-assisted outputs, every displayed metric should ideally be traceable to:
- source/provider,
- endpoint,
- timestamp,
- transformation logic.

### 6. Research-workspace first
New roadmap tabs and features should default to the existing research workflow unless there is a strong reason to introduce a different surface.

The intended bias is:
- keep new roadmap work primarily inside the research view,
- avoid adding new top-level workspace abstractions unless the existing research flow cannot support the feature cleanly,
- optimize for comparative analysis, cross-domain investigation, and hypothesis generation rather than separate operating modes.

This applies across the roadmap, including prediction markets, macro, crypto, fundamentals, and AI-assisted research features.

---

## Phase 1 - Prediction Markets Tab

_Status: Complete (100%)_
_Phase transition note: Phase 1 is considered complete as a first pass. Remaining refinements are intentionally deferred until later tabs create clearer comparative needs and reveal where a second pass is most valuable._
_Recent hardening before transition: Kalshi historical discovery/history support, Kalshi closed-status filtering, outcome-aware wallet edge math, and venue-toggle persistence were corrected._

### Why this phase comes first

Prediction markets are one of the highest-upside additions to Gamma because they combine:
- relatively accessible public data,
- rich behavioral and microstructure dynamics,
- strong fit with research-oriented workflows,
- differentiated analytical surface compared to standard equity dashboards,
- a natural bridge between venue-level pricing and cross-market expectations work.

This tab would make Gamma feel unique very quickly. It also aligns with the user's interest in market structure, informed flow, wallet behavior, and event-driven repricing.

It should also be treated as a **multi-venue system by design**, not as a single-provider feature. Supporting both Polymarket and Kalshi creates a much stronger research surface because the user can compare:
- one prediction market against another prediction market on the same theme,
- venue-specific repricing behavior,
- venue-specific liquidity and microstructure,
- prediction markets against the broader Macro tab later on.

### Goal of the tab

The Prediction Markets tab should allow the user to explore prediction markets as probabilistic systems, behavioral systems, and market microstructure systems across one or more venues.

It should help answer questions such as:
- Which markets are active and interesting right now?
- How have implied probabilities evolved over time?
- Are some wallets consistently early to information?
- Are related contracts priced inconsistently?
- Do Polymarket and Kalshi price the same event similarly?
- How does liquidity affect repricing behavior?
- Are market probabilities well-calibrated historically?

### Functionality

#### 1. Market screener
A high-level market discovery panel showing active and historical contracts with filters such as:
- category/topic,
- platform,
- liquidity,
- volume,
- open interest,
- time to resolution,
- probability range,
- recent repricing magnitude.

This screener should make it easy to find markets worth deeper study.

The screener should be multi-venue from the start even if only one venue is deep on Day 1.

#### 2. Market detail view
A dedicated detail page/panel for a selected market containing:
- market title and description,
- resolution criteria,
- resolution date,
- current implied probability,
- liquidity/volume/open interest stats,
- historical probability chart,
- recent trade flow summary,
- concentration metrics.

This becomes the main workspace for studying a specific contract.

The detail view should also clearly identify:
- venue,
- venue-native contract identifiers,
- normalized internal market identifiers,
- linked related contracts on the same or different venues.

#### 3. Probability history and event dynamics
A time-series module showing:
- probability over time,
- cumulative volume over time,
- spread and liquidity evolution if available,
- large price jumps,
- pre-resolution convergence behavior.

This allows the user to study how information gets incorporated into prices.

#### 4. Wallet behavior module
A wallet-centric research component that allows:
- tracking trades by wallet,
- reviewing trade timing,
- measuring wallet concentration,
- identifying repeat high-signal participants,
- comparing wallet entries to subsequent repricings.

This is one of the most differentiated parts of the tab. It directly supports the study of potentially informed or unusually skilled participants.

Wallet-centric analytics may be richer on some venues than others, so the tab should be designed to support venue-specific depth without requiring identical features everywhere.

#### 5. Cross-contract and cross-venue consistency engine
A module for comparing related markets that should obey rough probabilistic consistency. For example:
- overlapping event outcomes,
- conditional event structures,
- mutually exclusive contracts,
- related geopolitical or electoral contracts,
- Polymarket vs Kalshi contracts expressing the same event.

This can surface market dislocations or possible research opportunities.

This engine should distinguish between:
- **cross-contract consistency** within one venue,
- **cross-venue consistency** across venues,
- later **cross-market consistency** against rates, commodities, credit, or other Macro-tab datasets.

#### 6. Calibration and historical outcomes
A backtesting/research area for studying whether market probabilities have historically been well-calibrated. This could include:
- bucketed calibration analysis,
- topic-level calibration,
- horizon-to-resolution calibration,
- analysis of favorites vs underdogs,
- probability drift near event resolution.

This shifts the tab from descriptive analytics into actual research.

#### 7. Research notebook hooks
The tab should eventually support saving:
- selected markets,
- screens,
- flagged wallets,
- observations,
- hypotheses,
- follow-up tasks.

Even if a full notebook system is not implemented in Phase 1, the tab should be designed with this in mind.

### Data requirements

The tab would need:
- venue metadata,
- market metadata,
- venue-native contract identifiers,
- normalized market / event identifiers,
- market status,
- category/tag data,
- implied probability history,
- volume/liquidity/open interest,
- trade history,
- wallet participation data,
- holder/concentration data,
- linked-contract mapping data,
- final resolution/outcome data.

### Data sources / APIs

Potential sources include:
- **Polymarket Gamma API** for market discovery and metadata
- **Polymarket Data API** for trades, activity, holders, positions, and related data
- **Kalshi API** for market discovery, event metadata, and market data

A practical implementation path would be:
- build a venue-agnostic internal schema first,
- launch deep support with **Polymarket** first,
- add **Kalshi** next as the second venue,
- then layer on contract matching, cross-venue divergence analysis, and lead/lag comparisons.

Longer term, external news/context could be linked, but that is optional and should not be required for the initial release.

### Deliverable of the phase

At the end of Phase 1, Gamma should be able to:
- browse and filter prediction markets,
- inspect a market deeply,
- support a multi-venue prediction-market model,
- analyze probability dynamics,
- review wallet behavior,
- compare related contracts across venues,
- begin basic historical research on calibration and microstructure.

This phase gives Gamma a highly distinctive research edge with relatively manageable implementation complexity.

For roadmap purposes, this deliverable is now treated as achieved at a first-pass level. Future work on prediction markets should be driven by concrete needs discovered after later tabs land, rather than by continuing to deepen Phase 1 in isolation.

---

## Phase 2 - Macro Tab

_Status: In progress (~30%)_
_Active focus: deepen the expectations engine, link Macro to prediction markets, and keep Macro the primary implementation track._

#### Completion snapshot
- `Snapshot mode`: ~45% complete. The early V1 workspace now includes linked-expectation context, but breadth and interpretation depth remain limited.
- `Cross-asset expectations mode`: ~40% complete. A first-pass Macro-versus-prediction-markets bridge now exists, but the expectations engine is still early and mostly heuristic.
- `Rates & policy mode`: ~40% complete. This is the strongest current Macro mode, but it still needs broader depth and richer interpretation.
- `Optional commodities mode`: ~0% complete. Not started and not required for the first pass.
- `Coherence and divergence engine`: ~35% complete. A first-pass divergence layer exists and now has linked prediction-market comparisons, but the scoring is still narrow and proxy-driven.
- `Event and regime interpretation`: ~10% complete. Event context is present, but regime framing and event-window interpretation are still limited.
- `Research notebook hooks`: ~0% complete. Not started.

### Why this phase comes next

Macro is the strongest follow-on to prediction markets because it extends Gamma into **cross-asset expectations research** rather than into another isolated asset-class dashboard.

It fits the roadmap especially well because:
- the data is relatively accessible compared to company fundamentals,
- the research surface is rich without requiring execution infrastructure,
- it creates direct synergy with prediction markets through expectation and coherence analysis,
- it can absorb rates, inflation, commodities, and credit views without creating too many top-level tabs.

Just as importantly, a Macro tab lets Gamma avoid premature tab sprawl. Instead of adding separate top-level tabs for rates, commodities, and cross-asset macro monitoring, Gamma can treat them as **internal research modes** inside one broader workspace.

### Goal of the tab

The Macro tab should provide a structured environment for:
- regime awareness,
- macro snapshot monitoring,
- cross-asset expectations analysis,
- rates and policy interpretation,
- selective commodities and inflation research,
- dislocation spotting across related markets.

It should help answer questions such as:
- What macro regime are markets currently pricing?
- What changed materially across rates, inflation, credit, FX, and commodities?
- Do prediction markets and traditional markets tell the same story?
- Which market moved first on a given theme?
- Where are the largest cross-market inconsistencies worth researching?

### Product structure

The Macro tab should be designed as a **multi-mode workspace** rather than a single static page. That makes it possible to compress several related research surfaces into one tab without turning it into an incoherent dashboard.

The initial modes should be:
- **Snapshot** for fast situational awareness,
- **Cross-Asset** for coherence and divergence analysis,
- **Rates & Policy** for deeper term-structure and policy-expectation work.

A later extension could add:
- **Commodities** for futures-curve and inflation-sensitive market analysis,
- **Credit / Stress** for spread and financial-condition monitoring.

The UI should support collapsible, expandable, and reorderable cards so the user can move between a dense monitoring view and a deeper analytical view without fragmenting the product into too many tabs.

The intended information architecture is:
- one top-level **Macro** tab inside the existing research workspace,
- one visible **mode bar** inside Macro for switching between the major research tasks,
- one persistent **context bar** for region, timeframe, theme, and comparison state,
- mode-specific cards and modules below that shared context.

The navigation bias should be:
- organize the tab primarily by **research task** rather than by geography or instrument family,
- treat region and curve family as **lenses / filters** rather than as separate first-class pages,
- allow overview cards to **deep-link** into another mode while preserving context,
- avoid a long single-page dashboard and avoid multiplying pages such as `US Rates`, `EU Rates`, `US Macro`, and `EU Macro`.

For the first pass, the user flow should feel like:
- enter **Macro** and land on **Snapshot**,
- adjust a persistent context such as `Region = US`, `Timeframe = 3M`, `Theme = Policy`,
- switch to **Rates & Policy** or **Cross-Asset** without losing that context,
- click important cards in **Snapshot** to jump directly into a deeper mode with the relevant lens pre-applied.

#### Navigation model

The main navigation inside Macro should be a visible horizontal mode bar rather than a dropdown. The purpose of this bar is to make mode switching one-click and always legible.

The persistent context bar should contain compact selectors such as:
- region,
- timeframe,
- theme,
- comparison target,
- event window when relevant.

This means the user should navigate in three layers:
- **Tab**: Macro
- **Mode**: Snapshot, Cross-Asset, Rates & Policy, later Events / Regimes
- **Lens**: region, market family, timeframe, and comparison state

The important distinction is:
- **mode** answers what kind of research the user is doing,
- **lens** answers which slice of the macro world they are viewing,
- **modules** answer which chart, table, or ranking is visible inside the chosen mode.

#### Regional rollout model

The first pass should not try to make every region equally deep.

The intended rollout is:
- **US** as the deepest initial region,
- **EU** as a lighter but structurally compatible second region,
- **Global** views only where cross-market comparison is naturally meaningful,
- additional regions later, once the internal schemas and analytics are stable.

This matters because the product should avoid duplicating the same workspace into a separate page for every region. The same mode should be reused with different regional lenses.

### Functionality

#### 1. Snapshot mode
A high-level macro overview should present a compact but research-oriented view of:
- growth indicators,
- inflation indicators,
- policy-rate context,
- curve shape,
- real yields and breakevens,
- dollar / FX proxies,
- credit-spread proxies,
- major commodities such as oil, gas, copper, and gold,
- relevant linked prediction markets.

This mode should answer the question: **what matters right now?**

#### 2. Cross-asset expectations mode
This should be the signature module of the tab. It should compare how different markets express views on:
- growth,
- inflation,
- policy,
- recession risk,
- geopolitics,
- risk appetite.

Examples include:
- recession contracts vs curve slope and credit spreads,
- inflation contracts vs breakevens and energy prices,
- geopolitical contracts vs oil, gold, and dollar strength,
- policy contracts vs front-end rates and implied meeting paths.

This mode should answer the question: **do these markets agree?**

#### 3. Rates & policy mode
A dedicated internal mode should allow the user to inspect:
- front-end rate pricing,
- curve structure,
- term premium proxies if available,
- real yields,
- breakevens,
- meeting-by-meeting policy expectations,
- recent repricing episodes.

This is likely the most practical Macro sub-mode to mature early because it has the strongest synergy with prediction markets and relatively manageable data complexity.

For the first pass, this mode should emphasize:
- Treasury and public-policy-rate context first,
- real-yield and breakeven context where public coverage is clean,
- meeting and event interpretation where official calendars are available,
- public market proxies before attempting deeper swap-curve coverage.

Free and clean public swap / OIS coverage is materially weaker than Treasury and public macro coverage, so swap-specific depth should be treated as a later extension unless a robust data source is selected.

#### 4. Optional commodities mode
A later internal mode can focus on selected futures-sensitive markets, especially where cross-market interpretation is strong:
- energy,
- inflation-sensitive commodities,
- precious metals,
- selected industrial metals.

The emphasis should be on:
- spot vs term structure,
- contango / backwardation state,
- roll structure,
- macro-event sensitivity,
- linkage to inflation and geopolitical narratives.

This mode should only expand once the core Macro tab has a solid cross-asset framework. It should not launch as a generic commodity quotes page.

#### 5. Coherence and divergence engine
The Macro tab should include a reusable engine that scores or ranks:
- consistency across markets,
- unusually large divergences,
- recent repricing clusters,
- lead/lag relationships,
- research candidates worth deeper investigation.

This is the most important analytical layer. It is what prevents the Macro tab from becoming a collection of disconnected charts.

#### 6. Event and regime interpretation
The tab should support event-aware analysis such as:
- major macro releases,
- central-bank meetings,
- geopolitical events,
- pre/post repricing windows,
- historical comparisons across regimes.

This should help the user study how different markets absorb new information rather than merely watch current levels.

This may appear as a later dedicated **Events / Regimes** mode once the core Snapshot, Cross-Asset, and Rates & Policy modes are stable. It does not need to be a Day 1 requirement for the first usable Macro release.

#### 7. Research notebook hooks
As with prediction markets, the Macro tab should eventually support saving:
- watched themes,
- selected charts,
- flagged divergences,
- hypotheses,
- linked contracts and assets,
- follow-up tasks.

Even if a full notebook system is not yet implemented, the tab should be designed with this persistence model in mind.

### Data requirements

The tab would need:
- macro time series,
- policy-rate and meeting-context data,
- yield-curve points,
- real-yield and breakeven series or proxies,
- major FX and dollar proxies,
- credit-spread proxies,
- selected commodity spot and futures-curve data,
- event calendars and timestamps,
- linked prediction-market metadata and probability history,
- transformation metadata for derived regime and coherence signals.

### Data sources / APIs

Potential sources include:
- **FRED API / ALFRED** for major macro series, rate-related public datasets, and revision-aware history
- **Treasury public data** for policy and yield-curve context where available, including Treasury curve feeds and Treasury Fiscal Data datasets
- **BLS API** for inflation and labor series
- **BEA API** for GDP, PCE, income, and related macro series
- **Fed public releases** such as H.10 / H.15 for selected FX and rates context
- **EIA API** for energy-sensitive macro overlays
- **Stooq / Nasdaq Data Link / other market-data providers** only as selective later supplements where free public coverage is insufficient
- existing and future internal Gamma market-data adapters for rates, commodity proxies, and linked market histories
- prediction-market providers already planned in Phase 1 for contract linkage

A practical implementation path should begin with:
- FRED / ALFRED as the backbone for normalized public macro series,
- Treasury public data for US curve and issuance context,
- BLS and BEA for canonical inflation, labor, growth, and income series,
- a narrow set of official or durable public event-calendar sources,
- a limited set of liquid cross-asset proxies rather than broad market coverage.

The first-pass implementation should prefer:
- official public data,
- stable and reproducible identifiers,
- series registries curated by Gamma rather than open-ended symbol search,
- provenance-rich normalized records,
- region-first depth in the US before broadening global coverage.

Later additions can expand deeper commodity-curve coverage, broader cross-asset proxy sets, swap / OIS depth where data quality allows, and richer region-by-region support once the internal schema and cache behavior are proven.

### First-pass implementation bias

The first usable Macro release should be intentionally narrow and coherent.

The expected V1 bias is:
- ship **Snapshot**, **Rates & Policy**, and **Cross-Asset** first,
- keep **Events / Regimes** as the next extension rather than forcing it into the first pass,
- support **US** most deeply first,
- treat **EU** as a lighter second-region extension,
- prefer a few well-normalized public datasets over a broad but inconsistent market-data surface.

This keeps the tab aligned with Gamma's research-first scope and reduces the risk of building a large UI before the normalized macro data layer is reliable.

### Deliverable of the phase

At the end of Phase 2, Gamma should be able to:
- present a useful macro snapshot,
- compare cross-asset expectations,
- analyze rates and policy pricing,
- link prediction markets to macro market context,
- surface coherence breaks and divergence candidates for research.

This phase would make Gamma much more effective as a cross-market research environment while still staying within a manageable data and normalization scope.

---

## Phase 3 - Keyboard Navigation & Power-User Workspace Customization

_Status: Not started (0%)_
_Remaining focus: full phase scope._

### Why this phase comes here

By this point Gamma has multiple data-rich tabs (Portfolio, Risk, IV, Prediction Markets, Macro with internal modes) and a collapsible sidebar for navigation. As the tab count grows, click-based navigation becomes friction for the power users this app is built for. Adding keyboard shortcuts after Phase 2 means there are enough views to make shortcuts valuable, but the investment is small enough to slot in before heavier feature phases.

This phase is also a natural companion to the sidebar rework: the sidebar becomes the discovery and orientation layer for new users, while keybindings become the primary navigation method for regular users. Combined with drag-and-drop reordering, it lets users fully personalize their navigation layout.

### Goal of the phase

Provide a keyboard-driven navigation layer and customizable tab ordering that lets power users move between views, trigger common actions, control the UI without touching the mouse, and arrange their workspace to match their workflow.

### Functionality

#### 1. Drag-and-drop tab reordering in sidebar

The sidebar should support drag-and-drop reordering of tabs, with the following rules:

- **The first tab is pinned and not draggable.** In Portfolio mode, the Portfolio tab stays at position 1. In Research mode, the Research tab stays at position 1. This anchors orientation so the user always knows where "home" is.
- **All other tabs are freely reorderable** by dragging within the sidebar list.
- **Visual feedback during drag:** a subtle drag handle icon (`⠿` or `≡`) on the left of each draggable item, a ghost/shadow of the dragged item, and a clear insertion-line indicator at the drop target. Keep animations minimal — no bouncy physics.
- **Order persists per workspace mode.** Portfolio mode and Research mode each maintain their own independent tab order. The order should be saved to localStorage (or a small config file) and restored on reload. A reset-to-default option should be available somewhere (e.g. right-click context menu or a small reset link in the sidebar footer).
- **Order determines keybinding mapping.** If the user moves Risk to position 2, then `Ctrl+2` should navigate to Risk. The mental model must be consistent: visual order = shortcut order.

Implementation options:
- Native HTML5 drag-and-drop (`dragstart`, `dragover`, `drop`) is sufficient for a vertical list.
- Alternatively, `svelte-dnd-action` is a lightweight Svelte-native library that handles edge cases (scroll during drag, touch support, accessible reorder).
- Avoid heavy libraries — the interaction surface is small (3–8 items in a vertical list).

#### 2. Tab/view switching via Ctrl+N
`Ctrl+1` through `Ctrl+N` should map to the tab list in the user's custom order. The mapping should be consistent within a workspace mode (e.g. if the user has reordered Research mode to `Research, Risk, Prediction Markets, IV`, then `Ctrl+1` = Research, `Ctrl+2` = Risk, `Ctrl+3` = Prediction Markets, `Ctrl+4` = IV). This mirrors the convention used by browsers, VS Code, and terminal multiplexers.

#### 3. Sidebar toggle
A single keybinding (e.g. `Ctrl+B` or backtick) should toggle the sidebar open/closed. This gives keyboard users a way to check available views without reaching for the mouse.

#### 4. Shortcut hints in sidebar
Each tab entry in the sidebar should display its keybinding hint (e.g. `Portfolio  ⌃1`). The hint number should reflect the current order, updating live if the user reorders tabs. This teaches the shortcuts through usage and eventually makes the sidebar unnecessary for regular users.

#### 5. Action shortcuts
Common actions should have keybindings:
- `Ctrl+R` or `F5` for refresh,
- `Ctrl+,` for settings,
- `Escape` to close sidebar / dismiss popovers.

#### 6. Workspace switching
A keybinding (e.g. `Ctrl+Shift+P` / `Ctrl+Shift+R`) to switch between Portfolio and Research workspaces without returning to the landing page.

### Implementation notes

- Keybindings should be registered at the app level (window keydown listener) and cleaned up on unmount.
- Avoid conflicts with browser defaults and Tauri/OS shortcuts.
- Keybindings should be discoverable but not intrusive — no tooltip overlays or onboarding modals.
- Consider a `?` shortcut that shows all available keybindings in a lightweight overlay.
- Tab order state should be managed in a shared store (e.g. a Svelte writable store backed by localStorage) so that the sidebar, the keybinding handler, and the breadcrumb label all read from the same source of truth.
- New tabs added in future phases should appear at the end of the user's custom order by default.

### Deliverable of the phase

At the end of Phase 3, Gamma should support full keyboard-driven navigation across all views and common actions, with user-customizable tab ordering in the sidebar. The sidebar becomes a fallback discovery tool, keybindings follow the user's preferred order, and regular users can operate entirely from the keyboard with a layout that matches their workflow.

---

## Phase 4 - AI Copilot Layer

_Status: Not started (0%)_
_Remaining focus: full phase scope._

### Why this phase comes here

The AI component becomes most useful **after** Gamma already has meaningful data surfaces. If added too early, it risks becoming a generic chatbot with little grounding. If added after the app has prediction-market and macro data infrastructure, it can act as a true research assistant rather than a novelty feature.

This phase is not really "just another tab." It is better thought of as a **cross-tab research layer**. That said, it may still have its own dedicated area, depending on UI design.

### Goal of the feature

The AI Copilot should help the user:
- generate ideas,
- frame hypotheses,
- design tests,
- interpret patterns,
- summarize current context,
- structure research workflows.

Its purpose is not to replace judgment. Its purpose is to reduce the friction of:
- going from raw data to a research question,
- going from observation to test design,
- going from analysis to organized next steps.

### Functionality

#### 1. Context-aware chat / assistant
The assistant should be aware of:
- the current tab,
- currently selected asset/market/company,
- visible charts or metrics,
- available internal analytics,
- currently loaded datasets.

This is what makes it useful. It should not operate in isolation from the app state.

#### 2. Hypothesis generation
The assistant should be able to generate structured research hypotheses based on the current context. For example:
- possible informed-wallet dynamics,
- relationships between liquidity and repricing,
- cross-asset expectation divergences,
- rates / inflation inconsistencies,
- divergence between narrative strength and price action.

The goal is to help the user think of what to test next.

#### 3. Research design support
The assistant should be able to convert an idea into a testable plan:
- what data is needed,
- what metric should be computed,
- what confounders matter,
- what result would support or weaken the hypothesis.

This is one of the highest-value use cases.

#### 4. Explanation and interpretation
The assistant should be able to explain:
- why a chart might matter,
- what a metric means,
- what changed recently,
- possible interpretations of a pattern,
- what caveats should be considered.

This would make Gamma more usable during exploratory sessions.

#### 5. Structured outputs
Instead of always returning free-form prose, the assistant should be able to return research cards with fields such as:
- hypothesis,
- rationale,
- required data,
- proposed test,
- confounders,
- next steps.

This makes the AI layer much more practical and much less "chat for the sake of chat."

#### 6. Cross-tab synthesis
Once multiple tabs exist, the assistant should be able to connect them conceptually. For example:
- compare prediction-market sentiment with macro market pricing,
- explain whether a contract looks coherent with rates, commodities, or credit,
- suggest related markets to monitor,
- explain how a company's valuation assumptions compare to market-implied expectations,
- identify analogous structures across datasets.

#### 7. Research memo drafting
A later extension could allow the assistant to produce:
- short notes,
- structured summaries,
- internal research memos,
- saved idea logs.

This should build on top of the structured outputs and saved research context.

### Data requirements

The AI layer primarily needs access to **internal Gamma state**, including:
- current context,
- selected entity,
- available metrics,
- normalized datasets,
- precomputed analytics,
- saved screens or notes.

It does not need to own a unique market dataset; it needs deep integration with the app's internal data layer.

### APIs / model layer

Potential sources / infrastructure include:
- **OpenAI API** for the model layer
- function/tool calling to access internal Gamma tools
- structured-output schemas for predictable research responses

Internally, the AI should call functions such as:
- fetching current context,
- listing loaded datasets,
- retrieving price/probability history,
- retrieving wallet activity,
- retrieving macro and rates context,
- retrieving token/company data,
- triggering internal analytics.

### Deliverable of the phase

At the end of Phase 3, Gamma should have an AI-assisted research workflow that can:
- understand current context,
- suggest hypotheses,
- propose tests,
- explain results,
- generate structured research outputs.

This phase does not replace the data tabs. It multiplies the value of every other phase.

---

## Phase 5 - Crypto Tab

_Status: Not started (0%)_
_Remaining focus: full phase scope._

### Why this phase comes here

Crypto remains a natural extension because:
- public data access is broad,
- on-chain activity is transparent,
- it complements behavioral and flow-oriented research,
- it opens up a large analytical surface without requiring execution infrastructure.

However, "crypto" is broad, so the key to Phase 4 is restraint. It should come after prediction markets and macro because those phases establish a clearer cross-market research identity first. The tab should not attempt to become a full crypto terminal immediately.

### Goal of the tab

The Crypto tab should provide a structured environment for:
- token-level market research,
- narrative/theme exploration,
- wallet-flow analytics,
- DEX and on-chain activity monitoring,
- broad crypto experimentation in a read-only setting.

It should help answer questions such as:
- What is happening in a token or sector right now?
- Which narratives are attracting flow?
- How are large wallets behaving?
- Are certain pools or assets showing unusual activity?
- How do on-chain signals compare to price behavior?

### Functionality

#### 1. Token explorer
A central interface for researching a token, including:
- token metadata,
- chain/network,
- price history,
- market cap / FDV / circulating supply,
- volume profile,
- category or narrative tags.

This should serve as the equivalent of a market profile page.

#### 2. Narrative and sector baskets
A framework for grouping tokens by theme, such as:
- AI,
- DeFi,
- layer 1,
- layer 2,
- infrastructure,
- memecoins,
- gaming,
- DePIN.

This allows the user to study narratives as baskets rather than isolated tokens.

#### 3. Wallet and flow analytics
A module focused on wallet behavior, including:
- token balances,
- transfer history,
- major inflows/outflows,
- exchange interaction,
- large holder behavior,
- notable counterparty patterns.

This supports the user's interest in studying market structure and potentially informed activity.

#### 4. DEX / liquidity view
A component for studying token trading conditions on-chain:
- liquidity pools,
- trading volume,
- turnover,
- liquidity changes,
- possible slippage proxies,
- concentration of liquidity.

This is especially useful for newer or less centralized assets.

#### 5. Cross-sectional screening
A screener that can filter tokens by:
- price momentum,
- realized volatility,
- volume expansion,
- liquidity,
- market cap tier,
- narrative group,
- on-chain activity.

This turns the tab into an exploratory research surface rather than a passive data page.

#### 6. Comparative analytics
A comparison layer allowing users to compare:
- token vs token,
- token vs basket,
- basket vs basket,
- wallet behavior across assets,
- on-chain activity vs price dynamics.

This should support the broader Gamma identity as an experimentation environment.

#### 7. Optional derivatives / advanced market overlays
This is a later extension, not a V1 requirement. Potential additions:
- funding rates,
- basis,
- perpetual-futures overlays,
- open interest across centralized venues.

This should only be pursued once the core token/on-chain framework is solid.

### Data requirements

The tab would need:
- token metadata,
- historical prices and volume,
- supply metrics,
- category/narrative classification,
- DEX pool information,
- wallet balances,
- transfer history,
- large transaction data,
- chain-specific identifiers and mapping logic.

### Data sources / APIs

Potential sources include:
- **CoinGecko API** for broad token market coverage
- **GeckoTerminal / CoinGecko on-chain coverage** for DEX and pool-related data
- **Alchemy APIs** for wallet, token, and transfer analytics
- **Dune API** for custom query-based blockchain analytics

A practical approach would be to begin with CoinGecko for broad market data, then add deeper wallet and on-chain analytics through Alchemy or Dune as needed.

### Deliverable of the phase

At the end of Phase 5, Gamma should be able to:
- research tokens and sectors,
- explore narrative baskets,
- study wallet flows,
- inspect DEX liquidity conditions,
- run screens across a crypto universe.

This phase broadens the app into a more general market-research platform while staying consistent with its data-driven, read-only identity.

---

## Phase 6 - Fundamentals Tab

_Status: Not started (0%)_
_Remaining focus: full phase scope._

### Why this phase comes later

The Fundamentals tab is highly valuable, but it is the most likely to become bloated and technically messy. Company financial data is not just "another dataset." It involves:
- normalization issues,
- quarterly vs annual mismatches,
- restatements,
- reporting differences across firms,
- derived metric ambiguity,
- valuation-model complexity.

This makes it better suited for a later phase, once Gamma's architecture is mature enough to handle provenance, caching, and reusable analytics cleanly.

### Goal of the tab

The Fundamentals tab should provide a workspace for:
- company-level financial analysis,
- historical statement review,
- ratio and trend analysis,
- valuation modeling,
- scenario testing.

It should help answer questions such as:
- How has this business evolved financially?
- What are the main drivers of profitability and cash generation?
- What assumptions are embedded in the current valuation?
- What would have to be true for the stock to be attractive or overpriced?

### Functionality

#### 1. Company overview
A high-level profile including:
- company description,
- sector/industry,
- market cap,
- enterprise value,
- headline valuation multiples,
- share count and capital structure highlights.

This acts as the first-pass orientation layer.

#### 2. Financial statements viewer
A detailed, well-structured panel for:
- income statement,
- balance sheet,
- cash flow statement,
- annual and quarterly views,
- historical trend comparison.

The user should be able to inspect raw and normalized financial history easily.

#### 3. Ratio and operating metrics panel
A layer for displaying:
- gross margin,
- operating margin,
- net margin,
- ROE / ROIC / ROA,
- leverage metrics,
- liquidity metrics,
- FCF conversion,
- capital intensity.

This converts raw statements into a more interpretable format.

#### 4. Trend analysis engine
A component for examining:
- YoY and QoQ changes,
- multi-year growth rates,
- margin progression,
- cost structure evolution,
- revenue composition if available,
- capital allocation patterns.

This is where the tab becomes analytical rather than merely descriptive.

#### 5. DCF workbench
A dedicated valuation module allowing the user to:
- define revenue growth assumptions,
- define margin trajectories,
- estimate reinvestment needs,
- input WACC / discount rates,
- define terminal growth or exit assumptions,
- generate implied value estimates.

This should be one of the flagship features of the tab, but it needs to be implemented carefully.

#### 6. Sensitivity analysis
The DCF engine should support:
- bull / base / bear cases,
- WACC vs terminal growth matrices,
- growth vs margin scenario matrices,
- implied upside/downside under different assumptions.

This is essential because the purpose of DCF is not just to produce one number, but to understand valuation sensitivity.

#### 7. Expectation / reverse-valuation analysis
A very useful extension would allow the app to estimate:
- what growth/margin path the current price implies,
- how much execution is embedded in valuation,
- how sensitive valuation is to key assumptions.

This aligns well with the user's research style.

#### 8. Peer comparison layer
A later feature could compare a company against peers in terms of:
- margins,
- multiples,
- growth,
- capital efficiency,
- implied expectations.

This should come after the core company-analysis and DCF infrastructure is stable.

### Data requirements

The tab would need:
- company metadata,
- annual and quarterly financial statements,
- shares outstanding,
- debt and cash balances,
- market valuation fields,
- filing timestamps,
- derived metrics and transformation logic,
- potentially analyst-estimate or peer-reference data later on.

### Data sources / APIs

Potential sources include:
- **SEC EDGAR / data.sec.gov** for raw filings and extracted data
- **Financial Modeling Prep** for normalized statements and related financial data
- **Polygon / Massive fundamentals endpoints** for standardized company financials

A practical implementation path would likely use a normalized provider first for speed, while keeping open the possibility of validating or backfilling with SEC-derived data later.

### Deliverable of the phase

At the end of Phase 6, Gamma should be able to:
- display company financial history clearly,
- compute major operating and valuation metrics,
- allow scenario-based DCF research,
- support sensitivity analysis,
- help the user reason about market-implied expectations.

This phase makes Gamma meaningfully useful for traditional equity research, but it should only be implemented once the data architecture is strong enough to support it properly.

---

## Cross-Phase Technical Priorities

These are not separate tabs, but they are essential to make the roadmap work.

### 1. Provider adapter layer
Every external source should be accessed through a dedicated adapter module rather than directly in the UI.

### 2. Normalized internal schemas
Gamma should standardize internal entities such as:
- prediction markets,
- market trades,
- wallets,
- macro series,
- rates curves,
- commodity curves,
- crypto tokens,
- pools,
- company financials,
- DCF scenarios,
- research hypotheses.

### 3. Local cache / storage
A local persistence layer should store:
- fetched data,
- transformed data,
- timestamps,
- saved screens,
- saved notes,
- scenario definitions.

This improves reproducibility and reduces repeated API calls.

### 4. Analytics engine separation
Analytics should be modular and reusable:
- market calibration,
- cross-market coherence scoring,
- curve and spread analytics,
- regime and event analysis,
- wallet concentration,
- flow metrics,
- DCF calculations,
- scenario analysis,
- cross-sectional screens.

### 5. Provenance metadata
Every important field should ideally carry:
- source/provider,
- retrieval timestamp,
- endpoint/module origin,
- transformation note if derived.

This becomes increasingly important as fundamentals and AI-assisted outputs are added.

---

## Summary of the Development Order

### Phase 1 - Prediction Markets (`Complete`)
Build the most differentiated and accessible research tab first.

### Phase 2 - Macro (`In progress ~30%`)
Build a multi-mode macro workspace for snapshot monitoring, rates and policy analysis, and cross-asset expectations coherence.

### Phase 3 - Keyboard Navigation & Workspace Customization (`Not started`)
Add keyboard shortcuts for view switching, sidebar toggle, and common actions. Add drag-and-drop tab reordering in the sidebar with per-workspace persistence. Keybindings follow the user's custom tab order.

### Phase 4 - AI Copilot (`Not started`)
Add a context-aware research assistant that sits on top of the data architecture already built.

### Phase 5 - Crypto (`Not started`)
Expand into a broader public-data market research environment with token, wallet, and on-chain analytics.

### Phase 6 - Fundamentals (`Not started`)
Add company financial analysis and valuation once the architecture is mature enough to handle normalization and provenance correctly.

---

## End State Vision

If the roadmap is executed well, Gamma evolves from a portfolio/risk app into a **multi-domain research platform** where the user can:

- inspect markets,
- inspect macro regimes,
- study behavior,
- analyze flows,
- compare cross-asset expectations,
- compare scenarios,
- test valuation assumptions,
- generate ideas,
- structure research more effectively.

The long-term goal is not to become "Bloomberg-lite" or "a trading terminal."  
The long-term goal is to become a **personal research laboratory for markets**.

That distinction should guide every design decision.
