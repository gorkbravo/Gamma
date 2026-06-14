# Gamma Usability Findings

Date: 2026-06-12  
Audience: future AI agents and contributors improving Gamma  
Context: live local app audit at `http://127.0.0.1:5173/` with TWS/IBKR connected, `mock_mode=false`, `market_data_mode=delayed`, active account `U15779203`.

## Purpose

This note captures product findings from a live end-to-end trade-idea workflow. It is not an investment recommendation. The purpose is to document what Gamma helped with, where the branch fixes worked, where the workflow still broke, and which gaps matter most for making Gamma a reliable read-only research workbench.

The audit intentionally started from an idea discovered inside Gamma. Outside sources were used only to cross-check a news-driven oil signal after Sitrep surfaced it.

## Audit Setup

Backend and frontend were run locally with live IBKR/TWS connectivity:

- Backend: FastAPI on `127.0.0.1:8000`
- Frontend: Vite on `127.0.0.1:5173`
- Session auth header: `X-Gamma-Session`
- IBKR: connected to account `U15779203`
- Market data: delayed mode
- Commodities provider: IBKR futures curves, with WTI, Brent, Henry Hub, gold, and copper enabled

Tabs exercised:

- Sitrep
- Commodities
- Strategy Lab
- Risk
- Macro
- Fundamentals
- Options
- Prediction Markets
- Copilot

External sources used for cross-checking the app-originated oil signal:

- MarketWatch: crude oil sank toward a two-month low after a Trump post about Iran talks.
- Trading Economics: Brent fell on 2026-06-11.
- The Guardian: context around Trump, Iran, oil/gas, and ceasefire claims.

## Thesis Log

### Thesis 1: Oil de-escalation should favor airlines over energy beta

One-line thesis: Middle East / Iran de-escalation and falling crude should favor airline/transport exposure over energy beta, expressed as long `JETS` versus short `XLE`, with `DAL` as the quality airline read-through and an `XLE` put spread as a defined-risk expression.

How it started: Sitrep showed oil-deescalation headlines, WTI weakness, and a strong U.S. equity tape. The idea came from Gamma's Sitrep/news/commodity context rather than being brought in prewritten.

Steps taken:

1. **Sitrep:** Reviewed index tape, rates, FX, commodities, and headlines. The app surfaced the signal: U.S. equities were green, oil headlines were de-escalation-oriented, and WTI was weak.
2. **Commodities:** Opened WTI and energy context. The curve nodes supported lower front crude, but the WTI header showed `95` and `+0.72%`, conflicting with the oil-down Sitrep story and the curve itself.
3. **Strategy Lab:** Built `+0.7 JETS / -0.7 XLE`, validated, then composed. Validation worked well: 2/2 usable legs, 940 aligned observations, yfinance source diagnostics, signed normalized weights, and clear warnings. The result weakened the trade: total return `-0.78%`, annual return `-0.21%`, annual volatility `16.68%`, Sharpe `0.07`, max drawdown `-24.14%`, and 2026 return `-11.01%`.
4. **Risk:** Tried to continue the Strategy Lab book into risk/scenario analysis. Blocked. Risk did not inherit the Strategy Lab research book and opened with unknown coverage, N/A KPIs, return history length 0, and disabled compute buttons.
5. **Macro:** Checked rates and dollar backdrop. Macro pushed against the thesis: Headline CPI was hot, 2Y was well above Fed Funds, 10Y and real yields were higher, and the broad dollar was stronger.
6. **Fundamentals:** Loaded `DAL` manually because the Strategy Lab context did not carry into Fundamentals. DAL looked stronger than peers on the heatmap, but the DCF defaults produced negative equity value with suspect airline assumptions: D&A/revenue near zero, high revenue growth, heavy capex, negative projected FCF, and a high WACC.
7. **Options:** Loaded `XLE` manually because Options did not inherit the short leg. The live delayed IBKR surface loaded, and the put-spread template built a defined-risk `57P / 54.5P` structure. This was useful, but the default front expiry was too short for a thesis trade without manual adjustment.
8. **Prediction Markets:** Searched `Iran oil`. The app found an oil-specific market, "Will Crude Oil reach a new all-time high by June 30?", at about `2.2% Yes`, with related crude-threshold markets. This was directionally relevant but did not answer the actual de-escalation question.
9. **Copilot:** Selected all loaded contexts and asked for a synthesis. Context detection worked, but generation stayed on `GENERATING...` after the 12-second guard and only showed a planner preview.

Outcome: rejected as a clean pair trade. The event idea is plausible, but Gamma's own Strategy Lab history, macro context, and commodity data inconsistency did not support putting on the full long-airlines/short-energy book.

## Trade Verdict

The trade does not make sense as a clean `long JETS / short XLE` pair from this workflow.

