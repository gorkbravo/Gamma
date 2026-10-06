# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Marketing website: plain static HTML/CSS/JS (user decision). No build step, no
dependencies, deployable by dropping the folder on GitHub Pages, Netlify, or
Vercel. Lives in `website/` inside the Gamma repository.

The product it markets is a separate stack: FastAPI backend, Svelte frontend,
Tauri desktop shell, Python analytics.

## Users

Primary: technically capable individual market researchers and quant-leaning
retail/prosumer investors who will clone the repository, obtain their own
provider API keys (IBKR/TWS, FRED, EIA, CoinGecko, AISstream, OpenAI), and run
Gamma locally on their own machine. They are comfortable with a terminal, a
Python venv, and a broker session.

Secondary: peers, collaborators, and evaluators assessing the depth of the build
itself. The site must read as a real product front door for the first group
while doubling as evidence of craft for the second.

Situation: at a desk, on a dark screen, before or during market hours, forming a
view. Not on a phone in a queue.

## Product Purpose

Gamma is a read-only market research environment. It exists so one person can
inspect data, compare signals across unrelated domains, and understand the
calculation behind every number on screen — without the tool hiding its
analytics behind unexplained proprietary scores, and without it ever placing a
trade.

Success is a user who trusts what changed, where it came from, and what to do
next.

## Positioning

The mechanism a neighbor could not truthfully copy: **Gamma refuses to execute,
and shows its work.**

- Read-only is a platform-level contract, not a setting. It is exposed as an
  API (`/system/read-only-boundary`) and covers the TWS operator lock and the
  app-side no-execution boundary.
- Provenance is structural. Entities carry `source_provider`, `retrieved_at`,
  `origin`, and `transformation_note`, so a heuristic is always legible as a
  heuristic.
- Absence is a first-class state. Gamma never silently substitutes sample data
  for an unavailable live provider; degradation is labeled, and mock mode is
  always marked `MOCK / DEMO`.
- Breadth under one roof, on one plane: portfolio, risk, options/IV, equities,
  strategy, macro, commodities, prediction markets, crypto, fundamentals,
  maritime AIS, and an AI copilot — cross-linked by handoffs, not siloed tabs.

## Operating Context

- Desktop product (Tauri shell; browser dev path; legacy PySide fallback).
- Runs locally against the user's own credentials. Provider keys stay
  server-side; the browser never holds them.
- Live IBKR path requires Trader Workstation running. IB Gateway is not
  supported.
- Keyboard-driven: `Ctrl+1..N` tabs, `Shift+1..N` modes, `Ctrl+Shift+P/R`
  workspaces, `Ctrl+B` sidebar, `Ctrl+R` refresh.
- Two workspaces (Portfolio, Research) with user-reorderable tabs.
- Mock mode (`MOCK_DATA=true`) runs the whole app offline with sample providers.

## Capabilities and Constraints

Shipped surfaces: Portfolio, Risk, Options/IV, SITREP, Equity Research, Strategy
Lab, Macro, Commodities, Prediction Markets, Crypto, Fundamentals, Sealanes,
Copilot.

Providers actually integrated: IBKR/TWS, yfinance, FRED, US Census, EIA, US
Treasury, Polymarket, Kalshi, CoinGecko, GeckoTerminal, SEC EDGAR (EdgarTools),
AISstream, OpenAI. Planned-but-not-live: BLS, BEA, ECB, Eurostat, IMF, OECD, UN
Comtrade, WTO, AKShare — these appear in provider capability metadata as
`planned` and must never be described as working.

Hard constraints the site must preserve:

- No order placement, execution, rebalancing, or trading automation. Ever.
- No personalized investment advice.
- Macro interpretation, commodity roll/spread heuristics, prediction-market
  freshness/rank, and crypto screen scores are Gamma heuristics, not models or
  ground truth.
- Monte Carlo v1 is long-only, unlevered. Risk coverage can be partial.
- Fundamentals is strongest on US SEC filers. Sealanes has real AIS coverage
  gaps. Macro and Crypto are paused at first-pass checkpoints.
- Strategy Lab `Script` runs only in an isolated ephemeral runtime with no
  network, credentials, Gamma API, broker, wallet, or execution authority.

## Brand Commitments

- Name: **Gamma**. Wordmark exists as a Γ-derived glyph at
  `frontend/public/gamma-mark.svg` (a stepped Γ form, cool near-white gradient).
- Voice: precise, unhedged, technical. States limits plainly rather than
  marketing around them. The README's "What Gamma Does Not Do" section is the
  voice reference.
- Existing design doctrine: `docs/design_principles.md` — "Bloomberg Terminal's
  information density with Linear's spatial discipline." Dark, one-plane,
  quiet-chrome, two-type (mono for data, sans for chrome).
- Implemented token system: `frontend/src/lib/theme/tokens.css` (bg `#070809`,
  accent `#7aa6c8`, positive `#4bb474`, negative `#d97a70`, warning `#c49a5a`).
- Repository: https://github.com/gorkbravo/Gamma

## Evidence on Hand

- Full product documentation: `README.md` (~895 lines, tab-by-tab, including the
  math behind each metric and each surface's caveats).
- Design doctrine: `docs/design_principles.md`. Provenance contract:
  `docs/provenance_expectations.md`. Roadmap: `roadmap.md`.
- Real running application, capturable in mock mode for screenshots.
- Brand mark SVG.

Absences future work must not fabricate: there are **no** users, customers,
testimonials, press, funding, pricing, benchmarks, uptime figures, download
counts, or third-party endorsements. No LICENSE file exists yet. There is no
hosted/SaaS version and no installer release — the only distribution path today
is cloning and running the repository.

## Product Principles

1. **Show the work.** Every derived number should be traceable to a source and a
   transformation. Marketing it is the same as building it.
2. **Absence is data.** Missing, stale, degraded, and sample states are labeled,
   never filled in silently.
3. **Read-only is the product, not a limitation.** The refusal to execute is
   what makes the analysis trustworthy.
4. **Density earns its keep.** More useful relationships per viewport — never
   smaller text or decoration standing in for information.
5. **Claim only what runs.** Planned providers, paused tabs, and first-pass
   depth are stated as such.

## Accessibility & Inclusion

No product-specific standard was established by the user. Baseline expectation
for the website: WCAG AA contrast on all text, full keyboard operability,
visible focus, respect for `prefers-reduced-motion`, and semantic landmarks —
consistent with the app's own keyboard-first posture.
