# Gamma Usability Findings

Date: 2026-06-07  
Audience: future AI agents and contributors improving Gamma  
Context: live local app audit at `http://127.0.0.1:5173/` with TWS/IBKR available for at least some market-data paths.

## Purpose

This note captures product findings from a live end-to-end trade-idea workflow. It is not an investment memo and should not be treated as a recommendation. The goal is to help future agents understand what Gamma already does well, what breaks a real analyst workflow, and what improvements are most worth doing next.

Gamma should remain a read-only research environment. The right target is not "Bloomberg-grade everything." The app is built around free or low-cost data sources, public APIs, local caches, and optional IBKR/TWS connectivity. That constraint is acceptable, but Gamma needs to be very explicit about what is live, cached, delayed, synthetic, sample-backed, inferred, or unavailable.

## Audit Setup

The live audit started from a fresh thesis discovered inside Gamma, not a prewritten idea:

- Sitrep and Equity Research showed semis/AI selling off hard while defensive and quality names held up.
- Rates, real yields, the dollar, and oil were all moving in a way that plausibly pressured long-duration growth equities.
- The tested thesis was: small long low-beta defensives or quality versus short semis/AI beta after a rates/oil/crowding shock.

Tabs exercised:

- Sitrep
- Equity Research
- Strategy Lab
- Risk
- Options
- Fundamentals
- Macro
- Prediction Markets
- Copilot

## High-Level Finding

Gamma is much more useful when the live/provider paths are working. In this run it was able to generate a real research trail from market discovery through valuation, risk, options, macro, and prediction-market context.

The core issue is no longer "the app has no data." The main issues are:

1. Cross-tab state is inconsistent.
2. Strategy composition can retain stale hidden state and produce untrustworthy results.
3. Signed long/short research is not reliably supported end-to-end.
4. Copilot active-tab grounding is honest, but cross-context synthesis is too manual and unstable.
5. Provider/provenance labels exist in places, but the user still has to infer too much.

## What Worked Well

### Sitrep

Sitrep worked as the intended research triage surface. It surfaced a non-generic idea quickly: semis/AI were down sharply, defensive/quality names were green, rates and oil were pressuring risk assets, and news context pointed to a broader selloff/crowding concern.

This is the correct role for Sitrep. It should continue to be the place where a user notices anomalies before deciding which tab deserves deeper work.

What to preserve:

- Dense cross-asset snapshot.
- Fast read on leaders, laggards, rates, FX, commodities, and headlines.
- Explicit live/provider/status labels.

What to improve:

- Make each signal handoff-ready. A laggard, commodity move, headline, or rate shock should be easy to send into Equity Research, Macro, Strategy Lab, Risk, or Copilot with the originating context attached.

### Equity Research

Equity Research was useful for quickly turning a tape observation into quantitative context. The Scope workflow handled single names and long-only baskets well.

Useful outputs observed:

- NVDA: 317 observations, high volatility, high beta, meaningful drawdown.
- AI Infrastructure preset: transparent constituent weights and high-beta/high-return profile.
- Defensive basket: low-beta profile, useful as a hedge leg but not an alpha engine.

What to preserve:

- Preset baskets with visible weights.
- Fast performance, volatility, drawdown, beta, and correlation summary.
- Clear warnings about static metadata, unofficial providers, limited observations, or missing fields.

What to improve:

- Do not silently drop negative weights. If the scope builder cannot support shorts, reject the input visibly and explain why.
- If long/short is intended to be handled only in Strategy Lab, provide a direct "Send signed book to Strategy Lab" flow with validation.
- Preserve the active basket when moving away and returning. In the audit, returning from Strategy Lab reverted the active context to NVDA, which lost the analytical thread.

### Fundamentals

Fundamentals was the strongest deep-analysis tab. It provided real analytical depth, not just a quote page.

Useful outputs observed:

- Company reference and SEC/filing provenance.
- Revenue, EBIT, FCF, market cap, EV, valuation multiples, profitability, growth, returns.
- Peer heatmap.
- DCF scenarios and editable assumptions.
- WACC bridge with macro-derived risk-free rate.
- Sensitivity table and value-driver bridge.

What to preserve:

- Assumption transparency.
- Raw versus normalized financial grounding.
- DCF and reverse-valuation surfaces.
- Peer comparison.
- Filing dates, source dates, and retrieval timestamps.

What to improve:

