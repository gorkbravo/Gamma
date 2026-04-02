# Gamma

For future product expansion work, start with [`roadmap.md`](./roadmap.md). It is the source of truth for what Gamma is meant to become, what order new work should land in, and which constraints should not be crossed.

Gamma is a read-only market research application built as a FastAPI backend, a Svelte frontend, and a Tauri desktop shell. Tauri is the primary desktop path today, while the older PySide client still exists as an explicit fallback. In practice, the product currently combines two things:

- an existing IBKR-connected portfolio, risk, and implied-volatility workstation
- a newer research workspace centered on macro and prediction-market analysis

The app is designed to help the user inspect data, compare signals, and understand the calculations behind the screens. It is not designed to place trades or to hide its analytics behind unexplained scores.

For the documentation map, see [`docs/README.md`](./docs/README.md). Historical migration and audit material lives in [`docs/archive/`](./docs/archive/README.md).

## What Gamma Does

Gamma currently lets a user:

- connect to IBKR or run in mock mode
- monitor a live or sample portfolio in a chosen base currency
- study portfolio performance, exposures, and local history
- build single-name or synthetic research scopes
- forward research scopes into Risk and IV
- explore a multi-mode Macro workspace
- screen and inspect prediction markets across Polymarket and Kalshi
- inspect implied-volatility surfaces through the IV explorer
- navigate the app as a desktop product with reorderable tabs and keyboard shortcuts

## What Gamma Does Not Do

Gamma does not:

- place orders or execute strategies
- act as a trading bot or portfolio rebalancer
- support IB Gateway yet; the live path is Trader Workstation
- treat heuristic macro interpretation layers as causal models
- treat incomplete risk coverage as exact portfolio-wide truth
- present prediction-market freshness, relatedness, or research rank as objective ground truth

That boundary is intentional and roadmap-aligned: Gamma is a research environment, not an execution platform.

## Product Shape

Gamma opens on a landing screen that shows connection state and lets the user enter one of two workspaces:

1. `Portfolio View`
2. `Research View`

Within each workspace, tabs can be reordered in the sidebar. The default layout is:

- `Portfolio View`: `Portfolio`, `Risk`, `IV`
- `Research View`: `Research`, `Macro`, `Prediction Markets`, `Risk`, `IV`

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

- `/system/*`: runtime status, connection state, diagnostics, settings
- `/portfolio/*`: snapshot, local history, performance
- `/research/*`: single-name and synthetic-scope analysis
- `/macro/*`: snapshot payload, divergences, event feed, series history
- `/prediction-markets/*`: screener, detail, history, wallet summary, related markets, calibration
- `/risk/*`: risk computation
- `/iv/*`: IV snapshot and session loop

## Data Sources And Provenance

Gamma mixes broker, public-market, and public-macro data:

- `IBKR`: portfolio snapshots, security history, FX spot/history, IV surfaces
- `FRED`: macro time series
- `US Treasury`: Treasury curve snapshots for the US rates view
- official macro event adapters: policy and macro calendar coverage used in `Events / Regimes`
- `Polymarket`: Gamma API, Data API, and CLOB history endpoints
- `Kalshi`: public market, event, history, and trade endpoints
- `sample_data/`: local offline development data when `MOCK_DATA=true`

A lot of the app's trust model depends on provenance. Many returned entities carry:

- `source_provider`
- `retrieved_at`
- `origin`
- `transformation_note`

That metadata is especially important in Macro and Prediction Markets, where Gamma is often transforming raw public data into normalized metrics or heuristic interpretations.

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

The IV explorer is a surface-inspection tool, not an options pricer.

It provides:

- one-shot IV surface loads
- a Python-owned session loop for repeated refreshes
- expiry/strike heatmap
- selected expiry slice
- ATM term structure

Under the hood:

- live mode requests an IV surface snapshot from the backend IV engine over IBKR
- the frontend highlights the strike nearest to spot and uses that strike to derive ATM term structure
- in mock mode, Gamma generates a synthetic surface with a simple skew/term-structure shape so the UI remains testable

Important caveats:

- this tab shows the returned surface; it does not derive Greeks, fit a surface model, or run an options valuation stack
- if IBKR is disconnected, the live surface path is unavailable

### Research Workspace

#### Research tab

This tab builds and analyzes either:

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

#### Macro tab

Macro is Gamma's current active roadmap phase and the densest research workspace in the app. It is a multi-mode surface with shared context:

- `Snapshot`
- `Cross-Asset`
- `Rates & Policy`
- `Events / Regimes`

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
- EU coverage is intentionally lighter than US coverage in v1

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

## Current Roadmap Position

Per [`roadmap.md`](./roadmap.md), Gamma's current roadmap state is:

- `Phase 1 - Prediction Markets`: complete at a first-pass level
- `Phase 2 - Macro`: in progress, with Snapshot, Cross-Asset, Rates & Policy, and Events / Regimes already live
- `Phase 3 - Keyboard Navigation & Workspace Customization`: complete
- `Phase 4 - AI Copilot`: not started
- `Phase 5 - Crypto`: not started
- `Phase 6 - Fundamentals`: not started

That means the app already has meaningful portfolio/risk/IV capabilities plus the first two roadmap-era research surfaces, but it is not yet at the intended end-state research platform described in the roadmap.

## Practical Limitations

- IB Gateway is not supported yet
- some live IBKR data paths still depend on entitlements and symbol availability
- portfolio and research analytics depend on overlapping daily histories
- historical FX gaps can force spot-FX fallback
- Macro interpretation is intentionally heuristic and should be read as structured research assistance, not inference certainty
- Prediction Markets currently go deepest on discovery, normalization, and first-pass comparative analysis, not exhaustive microstructure backtesting
- IV is an exploration surface, not a full options analytics suite

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
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
npm install
$env:VITE_API_BASE="http://127.0.0.1:8000"
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
