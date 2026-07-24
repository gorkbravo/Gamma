# Gamma

For future product expansion work, start with [`roadmap.md`](./roadmap.md). It is the single active source of truth for current product direction, historical phase checkpoints, next hardening work, extension work, and new-domain planning.

Gamma is a read-only market research application built as a FastAPI backend, a Svelte frontend, and a Tauri desktop shell. Tauri is the primary desktop path today, while the older PySide client still exists as an explicit fallback. In practice, the product currently combines two things:

- an existing IBKR-connected portfolio, risk, and implied-volatility workstation
- a newer research workspace centered on macro, prediction-market, crypto, fundamentals, commodities, and AI-assisted analysis

The app is designed to help the user inspect data, compare signals, and understand the calculations behind the screens. It is not designed to place trades or to hide its analytics behind unexplained scores.

For the documentation map, see [`docs/README.md`](./docs/README.md). Dated audits live in [`docs/audits/`](./docs/audits/README.md), and historical migration/handoff material lives in [`docs/archive/`](./docs/archive/README.md).

## What Gamma Does

Gamma currently lets a user:

- connect to IBKR or run in mock mode
- monitor a live or sample portfolio in a chosen base currency
- study portfolio performance, exposures, and local history
- open a dense SITREP surface for cross-asset situation awareness
- build single-name or synthetic research scopes
- forward research scopes into Risk and IV
- explore a multi-mode Macro workspace
- screen and inspect prediction markets across Polymarket and Kalshi
- screen and inspect crypto tokens with narrative baskets, DEX liquidity context, and comparative analytics
- inspect company fundamentals, financial statements, peer context, and persistent DCF scenarios
- research commodities across energy, metals, curves, spreads, inventories, events, and cross-domain handoffs
- inspect implied-volatility surfaces, implied probability slices, strategy payoffs, and Gamma-owned options Greeks through the Options / IV explorer
- generate Copilot research cards, synthesis, operator plans, and memos from loaded Gamma state through both the shell shelf and the dedicated Copilot workspace
- navigate the app as a desktop product with reorderable tabs and keyboard shortcuts

## What Gamma Does Not Do

Gamma does not:

- place orders or execute strategies
- act as a trading bot or portfolio rebalancer
- run arbitrary user strategy code inside the app
- support IB Gateway yet; the live path is Trader Workstation
- treat heuristic macro interpretation layers as causal models
- treat commodity curve, roll-yield, spread, or inventory heuristics as execution signals
- treat incomplete risk coverage as exact portfolio-wide truth
- present prediction-market freshness, relatedness, or research rank as objective ground truth

That boundary is intentional and roadmap-aligned: Gamma is a research environment, not an execution platform.

## Product Shape

Gamma opens on a landing screen that shows connection state and lets the user enter one of two workspaces:

1. `Portfolio View`
2. `Research View`

Within each workspace, tabs can be reordered in the sidebar. The default layout is:

- `Portfolio View`: `PORTFOLIO`, `RISK`, `OPTIONS`
- `Research View`: `SITREP`, `EQUITY RESEARCH`, `STRATEGY LAB`, `MACRO`, `PREDICTION MARKETS`, `CRYPTO`, `FUNDAMENTALS`, `COMMODITIES`, `SEALANES`, `COPILOT`, `RISK`, `OPTIONS`

The current desktop navigation model is part of the product, not an afterthought:

- `Ctrl+1` ... `Ctrl+N` switches tabs in the user-defined order
- `Ctrl+Shift+P` switches to the Portfolio workspace
- `Ctrl+Shift+R` switches to the Research workspace
- `Ctrl+B` or backtick toggles the sidebar
- `Ctrl+R` or `F5` refreshes the active surface
- `Ctrl+,` opens settings
- `Esc` dismisses sidebar and light overlays

## How Gamma Is Built

At a high level, the stack is:

- `frontend/`: Svelte application that renders the desktop and browser UI
- `src/api/`: FastAPI route layer
- `src/application/`: service layer where most product logic lives
- `src/services/`: adapters, market-data access, caches, FX conversion, IBKR integration
- `src/analytics/`: reusable return, risk, and VaR math
- `frontend/src-tauri/`: Tauri desktop shell

The architecture follows a fairly clean pattern:

1. The frontend calls FastAPI endpoints.
2. Routes stay thin and delegate to application services.
3. Services call provider adapters and reusable analytics helpers.
4. Responses return both values and metadata such as source provider, retrieval time, origin, and transformation notes where available.

The current API surface is grouped by workspace:

- `/system/*`: runtime status, connection state, diagnostics, settings, provider capability metadata
- `/portfolio/*`: snapshot, local history, performance
- `/research/*`: single-name and synthetic-scope analysis
- `/macro/*`: snapshot payload, divergences, event feed, series history
- `/commodities/*`: workspace payload, market summaries, price history, curves, spreads, inventories, events, and cross-domain links
- `/prediction-markets/*`: screener, detail, history, wallet summary, related markets, calibration
- `/crypto/*`: workspace screener, token detail, price history, DEX liquidity, comparison
- `/fundamentals/*`: company search, overview, financials, DCF model, peer baskets
- `/maritime/*`: Sealanes workspace, AIS position samples, chokepoints, flows, and event windows
- `/copilot/*`: structured research-card generation from app context
- `/risk/*`: risk computation
- `/iv/*`: IV snapshot and session loop