- Global equity focus should load the focused company or at least show a one-click "Load NVDA from current focus" action. In the audit, Fundamentals showed global NVDA focus but did not load NVDA automatically.
- Search selection feedback needs work. Pressing Enter appeared to select NVDA but left the UI in a loading state; explicitly clicking the row loaded it.
- DCF assumptions should be easy to export or send to Copilot/Strategy Lab as a named research object.

### Risk

Risk was useful for converting a thesis into sizing caution. The NVDA view surfaced concentration, volatility, beta, drawdown, Monte Carlo-style terminal distribution, and provenance warnings.

What to preserve:

- Concentration and coverage warnings.
- Drawdown, beta, correlation, VaR/ES, and contribution breakdown.
- Clear notes when optimization/frontier outputs are unavailable because the book is too narrow.
- Provenance around aligned observations and benchmark overlap.

What to improve:

- Make it easier to evaluate a synthetic research book created in Equity Research or Strategy Lab.
- Add clearer "this is research context, not account context" labeling when a selected symbol or basket is analyzed outside the real portfolio.
- Provide stress templates linked to Macro and Commodities shocks, such as rates up, oil up, dollar up, or semis factor unwind.

### Options

Options was materially better with live IBKR data available. The audit observed a live NVDA surface with IBKR provider labeling, live chain metadata, spot, ATM IV, term slope, expiry depth, and strategy controls.

What to preserve:

- Provider/source labeling.
- Surface reload controls.
- Overview, chain, surface, implied probability, and strategy modes.
- Gamma-owned Greeks and quality metadata, even when fields are missing.

What to improve:

- Options should not default the payoff glance to a call when the active research thesis or recent prompt is bearish. A neutral default is better than an implied recommendation.
- Many strikes/Greeks were N/A. That is acceptable with free/live constraints, but the UI should distinguish provider-missing, model-missing, stale, and not-computable.
- Strategy construction needs a faster path to common structures: put spread, call spread, collar, straddle, risk reversal.
- The app should show when buying front-vol is unusually expensive versus historical or back-expiry IV, because this directly affects trade construction.

### Macro

Macro provided useful context for the trade: rates, real yields, the dollar, oil, CPI, policy divergence, and curve movement.

What to preserve:

- Cross-asset macro snapshot.
- Rates and policy context.
- FX integration.
- Provenance and retrieved-date labels.

What to improve:

- Add explicit handoffs from Macro shocks into Risk and Strategy Lab.
- Make "macro shock packets" reusable: rates up, oil up, USD up, inflation surprise, curve steepener/flattener.
- Expose source depth and fallback status consistently, especially when using free public feeds.

### Prediction Markets

Prediction Markets was useful as event and policy color, but not decisive for the trade.

What worked:

- Search found AI-policy markets.
- Market detail showed probability, flow, liquidity, participants, provenance, resolution text, and calibration limitations.
- Active-tab Copilot used PM context honestly.

What did not work:

- Related markets were clearly wrong in one case: an AI policy market linked to unrelated GTA VI-themed markets because of shared venue metadata.
- Calibration was unavailable, which is fine, but should be visually framed as "not enough history" rather than just a warning.

What to improve:

- Related-market linking needs a semantic/event taxonomy layer, not just venue event metadata.
- Let users mark bad related links so future normalization can improve.
- Improve cross-domain linking from PM events to equities, macro, commodities, and Copilot memos.

### Copilot

Copilot was mixed.

Active-tab mode was useful because it was honest. When asked to evaluate an equity long/short thesis while active on a Prediction Markets context, it refused to overclaim and listed the missing data.

Synthesis mode was weaker. It required manual context selection even though several tabs had been loaded. After selecting Equity Research, Fundamentals, Macro, Options, Risk, and related contexts, the generation hung/reset without returning a card.

What to preserve:

- Clear distinction between source-backed and inferred claims.
- Refusal to validate a thesis from insufficient active-tab context.
- Context labels showing what the model is grounded on.

What to improve:

- Synthesis should auto-suggest recently loaded contexts.
- Synthesis needs a timeout/error state with a recoverable draft, not a silent reset.
- The user should see exactly which data snapshots Copilot will use before generation.
- Copilot should be able to say "Strategy Lab result appears unreliable because composition state is stale or inconsistent" when the app has enough evidence.

## What Did Not Work

### Strategy Lab Is The Biggest Workflow Risk

Strategy Lab is promising, but in this audit it broke trust.

The attempted book was a simple signed research expression:

- Long XLP
- Long BRK-B
- Short SMH

The result was invalid:

- The composer retained stale inline data from a previous workflow.
- Clearing the visible text did not clear hidden inline state.
- The generated result used only 6 return points and showed nonsensical performance.
- The output looked like a valid analysis even though the underlying data was contaminated.