The strongest expression, if any, is a small defined-risk bearish `XLE` put spread rather than pairing energy short exposure with airline long exposure. Sizing should be event-sized only, with premium as the known max risk. The idea needs more proof because Strategy Lab showed poor historical spread behavior, Macro showed a hostile rates/dollar setup for airlines, and Commodities had conflicting WTI values.

What would kill the trade:

- Oil rebounds or Iran de-escalation fails.
- Backwardation persists and energy equities hold up.
- Higher real yields and stronger dollar keep pressuring airline beta.
- The DAL DCF issue turns out to reflect real capital intensity rather than a modeling normalization bug.
- The XLE options structure is too short-dated or too expensive relative to the event window.

## What Worked Well

### Strategy Lab validation

The branch fixes here are real. The validated `JETS / XLE` book showed signed exposure, source diagnostics, alignment window, observation counts, normalized weights, provenance, and fail-closed warnings. It did not repeat the prior audit's stale hidden-state failure.

Preserve:

- Dedicated Validate Book action.
- Per-leg provider/source diagnostics.
- Gross/net signed exposure summary.
- Alignment diagnostics before performance interpretation.
- Warnings about yfinance and gross-normalized exposures.

### Options templates

The Options strategy templates worked on a live delayed IBKR `XLE` surface. Put Spread built a bounded-risk structure with max profit/loss, breakeven, delta, gamma, vega, theta, and rho.

Preserve:

- One-click templates.
- Source strip and delayed/provider metadata.
- Strategy payoff summary.
- Data diagnostics showing chain rows, cells, lines, interpolation, and update time.

Improve:

- Template expiry selection should consider thesis horizon, not just nearest expiry.
- Missing or interpolated cells should remain visible near the strategy output, not only in diagnostics.

### Copilot context discovery

Copilot found seven loaded contexts: Commodities, Fundamentals, Macro, Options, Portfolio, Prediction Markets, and Strategy Lab. This is the right direction for cross-context synthesis.

Preserve:

- Loaded context count.
- Context fingerprints.
- Provider/timestamp/warning summaries.
- Editable synthesis scope.

### Prediction Markets related links for oil

The oil market's related links stayed within crude all-time-high threshold siblings. That is materially better than the prior audit's unrelated GTA-style links on an AI-policy market.

Preserve:

- Relationship labels such as adjacent threshold and conditional consistency.
- Gap display between related probabilities.
- Calibration warning when venue history is unavailable.

### Provenance visibility

Provenance and source badges were useful across Strategy Lab, Options, Fundamentals, Commodities, and Prediction Markets. They helped distinguish SEC history, model-generated summaries, IBKR-delayed data, Gamma-derived analytics, and provider warnings.

## What Did Not Work

### Risk did not inherit the research book

This was the most damaging workflow failure. After building and validating a signed Strategy Lab book, Risk did not receive it as a research snapshot. The Risk tab opened as `research / USD` with unknown coverage, no return history, N/A KPIs, and disabled compute actions.

Why it matters:

- The natural analyst workflow is "build signed book, validate data, stress it."
- Without this handoff, Strategy Lab and Risk feel like separate tools rather than one research workflow.

Required improvement:

- Strategy Lab composition output should create a durable research-book object that Risk can consume directly.
- Risk should declare whether it is using account portfolio, single focus, or research book.
- If no usable book is present, Risk should offer "Load latest Strategy Lab result" when one exists.

### Commodities had conflicting WTI values

Commodities showed internally inconsistent WTI state:

- Sitrep and external headlines supported an oil-down story.
- WTI curve nodes showed front prices around the mid-80s.
- The Commodities header showed WTI `95` and `+0.72%`.

Why it matters:

- The thesis was oil-sensitive.
- Conflicting commodity values make the user distrust the whole chain.

Required improvement:

- Add a commodity data reconciliation layer for selected root, header quote, curve nodes, Sitrep tile, and history.
- If front contract, continuous series, and Sitrep proxy differ, label the basis explicitly.
- Show the contract month and timestamp next to the headline WTI value.

### Copilot synthesis hung

The workspace selected contexts correctly, but Generate stayed on `GENERATING...` after the 12-second guard and did not produce a synthesis or recoverable failure card. The visible card was planner-only and explicitly said it did not execute tools or fetch provider data.

Why it matters:

- The branch was supposed to improve recoverable timeout behavior.
- A hung synthesis leaves the user without the cross-context conclusion the workflow was building toward.

Required improvement:

- The 12-second guard should produce an explicit failure card or partial card.
- The prompt should remain editable.
- The UI should expose whether the provider call started, timed out, or was blocked before execution.

### Fundamentals DCF defaults were not trustworthy for DAL

The DAL peer heatmap was useful, but the DCF output was not reliable enough to support or reject the airline leg by itself.

Observed issues:

- Bear/Base/Bull values were all negative despite DAL showing reasonable peer quality.
- D&A/revenue showed near `0.0%`, implausible for an airline.
- Revenue growth was fixed around `18.3%` per year through the projection.
- Capex consumed more than EBIT and drove negative FCF.
- The driver bridge used "lift" language on a negative value in at least one row.

Required improvement:

- Add sector-aware DCF sanity checks for capital-intensive businesses.
- Flag implausible D&A/revenue and capex/revenue assumptions.
- Add reverse-DCF or market-implied assumptions so the user can compare the current price to plausible operating paths.

### Cross-tab context remains inconsistent

Context moved into Copilot, but not into the tools where it was needed most.

Observed:

- Strategy Lab did not flow into Risk.
- `DAL` did not flow from thesis context into Fundamentals; it had to be typed manually.
- `XLE` did not flow into Options; it had to be typed manually.
- Prediction Markets did not preserve the actual "Iran oil" event intent.
- Navigation had duplicate accessible names for tab buttons and drag handles, making automation and assistive selection ambiguous.

Required improvement:

- Promote a current research-thread object with selected thesis, instruments, legs, market, macro shock, and validated outputs.
- Each tab should state: using current context, context available but not loaded, context unsupported, or no context.

## Gaps

### Research object model

Gamma needs first-class research objects:

- signed book
- single-name focus
- commodity shock
- option structure
- macro regime or shock packet
- prediction-market event
- DCF scenario
- Copilot synthesis card

These objects should have stable IDs, provenance, timestamps, and handoff eligibility.

### Commodity basis and contract transparency

Oil workflows need explicit distinction between:

- continuous proxy
- front futures contract
- selected futures contract month
- spot/proxy price
- Sitrep commodity tile
- EIA/FRED reference series

The app should not show a single "WTI" number without saying which one it is.

### Sector-aware DCF checks

Fundamentals needs model sanity checks before users trust DCF output:

- D&A plausibility by sector
- capex/revenue plausibility
- terminal value share of enterprise value
- negative FCF warnings
- implied revenue scale warnings
- "current price requires X" reverse-valuation view

### Thesis-horizon-aware options

Options templates should ask or infer:

- event horizon
- directional view
- vol view
- max premium budget
- desired moneyness

The app can stay read-only while still preventing accidental front-expiry structures from becoming the default answer.

### Prediction-market intent search

Search should distinguish "oil all-time high" from "Iran oil de-escalation." The found market was related to crude, but not to the actual event catalyst.

Needed:

- event/entity extraction
- search result explanation
- fallback disclosure when no direct market exists
- cross-link from geopolitical markets to commodity markets

## Cross-Tab Coherence

Current state: better context collection, weak workflow continuity.

Improved:

- Copilot loaded-context discovery worked.
- Strategy Lab stale handoffs were separated into Earlier Sessions.
- Prediction-market related links were more semantically coherent for crude.

Still broken:

- Strategy Lab to Risk.
- Strategy Lab to Options.
- Thesis to Fundamentals.
- Sitrep news/event to Prediction Markets.
- Commodity selection to Macro/Risk shock templates.

Target behavior:

1. Sitrep surfaces oil de-escalation.
2. User sends the oil signal to a research thread.
3. Strategy Lab builds the signed book.
4. Risk consumes the signed book.
5. Options consumes the short energy leg and selected horizon.
6. Fundamentals consumes the airline candidate.
7. Prediction Markets searches the event catalyst.
8. Copilot synthesizes only the validated objects.

## Copilot Evaluation

Prompt tried:

```text
Evaluate this Gamma-built trade idea: oil de-escalation should favor long JETS versus short XLE, with DAL as the quality airline read-through and an XLE put spread as the defined-risk expression. Use the loaded Commodities, Strategy Lab, Macro, Fundamentals, Options, and Prediction Markets contexts. Be explicit about what confirms it, what rejects it, and what would kill the trade.
```

Useful behavior:

- Detected `JETS`, `XLE`, `DAL`, and oil.
- Selected seven loaded contexts.
- Displayed context fingerprints and warnings.
- Built a planner view with relevant domains.

Failed behavior:

- Did not return an analytical synthesis.
- Stayed on `GENERATING...` after the guard.
- The visible result was planner-only and stated it did not execute tools or fetch provider data.

No hallucinated thesis answer was observed because no answer was produced. The failure mode was absence, not fabrication.