### Request Size And Compute Limits

Gamma's local API rejects oversized or obviously invalid request payloads before they reach provider adapters or analytics engines. These limits are separate from external provider rate limits; they are local safety bounds for memory, CPU, cache-key size, and accidental refresh bursts.

The shared constants live in `src/application/request_limits.py`. Current public request caps include:

- Risk: Monte Carlo simulations are capped at `20,000`, Monte Carlo horizon and VaR horizon at `252` trading days, VaR lookback at `2,520` trading days, and beta window at `756` trading days.
- Strategy Lab: imported return streams are capped at `10,000` rows, with bounded column counts and text field lengths.
- Crypto: workspace search text is capped at `128` characters, workspace results at `100`, and synthetic portfolio positions at `100`.
- Prediction Markets: screener text is capped at `256` characters, venues at `20`, and result limit at `100`.

Oversized API requests return FastAPI/Pydantic `422` validation errors. Normal UI presets stay under these ceilings, and the Risk service also clamps direct in-process callers before Monte Carlo arrays are allocated.

## Data Sources And Provenance

Gamma mixes broker, public-market, public-macro, on-chain, and filing data. The product expectation is provider-backed data wherever the needed public endpoint, API key, entitlement, or TWS session is available. Mock and sample providers are useful for development, demos, offline fallback, and explicit degraded states, but they are not the success criterion for a completed feature when a real provider path exists.

- `IBKR`: portfolio snapshots, security history when explicitly configured or needed as fallback, FX spot/history, IV surfaces, fundamentals market-price context, and commodity futures curves where the user has entitlements
- `Yahoo Finance / yfinance`: default public live-ish listed-market history for Research Overview and SITREP boards; unofficial and not institutional quote truth
- `FRED`: macro time series; configure `FRED_API_KEY` for uncached API requests. Macro snapshots preserve the remaining series and return an explicit warning when an individual FRED series is unavailable.
- `US Census`: optional live US trade-partner rows for Macro when `CENSUS_API_KEY` is configured
- `EIA`: optional selected official US energy fundamentals for the Commodities tab when `EIA_API_KEY` is configured
- `US Treasury`: Treasury curve snapshots for the US rates view
- official macro event adapters: policy and macro calendar coverage used in `Events / Regimes`
- planned macro depth providers: `BLS`, `BEA`, `ECB`, `Eurostat`, `IMF`, `OECD`, `UN Comtrade`, and `WTO` are represented in provider capability metadata for country comparison and trade-partner adapter work; the first UI pass uses explicit curated placeholders until live adapters are added
- `Polymarket`: Gamma API, Data API, and CLOB history endpoints
- `Kalshi`: public market, event, history, and trade endpoints
- `CoinGecko`: broad token market coverage, token metadata, categories, and price history
- `GeckoTerminal`: DEX network metadata, pool search, token-pool lookup, and liquidity context
- `SEC EDGAR / data.sec.gov via EdgarTools`: company resolution, filing chronology, company facts, and statement inputs
- `OpenAI`: optional Copilot model provider behind Gamma's AI service boundary
- `sample_data/` and generated sample providers: local offline development, demos, and explicit fallback/degraded behavior when `MOCK_DATA=true` or a domain provider is not configured

A lot of the app's trust model depends on provenance. Many returned entities carry:

- `source_provider`
- `retrieved_at`
- `origin`
- `transformation_note`

That metadata is especially important in Macro, Prediction Markets, Crypto, and Commodities, where Gamma is often transforming raw public data into normalized metrics or heuristic interpretations.

The backend exposes shared Workstream 1 metadata through `/system/*` routes:

- `/system/provider-capabilities`: read-only provider capability metadata so future services, UI surfaces, and Copilot context builders can distinguish active, optional, sample, and planned providers without making provider calls
- `/system/read-only-boundary`: Gamma's platform-level read-only contract, including the TWS API read-only operator lock note and the app-side no-execution boundary

Shared backend primitives now cover provenance, freshness labels, cache freshness policy assessment, generic cross-tab handoff envelopes, and future Copilot context contracts. These are foundation contracts for new providers and roadmap builders, not a big-bang retrofit requirement for every legacy response.

For current roadmap planning, the intended provider stance is:

- keep `IBKR / TWS` first-class for Portfolio, IV/options, FX, fundamentals price context, selected commodity futures curves, and explicit high-fidelity research workflows
- keep Research Overview and SITREP listed-market boards behind provider policy so they can prefer public providers such as `yfinance` first, with IBKR fallback only when configured
- use official/free sources such as `FRED`, `BLS`, `BEA`, `EIA`, `ECB`, `Eurostat`, `US Treasury`, and `SEC EDGAR` for macro, energy, economic, and filing-backed datasets
- consider specialist providers only where they add a structurally different surface, such as AIS/maritime data, deeper futures history, or on-chain analytics
- keep every provider path read-only; market-data access must not imply order placement or execution features
- treat sample-only behavior as degraded or incomplete when the relevant live/provider-backed path is configured and expected to work

The current listed-market policy is configured server-side:

- `RESEARCH_MARKET_DATA_PROVIDERS=yfinance,ibkr` for Research Overview
- `SITREP_MARKET_DATA_PROVIDERS=yfinance` for SITREP listed-market boards
- `RESEARCH_OVERVIEW_CACHE_SECONDS=300` and `SITREP_MARKET_DATA_CACHE_SECONDS=300` for the 5-minute live-ish overview cache

yfinance is treated as an unofficial, rate-limited provider. Gamma performs at most two bounded retries by default with exponential backoff and jitter, opens a short circuit after repeated rate limits, preserves stale history when available, and continues to the next configured provider for symbols that remain unresolved. Tune this with `YFINANCE_MAX_RETRIES`, `YFINANCE_BACKOFF_SECONDS`, `YFINANCE_MAX_BACKOFF_SECONDS`, `YFINANCE_CIRCUIT_THRESHOLD`, and `YFINANCE_CIRCUIT_COOLDOWN_SECONDS`. SITREP cash-index symbols remain on their own provider policy because public Yahoo symbols do not map generically to IBKR index contracts.

`AKShare` is documented and recognized as a future China/Asia provider hook, but Gamma does not ship a live AKShare adapter yet.

## Currency, Caching, And State

Gamma is base-currency aware. That matters across Portfolio, Research, and Risk:

- positions carry native currency and base-currency market value
- historical price series are converted into the selected base currency when possible
- Gamma prefers historical FX history
- when historical FX is unavailable, it falls back to spot FX and emits explicit warnings

There are also multiple persistence layers:

- a local portfolio-history store for portfolio value snapshots
- a research history cache for symbol histories used repeatedly in research flows
- a general cache for provider payloads such as macro series and prediction-market API responses

Changing the base currency clears the local portfolio-history store because those snapshots are base-currency specific.

## Workspace Guide

### Portfolio Workspace

#### Portfolio tab

This is Gamma's portfolio monitor. It combines broker snapshot fields, local history, and normalized historical returns.

Main outputs:

- net liquidation, day P&L, gross exposure, net exposure, cash weight
- local portfolio history with `Value`, `Growth`, and `Drawdown` views
- benchmark-relative performance
- position table with native and base-currency values
- allocation and concentration side panels
- broker/runtime messages and diagnostics

Under the hood:

- position weights are `base_market_value / total base market value`
- price histories are aligned on the common date intersection, then converted with `pct_change()`
- portfolio return series is the weighted sum of constituent returns
- cumulative performance is `(1 + returns).cumprod()`, rebased to `1.0`
- benchmark series is also rebased to `1.0`
- max drawdown is computed from the cumulative series as `(cumulative / cumulative.cummax()) - 1`
- if account-level day P&L is missing, Gamma estimates it from the latest two daily bars plus FX conversion

Important caveats:

- the local history store is not a full broker backfill; it is a local snapshot trail
- performance quality depends on overlapping history and FX availability
- cash legs are modeled as zero-return series

#### Risk tab

The Portfolio workspace Risk tab runs the same backend engine used by the Research workspace, but against the active portfolio snapshot.

It provides:

- historical VaR and CVaR
- parametric VaR
- Monte Carlo VaR and CVaR
- annualized volatility and drawdown
- rolling beta and rolling correlation views
- Jensen alpha when the base currency is USD and the risk-free series is available
- contribution-to-risk tables and rankings
- risk coverage diagnostics and excluded assets

Under the hood:

- historical VaR is the negative lower-tail quantile of portfolio returns at `1 - alpha`
- historical CVaR is the negative mean of returns in that tail
- parametric VaR is `z(alpha) * sigma`, where `sigma` comes from the weighted covariance matrix
- multi-day parametric VaR scales by `sqrt(time)`
- Monte Carlo supports:
  - `Gaussian`: multivariate normal draws using a nearest-positive-semidefinite covariance matrix
  - `Bootstrap`: resampling historical aligned return rows
- Monte Carlo paths are compounded into cumulative paths, terminal return distributions, and percentile fans
- variance contribution is `w_i * (Sigma w)_i / (w' Sigma w)`
- marginal contribution to risk is `(Sigma w)_i / sigma_p`
- component VaR is `w_i * MCTR_i * z(alpha)`, scaled into currency terms

Important caveats:

- the engine is history-based and linear in spirit; it is not a full nonlinear scenario engine
- Monte Carlo v1 only supports long-only, unlevered books
- headline total VaR can be a scaled estimate when only part of the book has usable history
- Gamma warns when coverage is incomplete or observations are thin

#### IV tab

The IV explorer is a surface and scenario-inspection tool, not a broker pricer or execution surface.

It provides:

- max-depth IV surface snapshots as the primary UI workflow
- a Python-owned session loop for explicit repeated refreshes
- backend depth presets that trade expiry count and strike width against TWS market-data-line usage; the UI favors the `Max` preset so line budget goes toward strike breadth
- registered modes for `Overview`, `Chain`, `Surface`, `Realized vs IV`, `Implied Probabilities`, and `Strategies`
- expiry/strike heatmap
- selected expiry slice
- ATM term structure
- selectable display-grid fitting for the 3D surface: line interpolation, spline interpolation, or SSVI
- front-expiry IV smile, wing-skew rows, and term-structure rows derived from the current surface
- local realized-volatility comparisons when underlying price history is available
- local implied-probability density slices with selectable strike-range probability mass
- a chain-driven strategy builder with selected long/short call/put legs, net premium, breakevens, max profit/loss, and payoff matrix by price and remaining DTE
- Gamma-owned Black-Scholes Greeks for chain rows and aggregate selected strategies

