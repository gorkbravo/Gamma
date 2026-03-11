# StrataLab Roadmap

## Purpose

This roadmap defines the planned expansion of **StrataLab** from a portfolio/risk-oriented research app into a broader **read-only research environment** for markets, valuation, on-chain analytics, prediction markets, and AI-assisted idea generation.

The core principle behind this roadmap is simple:

**StrataLab is not a trading bot and not an execution platform.**  
It is a place to **aggregate data, structure research, test hypotheses, explore market behavior, and generate ideas**.

Because of that, every new tab should satisfy at least one of these goals:

1. Improve the ability to **discover research opportunities**
2. Improve the ability to **analyze a market, asset, or company**
3. Improve the ability to **generate, structure, and refine hypotheses**
4. Improve the ability to **compare scenarios without execution risk**

The roadmap is organized into phases so that development follows the highest **research value / implementation complexity** path first. The order is designed to avoid turning StrataLab into a bloated dashboard with weak data foundations. The idea is to first build tabs where the data is relatively accessible and the research surface is rich, then later move into heavier normalization problems such as company fundamentals and valuation.

---

## Guiding Product Principles

### 1. Read-only by design
StrataLab should remain focused on research, data aggregation, analytics, and experimentation. Even when the app studies strategies, wallet behavior, or arbitrage structures, it should not become an execution layer.

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
As StrataLab expands, especially into fundamentals and AI-assisted outputs, every displayed metric should ideally be traceable to:
- source/provider,
- endpoint,
- timestamp,
- transformation logic.

---

## Phase 1 - Prediction Markets Tab

### Why this phase comes first

Prediction markets are one of the highest-upside additions to StrataLab because they combine:
- relatively accessible public data,
- rich behavioral and microstructure dynamics,
- strong fit with research-oriented workflows,
- differentiated analytical surface compared to standard equity dashboards.

This tab would make StrataLab feel unique very quickly. It also aligns with the user's interest in market structure, informed flow, wallet behavior, and event-driven repricing.

### Goal of the tab

The Prediction Markets tab should allow the user to explore prediction markets as probabilistic systems, behavioral systems, and market microstructure systems.

It should help answer questions such as:
- Which markets are active and interesting right now?
- How have implied probabilities evolved over time?
- Are some wallets consistently early to information?
- Are related contracts priced inconsistently?
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

#### 5. Cross-market consistency engine
A module for comparing related markets that should obey rough probabilistic consistency. For example:
- overlapping event outcomes,
- conditional event structures,
- mutually exclusive contracts,
- related geopolitical or electoral contracts.

This can surface market dislocations or possible research opportunities.

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
- market metadata,
- market status,
- category/tag data,
- implied probability history,
- volume/liquidity/open interest,
- trade history,
- wallet participation data,
- holder/concentration data,
- final resolution/outcome data.

### Data sources / APIs

Potential sources include:
- **Polymarket Gamma API** for market discovery and metadata
- **Polymarket Data API** for trades, activity, holders, positions, and related data

Longer term, external news/context could be linked, but that is optional and should not be required for the initial release.

### Deliverable of the phase

At the end of Phase 1, StrataLab should be able to:
- browse and filter prediction markets,
- inspect a market deeply,
- analyze probability dynamics,
- review wallet behavior,
- begin basic historical research on calibration and microstructure.

This phase gives StrataLab a highly distinctive research edge with relatively manageable implementation complexity.

---

## Phase 2 - Crypto Tab

### Why this phase comes next

Crypto is a natural extension because:
- public data access is broad,
- on-chain activity is transparent,
- it complements prediction-market and behavioral research,
- it opens up a large analytical surface without requiring execution infrastructure.

However, "crypto" is broad, so the key to Phase 2 is restraint. The tab should not attempt to become a full crypto terminal immediately.

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

This should support the broader StrataLab identity as an experimentation environment.

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

At the end of Phase 2, StrataLab should be able to:
- research tokens and sectors,
- explore narrative baskets,
- study wallet flows,
- inspect DEX liquidity conditions,
- run screens across a crypto universe.

This phase broadens the app into a more general market-research platform while staying consistent with its data-driven, read-only identity.

---

## Phase 3 - AI Copilot Layer

### Why this phase comes here

The AI component becomes most useful **after** StrataLab already has meaningful data surfaces. If added too early, it risks becoming a generic chatbot with little grounding. If added after the app has prediction-market and crypto data infrastructure, it can act as a true research assistant rather than a novelty feature.

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
- token flow anomalies,
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

This would make StrataLab more usable during exploratory sessions.

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
- compare prediction-market sentiment with crypto narrative activity,
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

The AI layer primarily needs access to **internal StrataLab state**, including:
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
- function/tool calling to access internal StrataLab tools
- structured-output schemas for predictable research responses

Internally, the AI should call functions such as:
- fetching current context,
- listing loaded datasets,
- retrieving price/probability history,
- retrieving wallet activity,
- retrieving token/company data,
- triggering internal analytics.

### Deliverable of the phase

At the end of Phase 3, StrataLab should have an AI-assisted research workflow that can:
- understand current context,
- suggest hypotheses,
- propose tests,
- explain results,
- generate structured research outputs.

This phase does not replace the data tabs. It multiplies the value of every other phase.

---

## Phase 4 - Fundamentals Tab

### Why this phase comes later

The Fundamentals tab is highly valuable, but it is the most likely to become bloated and technically messy. Company financial data is not just "another dataset." It involves:
- normalization issues,
- quarterly vs annual mismatches,
- restatements,
- reporting differences across firms,
- derived metric ambiguity,
- valuation-model complexity.

This makes it better suited for a later phase, once StrataLab's architecture is mature enough to handle provenance, caching, and reusable analytics cleanly.

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

At the end of Phase 4, StrataLab should be able to:
- display company financial history clearly,
- compute major operating and valuation metrics,
- allow scenario-based DCF research,
- support sensitivity analysis,
- help the user reason about market-implied expectations.

This phase makes StrataLab meaningfully useful for traditional equity research, but it should only be implemented once the data architecture is strong enough to support it properly.

---

## Cross-Phase Technical Priorities

These are not separate tabs, but they are essential to make the roadmap work.

### 1. Provider adapter layer
Every external source should be accessed through a dedicated adapter module rather than directly in the UI.

### 2. Normalized internal schemas
StrataLab should standardize internal entities such as:
- prediction markets,
- market trades,
- wallets,
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

### Phase 1 - Prediction Markets
Build the most differentiated and accessible research tab first.

### Phase 2 - Crypto
Expand into a broader public-data market research environment with token, wallet, and on-chain analytics.

### Phase 3 - AI Copilot
Add a context-aware research assistant that sits on top of the data architecture already built.

### Phase 4 - Fundamentals
Add company financial analysis and valuation once the architecture is mature enough to handle normalization and provenance correctly.

---

## End State Vision

If the roadmap is executed well, StrataLab evolves from a portfolio/risk app into a **multi-domain research platform** where the user can:

- inspect markets,
- study behavior,
- analyze flows,
- compare scenarios,
- test valuation assumptions,
- generate ideas,
- structure research more effectively.

The long-term goal is not to become "Bloomberg-lite" or "a trading terminal."  
The long-term goal is to become a **personal research laboratory for markets**.

That distinction should guide every design decision.