## Scoring

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Gamma covered macro, commodities, options, fundamentals, prediction markets, portfolio, Strategy Lab, and news in one workspace. |
| Data depth / drill-down | 6/10 | Several tabs were deep enough for real analysis, but commodity conflicts, limited event search, and DCF normalization issues hurt trust. |
| Analytical tooling | 7/10 | Strategy Lab validation and Options templates were strong; Risk handoff and DCF reliability were the limiting failures. |
| Copilot usefulness | 4/10 | Context discovery worked, but synthesis did not complete. |
| Cross-tab workflow / state continuity | 3/10 | Contexts are visible to Copilot, but the actual research object does not reliably move between analytical tabs. |
| Visual density and terminal feel | 8/10 | The app remains dense, data-rich, and provenance-heavy, though navigation and accessibility naming need cleanup. |
| Speed to insight | 5/10 | Sitrep produced a thesis quickly, but manual re-entry, blocked Risk, slow DAL load, and data conflicts slowed the workflow. |
| Overall | 6/10 | The recent fixes are real, especially Strategy Lab and Options, but end-to-end research still breaks around cross-tab state, commodity coherence, and Copilot completion. |

## Prioritized Follow-Up

### P0: Strategy Lab to Risk handoff

Create a durable validated research-book object from Strategy Lab and make Risk consume it directly.

Acceptance criteria:

- Validated signed book appears in Risk as a selectable source.
- Risk clearly labels the source as research book, not live account portfolio.
- Scenarios and core risk metrics run on the same aligned return set Strategy Lab validated.

Status: Complete as of 2026-06-14.

Implemented:

- Strategy Lab portfolio composition now requires a current valid book validation before creating the composed signed book.
- A successful validated composition is promoted into a persisted `strategy_research_book` object with signed normalized weights, validation provenance, aligned return points, and a Risk-ready synthetic snapshot.
- Risk accepts `source_scope = research_book` with explicit source label/object/origin fields and computes core risk metrics from the supplied Strategy Lab aggregate return stream instead of reloading provider histories.
- Risk shows the Strategy Lab book as a selectable source and labels the active source as `Strategy Lab book: ...`, separate from account portfolio and research-scope snapshots.
- Focused backend/API/frontend tests cover the direct return-stream compute path, API contract, durable book object construction, and Risk source labeling.

Still left:

- Risk contribution detail for research books is aggregate-book level in this pass. Per-leg contribution decomposition can be added later by carrying aligned per-leg return columns from Strategy Lab, but the P0 acceptance criterion of using the validated aggregate aligned return set is complete.
- Broader research-thread context continuity remains open under the P1 research-thread context contract item below.

### P0: Commodity value reconciliation

Fix WTI header/curve/Sitrep inconsistency or make the basis explicit.

Acceptance criteria:

- WTI header shows contract month, timestamp, provider, and basis.
- If Sitrep and Commodities use different instruments, the UI states that clearly.
- Copilot context includes the basis note.

### P1: Copilot timeout and synthesis completion

Make the dedicated Copilot workspace return a ready card or explicit recoverable failure.

Acceptance criteria:

- A 12-second guard never leaves the UI indefinitely on `GENERATING...`.
- The user sees whether the issue was planner-only, provider timeout, route timeout, or model error.
- The prompt and selected contexts remain recoverable.

### P1: Research-thread context contract

Create a shared context object across tabs.

Acceptance criteria:

- Tabs declare context status.
- Instruments, books, option structures, DCF scenarios, commodity shocks, and prediction markets can attach to one research thread.
- Copilot uses the same validated context records the UI uses.

### P1: Fundamentals DCF sanity checks

Add sector-aware DCF validation and reverse-valuation tools.

Acceptance criteria:

- Implausible D&A, capex, growth, and terminal-value assumptions are flagged before the valuation summary.
- The DCF panel explains why DAL shows negative value under defaults.
- User can compare current price to implied growth/margin/capex assumptions.

### P2: Prediction-market intent search

Improve event-sensitive search for geopolitical/commodity catalysts.

Acceptance criteria:

- `Iran oil` returns direct geopolitical/oil markets when available.
- If no direct market exists, Gamma says so and offers adjacent crude, Iran, or Middle East contracts separately.
- Related-market rows explain event, topic, entity, threshold, or weak-match basis.

### P2: Navigation/accessibility cleanup

Remove duplicate accessible names between tab buttons, drag handles, global search results, and floating Copilot controls.

Acceptance criteria:

- `getByRole('button', { name: 'COPILOT' })` resolves predictably in the intended scope.
- Drag handles include distinct labels that do not collide with tab names.
- Offscreen nav controls are not exposed as active duplicates when the drawer is closed.

## Guidance For Future Agents

Do not add another research tab to solve these findings. The app already has enough surfaces. The next improvement should make the existing research path trustworthy:

1. Make validated research objects durable.
2. Make provider/basis conflicts explicit.
3. Make Risk consume Strategy Lab books.
4. Make Copilot consume the same validated objects.
5. Add sector/model sanity checks before showing valuation conclusions.

The product bar is not "more data." The bar is that a user can understand exactly which data Gamma used, how it transformed it, and whether the workflow remained coherent across tabs.