Under the hood:

- live mode requests an IV surface snapshot from the backend IV engine over IBKR
- `Compact`, `Standard`, `Deep`, `Front Deep`, and `Max` presets tune the backend's expiry count, strike band, contract cap, and line budget; the default max surface keeps expiries tight so calls and puts can cover more strikes
- the backend preserves observed option-chain rows and applies the selected model only to the display IV grid, with fit/fallback metadata returned in the surface payload
- provider-returned Greeks are preserved when IBKR supplies them, while Gamma can derive fallback Greeks from provider IV or solved IV using zero-rate/zero-dividend Black-Scholes assumptions
- the frontend highlights the strike nearest to spot and uses that strike to derive ATM term structure
- the implied-probability surface is a local lognormal density proxy derived from the fitted IV grid, not a vendor-grade risk-neutral-density feed
- the strategy payoff matrix marks selected legs to model values across remaining DTE; it is research math only and does not imply order routing or broker valuation authority
- in mock mode, Gamma generates a synthetic surface with a simple skew/term-structure shape so the UI remains testable

Important caveats:

- this tab shows returned surface data, contract rows, display-grid fit, local Greeks, implied probability proxies, and payoff scenarios; it does not route orders or manage option positions
- Gamma-owned Greeks and payoff matrices depend on the current fitted IV grid, selected chain rows, and simplified Black-Scholes assumptions
- historical IV/skew persistence, deeper source inspection, richer expiry/strike controls, and durable Realized vs IV history remain current-roadmap hardening work
- if IBKR is disconnected, the live surface path is unavailable

### Research Workspace

#### Equity Research tab

This tab owns equity market overview, scope analysis, comparables, scenario/context framing, and saved equity research. Its modes are:

- `Overview`
- `Scope Analysis`
- `Comparables`
- `Scenario / Context`
- `Saved Equity Research`

The scope builder analyzes either:

- a `single_ticker` scope
- a `synthetic_portfolio` scope

Synthetic scopes are normalized to a notional portfolio of `100` base-currency units before analysis.

Main outputs:

- total return, annualized return, annualized volatility, max drawdown
- benchmark beta and correlation
- weight structure, HHI, effective positions, top-weight concentration
- constituent-level return, volatility, and drawdown
- scope preview before execution
- handoff actions into `Risk` and `IV`
- handoff actions into `Strategy Lab` for read-only object composition

Under the hood:

- single-name scopes become one synthetic position with weight `1.0`
- synthetic text inputs are parsed line by line and renormalized to sum to `1.0`
- historical returns are computed from aligned base-currency price histories
- portfolio performance is again a weighted return stream
- total return is the terminal value of cumulative returns minus `1`
- annualized return is `cumulative^(252 / n) - 1`
- annualized volatility is `std(daily_returns) * sqrt(252)`
- benchmark beta is `cov(portfolio, benchmark) / var(benchmark)`
- correlation is computed on aligned portfolio and benchmark returns
- concentration HHI is `sum(w_i^2)` on absolute normalized weights
- effective positions is `1 / HHI`

Important caveats:

- research scopes are synthetic analysis contexts, not broker portfolios
- missing symbols and incomplete overlap reduce the number of aligned observations
- only single-name research can forward directly into IV

#### Strategy Lab tab

This tab owns read-only strategy-object work. Its modes are:

- `Composer`
- `Backtest / Analyze`
- `Regime / Stress`
- `Imports`
- `Saved Runs`

Current Strategy Lab flows can import CSV return streams, analyze normalized performance, compose return-bearing Gamma objects, inspect drawdown and rolling-risk stress windows, and reload saved normalized runs. It does not execute strategy code, connect to broker execution, or persist raw uploaded CSV rows by default.

#### Macro tab

Macro is paused at the roadmap's first-pass checkpoint and is the densest research workspace in the app. It is a multi-mode surface with shared context:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`
- `Trade Partners`
- `Country Compare`

Shared context:

- region: `US`, `EU`, `Global`
- timeframe: `1M`, `3M`, `6M`, `1Y`
- theme: `all`, `growth`, `inflation`, `policy`, `recession_risk`
- optional comparison region for US/EU concept matching

What is sourced directly:

- raw FRED series
- derived YoY series from index levels
- derived spread series such as `10Y - 2Y`, scaled into basis points
- IBKR midpoint FX histories for the FX strip
- Treasury XML curve nodes for the US curve view
- official event calendars used in event studies

What Gamma adds on top:

- snapshot cards with level, active-timeframe change, and `why now` text
- cross-asset divergence scoring
- coherence labels
- lead/lag annotations
- linked prediction-market context
- policy-path and meeting-ladder proxies
- bilateral trade-partner rows for US/EU first, with Global kept as a lighter context lens
- country comparison rows across growth, inflation, labor, policy, and trade-balance metrics