This is the highest-priority fix because Strategy Lab is where Gamma should validate multi-leg research ideas. If it produces plausible-looking invalid metrics, it can mislead users.

Required improvements:

- Every leg needs a visible source badge: provider, inline, imported CSV, Gamma object, sample, stale, unavailable.
- Every row needs a hard reset/remove action.
- Hidden inline state must not persist after the visible row is cleared.
- Composition output must fail closed when observation count is too low or mixed-source alignment is suspicious.
- Show alignment diagnostics before performance metrics: date range, number of overlapping observations, dropped legs, stale rows, missing prices.
- Add a "validate book" step before running analysis.

### Long/Short Workflow Is Fragmented

Gamma can discover a long/short idea, but cannot yet pressure-test it cleanly end-to-end.

Current behavior:

- Equity Research can analyze long-only baskets well.
- Equity Research silently drops short weights.
- Strategy Lab theoretically supports signed legs but had stale-state contamination.
- Risk can analyze selected contexts but needs cleaner synthetic-book handoffs.
- Options can inspect a single-name hedge but does not yet connect cleanly to the broader thesis.

Target behavior:

1. Discover anomaly in Sitrep.
2. Create signed research book in Equity Research or Strategy Lab.
3. Validate data coverage and alignment.
4. Send book to Risk for factor/contribution/stress analysis.
5. Send short leg to Options for defined-risk expression.
6. Send thesis to Fundamentals and Macro for support/contradiction.
7. Ask Copilot to synthesize only the validated context.

### State Continuity Is Inconsistent

The app has a global focus concept, but it is not consistently applied.

Observed examples:

- NVDA focus carried into Risk and Options.
- Fundamentals showed NVDA focus in the shell but did not automatically load NVDA.
- Strategy Lab contained stale objects and old handoffs from earlier workflows.
- Returning to Equity Research lost the AI Infrastructure basket and reverted to NVDA.
- Copilot Synthesis did not automatically infer recently loaded contexts.

Required improvements:

- Define a single context contract across tabs: selected entity, selected basket, selected market, selected macro shock, selected strategy object.
- Every tab should clearly state whether it used, ignored, or could not use the current focus.
- Stale handoffs should expire or be grouped by session.
- A "current research thread" object should collect the active thesis, selected objects, and validated outputs.

### Provider Status Needs To Be More Explicit

The free-data constraint is fine. The app should not pretend to have institutional coverage. But users and agents need to know exactly what kind of data they are seeing.

Provider labels should distinguish:

- live IBKR
- delayed provider
- yfinance/unofficial
- SEC/public filing
- FRED/public macro
- EIA/public commodity
- RSS/news
- cached
- sample/mock
- synthetic/derived
- unavailable

This should be normalized across tabs. Do not rely on local widget-specific warning prose.

## Free-Data Constraint: Product Stance

Gamma can be excellent without premium data if it is honest and methodical.

Future agents should not respond to every gap by proposing expensive vendor feeds. Prefer this order:

1. Better provenance and source labeling.
2. Better validation and failure modes.
3. Better use of existing free/public/provider-backed data.
4. Optional adapter interfaces for premium data later.

Examples:

- Missing options Greeks are acceptable if the UI says whether the provider omitted them or Gamma could not compute them.
- Prediction-market calibration can be limited if the app clearly shows sample size and resolved-market availability.
- Commodity curves can be public/sample-backed if curve construction and freshness are explicit.
- yfinance can be useful for exploratory equities if warnings and provider labels are visible.
- IBKR can be used opportunistically when TWS and entitlements are available, but the app should degrade gracefully when they are not.

The highest-value work is not "buy better data." It is making the current data safe to reason with.

## Prioritized Improvements For Future Agents

### P0: Make Strategy Lab Fail Closed

Fix stale state, row reset, hidden inline data, source diagnostics, observation alignment, and invalid metric gating.

Progress update - 2026-06-07:

- Completed: Strategy Lab composition responses now include `alignment_diagnostics` with minimum observations, aligned observation count/window, per-leg source provider, object id/type, raw and normalized weights, available window, and usable observation count.
- Completed: thin-overlap Strategy Lab compositions still fail closed, and the validation error now includes per-leg alignment diagnostics instead of only a generic shared-observation message.
- Completed: failed object or portfolio composition calls clear the previously displayed Strategy Lab composition in the frontend store, so a stale valid-looking result is not left on screen after a failed run.
- Completed: the Strategy Composer table now shows a visible `Source` column for each leg (`Provider`, `Inline`, `Object`, or `Unset`), plus separate `Reset` and `Remove` actions. Choosing a provider identifier, Gamma object, or inline history clears the other source fields for that row, reducing hidden-source contamination.
- Completed: successful composition output now shows alignment diagnostics before performance KPIs, including shared window, aligned observations, per-leg source, per-leg window, per-leg observations, and normalized weight.
- Validation run: `python -m pytest tests/test_research_v2.py -k strategy_lab`, `python -m pytest tests/test_api.py -k "strategy_lab_portfolio_compose_endpoint_accepts_signed_inline_legs or strategy_lab_resolve_handoff_endpoint_returns_equity_draft or strategy_lab_composes"`, `npm run typecheck`, `npx vitest run src/lib/stores/app.test.ts -t "clears stale Strategy Lab composition after failed portfolio compose"`, `npx vitest run src/lib/view-models/research.test.ts`, and an in-app browser smoke check of Strategy Lab at `http://127.0.0.1:5173/`.
- Known validation note: a full `npm test -- --run src/lib/stores/app.test.ts src/lib/view-models/research.test.ts` invocation still hits an existing unrelated IV store test failure around `/iv/session/stop` not being called; the new Strategy Lab store test passes when filtered directly through `npx vitest`.

Still left:

- ~~Add a dedicated "Validate book" pre-run step instead of relying on the Compose action to perform validation.~~ Completed 2026-06-10 (see below).
- Expand source badges into the shared provider/provenance badge contract once that P1 shared component exists.
- Add stronger session expiry/grouping for old handoffs so stale handoff queues cannot reappear as current-session context.
- Add end-to-end tests for the exact audited book, long XLP / long BRK-B / short SMH, when the local market-data test fixtures can support those listed histories deterministically.

Progress update - 2026-06-10 (branch `claude/audit-completion-v2`):

- Completed (P0 leftover): Strategy Lab now has a dedicated "Validate Book" pre-run action backed by a new read-only `/research/strategy-lab/portfolio-validate` endpoint. It resolves every leg (provider, inline, Gamma object), reports per-leg source/window/observation diagnostics with signed normalized weights, applies the same fail-closed alignment gate as Compose, and renders a VALID/INVALID report (with a STALE marker when the draft changes after validation) without computing performance metrics.
- Completed (P1 signed books): the Equity Research scope builder no longer silently drops negative weights. A signed basket is rejected visibly ("Scope Analysis is long-only... Nothing was dropped or analyzed"), the parsed long/short legs are shown with short legs highlighted, and a "Send Signed Book to Strategy Lab" action hands every leg off with its sign preserved (`default_side: short`, negative `default_weight` flow through the existing resolver).
- Completed (P1 cross-tab state): returning to Equity Research no longer clobbers an active synthetic basket with the focal single ticker. The basket is preserved and the builder shows "Focus <SYM> is available but not loaded; the active basket is preserved" with an explicit load action. Explicit Sitrep handoffs still override the basket because they express direct intent.
- Completed (P2 options): the Strategies mode has one-click templates (call spread, put spread, straddle, collar, risk reversal) built from the nearest priced strikes with per-leg warnings, and the Overview Payoff Glance defaults to a neutral straddle instead of a call.
- Completed (P2 Copilot synthesis): research-card generation (180s) and operator runs (300s) now have request timeouts that surface as recoverable failure cards instead of a silent hang, and the prompt draft is preserved unless generation returns `ready`.
- Verified live in-browser on 2026-06-10 with yfinance-backed providers: the exact audited signed book (long XLP / long BRK-B / short SMH) was rejected in Scope, handed to Strategy Lab with signs intact, resolved against ~940-observation listed histories, and validated through the new pre-run check; Fundamentals auto-loaded the focal NVDA company; Copilot synthesis auto-suggested the session's loaded contexts and generated a READY card.
- Not verified live on 2026-06-10 (first pass): IBKR-backed paths (live options chain for the strategy templates, IBKR account/market data). TWS was not running during verification, so the connection was refused on port 7496; rerun the Options live checks with TWS open.
- Also fixed while validating: two stale navigation-test expectations for the current Options mode registry, and a `loadIvSurface` crash when a cached underlying-history payload has no symbol.

Progress update - 2026-06-10 (second pass, live TWS/IBKR):