The key Macro math is heuristic and transparent:

- each metric's active-timeframe move is `latest - prior_timeframe_point`
- each themed signal is scaled as `clamp((delta / scale) * factor, -3, 3)`
- `factor` encodes whether a series supports or opposes a theme
- `scale` normalizes different series into a shared rough signal range
- divergence score is `strongest positive signal - strongest negative signal`
- divergence labels are currently:
  - `high` for score `>= 2.4`
  - `moderate` for score `>= 1.2`
  - `low` otherwise

The coherence and lead/lag layer is explicitly heuristic:

- Gamma infers the dominant theme direction from the sign of the aggregate signal set
- it then labels signals as supporting, opposing, or neutral
- for timeframe coherence, Gamma asks when each supportive series reached roughly `60%` of its current themed move
- the earliest series becomes the provisional leader and the latest supportive series becomes the laggard
- coherence is labeled `coherent`, `narrow`, or `fractured` based on agreement and lag span

For event studies:

- Gamma compares curated proxies around official event windows
- recent studies look at post-event reactions
- upcoming studies look at pre-event setup windows
- event lead/lag is again heuristic and especially noisy for monthly or quarterly series

Important caveats:

- Macro is not a statistical factor model
- comparison overlays only exist where Gamma has curated counterpart mappings
- `Global` is a lighter comparative lens, not a fully independent region stack
- EU coverage is now a first-class target for trade and country-compare context, while some underlying live adapters remain planned
- US trade-partner rows use live Census country goods-trade data when `CENSUS_API_KEY` is configured and fall back to curated rows; EU/global trade-partner and country-compare rows remain read-only scaffolds until Eurostat, IMF/OECD, UN Comtrade, WTO, BEA, and BLS adapter paths replace the placeholders

#### Commodities tab

Commodities is a current-roadmap Workstream 8 first pass. It is a research workspace, not a trading terminal.

Modes:

- `Overview`
- `Energy`
- `Metals`
- `Curves & Spreads`
- `Inventories & Fundamentals`
- `Events / Cross-Domain`

Main surfaces:

- commodity universe selector across energy and metals
- KPI strip for latest price, curve shape, front spread, roll-yield proxy, inventory signal, and provider coverage
- price-history and curve charts using the shared time-series chart
- market snapshot tables for energy and metals
- curve node tables
- calendar spreads, inter-commodity ratios, and product-crack proxies
- inventory and fundamental panels
- event notes and heuristic links into Macro, Prediction Markets, and Sealanes

Provider behavior:

- default `COMMODITIES_PROVIDER=sample` uses generated offline sample prices, curves, inventories, and events
- `COMMODITIES_PROVIDER=eia` enables selected EIA official energy fundamentals when `EIA_API_KEY` is present
- optional `FRED_API_KEY` lets the EIA provider enrich selected spot/proxy price histories through existing FRED client infrastructure, including broad monthly metal proxies for aluminum, zinc, nickel, lead, tin, iron ore, uranium, and configured precious/industrial metals
- `COMMODITIES_PROVIDER=ibkr` builds read-only futures curves from individual IBKR/TWS `FUT` contract details and market-data snapshots when TWS is connected and the account has the needed futures market-data entitlements
- IBKR futures curves use `IBKR_COMMODITIES_ENABLED`, `IBKR_COMMODITIES_STARTUP_ENABLED`, `IBKR_COMMODITIES_BREADTH_ENABLED`, `IBKR_COMMODITIES_ON_DEMAND`, `IBKR_COMMODITIES_SELECTED_CACHE_SECONDS`, `IBKR_COMMODITIES_CONTRACT_DEPTH`, `IBKR_COMMODITIES_BREADTH_CONTRACT_DEPTH`, `IBKR_COMMODITIES_HISTORY_DAYS`, `IBKR_COMMODITIES_QUOTE_TIMEOUT_SECONDS`, `IBKR_COMMODITIES_CONTRACT_TIMEOUT_SECONDS`, `IBKR_COMMODITIES_QUOTE_BATCH_SIZE`, and optional `IBKR_COMMODITIES_ROOT_OVERRIDES` to tune roots, depth, and request behavior
- when `COMMODITIES_PROVIDER=ibkr` and `EIA_API_KEY` is present, Gamma uses EIA/FRED as the low-cost SITREP reference layer and overlays shallow IBKR breadth curves plus deeper selected-root coverage; EIA product spot defaults cover RBOB gasoline and heating oil via `EIA_RBOB_GASOLINE_PRICE_SERIES_ID` and `EIA_HEATING_OIL_PRICE_SERIES_ID`
- IBKR futures rows carry either a usable daily reference history (`IBKR` front-contract bars, `FRED`/`EIA` spot proxies, or another continuous/spot proxy) or an explicit no-daily-reference placeholder with a warning; Gamma does not silently validate futures rows with sample histories
- if IBKR contract discovery, quotes, or entitlements are unavailable, Gamma keeps the sample or EIA/FRED fallback payload and returns explicit coverage warnings

What Gamma computes:

- contango / backwardation / flat curve labels
- headline price change from a dated prior close/reference when available; otherwise `N/A`
- front spread, M1-M6 spread, curve slope, and a simple front-spread roll-yield proxy
- spread change, z-score, and percentile when enough history exists
- latest inventory change and simple percentile context
- commodity-linked macro, maritime, and prediction-market handoff notes

Important caveats:

- sample data is illustrative and explicitly marked as sample or proxy coverage
- EIA coverage is official but partial, US-energy-focused, and release-lagged
- FRED price histories are spot or proxy series, not futures chains
- IBKR curves are constructed by Gamma from discovered futures contracts; live, delayed, cached, or missing quote status depends on TWS connectivity, exchange subscriptions, and market-data mode
- IBKR front-contract histories are not back-adjusted continuous futures; cached local curve snapshots are never used as prior settlements for headline `% CHG`
- local daily curve snapshots accumulate only after Gamma observes the curve and are treated as curve-history context, not as unknown-vintage daily closes
- roll-yield, spread z-scores, seasonal inventory context, and cross-domain links are Gamma heuristics
- Commodities remains read-only and does not expose order placement, strategy execution, or trading automation

#### Prediction Markets tab

This is Gamma's first roadmap tab completed at a first-pass level. It is multi-venue by design and currently supports Polymarket and Kalshi.

Main surfaces:

- a screener
- market detail and probability history
- wallet or flow summary
- related-market consistency view
- first-pass historical calibration

What Gamma normalizes:

- venue-specific market metadata into a common market record
- probability histories into a primary-outcome probability stream
- related-market records across venues
- freshness and integrity status
- wallet or flow summaries into a shared structure

Research rank in the screener is not a model output from the venues. Gamma computes it:

- with query: it emphasizes query relevance, then signal, recency, and resolution timing
- without query: it emphasizes market signal, resolution window, recency, and recent repricing
- signal itself is a weighted log-scaled mix of volume, liquidity, total volume, and open interest
- freshness penalties lower the score for delayed, stale, or broken markets

Freshness is also Gamma-defined:

- `fresh`, `delayed`, `stale`, `broken`, or `closed`
- broken means venue metadata conflicts with market integrity, such as an "open" contract with a passed end time
- history lag thresholds tighten as resolution approaches

Related-market linking is heuristic:

- same-event sibling detection inside a venue
- cross-venue analogs via lexical similarity, threshold extraction, and resolution-date proximity
- relationship labels include `cross_venue_analog`, `adjacent_threshold`, `conditional_consistency`, `same_event`, and `topic_similarity`

Wallet and calibration notes:

- Polymarket can expose participant-level flow summaries from public data
- Kalshi public endpoints do not expose wallet identities, so Gamma shows aggregate taker-flow style rows instead
- participant `current_edge` is current normalized probability minus average paid price for buys, and the inverse for sells
- calibration buckets compare average pre-resolution probability against realized frequency on resolved markets

Important caveats:

- Gamma filters out non-research categories on purpose
- freshness, relatedness, and research rank are Gamma heuristics
- calibration coverage is still thin and venue dependent

#### Crypto tab

Crypto is paused at the roadmap's first-pass checkpoint. The current pass is a research-first vertical slice, not a trading terminal.

Main surfaces:

- token screener with query, narrative, chain, market-cap, volume, and turnover filters
- normalized token profile with market cap, FDV, supply, category tags, and provenance
- price history with market-cap and volume context
- narrative and sector baskets mapped from CoinGecko categories
- DEX liquidity summary with top matched pools from GeckoTerminal
- default relative comparison versus a narrative basket or fallback token benchmark

What Gamma normalizes:

- CoinGecko token and category payloads into shared token and basket records
- 24H turnover as `volume / market_cap`
- a Gamma screen score across size, liquidity, turnover, momentum, and FDV premium
- GeckoTerminal network and pool payloads into a shared liquidity view
- token-versus-token and token-versus-basket comparisons into a common comparison record

Important caveats:

- screen score, narrative mapping, and basket comparisons are Gamma-defined heuristics
- DEX lookup can fall back to heuristic pool search when exact contract lookup is unavailable
- wallet-level or deeper on-chain analytics are not in this first pass yet

#### Fundamentals tab

Fundamentals is complete for the current roadmap pass. It is a company-analysis workspace built around SEC-native data, Gamma-owned calculations, explicit provenance, and local model state.

Main surfaces:

- exact-ticker company focus, keyboard/browser-drivable search, and explicit unsupported ETF/fund/non-US states
- overview with company profile, headline KPIs, filing provenance, peer basket, and peer heatmap
- financial statement views across income statement, balance sheet, cash flow, and ratios, with YoY/QoQ comparisons and amendment context
- annual and quarterly statement basis toggles
- Gamma-owned ratio and operating metric views
- DCF workbench with Bear / Base / Bull scenarios, sensitivity, terminal-value multiple framing, snapshots, and local persistence
- reverse valuation and raw-versus-normalized filing inspection
- context-preserving handoffs to Strategy Lab, Copilot, Equity Research, Risk, and Options
- section-level degradation warnings that retain successful payloads when one Fundamentals endpoint is unavailable

What Gamma normalizes:

- SEC company facts and filing chronology into a company workspace record
- annual and quarterly statement rows into a shared financial-statement structure
- ratio and valuation fields into Gamma-derived metrics with source/provenance separation
- peer baskets and DCF assumptions into local workspace state

Important caveats:

- Fundamentals is currently strongest for US SEC filers
- market-price-aware fields depend on available market context
- broader non-US filing/reference providers and consensus-estimate depth are optional future expansion rather than blockers for the current completion boundary

#### Copilot layer

Copilot now exists in two places: a shell shelf for quick active-context research cards, and a dedicated Research workspace tab for synthesis, active-tab focus, operator plans, session history, and memo-oriented workflows. Both surfaces remain read-only and grounded in loaded Gamma state.

Current behavior:

- adapts its grounding to the active tab and selected entity
- preserves lightweight per-domain thread history
- forwards compatible follow-up turns through the provider boundary
- exposes scope, provenance, warnings, and tool traces in generated outputs
- supports first-pass cross-context synthesis across loaded Gamma domains
- stores local sessions, turns, context snapshots, and first-pass memos
- exposes a feature-flagged operator path for bounded read-only research actions

Important caveats:

- Copilot is read-only and should remain grounded in Gamma state, not external execution
- provider-level streaming, richer archive/search/title handling, memo editing/export, stricter source-backed/inferred labeling, and voice interaction remain current-roadmap work

## Current Roadmap Position

Per [`roadmap.md`](./roadmap.md), Gamma's current roadmap state is:

- `Phase 1 - Prediction Markets`: complete at a first-pass level
- `Phase 2 - Macro`: paused around 84% in the archived phase roadmap, with Snapshot, Cross-Asset, Rates & Policy, and Events / Regimes as the first-pass checkpoint; the current roadmap has since expanded the live tab to include Trade Partners and Country Compare
- `Phase 3 - Keyboard Navigation & Workspace Customization`: complete
- `Phase 4 - AI Copilot`: paused around 70% in the archived phase roadmap; the current roadmap has since added a dedicated Copilot workspace alongside the shell shelf, with local sessions, synthesis, memos, and bounded read-only operator actions
- `Phase 5 - Crypto`: paused around 73%, with a first-pass token explorer, screener, narrative baskets, DEX liquidity view, comparative context, and Copilot support now live
- `Phase 6 - Fundamentals`: archived phase checkpoint paused around 83%; current-roadmap Fundamentals V2 is complete for this pass with six modes, filing inspection, peer/DCF/reverse-valuation workflows, cross-tab handoffs, and reliability coverage
- `Workstream 1A - SITREP`: first-pass locked research-home tab live with cross-domain triage, Bloomberg Television YouTube embed, equities/FX/yields/commodities tables, and explicit provider caveats
- `Workstream 8 - Commodities`: first-pass vertical slice live with sample fallback, optional EIA energy fundamentals, IBKR-built futures curves, curves/spreads/inventory analytics, UI tab, API surface, and Copilot context

That means the app already has meaningful portfolio/risk/IV capabilities, a first-pass SITREP entry surface, first-pass research surfaces across Prediction Markets, Macro, Crypto, Fundamentals, and Commodities, plus a live Copilot workspace and shell layer. Remaining deepening work is tracked as current-roadmap scope.

## Current Roadmap Direction

The current roadmap is organized as parallel workstreams rather than a strict sequence. The intent is to distinguish real dependencies from work that can proceed independently.

The main roadmap buckets are:

- cross-cutting platform work: provider adapters, read-only market-data boundaries, mode-level keybindings, shared cache/provenance behavior, and stronger cross-tab handoffs
- existing-tab hardening passes: Equity Research, Strategy Lab, Macro, IV, Crypto, Fundamentals, and Copilot hardening / extension work
- new research surfaces: a deep Commodities workspace and a Maritime Intelligence workspace if the data-provider path is viable
- beta readiness: installer, tutorial, first-run setup, mock/demo flows, diagnostics, and friend/family testing polish

The likely feature direction is:

- `Equity Research` and `Strategy Lab`: deepen market overview / tree-map views, scope analysis, comparables, saved equity research, imported return-stream analytics, weighted Gamma object compositions, and comparison workflows
- `Macro`: finish EU/global depth, official-event breadth, policy-path interpretation, and coherence / lead-lag refinement
- `IV`: harden the shipped volatility lab around selectable surface models, skew / term views, Gamma-owned Greeks, realized-vs-implied overlays, implied-probability slices, strategy payoff flow, source transparency, history, and cross-tab handoffs
- `Crypto`: add real wallet analytics, stronger pool / transaction monitoring, richer peer and basket comparisons, and later derivatives overlays
- `Fundamentals`: add reverse valuation, implied expectations, richer raw-vs-normalized inspection, better peer/reference depth, and eventually broader non-US coverage
- `Copilot`: keep the shell shelf for quick context, but add a dedicated workspace for persistent sessions, saved memos, streaming, workflow handoffs, synthesis, and later voice interaction
- `Commodities`: treat as a full research tab if it includes futures curves, calendar spreads, inter-commodity spreads, inventories, seasonal overlays, and macro / geopolitical links
- `Maritime Intelligence`: treat AIS and shipping data as a trade-flow intelligence surface, with live map, chokepoints, route shifts, event replay, commodity-flow links, and possible later shadow-fleet analytics