- Verified live with TWS connected (port 7496, account-level read-only paths): IBKR connect/disconnect via the System toggle, a live NVDA IV surface (provider `ibkr`, live mode, 13 chain rows, ATM 205 vs spot 205.92, front ATM IV 48.6%), and the live account snapshot (real positions and cash balances).
- Verified live: the new one-click strategy templates against the live NVDA chain. Put Spread built long 205P @ 0.89 / short 197.5P @ 0.14 from the nearest priced strikes with Gamma-owned Greeks (net delta -0.334) and a correct breakeven; the neutral straddle Payoff Glance rendered the live ATM 205 straddle @ 4.89 with a full repricing matrix.
- Fixed (found during live template verification): `deriveStrategyPayoff` treated any short put as unbounded max loss and any short call as unbounded max profit, so defined-risk spreads showed "Max Loss: Open". Boundedness is now computed from the structure: only net call tail exposure is open-ended, and the downside extreme is the finite payoff at an underlying price of zero. A put spread now reports max loss = net premium; a naked short put reports its strike-minus-premium floor. Covered by new unit tests.
- Completed (audit "still left" item): Strategy Lab handoff session expiry/grouping. Persisted handoffs older than 24 hours load as an "Earlier Sessions" group: they are excluded from Resolve, Accept All, and the pending counts; any previously resolved payload is dropped so day-old return streams cannot be accepted silently; and each item offers Revive (re-enters the current queue as pending for fresh re-resolution), Dismiss, or a group-level Clear Earlier. Verified live by injecting a 9-day-old persisted queue item.
- Validation: backend 354 passed, frontend 182 passed (2 new tests), `tsc --noEmit` clean, plus in-browser verification of both fixes against the live IBKR session.

Success criteria:

- A user can build long XLP / long BRK-B / short SMH and see whether each leg has usable data.
- If the book has too few aligned points, Gamma refuses to show performance metrics as if they are meaningful.
- Clearing a row truly clears all associated source state.

### P1: Make Signed Books First-Class Research Objects

Signed books should not be an accidental feature split between Equity Research and Strategy Lab.

Success criteria:

- Negative weights are either supported or rejected visibly.
- Long/short books can move from Equity Research to Strategy Lab to Risk without losing leg signs.
- The book has a stable object ID, source metadata, and alignment diagnostics.

### P1: Strengthen Cross-Tab Context

Build a durable research-thread context instead of relying on ad hoc focus handoffs.

Success criteria:

- Tabs can declare: "using current context," "context available but not loaded," or "context unsupported."
- Copilot Synthesis can select recently loaded contexts automatically.
- Stale handoffs are visibly separated from the current session.

### P1: Normalize Provider/Provenance Badges

Create a shared provider-state component and data contract.

Success criteria:

- Every metric can show provider, timestamp, freshness, cache/sample/live state, and transformation note where applicable.
- Free/public/unofficial data is clearly labeled without making the UI noisy.
- Agents can inspect the same metadata programmatically for Copilot grounding and tests.

### P2: Improve Options Strategy Workflow

Options is useful live, but strategy construction needs to match analyst workflows.

Success criteria:

- Common structures are one-click templates.
- Missing Greeks have reason codes.
- IV term structure and historical context help decide whether to buy or sell vol.
- Equity/Fundamentals/Risk context can seed bearish, bullish, neutral, or hedge-oriented option templates without implying execution.

### P2: Repair Prediction-Market Related Links

Related markets need semantic validation.

Success criteria:

- AI-policy markets no longer link to unrelated venue-event artifacts.
- Related links explain whether they are same event, same topic, same entity, same resolution family, or weak semantic match.
- Users can downrank or flag bad links.

### P2: Make Copilot Synthesis Reliable

Copilot is valuable only if it can reliably work across Gamma contexts.

Success criteria:

- Synthesis can recover from timeout.
- Selected contexts are visible and editable.
- Recently loaded tabs are suggested automatically.
- Generated cards cite exact Gamma context records and state missing data plainly.

## Guidance For Future Agents

When improving Gamma, do not start by adding another tab. The app already has enough surfaces. Focus on making the existing research workflow trustworthy.

Recommended order:

1. Validate data and state before showing analytics.
2. Make cross-tab objects durable.
3. Make provider status explicit.
4. Make Copilot consume the same validated objects the UI uses.
5. Add depth only where the data model is ready.

Be especially careful with Strategy Lab, Risk, and Copilot because those surfaces can make weak or contaminated data look authoritative.

The product bar should be:

- good enough for real research,
- honest about free-data limits,
- read-only by design,
- impossible or at least difficult to confuse sample/stale/synthetic output with validated live analysis.