The important boundary does not change: Gamma can study strategies, market data, vessels, commodities, wallets, options, and companies, but it should remain a read-only research environment.

## Practical Limitations

- IB Gateway is not supported yet
- some live IBKR data paths still depend on entitlements and symbol availability
- TWS market data is useful but session-based, entitlement-dependent, and not a bulk historical warehouse
- portfolio and research analytics depend on overlapping daily histories
- historical FX gaps can force spot-FX fallback
- Macro interpretation is intentionally heuristic and should be read as structured research assistance, not inference certainty
- Prediction Markets currently go deepest on discovery, normalization, and first-pass comparative analysis, not exhaustive microstructure backtesting
- Crypto is currently strongest on token discovery, normalization, and liquidity-aware first-pass comparison, not deep wallet analytics or derivatives overlays
- Fundamentals is strongest on US SEC-native coverage; broader international equities remain future work
- Commodities has a practical first pass with sample curves, optional EIA fundamentals, and IBKR-built futures curves; deeper vendor-grade historical curve storage remains future work
- IV is now a usable volatility-lab first pass, but it is not a full options analytics suite; historical IV/skew storage, richer source/Greek inspection, stronger Realized vs IV history, and broader handoffs remain current-roadmap work

## Running Gamma

The README is no longer mainly an install tutorial, but the basic operator paths still matter.

Setup:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
```

Backend:

```powershell
$env:MOCK_DATA="true"
$env:GAMMA_SESSION_TOKEN="<dev-only random token>"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Optional live FRED-backed Macro series:

```powershell
$env:FRED_API_KEY="<your key>"
$env:GAMMA_SESSION_TOKEN="<dev-only random token>"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

If one FRED or IBKR FX series fails, Macro skips that series, keeps the remaining snapshot, and returns a provider/reference-specific warning. Provider exception text and credentials are not copied into the user-facing warning.

Optional Commodities EIA enrichment:

```powershell
$env:COMMODITIES_PROVIDER="eia"
$env:EIA_API_KEY="<your key>"
$env:GAMMA_SESSION_TOKEN="<dev-only random token>"
# Optional: set FRED_API_KEY to enrich selected spot/proxy price histories.
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Without `EIA_API_KEY`, Commodities degrades to the sample provider and returns explicit coverage warnings. Provider credentials stay server-side.

Optional Commodities IBKR futures curves:

```powershell
$env:COMMODITIES_PROVIDER="ibkr"
$env:IB_MARKET_DATA_MODE="delayed"
$env:IBKR_COMMODITIES_ENABLED="wti,henry_hub,gold,copper"
$env:IBKR_COMMODITIES_STARTUP_ENABLED="wti"
$env:IBKR_COMMODITIES_BREADTH_ENABLED="__enabled__"
$env:IBKR_COMMODITIES_ON_DEMAND="true"
$env:IBKR_COMMODITIES_CONTRACT_DEPTH="12"
$env:IBKR_COMMODITIES_BREADTH_CONTRACT_DEPTH="2"
$env:GAMMA_SESSION_TOKEN="<dev-only random token>"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

This path requires a running TWS session and futures market-data permissions. Gamma treats `IBKR_COMMODITIES_ENABLED` as the allowed universe, fetches shallow breadth curves for `IBKR_COMMODITIES_BREADTH_ENABLED` roots on the Commodities workspace, and deepens the selected enabled root to `IBKR_COMMODITIES_CONTRACT_DEPTH`. Set `IBKR_COMMODITIES_BREADTH_ENABLED=__enabled__` to request thin curves for every enabled root, or provide a comma-separated subset to reduce market-data-line pressure. Cached selected curves default to 300 seconds, contract discovery defaults to a longer cache, and fallback sample or EIA/FRED records remain visible when IBKR is disconnected, entitlement-limited, stale, or not selected.

Optional Maritime AISstream prototype:

```powershell
$env:MARITIME_PROVIDER="aisstream"
$env:AISSTREAM_API_KEY="<your key>"
$env:AISSTREAM_SAMPLE_SECONDS="6"
$env:GAMMA_SESSION_TOKEN="<dev-only random token>"
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

AISstream is treated as partial live AIS only. Gamma samples configured chokepoint bounding boxes, keeps the key server-side, and does not infer cargo, risk, sanctions, routing, or operational labels from the live stream.

Frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
$env:VITE_GAMMA_SESSION_TOKEN="<same dev-only random token>"
npm run dev -- --host 127.0.0.1 --port 5173
```

Desktop:

```powershell
$env:MOCK_DATA="true"
.\.venv\Scripts\python.exe -m src.desktop_launcher
```

Tauri development:

```powershell
cd frontend
npm install
$env:MOCK_DATA="true"
npm run tauri:dev
```

## Validation

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The test suite forces mock listed-market providers before application runtime import, regardless of local `.env` values. It uses a deterministic offline SPY benchmark derived from bundled sample histories, so tests cannot accidentally contact Yahoo Finance or TWS.

Frontend and desktop checks:

```powershell
cd frontend
npm run test
npm run build
npm run desktop:check
npm run backend:smoke
npm run desktop:smoke
```

The supported desktop compile validation path remains:

```powershell
cd frontend
npm run desktop:check
```
